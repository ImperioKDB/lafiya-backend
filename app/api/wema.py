from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.models.common import CurrentUser
from app.services.wema_client import get_wallet_details, WemaSandboxError

router = APIRouter(prefix="/api/wema", tags=["wema"])

# Blueprint SS9/SS16 -- "Live Wema/ALAT account lookup + balance check."
# This is the one integration in the whole build that's a genuinely live
# external call, not a Supabase read/write -- kept as its own router so
# it's obvious at a glance which endpoint that is.
#
# Deliberately read-only: no account/wallet CREATION endpoint is wired up
# anywhere in this backend. Every ALAT creation flow needs a real BVN/NIN
# (or, for the e-commerce variant, an indirect NIMC check on the phone
# number) -- that conflicts with LAFIYA's locked decision to keep NIN
# simulated. If a real disbursement flow gets built later, that's a new,
# explicit decision -- not something that should sneak in via this file.


@router.get("/account-lookup/{account_number}")
# CHW-initiated -- matches the loan flow's "does this account exist /
# what's its balance" step (blueprint SS6). Not currently persisted
# anywhere; the loan/disbursement account number field is a decision for
# whenever the (simulated) disbursement step itself gets built.
def account_lookup(account_number: str, user: CurrentUser = Depends(require_role("chw"))):
    try:
        return get_wallet_details(account_number)
    except WemaSandboxError as e:
        # Matches blueprint SS17's explicit error state for this exact
        # integration -- "Sandbox unreachable -- retry", never a silent
        # infinite spinner on the frontend.
        raise HTTPException(status_code=502, detail="ALAT sandbox unreachable: " + str(e))
