from collections.abc import AsyncIterator
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LOGGER, get_current_user_id
from app.core.config import A3_CONTEXT_FILE, CONTEXT_FILE, SUPPORTED_ATTACHMENT_EXTS, settings
from app.core.database import get_db
from app.extractors.manager import _extract_attachment_excerpt, _save_attachments
from app.models.chat import ChatMessage, ChatSession
from app.services.chat_service import _append_user_message_with_attachments, _finalize_stream_reply
from app.services.coaching_mode_service import detect_coaching_mode
from app.services.context_service import reload_context_for_mode
from app.services.llm_service import _build_model_messages, _call_llm, _call_llm_stream
from app.services.message_service import append_message
from app.services.session_service import SESSION_CACHE, _session_history_for_client, get_session_by_id, rebuild_memory_session
from app.services.sse_service import build_delta_event, build_error_event, format_sse_event

router = APIRouter()


_LLM_PAYLOAD_DEBUG = settings.llm_payload_debug
_LLM_PAYLOAD_PREVIEW_CHARS = max(settings.llm_payload_preview_chars, 50)


def _sanitize_preview(text: str, limit: int) -> str:
    if not text:
        return ""
    compact = text.replace("\n", "\\n")
    return compact[:limit]


def _log_llm_payload_debug(logger, llm_messages: list[dict[str, str]], user_msg: ChatMessage) -> None:
    if not _LLM_PAYLOAD_DEBUG:
        return

    total_chars = sum(len(m.get("content") or "") for m in llm_messages)
    final_user_content = ""
    if llm_messages and llm_messages[-1].get("role") == "user":
        final_user_content = llm_messages[-1].get("content") or ""

    attachment_stats: list[dict[str, Any]] = []
    for att in user_msg.attachments:
        excerpt = att.get("excerpt") or ""
        attachment_stats.append(
            {
                "filename": att.get("filename"),
                "size": att.get("size"),
                "excerpt_chars": len(excerpt),
            }
        )

    logger.info(
        "llm_payload_debug messages={} total_chars={} final_user_chars={} attachment_stats={} user_head='{}' user_tail='{}'",
        len(llm_messages),
        total_chars,
        len(final_user_content),
        json.dumps(attachment_stats, ensure_ascii=False),
        _sanitize_preview(final_user_content, _LLM_PAYLOAD_PREVIEW_CHARS),
        _sanitize_preview(final_user_content[-_LLM_PAYLOAD_PREVIEW_CHARS:], _LLM_PAYLOAD_PREVIEW_CHARS),
    )


async def _get_or_load_session(session_id: str, user_id: str, db: AsyncSession | None) -> ChatSession | None:
    """Look up session from cache, falling back to DB when available."""
    session = SESSION_CACHE.get(session_id)
    if session and session.user_id == user_id:
        return session
    # Try DB fallback
    if db is not None:
        try:
            session_db = await get_session_by_id(db=db, session_id=session_id, user_id=user_id)
            if session_db:
                session = rebuild_memory_session(session_db)
                SESSION_CACHE[session_id] = session
                return session
        except Exception:
            pass
    return None


@router.post("/chat")
async def chat(
    session_id: str = Form(...),
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = await _get_or_load_session(session_id, user_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="\u4f1a\u8bdd\u4e0d\u5b58\u5728")

    chat_logger = LOGGER.bind(session_id=session_id)
    user_msg = await _append_user_message_with_attachments(
        session=session,
        session_id=session_id,
        db=db,
        message=message,
        files=files,
        save_attachments=_save_attachments,
        request_logger=chat_logger,
        log_event="chat_request_received attachments={} has_text={}",
    )

    # Detect and switch coaching mode based on uploaded file.
    _maybe_switch_coaching_mode(session, user_msg, message, db, chat_logger)

    llm_messages = _build_model_messages(session, user_msg)
    _log_llm_payload_debug(chat_logger, llm_messages, user_msg)
    assistant_text = await _call_llm(llm_messages)

    assistant_msg = ChatMessage(role="assistant", content=assistant_text)
    session.messages.append(assistant_msg)
    chat_logger.info("chat_reply_generated reply_chars={}", len(assistant_text))

    # Persist assistant reply to DB when available
    if db is not None:
        await append_message(
            db=db, session_id=session_id, role="assistant",
            content=assistant_text,
        )

    return {
        "session_id": session.session_id,
        "reply": assistant_text,
        "history": _session_history_for_client(session),
        "coaching_mode": session.coaching_mode,
    }


@router.post("/chat/stream")
async def chat_stream(
    session_id: str = Form(...),
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    session = await _get_or_load_session(session_id, user_id, db)
    if not session:
        raise HTTPException(status_code=404, detail="\u4f1a\u8bdd\u4e0d\u5b58\u5728")

    stream_logger = LOGGER.bind(session_id=session_id)
    user_msg = await _append_user_message_with_attachments(
        session=session,
        session_id=session_id,
        db=db,
        message=message,
        files=files,
        save_attachments=_save_attachments,
        request_logger=stream_logger,
        log_event="chat_stream_request_received attachments={} has_text={}",
    )

    # Detect and switch coaching mode based on uploaded file.
    _maybe_switch_coaching_mode(session, user_msg, message, db, stream_logger)

    llm_messages = _build_model_messages(session, user_msg)
    _log_llm_payload_debug(stream_logger, llm_messages, user_msg)

    async def event_gen() -> AsyncIterator[str]:
        chunks: list[str] = []
        try:
            async for delta in _call_llm_stream(llm_messages):
                chunks.append(delta)
                yield build_delta_event(delta)
        except HTTPException as exc:
            stream_logger.warning("chat_stream_http_error detail={}", exc.detail)
            yield build_error_event(str(exc.detail))
            return
        except Exception as exc:  # pragma: no cover - defensive branch
            stream_logger.exception("chat_stream_unexpected_error")
            yield build_error_event(f"\u6d41\u5f0f\u8f93\u51fa\u5931\u8d25: {exc}")
            return

        done_payload = _finalize_stream_reply(
            session=session,
            session_id=session_id,
            db=db,
            chunks=chunks,
            stream_logger=stream_logger,
        )
        # Persist assistant reply to DB when available
        if db is not None:
            await append_message(
                db=db, session_id=session_id, role="assistant",
                content=done_payload["reply"],
            )
        done_payload["coaching_mode"] = session.coaching_mode
        yield format_sse_event(done_payload)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


def _maybe_switch_coaching_mode(
    session: ChatSession,
    user_msg: ChatMessage,
    message: str,
    db: AsyncSession | None,
    logger,
) -> None:
    """Detect coaching mode from the user's attachment/message and switch if needed."""
    if not user_msg.attachments:
        return

    att = user_msg.attachments[0]
    filename = att.get("filename", "")
    excerpt = att.get("excerpt", "")

    detected = detect_coaching_mode(
        filename=filename,
        excerpt=excerpt,
        user_message=message,
    )

    if detected == session.coaching_mode:
        return

    old_mode = session.coaching_mode
    session.coaching_mode = detected
    context_file = A3_CONTEXT_FILE if detected == "a3" else CONTEXT_FILE
    session.context_file = context_file.name

    # Reload context messages for the new mode.
    reload_context_for_mode(
        session=session,
        context_file=context_file,
        supported_attachment_exts=SUPPORTED_ATTACHMENT_EXTS,
        extract_attachment_excerpt=_extract_attachment_excerpt,
        logger=logger,
    )

    logger.info(
        "coaching_mode_switched old={} new={}", old_mode, detected,
    )

    # Persist mode change to DB when available.
    if db is not None:
        import sqlalchemy as sa
        from app.models.db_models import ChatSessionDB

        async def _update_db_mode() -> None:
            try:
                await db.execute(
                    sa.update(ChatSessionDB)
                    .where(ChatSessionDB.id == session.session_id)
                    .values(coaching_mode=detected, context_file=session.context_file)
                )
                await db.commit()
            except Exception as exc:
                logger.warning("coaching_mode_db_update_failed err={}", exc)

        import asyncio
        asyncio.create_task(_update_db_mode())
