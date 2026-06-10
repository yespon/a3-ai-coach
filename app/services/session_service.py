from typing import Any

from app.models.chat import ChatSession

SESSIONS: dict[str, ChatSession] = {}


def _session_history_for_client(session: ChatSession) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for msg in session.messages:
        if not msg.visible_in_history:
            continue
        if msg.is_context and not session.show_context_in_history:
            continue
        history.append(
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
                "is_context": msg.is_context,
                "attachments": msg.attachments,
            }
        )
    return history


def _session_summary_for_client(session: ChatSession) -> dict[str, str]:
    last_message = session.messages[-1] if session.messages else None
    latest_preview = "新会话"

    if last_message:
        preview = last_message.content.strip().replace("\n", " ")
        latest_preview = preview[:40] if preview else "空消息"

    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "updated_at": last_message.created_at if last_message else session.created_at,
        "latest_preview": latest_preview,
    }
