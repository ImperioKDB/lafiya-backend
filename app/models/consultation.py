from pydantic import BaseModel, Field
from typing import Optional
from app.services.triage import SYMPTOM_CATEGORIES


class ConsultationCreate(BaseModel):
    patient_id: str
    # NEW -- was required with no default, but the smartphone app's
    # Triage screen (voice and text modes) never collects a category at
    # all -- only the USSD numeric-menu path was ever designed to supply
    # one (Master Build Spec SS9). Every text/voice submission from the
    # frontend was failing 422 as a result. Defaulting to None here and
    # falling back to "other" in the endpoint matches score_urgency's
    # own existing fallback behavior exactly (app/services/triage.py
    # already treats any unrecognized category as "other") -- this is a
    # decision made in this pass, not a silent behavior change: flag if
    # a real category-picker UI is wanted on the smartphone flow later.
    symptom_category: Optional[str] = Field(
        default=None,
        description="One of: " + ", ".join(SYMPTOM_CATEGORIES.keys()) + ". Defaults to 'other' if omitted.",
    )
    # Optional for now -- live Whisper wiring is Master Build Spec Phase 2,
    # the next thing after this. Until then this is either omitted
    # (USSD-style, category only) or hand-entered test text standing in
    # for a real transcript (Master Build Spec SS15 Phase 1).
    transcript: Optional[str] = Field(default=None, max_length=5000)


class ConsultationUpdate(BaseModel):
    prescription: Optional[str] = Field(default=None, max_length=2000)
    cost_estimate: Optional[float] = Field(default=None, ge=0)
    # Doctor explicitly marks a case done -- this is what triggers the
    # NGN500 stipend accrual, not just the presence of a prescription.
    complete: Optional[bool] = False


class ConsultationOut(BaseModel):
    id: str
    patient_id: str
    doctor_id: Optional[str] = None
    transcript: Optional[str] = None
    urgency_score: int
    urgency_level: str
    prescription: Optional[str] = None
    cost_estimate: Optional[float] = None
    status: str
    created_at: str
