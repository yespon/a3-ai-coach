from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class CreateSessionRequest(BaseModel):
    show_context_in_history: bool = True


class UpdateSessionSettingsRequest(BaseModel):
    show_context_in_history: bool


class SessionResponse(BaseModel):
    session_id: str
    show_context_in_history: bool
    created_at: str
    history: list[dict[str, Any]]


class SessionSummaryResponse(BaseModel):
    session_id: str
    title: str | None = None
    pinned: bool = False
    created_at: str
    updated_at: str
    latest_preview: str


# --- Auth schemas ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    nickname: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str | None
    nickname: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime
    managed_user_id: str | None = None
    employee_no: str | None = None
    primary_role: str | None = None
    is_coach: bool = False

class CASUserResponse(BaseModel):
    ok: bool = True
    user: UserResponse | None = None
