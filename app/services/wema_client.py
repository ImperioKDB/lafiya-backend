from typing import Optional
import requests
from app.core.config import settings

# Confirmed live from the ALAT developer playground console
# (Wallet Services - Account Management API -> Get Wallet Details - GET),
# not guessed: https://apiplayground.alat.ng/ws-acct-mgt/api/
# AccountMaintenance/CustomerAccount/GetAccountV2/accountNumber/{accountNumber}
#
# Header name (x-api-key) is NOT confirmed from that screen -- it's the
# convention documented on every other ALAT product page (Wallet
# Creation, Account Creation, etc). If this 401s once WEMA_API_KEY is
# set in Render, that's the first thing to check, not a sign the whole
# integration is wrong.
#
# Deliberately does NOT call any account/wallet CREATION endpoint --
# every ALAT creation flow needs a real BVN/NIN (directly, or indirectly
# via a NIMC phone-number check for the e-commerce variant), which
# conflicts with LAFIYA's locked decision to keep NIN simulated.
GET_WALLET_DETAILS_PATH = "/ws-acct-mgt/api/AccountMaintenance/CustomerAccount/GetAccountV2/accountNumber/{account_number}"


class WemaSandboxError(Exception):
    # Raised for anything that should surface as "sandbox unreachable,
    # retry" per blueprint SS17 -- never let the caller see a raw
    # requests exception or hang on a silent timeout.
    pass


def get_wallet_details(account_number: str) -> dict:
    if not settings.wema_base_url or not settings.wema_api_key:
        raise WemaSandboxError("WEMA_BASE_URL / WEMA_API_KEY not configured")

    url = settings.wema_base_url.rstrip("/") + GET_WALLET_DETAILS_PATH.format(account_number=account_number)

    try:
        response = requests.get(
            url,
            headers={"x-api-key": settings.wema_api_key},
            timeout=10,
        )
    except requests.RequestException as e:
        raise WemaSandboxError("Could not reach ALAT sandbox: " + str(e))

    if response.status_code != 200:
        raise WemaSandboxError(
            "ALAT sandbox returned " + str(response.status_code) + ": " + response.text[:300]
        )

    try:
        payload = response.json()
    except ValueError:
        raise WemaSandboxError("ALAT sandbox returned a non-JSON response")

    if not payload.get("successful"):
        raise WemaSandboxError(payload.get("message") or "ALAT sandbox reported an unsuccessful lookup")

    result = payload.get("result") or {}

    return {
        "wallet_number": result.get("walletNumber"),
        "available_balance": result.get("availableBalance"),
        "wallet_status": result.get("walletStatus"),
        "account_type": result.get("accountType"),
        "raw_message": payload.get("message"),
    }
