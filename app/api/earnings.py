from fastapi import APIRouter, Depends
from app.core.auth import require_role
from app.core.supabase_client import get_user_client
from app.models.common import CurrentUser

router = APIRouter(prefix="/api/chw", tags=["earnings"])

# NEW -- src/features/chw/api.js (frontend) has referenced
# GET /api/chw/earnings since Phase 1, but no backend router ever
# implemented it. Unlike the /api/patients 405, this one 404'd cleanly,
# which safeFetch() on the frontend already handles gracefully (shows
# the "not wired up yet" notice instead of throwing) -- but it still
# needs to exist for the Earnings screen and dashboard stat to ever
# show real numbers.
#
# Uses get_user_client, not the service client -- chw_earnings already
# has a self-service SELECT policy (see app/api/patients.py's comment
# on the same table), only INSERT is service-role-only. Matches the
# "RLS is the real enforcement layer" convention used everywhere else
# in this backend.


@router.get("/earnings")
def list_earnings(user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)
    result = (
        client.table("chw_earnings")
        .select("*")
        .eq("chw_id", user.role_row_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []
