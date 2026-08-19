from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.core.supabase_client import get_user_client, get_service_client
from app.models.common import CurrentUser
from app.models.claim import ClaimCreate, ClaimOut

router = APIRouter(prefix="/api/claims", tags=["claims"])

# Blueprint SS4/SS17 -- claims matched against the doctor's cost
# estimate. Variance threshold was never locked anywhere in the docs
# before this pass -- 15% is a decision made here, not a fact restated
# from spec. It's a single constant to change if a different number is
# wanted.
VARIANCE_THRESHOLD = 0.15


@router.post("", response_model=ClaimOut, status_code=201)
# match_status is the actual payout gate on disbursement_claims -- there
# is no separate payout_status column. A clean match is the only path
# that's ever treated as paid (simulated -- no real transfer, same
# pattern as loan disbursement); a flagged claim blocks entirely and
# raises a fraud_flags row for admin review instead of sitting in an
# ambiguous "pending, maybe still payable" state. Nothing here
# auto-resolves a flag, matching every other human-gated check already
# in this build (guarantor defaults, pharmacy verification).
def submit_claim(payload: ClaimCreate, user: CurrentUser = Depends(require_role("pharmacy"))):
    client = get_user_client(user.access_token)
    service_client = get_service_client()

    # Only verified pharmacies may submit claims (PRD SS6.8) -- this
    # pharmacy's own status, looked up by role_row_id, never user input.
    pharmacy_row = service_client.table("pharmacies").select("status").eq("id", user.role_row_id).execute()
    if not pharmacy_row.data or pharmacy_row.data[0]["status"] != "verified":
        raise HTTPException(status_code=403, detail="Pharmacy is not verified -- cannot submit claims")

    # Loan must actually be disbursed -- otherwise there's no simulated
    # money in play yet and nothing to pay out against.
    loan_row = service_client.table("loans").select("id, status, consultation_id").eq("id", payload.loan_id).execute()
    if not loan_row.data:
        raise HTTPException(status_code=404, detail="Loan not found")
    loan = loan_row.data[0]
    if loan["status"] != "disbursed":
        raise HTTPException(status_code=409, detail="Loan has not been disbursed -- cannot submit a claim against it yet")

    if not loan["consultation_id"]:
        raise HTTPException(status_code=422, detail="Loan has no linked consultation -- cannot determine cost estimate")

    consultation_row = (
        service_client.table("consultations")
        .select("cost_estimate")
        .eq("id", loan["consultation_id"])
        .execute()
    )
    if not consultation_row.data or consultation_row.data[0]["cost_estimate"] is None:
        raise HTTPException(status_code=422, detail="Linked consultation has no cost estimate set yet")

    estimate_amount = consultation_row.data[0]["cost_estimate"]
    variance = (payload.claim_amount - estimate_amount) / estimate_amount if estimate_amount else 0.0
    flagged = variance > VARIANCE_THRESHOLD
    match_status = "variance_flagged" if flagged else "matched"

    insert_result = (
        client.table("disbursement_claims")
        .insert(
            {
                "loan_id": payload.loan_id,
                "pharmacy_id": user.role_row_id,
                "claim_amount": payload.claim_amount,
                "estimate_amount": estimate_amount,
                "variance": variance,
                "match_status": match_status,
            }
        )
        .execute()
    )
    if not insert_result.data:
        raise HTTPException(status_code=403, detail="Could not submit claim")

    claim = insert_result.data[0]

    if flagged:
        # fraud_flags has no self-service RLS policy, same pattern as
        # chw_earnings/guarantor_reputation -- service client only.
        service_client.table("fraud_flags").insert(
            {
                "entity_type": "disbursement_claims",
                "entity_id": claim["id"],
                "reason": (
                    "Claim amount exceeds doctor's estimate by "
                    + str(round(variance * 100))
                    + "% (threshold "
                    + str(int(VARIANCE_THRESHOLD * 100))
                    + "%)"
                ),
                "status": "open",
            }
        ).execute()

    # match_status='matched' is the simulated payout signal -- no real
    # transfer happens anywhere in this build (same as loan disbursement
    # above). This is the hook point a real payout call would attach to
    # later, if that ever becomes a live integration.
    return claim


@router.get("/{claim_id}", response_model=ClaimOut)
# Scoped to the calling pharmacy's own claims via RLS -- see
# pharmacy_read_own_claims in migrations/003. Admin access to all claims
# is part of the fraud-review console (build order item 7), not built
# yet.
def get_claim(claim_id: str, user: CurrentUser = Depends(require_role("pharmacy"))):
    client = get_user_client(user.access_token)
    result = client.table("disbursement_claims").select("*").eq("id", claim_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Claim not found or not accessible")
    return result.data[0]
