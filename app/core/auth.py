import jwt
from fastapi import Header, HTTPException, Depends
from app.core.config import settings
from app.core.supabase_client import get_service_client
from app.models.common import CurrentUser


def _decode_token(authorization: str = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1]

    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError:
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
