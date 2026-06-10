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
    latest_user_message = next(
        (
            msg
            for msg in reversed(session.messages)
            if msg.role == "user" and not msg.is_context and msg.visible_in_history
        ),
        None,
    )
    latest_preview = "新建会话"

    if latest_user_message:
        # Keep title focused on user's own question, not auto-appended attachment hints.
        user_text = latest_user_message.content.split("\n\n附件:", 1)[0]
        preview = user_text.strip().replace("\n", " ")
        latest_preview = preview[:40] if preview else "新建会话"

    return {
        "session_id": session.session_id,
        "created_at": session.created_at,
        "updated_at": latest_user_message.created_at if latest_user_message else session.created_at,
        "latest_preview": latest_preview,
    }
