from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from app.core.auth import require_role
from app.core.supabase_client import get_user_client, get_service_client
from app.models.common import CurrentUser
from app.models.consultation import ConsultationUpdate, ConsultationOut
from app.services.triage import score_urgency, _label as urgency_label, SYMPTOM_CATEGORIES
from app.services.whisper_client import transcribe_audio, WhisperError

router = APIRouter(prefix="/api/consultations", tags=["consultations"])

# Blueprint SS4 -- doctor stipend per completed consultation, funded from
# the flat 5% loan fee overall. Paid on completion regardless of whether
# this particular case ends up needing a loan.
STIPEND_NGN = 500


def _to_out(row: dict) -> dict:
    row = dict(row)
    score = row.get("urgency_score")
    row["urgency_level"] = urgency_label(score) if score is not None else "low"
    return row


@router.post("", response_model=ConsultationOut, status_code=201)
# Switched from a JSON body (ConsultationCreate) to multipart form
# fields -- this is the one endpoint that has to accept an audio file,
# and FastAPI can't mix a JSON body with UploadFile on the same route.
# The text-fallback path (no `audio`) now goes through the same
# multipart contract instead of a second JSON shape, so there's one
# request format to maintain, not two.
#
# symptom_category is required and validated against the exact same
# SYMPTOM_CATEGORIES the USSD numeric menu uses (app/services/triage.py)
# -- PRD SS6.7's "single source of truth" note applies to the *category
# list*, not just the scoring function behind it. Previously nothing on
# the frontend sent this field at all, which the old required
# pydantic field would have rejected outright; this was never actually
# wired end-to-end before now.
def create_consultation(
    patient_id: str = Form(...),
    symptom_category: str = Form(...),
    transcript: Optional[str] = Form(default=None),
    audio: Optional[UploadFile] = File(default=None),
    user: CurrentUser = Depends(require_role("chw")),
):
    if symptom_category not in SYMPTOM_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail="symptom_category must be one of: " + ", ".join(SYMPTOM_CATEGORIES.keys()),
        )

    client = get_user_client(user.access_token)
    final_transcript = transcript

    # Live Whisper call -- Master Build Spec SS8/PRD SS9: transcription
    # happens here, server-side, never trusted from a client-supplied
    # transcript when audio is actually present. A text-only submission
    # (mic denied, or the CHW chose to type) skips this branch entirely
    # and uses the Form-supplied transcript as-is.
    if audio is not None:
        audio_bytes = audio.file.read()
        try:
            final_transcript = transcribe_audio(audio_bytes, audio.filename or "triage-audio.webm")
        except WhisperError as e:
            # Matches blueprint SS17's exact error state for this
            # feature -- "Couldn't reach Whisper -- saved to offline
            # queue, will transcribe on reconnect" -- surfaced as a 502
            # so the frontend's error state can offer "switch to typing"
            # rather than hang.
            raise HTTPException(
                status_code=502,
                detail="Couldn't reach Whisper -- saved to offline queue, will transcribe on reconnect: " + str(e),
            )

    scored = score_urgency(symptom_category, final_transcript)

    # RLS's chw_insert_own_patient_consultations policy requires
    # patient_id to belong to a patient this chw registered -- enforced
    # at the DB layer, not just here. If the insert comes back empty,
    # RLS rejected it.
    insert_result = (
        client.table("consultations")
        .insert(
            {
                "patient_id": patient_id,
                "transcript": final_transcript,
                "urgency_score": scored["score"],
                "status": "queued",
            }
        )
        .execute()
    )

    if not insert_result.data:
        raise HTTPException(
            status_code=403,
            detail="Could not create consultation -- patient not found or not registered by you",
        )

    return _to_out(insert_result.data[0])


@router.get("/queue", response_model=list[ConsultationOut])
# RLS's doctor_consultations policy returns unclaimed cases (any doctor)
# plus this doctor's own already-claimed cases. Sorted here by urgency
# first, oldest-first as the tiebreaker.
def get_queue(user: CurrentUser = Depends(require_role("doctor"))):
    client = get_user_client(user.access_token)
    result = (
        client.table("consultations")
        .select("*")
        .eq("status", "queued")
        .order("urgency_score", desc=True)
        .order("created_at", desc=False)
        .execute()
    )
    return [_to_out(row) for row in (result.data or [])]


@router.patch("/{consultation_id}", response_model=ConsultationOut)
# Claim-on-write: the first doctor to PATCH an unclaimed consultation
# becomes its doctor_id (this endpoint always sends doctor_id=self in
# the update payload). RLS's USING clause on the old row blocks this
# from ever succeeding against a case another doctor already claimed --
# the row simply isn't visible to update, not a race a client can win.
def update_consultation(
    consultation_id: str,
    payload: ConsultationUpdate,
    user: CurrentUser = Depends(require_role("doctor")),
):
    client = get_user_client(user.access_token)

    existing = client.table("consultations").select("*").eq("id", consultation_id).execute()
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found, already claimed by another doctor, or not accessible",
        )

    current = existing.data[0]
    was_already_completed = current["status"] == "completed"

    update_payload = {"doctor_id": user.role_row_id}
    if payload.prescription is not None:
        update_payload["prescription"] = payload.prescription
    if payload.cost_estimate is not None:
        update_payload["cost_estimate"] = payload.cost_estimate
    if current["status"] == "queued":
        update_payload["status"] = "in_review"
    if payload.complete:
        update_payload["status"] = "completed"

    update_result = (
        client.table("consultations")
        .update(update_payload)
        .eq("id", consultation_id)
        .execute()
    )

    if not update_result.data:
        raise HTTPException(status_code=403, detail="Could not update -- already claimed by another doctor")

    updated = update_result.data[0]

    # Stipend accrues exactly once, on the transition into 'completed' --
    # never on a repeat PATCH to an already-completed case.
    if payload.complete and not was_already_completed:
        service_client = get_service_client()
        service_client.table("doctor_earnings").insert(
            {
                "doctor_id": user.role_row_id,
                "type": "stipend",
                "amount": STIPEND_NGN,
                "related_entity_id": consultation_id,
                "status": "accrued",
            }
        ).execute()

    return _to_out(updated)
