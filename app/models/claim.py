from pydantic import BaseModel, Field


class ClaimCreate(BaseModel):
    loan_id: str
    claim_amount: float = Field(..., gt=0)


class ClaimOut(BaseModel):
    id: str
    loan_id: str
    pharmacy_id: str
    claim_amount: float
    estimate_amount: float
    variance: float
    match_status: str
    created_at: str
