from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import LOGGER
from app.extractors.manager import _save_attachments
from app.models.chat import ChatMessage
from app.services.chat_service import _append_user_message_with_attachments, _finalize_stream_reply
from app.services.llm_service import _build_model_messages, _call_llm, _call_llm_stream
from app.services.session_service import SESSIONS, _session_history_for_client
from app.services.sse_service import build_delta_event, build_error_event, format_sse_event

router = APIRouter()


@router.post("/chat")
async def chat(
    session_id: str = Form(...),
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    chat_logger = LOGGER.bind(session_id=session_id)
    user_msg = await _append_user_message_with_attachments(
        session=session,
        session_id=session_id,
        message=message,
        files=files,
        save_attachments=_save_attachments,
        request_logger=chat_logger,
        log_event="chat_request_received attachments={} has_text={}",
    )

    llm_messages = _build_model_messages(session, user_msg)
    assistant_text = await _call_llm(llm_messages)

    assistant_msg = ChatMessage(role="assistant", content=assistant_text)
    session.messages.append(assistant_msg)
    chat_logger.info("chat_reply_generated reply_chars={}", len(assistant_text))

    return {
        "session_id": session.session_id,
        "reply": assistant_text,
        "history": _session_history_for_client(session),
    }


@router.post("/chat/stream")
async def chat_stream(
    session_id: str = Form(...),
    message: str = Form(...),
    files: list[UploadFile] = File(default=[]),
) -> StreamingResponse:
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    stream_logger = LOGGER.bind(session_id=session_id)
    user_msg = await _append_user_message_with_attachments(
        session=session,
        session_id=session_id,
        message=message,
        files=files,
        save_attachments=_save_attachments,
        request_logger=stream_logger,
        log_event="chat_stream_request_received attachments={} has_text={}",
    )
    llm_messages = _build_model_messages(session, user_msg)

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
            yield build_error_event(f"流式输出失败: {exc}")
            return

        done_payload = _finalize_stream_reply(
            session=session,
            chunks=chunks,
            stream_logger=stream_logger,
        )
        yield format_sse_event(done_payload)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
