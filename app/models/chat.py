from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ChatMessage:
    role: str
    content: str
    created_at: str = field(default_factory=_now_iso)
    is_context: bool = False
    visible_in_history: bool = True
    attachments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ChatSession:
    session_id: str
    show_context_in_history: bool
    context_file: str
    created_at: str = field(default_factory=_now_iso)
    messages: list[ChatMessage] = field(default_factory=list)
