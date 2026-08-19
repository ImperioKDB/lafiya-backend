from pydantic import BaseModel, field_validator
from typing import Optional


class PharmacyOut(BaseModel):
    id: str
    name: str
    license_number: str
    document_url: Optional[str] = None
    status: str
    auth_user_id: Optional[str] = None
    created_at: str


class PharmacyStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v):
        allowed = {"pending", "verified", "rejected"}
        if v not in allowed:
            raise ValueError("status must be one of: " + ", ".join(sorted(allowed)))
        return v


class FraudFlagOut(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    reason: str
    status: str
    created_at: str


class FraudFlagStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def status_must_be_valid(cls, v):
        allowed = {"open", "reviewed", "cleared", "confirmed_fraud"}
        if v not in allowed:
            raise ValueError("status must be one of: " + ", ".join(sorted(allowed)))
        return v
