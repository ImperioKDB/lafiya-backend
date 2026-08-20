from fastapi import APIRouter, Depends
from app.core.auth import get_current_user
from app.models.common import CurrentUser

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("")
# Thin wrapper around get_current_user -- no new logic, just exposes
# the same role-resolution the backend already trusts on every
# protected endpoint (app/core/auth.py) so the frontend can ask "who am
# I, what role, what's my row id" once at login instead of guessing.
def get_me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "role_row_id": user.role_row_id,
    }
