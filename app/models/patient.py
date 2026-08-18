from pydantic import BaseModel, Field
from typing import Optional


class PatientCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    phone: str = Field(..., min_length=7, max_length=20)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    # NIN is intentionally optional and unverified at this layer — see
    # blueprint §4/§17: registration never blocks on NIN in this build.
    nin: Optional[str] = None


class PatientOut(BaseModel):
    id: str
    full_name: str
    phone: str
    age: Optional[int] = None
    nin: Optional[str] = None
    registered_by_chw_id: str
    created_at: str
