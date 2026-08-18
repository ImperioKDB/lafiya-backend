from pydantic import BaseModel
from typing import Optional


# Resolved once per request in get_current_user. role_row_id is the
# primary key in chws/doctors/pharmacies for that role -- None for admin,
# since admin isn't backed by any of those tables.
class CurrentUser(BaseModel):
    id: str
    email: str
    role: str
    role_row_id: Optional[str] = None
    access_token: str
