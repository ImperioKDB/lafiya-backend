import requests
from app.core.config import settings

# Confirmed live from Africa's Talking's own developer docs before
# writing this -- POST, application/x-www-form-urlencoded body, apiKey
# header. Not guessed, same discipline as the ALAT and USSD integrations.
SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
LIVE_URL = "https://api.africastalking.com/version1/messaging"


class SmsSendError(Exception):
    # Raised for anything that should surface as a visible delivery
    # failure per blueprint SS17 ('SMS delivery failed -- retry') rather
    # than a silent stall. Callers should catch this and continue rather
    # than let a delivery hiccup block the whole guarantor-attach flow.
    pass


def send_sms(to_phone: str, message: str) -> dict:
    if not settings.africastalking_username or not settings.africastalking_api_key:
        raise SmsSendError("AFRICASTALKING_USERNAME / AFRICASTALKING_API_KEY not configured")

    # Sandbox apps always use the sandbox endpoint -- confirmed from AT's
    # own curl example, which pairs username=sandbox with the sandbox
    # host regardless of the app's real username elsewhere in the UI.
    url = SANDBOX_URL if settings.africastalking_username == "sandbox" else LIVE_URL

    try:
        response = requests.post(
            url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "apiKey": settings.africastalking_api_key,
            },
            data={
                "username": settings.africastalking_username,
                "to": to_phone,
                "message": message,
            },
            timeout=10,
        )
    except requests.RequestException as e:
        raise SmsSendError("Could not reach Africa's Talking SMS API: " + str(e))

    if response.status_code not in (200, 201):
        raise SmsSendError(
            "Africa's Talking SMS API returned " + str(response.status_code) + ": " + response.text[:300]
        )

    try:
        payload = response.json()
    except ValueError:
        raise SmsSendError("Africa's Talking SMS API returned a non-JSON response")

    return payload
