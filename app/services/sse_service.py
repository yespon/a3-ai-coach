import json
from typing import Any


def format_sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_delta_event(delta: str) -> str:
    return format_sse_event({"type": "delta", "delta": delta})


def build_error_event(error: str) -> str:
    return format_sse_event({"type": "error", "error": error})


def build_done_event(reply: str, history: list[dict[str, Any]]) -> str:
    return format_sse_event({"type": "done", "reply": reply, "history": history})
