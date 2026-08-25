from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.core.supabase_client import get_user_client, get_service_client
from app.models.common import CurrentUser
from app.models.patient import PatientCreate, PatientOut

router = APIRouter(prefix="/api/patients", tags=["patients"])

# From blueprint SS1/SS4 -- CHW earns this per verified visit registered.
REGISTRATION_FEE_NGN = 150


@router.post("", response_model=PatientOut, status_code=201)
# RLS on `patients` requires registered_by_chw_id to match the calling
# chw's own row (see chw_own_patients policy) -- using the user-scoped
# client means Postgres enforces that even if this endpoint's own logic
# had a bug, not just the application layer.
def register_patient(payload: PatientCreate, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)

    insert_result = (
        client.table("patients")
        .insert(
            {
                "full_name": payload.full_name,
                "phone": payload.phone,
                "age": payload.age,
                "nin": payload.nin,
                "registered_by_chw_id": user.role_row_id,
            }
        )
        .execute()
    )

    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Could not create patient record")

    patient = insert_result.data[0]

    # chw_earnings has no self-service RLS policy for inserts (only a
    # select policy -- see blueprint SS11), so this write goes through the
    # service client. The registration fee is marked accrued immediately;
    # there's no separate "visit verification" step defined yet, so this
    # is the simplest correct behavior for now -- flag if that changes.
    service_client = get_service_client()
    service_client.table("chw_earnings").insert(
        {
            "chw_id": user.role_row_id,
            "type": "registration",
            "amount": REGISTRATION_FEE_NGN,
            "related_entity_id": patient["id"],
            "status": "accrued",
        }
    ).execute()

    return patient


@router.get("", response_model=list[PatientOut])
# NEW -- the dashboard/loans/triage screens all call GET /api/patients
# (no id) expecting a list scoped to the calling CHW. That route never
# existed: only POST /api/patients and GET /api/patients/{id} were
# registered, so a GET to the bare path matched no method here and
# FastAPI/Starlette returned 405, not 404 -- which is what was showing
# up as "Couldn't load your dashboard / Method Not Allowed" in the app.
# Relies entirely on chw_own_patients RLS to scope the result -- no
# extra .eq() filter needed, same trust boundary as get_patient below.
def list_patients(user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)
    result = client.table("patients").select("*").order("created_at", desc=False).execute()
    return result.data or []


@router.get("/{patient_id}", response_model=PatientOut)
# Scoped to chw-owned patients for this endpoint. Doctor access to
# patient records now exists too, via the doctor_read_linked_patients
# RLS policy (migrations/002_consultations_rls.sql) -- but that's read
# access enforced at the DB layer, not a second code path here.
def get_patient(patient_id: str, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)
    result = client.table("patients").select("*").eq("id", patient_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Patient not found or not accessible")

    return result.data[0]
