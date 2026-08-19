from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.core.supabase_client import get_user_client, get_service_client
from app.models.common import CurrentUser
from app.models.loan import LoanCreate, LoanOut, GuarantorAttach, GuarantorOut, LoanStatusOut
from app.fraud.rules import check_loan_velocity, check_guarantor_overlap

router = APIRouter(prefix="/api/loans", tags=["loans"])

# Blueprint SS1 -- flat fee funds the doctor stipend and CHW commission
# simultaneously. Computed here, server-side, never trusted from the
# client payload (blueprint SS14).
FLAT_FEE_PCT = 0.05


@router.post("", response_model=LoanOut, status_code=201)
# RLS's chw_insert_own_patient_loans policy requires patient_id to
# belong to a patient this chw registered.
def create_loan(payload: LoanCreate, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)

    flat_fee = round(payload.amount * FLAT_FEE_PCT, 2)
    total_repayable = payload.amount + flat_fee

    insert_result = (
        client.table("loans")
        .insert(
            {
                "patient_id": payload.patient_id,
                "consultation_id": payload.consultation_id,
                "amount": payload.amount,
                "flat_fee_pct": FLAT_FEE_PCT,
                "flat_fee": flat_fee,
                "total_repayable": total_repayable,
                "status": "pending",
            }
        )
        .execute()
    )

    if not insert_result.data:
        raise HTTPException(
            status_code=403,
            detail="Could not create loan -- patient not found or not registered by you",
        )

    loan = insert_result.data[0]

    # Fraud check runs after the loan exists, never blocks it -- see
    # app/fraud/rules.py for the threshold and why this only flags.
    check_loan_velocity(get_service_client(), user.role_row_id, loan["id"])

    return loan


@router.get("/{loan_id}/status", response_model=LoanStatusOut)
def get_loan_status(loan_id: str, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)

    loan_result = client.table("loans").select("*").eq("id", loan_id).execute()
    if not loan_result.data:
        raise HTTPException(status_code=404, detail="Loan not found or not accessible")

    guarantors_result = client.table("guarantors").select("*").eq("loan_id", loan_id).execute()

    return {"loan": loan_result.data[0], "guarantors": guarantors_result.data or []}


@router.post("/{loan_id}/guarantors", response_model=list[GuarantorOut], status_code=201)
# Exactly two guarantors, 50/50 liability split (blueprint SS1/SS11).
# Each phone is checked against guarantor_reputation.barred first --
# that table has no self-service RLS policy on purpose (00_START_HERE),
# so the check goes through the service client, same pattern as
# chw_earnings writes.
def attach_guarantors(loan_id: str, payload: GuarantorAttach, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)
    service_client = get_service_client()

    loan_check = client.table("loans").select("id").eq("id", loan_id).execute()
    if not loan_check.data:
        raise HTTPException(status_code=404, detail="Loan not found or not accessible")

    existing_guarantors = client.table("guarantors").select("id").eq("loan_id", loan_id).execute()
    if existing_guarantors.data:
        raise HTTPException(status_code=409, detail="This loan already has guarantors attached")

    phones = payload.guarantor_phones
    if phones[0] == phones[1]:
        raise HTTPException(status_code=400, detail="The two guarantors must be different phone numbers")

    for phone in phones:
        rep = service_client.table("guarantor_reputation").select("barred").eq("guarantor_phone", phone).execute()
        if rep.data and rep.data[0]["barred"]:
            raise HTTPException(
                status_code=403,
                detail=phone + " is barred from guaranteeing loans (prior confirmed default)",
            )

    insert_result = (
        client.table("guarantors")
        .insert(
            [
                {"loan_id": loan_id, "guarantor_phone": phones[0], "liability_share": 0.5, "status": "pending"},
                {"loan_id": loan_id, "guarantor_phone": phones[1], "liability_share": 0.5, "status": "pending"},
            ]
        )
        .execute()
    )

    if not insert_result.data:
        raise HTTPException(status_code=403, detail="Could not attach guarantors")

    rows = insert_result.data

    # Overlap check per guarantor row, after insert, never blocks --
    # same reasoning as the velocity check above.
    for row in rows:
        check_guarantor_overlap(service_client, row["guarantor_phone"], row["id"])

    return rows


@router.post("/{loan_id}/disburse", response_model=LoanOut)
# Simulated disbursement -- blueprint SS1/SS9: real payout is
# access-constrained (needs coordination beyond the ALAT sandbox with
# Wema's banking side), so this only flips loans.status to 'disbursed'.
# No money moves anywhere. Required before a pharmacy claim can be
# submitted against this loan (app/api/claims.py).
def disburse_loan(loan_id: str, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)

    loan_result = client.table("loans").select("*").eq("id", loan_id).execute()
    if not loan_result.data:
        raise HTTPException(status_code=404, detail="Loan not found or not accessible")
    loan = loan_result.data[0]

    if loan["status"] == "disbursed":
        raise HTTPException(status_code=409, detail="Loan has already been disbursed")
    if loan["status"] != "pending":
        raise HTTPException(status_code=409, detail="Loan is not in a disbursable state (status: " + loan["status"] + ")")

    guarantors_result = client.table("guarantors").select("status").eq("loan_id", loan_id).execute()
    guarantors = guarantors_result.data or []
    if len(guarantors) != 2:
        raise HTTPException(status_code=409, detail="Loan does not have two guarantors attached yet")
    if any(g["status"] != "confirmed" for g in guarantors):
        raise HTTPException(status_code=409, detail="Both guarantors must confirm before disbursement")

    update_result = (
        client.table("loans")
        .update({"status": "disbursed"})
        .eq("id", loan_id)
        .execute()
    )
    if not update_result.data:
        raise HTTPException(status_code=403, detail="Could not update loan status -- not accessible")

    return update_result.data[0]
