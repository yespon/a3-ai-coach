from typing import Any

from pydantic import BaseModel


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
    created_at: str
    updated_at: str
    latest_preview: str
