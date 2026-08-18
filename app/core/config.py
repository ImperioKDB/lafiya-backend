import os


class Settings:
    # All config comes from environment variables -- set these in Render's
    # dashboard for production, and in a local .env (see .env.example) for
    # any local testing. Nothing here is a hardcoded secret.
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    supabase_service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    supabase_jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "")

    # Fallback admin allowlist — an email here gets role='admin' even with
    # no chws/doctors/pharmacies row. Comma-separated in the env var.
    admin_emails = [
        e.strip().lower()
        for e in os.environ.get("ADMIN_EMAILS", "").split(",")
        if e.strip()
    ]


settings = Settings()
