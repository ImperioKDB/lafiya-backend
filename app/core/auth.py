import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, Depends
from app.core.config import settings
from app.core.supabase_client import get_service_client
from app.models.common import CurrentUser

# This project has migrated to Supabase's newer JWT Signing Keys system
# (asymmetric, ES256) -- confirmed directly against the live dashboard
# (Settings -> API -> JWT Keys), not assumed. Supabase's own docs are
# explicit that once migrated, new session tokens are signed with the
# asymmetric key and the old shared secret stops working for them --
# there's no string to paste into SUPABASE_JWT_SECRET that fixes this,
# the verification approach itself has to change.
#
# JWKS endpoint format confirmed from Supabase's own JWT documentation
# (Auth -> JWT Signing Keys -> "Access the currently trusted signing
# keys at the following endpoint"). PyJWKClient caches the fetched keys
# internally, so this isn't a network round trip on every request.
#
# ES256/RS256 verification in PyJWT requires the optional `cryptography`
# backend (requirements.txt now pins pyjwt[crypto], not plain pyjwt) --
# without it, PyJWT can't even attempt asymmetric verification and
# raises an algorithm-not-supported error that looked, from the outside,
# identical to a real invalid token.
_JWKS_URL = settings.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json"
_jwks_client = None


def _get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(_JWKS_URL)
    return _jwks_client


def _decode_token(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        print("AUTH DEBUG: could not read token header -- " + repr(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    alg = unverified_header.get("alg")

    try:
        if alg == "HS256":
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=[alg],
                audience="authenticated",
            )
    except Exception as e:
        # TEMPORARY diagnostic logging -- prints the real exception to
        # Render's logs instead of only ever surfacing the same generic
        # 401 to the client. Remove once auth is confirmed stable; this
        # is deliberately broad (not just jwt.PyJWTError) so a
        # dependency/config problem like a missing crypto backend shows
        # up here too, not just a genuinely bad token.
        print("AUTH DEBUG: token verification failed -- alg=" + str(alg) + " error=" + repr(e))
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return token, payload


# Role is determined by table membership, not a JWT claim -- a user is
# a chw/doctor/pharmacy because an admin created that row for them with
# their auth_user_id attached. This matches how accounts actually get
# provisioned (see README) and needs no manual Supabase dashboard step
# beyond creating the auth user itself. Admin is the one exception,
# resolved from the ADMIN_EMAILS allowlist since it isn't backed by a
# table.
#
# Checks chws -> doctors -> pharmacies -> admin allowlist, in that
# order, first match wins. A real user should only ever match one.
def get_current_user(decoded=Depends(_decode_token)) -> CurrentUser:
    token, payload = decoded
    user_id = payload.get("sub")
    email = (payload.get("email") or "").lower()

    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")

    service_client = get_service_client()

    chw_row = service_client.table("chws").select("id").eq("auth_user_id", user_id).execute()
    if chw_row.data:
        return CurrentUser(id=user_id, email=email, role="chw", role_row_id=chw_row.data[0]["id"], access_token=token)

    doctor_row = service_client.table("doctors").select("id").eq("auth_user_id", user_id).execute()
    if doctor_row.data:
        return CurrentUser(id=user_id, email=email, role="doctor", role_row_id=doctor_row.data[0]["id"], access_token=token)

    pharmacy_row = service_client.table("pharmacies").select("id").eq("auth_user_id", user_id).execute()
    if pharmacy_row.data:
        return CurrentUser(id=user_id, email=email, role="pharmacy", role_row_id=pharmacy_row.data[0]["id"], access_token=token)

    if email and email in settings.admin_emails:
        return CurrentUser(id=user_id, email=email, role="admin", role_row_id=None, access_token=token)

    raise HTTPException(
        status_code=403,
        detail="Authenticated but no role assigned. An admin must create a chws/doctors/pharmacies "
               "row with this auth_user_id, or add this email to ADMIN_EMAILS.",
    )


# Usage: user: CurrentUser = Depends(require_role("chw"))
# This is a defense-in-depth check on top of Postgres RLS, not a
# substitute for it -- every data operation should still go through
# get_user_client() so RLS enforces the same boundary at the DB layer.
def require_role(*allowed_roles: str):
    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail="Role '" + user.role + "' is not permitted to perform this action",
            )
        return user

    return checker
