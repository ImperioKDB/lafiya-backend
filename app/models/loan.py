from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

# Must match the DB check constraint on loans.amount exactly (blueprint
# SS1/SS11) -- keep these two in sync if the tiers ever change.
TIER_AMOUNTS = [2500, 5000, 10000, 20000, 40000]


class LoanCreate(BaseModel):
    patient_id: str
    consultation_id: Optional[str] = None
    amount: float

    @field_validator("amount")
    @classmethod
    def amount_must_be_a_tier(cls, v):
        if v not in TIER_AMOUNTS:
            raise ValueError("amount must be one of: " + ", ".join(str(t) for t in TIER_AMOUNTS))
        return v


class LoanOut(BaseModel):
    id: str
    patient_id: str
    consultation_id: Optional[str] = None
    amount: float
    flat_fee_pct: float
    flat_fee: float
    total_repayable: float
    status: str
    created_at: str


class GuarantorAttach(BaseModel):
    guarantor_phones: List[str] = Field(..., min_length=2, max_length=2)


class GuarantorOut(BaseModel):
    id: str
    loan_id: str
    guarantor_phone: str
    liability_share: float
    status: str
    confirmed_at: Optional[str] = None
    created_at: str
    # NEW -- not a DB column, populated at request time only. Lets a
    # future frontend show a visible "SMS failed, retry" state per
    # blueprint SS17 instead of silently assuming delivery succeeded.
    # None on any response path that doesn't attempt an SMS (e.g. if this
    # model is ever reused elsewhere) so it stays backward-compatible.
    sms_sent: Optional[bool] = None


class LoanStatusOut(BaseModel):
    loan: LoanOut
    guarantors: List[GuarantorOut]


class GuarantorTokenAction(BaseModel):
    # Replaces the old GuarantorPhoneAction placeholder. A one-time
    # token issued when the guarantor was attached (app/api/loans.py),
    # delivered via the real SMS in app/services/sms_client.py, and
    # required (not just a bare phone match) to confirm or decline --
    # see app/api/guarantors.py.
    token: str
