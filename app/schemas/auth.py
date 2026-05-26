from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from app.models.user import UserRole


class RegisterRequest(BaseModel):
    username: str
    password: str
    full_name: str
    role: UserRole = UserRole.RESIDENT
    building_id: Optional[str] = None
    unit_number: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    full_name: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: UserRole
    building_id: Optional[str]
    unit_number: Optional[str]
    is_active: bool
    created_at: datetime
