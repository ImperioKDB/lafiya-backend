from supabase import create_client, Client
from app.core.config import settings


# Bypasses RLS entirely. Use only for operations no single user owns --
# role lookups at login, and writes to chw_earnings/doctor_earnings/
# guarantor_reputation/fraud_flags, which have RLS enabled with zero
# self-service write policies on purpose (see blueprint SS14). Never
# expose this key to the frontend.
def get_service_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


# Scoped to the calling user's own JWT, so every Postgres RLS policy
# still applies. This is the client every endpoint should use for
# anything the RLS policies already cover (patients, consultations,
# loans, guarantors, disbursement_claims) -- RLS is the real enforcement
# layer, the FastAPI role check is a second line of defense, not a
# replacement for it.
def get_user_client(access_token: str) -> Client:
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client
