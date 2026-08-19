from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.core.supabase_client import get_service_client
from app.models.loan import GuarantorOut, GuarantorTokenAction

router = APIRouter(prefix="/api/guarantors", tags=["guarantors"])

# Real confirmation now: a one-time token issued when the guarantor was
# attached (app/api/loans.py attach_guarantors), delivered via the
# actual SMS in app/services/sms_client.py. Replaces the earlier bare
# phone-match placeholder entirely -- a phone number typed into a JSON
# body proved nothing; this token does, since only the SMS recipient
# ever sees it.
#
# USSD's own guarantor confirm (app/api/ussd.py) is UNCHANGED and
# intentionally still phone-based -- a telco-verified caller ID is a
# real trust signal in that channel, not a placeholder needing this fix.


def _find_pending_guarantor_by_token(service_client, guarantor_id: str, token: str) -> dict:
    result = service_client.table("guarantors").select("*").eq("id", guarantor_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Guarantor record not found")
    row = result.data[0]

    if not row.get("confirmation_token") or row["confirmation_token"] != token:
        raise HTTPException(status_code=403, detail="Invalid or missing confirmation token")

    expires_at = row.get("confirmation_token_expires_at")
    if expires_at:
        # Python 3.11's fromisoformat handles a trailing 'Z' natively --
        # this project is pinned to 3.11.9 (see .python-version), so no
        # manual string replacement is needed here.
        if datetime.now(timezone.utc) > datetime.fromisoformat(expires_at):
            raise HTTPException(status_code=410, detail="This confirmation link has expired -- ask your CHW to resend it")

    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="This guarantor has already responded (" + row["status"] + ")")

    return row


@router.post("/{guarantor_id}/confirm", response_model=GuarantorOut)
def confirm_guarantor(guarantor_id: str, payload: GuarantorTokenAction):
    service_client = get_service_client()
    row = _find_pending_guarantor_by_token(service_client, guarantor_id, payload.token)

    # Token is single-use -- cleared on confirm so it can't be replayed.
    update_result = (
        service_client.table("guarantors")
        .update(
            {
                "status": "confirmed",
                "confirmed_at": datetime.now(timezone.utc).isoformat(),
                "confirmation_token": None,
            }
        )
        .eq("id", guarantor_id)
        .execute()
    )
    return update_result.data[0]


@router.post("/{guarantor_id}/decline", response_model=GuarantorOut)
# Declining carries no reputation penalty -- blueprint SS30 flags the
# guarantor-coercion risk explicitly and recommends the guarantor be
# free to decline without it being held against them.
def decline_guarantor(guarantor_id: str, payload: GuarantorTokenAction):
    service_client = get_service_client()
    row = _find_pending_guarantor_by_token(service_client, guarantor_id, payload.token)

    update_result = (
        service_client.table("guarantors")
        .update({"status": "declined", "confirmation_token": None})
        .eq("id", guarantor_id)
        .execute()
    )
    return update_result.data[0]
