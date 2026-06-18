"""Summarize a single chat session for the admin UI."""

from dataclasses import dataclass
import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import ChatMessageDB, User
from app.services.admin_conversation_service import (
    is_admin_user,
    resolve_session_for_summary,
)
from app.services.llm_service import _call_llm

MAX_SAMPLED_MESSAGES = 30
HEAD_KEEP = 5
TAIL_KEEP = 25

SUMMARIZE_SYSTEM_PROMPT = (
    "你是一名管理员对话审计助手。"
    "请基于提供的会话内容,生成一段不超过 300 字的中文摘要,"
    "涵盖学员关注话题、教练给出的建议、仍未解决的关键问题。"
)


@dataclass(slots=True)
class ConversationSummary:
    summary: str
    sampled_count: int
    total_count: int


def build_summary_prompt(messages: list, sampled_count: int, total_count: int) -> str:
    """Render messages into a single user-prompt string.

    If sampled_count < total_count, only the first HEAD_KEEP and last
    TAIL_KEEP messages are included in the rendered output.
    """
    if total_count > MAX_SAMPLED_MESSAGES:
        note = f"会话共 {total_count} 条,本次仅采样首 5 与末 25。"
        rendered_messages = messages[:HEAD_KEEP] + messages[-TAIL_KEEP:]
    else:
        note = f"会话共 {total_count} 条。"
        rendered_messages = messages
    rendered = "\n".join(
        f"[{idx + 1}] {msg.role}: {msg.content}" for idx, msg in enumerate(rendered_messages)
    )
    return f"{note}\n\n{rendered}"


async def summarize_conversation(
    db: AsyncSession,
    user: User,
    session_id: uuid.UUID,
    *,
    head_keep: int = HEAD_KEEP,
    tail_keep: int = TAIL_KEEP,
) -> ConversationSummary:
    session = await resolve_session_for_summary(db, user, session_id)
    visible = [m for m in session.messages if m.visible_in_history]
    total = len(visible)
    if total <= MAX_SAMPLED_MESSAGES:
        sampled = visible
        sampled_count = total
    else:
        sampled = visible[:head_keep] + visible[-tail_keep:]
        sampled_count = len(sampled)

    user_prompt = build_summary_prompt(sampled, sampled_count, total)
    try:
        summary_text = await _call_llm(
            [
                {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )
    except HTTPException:
        # Re-raise as-is so the route can preserve the status code.
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"AI 速览生成失败: {exc}") from exc

    return ConversationSummary(
        summary=summary_text.strip(),
        sampled_count=sampled_count,
        total_count=total,
    )
