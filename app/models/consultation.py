from pydantic import BaseModel, Field
from typing import Optional
from app.services.triage import SYMPTOM_CATEGORIES


class ConsultationCreate(BaseModel):
    patient_id: str
    symptom_category: str = Field(
        ..., description="One of: " + ", ".join(SYMPTOM_CATEGORIES.keys())
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
