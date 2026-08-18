from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.core.supabase_client import get_service_client
from app.models.loan import GuarantorOut, GuarantorPhoneAction

router = APIRouter(prefix="/api/guarantors", tags=["guarantors"])

# No Supabase Auth login exists for guarantors -- blueprint SS13 defines
# only 4 roles (chw/doctor/pharmacy/admin), none of them a guarantor or
# patient role. These two endpoints intentionally take no bearer token;
# the caller proves identity by supplying the exact guarantor_phone on
# the row, mirroring the "confirm via SMS-link or USSD webhook" design
# in PRD SS6.7.
#
# FLAG: this is a placeholder auth model, not a finished one. A bare
# phone-number match is guessable if guarantor_id values leak (they're
# sequential-ish UUIDs, so low risk, but not zero). A real deployment
# should pair this with a signed one-time token delivered in the SMS
# itself -- that depends on the Africa's Talking SMS integration, which
# is a depth-layer item (Master Build Spec Phase 6a) not built yet.
# Treat this as good enough for sandbox/demo, not production-ready.


def _find_pending_guarantor(service_client, guarantor_id: str, guarantor_phone: str) -> dict:
    result = (
        service_client.table("guarantors")
        .select("*")
        .eq("id", guarantor_id)
        .eq("guarantor_phone", guarantor_phone)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Guarantor record not found or phone number does not match")
    return result.data[0]


@router.post("/{guarantor_id}/confirm", response_model=GuarantorOut)
def confirm_guarantor(guarantor_id: str, payload: GuarantorPhoneAction):
    service_client = get_service_client()
    row = _find_pending_guarantor(service_client, guarantor_id, payload.guarantor_phone)

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="This guarantor has already responded (" + row["status"] + ")")

    update_result = (
        service_client.table("guarantors")
        .update({"status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", guarantor_id)
        .execute()
    )
    return update_result.data[0]


@router.post("/{guarantor_id}/decline", response_model=GuarantorOut)
# Declining carries no reputation penalty -- blueprint SS30 flags the
# guarantor-coercion risk explicitly and recommends the guarantor be
# free to decline without it being held against them. Only a confirmed
# default (not built yet -- needs the repayment/disbursement flow first)
# should ever touch guarantor_reputation.
def decline_guarantor(guarantor_id: str, payload: GuarantorPhoneAction):
    service_client = get_service_client()
    row = _find_pending_guarantor(service_client, guarantor_id, payload.guarantor_phone)

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="This guarantor has already responded (" + row["status"] + ")")

    update_result = (
        service_client.table("guarantors")
        .update({"status": "declined"})
        .eq("id", guarantor_id)
        .execute()
    )
    return update_result.data[0]
