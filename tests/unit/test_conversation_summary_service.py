import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services import conversation_summary_service as svc
from app.services.conversation_summary_service import (
    MAX_SAMPLED_MESSAGES,
    SUMMARIZE_SYSTEM_PROMPT,
    build_summary_prompt,
    summarize_conversation,
)


def _msg(role: str, content: str, visible_in_history: bool = True):
    return SimpleNamespace(role=role, content=content, created_at=None, visible_in_history=visible_in_history)


def test_build_summary_prompt_short_conversation_includes_all():
    messages = [_msg("user", "你好"), _msg("assistant", "在的"), _msg("user", "第二问")]
    prompt = build_summary_prompt(messages, sampled_count=3, total_count=3)
    assert "你好" in prompt and "在的" in prompt and "第二问" in prompt
    assert "本次仅采样" not in prompt


def test_build_summary_prompt_long_conversation_truncates_to_5_plus_25():
    head = [_msg("user", f"head{i}") for i in range(5)]
    middle = [_msg("user", f"mid{i}") for i in range(20)]
    tail = [_msg("assistant", f"tail{i}") for i in range(25)]
    messages = head + middle + tail
    prompt = build_summary_prompt(messages, sampled_count=30, total_count=50)
    assert "head4" in prompt
    assert "tail24" in prompt
    assert "mid0" not in prompt
    assert "共 50 条" in prompt and "本次仅采样首 5 与末 25" in prompt


def test_build_summary_prompt_uses_constant_max_sampled():
    assert MAX_SAMPLED_MESSAGES == 30


def test_summarize_conversation_returns_payload(monkeypatch):
    fake_session = SimpleNamespace(
        id=uuid.uuid4(),
        messages=[_msg("user", "q1"), _msg("assistant", "a1")],
        user=SimpleNamespace(managed_user=SimpleNamespace(primary_role="student", coach_id=None)),
    )
    db = SimpleNamespace()
    user = SimpleNamespace()

    async def fake_resolve(*args, **kwargs):
        return fake_session

    async def fake_call_llm(messages):
        assert messages[0]["role"] == "system"
        assert "q1" in messages[1]["content"]
        return "学员询问了 X, 教练已回复 Y"

    monkeypatch.setattr(svc, "resolve_session_for_summary", fake_resolve)
    monkeypatch.setattr(svc, "_call_llm", fake_call_llm)

    result = asyncio_run(summarize_conversation(db, user, fake_session.id))
    assert result.summary == "学员询问了 X, 教练已回复 Y"
    assert result.sampled_count == 2
    assert result.total_count == 2


def asyncio_run(coro):
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)
