import os


class Settings:
    # All config comes from environment variables -- set these in Render's
    # dashboard for production, and in a local .env (see .env.example) for
    # any local testing. Nothing here is a hardcoded secret.
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    supabase_service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")

    # Fallback admin allowlist -- an email here gets role='admin' even with
    # no chws/doctors/pharmacies row. Comma-separated in the env var.
    admin_emails = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    ]

    # ALAT Playground sandbox -- confirmed live at
    # https://apiplayground.alat.ng (Wallet Services - Account Management
    # API, "Get Wallet Details" operation). Set the real value only in
    # Render's dashboard -- never commit it, never paste it into chat.
    wema_base_url = os.environ.get("WEMA_BASE_URL", "https://apiplayground.alat.ng")
    wema_api_key = os.environ.get("WEMA_API_KEY", "")

    # Africa's Talking USSD sandbox -- the shared/dedicated service code
    # assigned when the channel was created in their dashboard. Used only
    # as a minimal sanity check in app/api/ussd.py.
    ussd_service_code = os.environ.get("USSD_SERVICE_CODE", "")

    # Africa's Talking SMS -- same account as USSD, "sandbox" as the
    # username in sandbox mode. Used by app/services/sms_client.py for
    # real guarantor confirmation SMS.
    africastalking_username = os.environ.get("AFRICASTALKING_USERNAME", "sandbox")
    africastalking_api_key = os.environ.get("AFRICASTALKING_API_KEY", "")

    # Base URL of the (not yet built) frontend -- the guarantor
    # confirmation SMS links here. Empty until a real frontend exists;
    # the backend token contract works regardless of whether this
    # resolves to anything yet.
    frontend_base_url = os.environ.get("FRONTEND_BASE_URL", "")


settings = Settings()
