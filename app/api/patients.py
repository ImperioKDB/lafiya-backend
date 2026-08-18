from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import require_role
from app.core.supabase_client import get_user_client, get_service_client
from app.models.common import CurrentUser
from app.models.patient import PatientCreate, PatientOut

router = APIRouter(prefix="/api/patients", tags=["patients"])

# From blueprint §1/§4 — CHW earns this per verified visit registered.
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
    # select policy — see blueprint §11), so this write goes through the
    # service client. The registration fee is marked accrued immediately;
    # there's no separate "visit verification" step defined yet, so this
    # is the simplest correct behavior for now — flag if that changes.
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


@router.get("/{patient_id}", response_model=PatientOut)
# Scoped to chw-owned patients only for now. Doctor/admin access to
# patient records arrives with the consultations endpoint next -- that
# needs its own RLS policy on `patients` (doctors currently have none),
# not a workaround here.
def get_patient(patient_id: str, user: CurrentUser = Depends(require_role("chw"))):
    client = get_user_client(user.access_token)
    result = client.table("patients").select("*").eq("id", patient_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Patient not found or not accessible")

    return result.data[0]
