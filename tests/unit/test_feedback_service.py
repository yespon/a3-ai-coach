import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import feedback_service as svc
from app.services.feedback_service import (
    MAX_ATTACHMENTS,
    MAX_ATTACHMENT_BYTES,
    MAX_CONTENT_LEN,
    build_attachment_url,
    summarize_excerpt,
    validate_status_transition,
)


class _Upload:
    def __init__(self, filename: str, content_type: str, data: bytes):
        self.filename = filename
        self.content_type = content_type
        self._data = data

    async def read(self):
        return self._data


@pytest.mark.asyncio
async def test_create_feedback_rejects_too_many_attachments(monkeypatch):
    uploads = [_Upload(f"a{i}.png", "image/png", b"x") for i in range(MAX_ATTACHMENTS + 1)]
    db = SimpleNamespace()
    monkeypatch.setattr(svc, "_persist_attachments", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await svc.create_feedback(db, SimpleNamespace(id=uuid.uuid4()), "hi", uploads)
    assert exc.value.status_code == 422
    assert "最多" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_feedback_rejects_oversize_image(monkeypatch):
    big = b"\0" * (MAX_ATTACHMENT_BYTES + 1)
    uploads = [_Upload("a.png", "image/png", big)]
    db = SimpleNamespace()
    monkeypatch.setattr(svc, "_persist_attachments", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await svc.create_feedback(db, SimpleNamespace(id=uuid.uuid4()), "hi", uploads)
    assert exc.value.status_code == 413
    assert "3MB" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_feedback_rejects_empty_content():
    with pytest.raises(HTTPException) as exc:
        await svc.create_feedback(SimpleNamespace(), SimpleNamespace(id=uuid.uuid4()), "   ", [])
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_feedback_rejects_oversize_content():
    too_long = "x" * (MAX_CONTENT_LEN + 1)
    with pytest.raises(HTTPException) as exc:
        await svc.create_feedback(SimpleNamespace(), SimpleNamespace(id=uuid.uuid4()), too_long, [])
    assert exc.value.status_code == 422


def test_summarize_excerpt_truncates_at_30():
    assert summarize_excerpt("x" * 100, limit=30) == ("x" * 30) + "…"


def test_build_attachment_url_returns_uploads_path():
    url = build_attachment_url("feedback/<id>/0_<rand>.png")
    assert url.startswith("/uploads/feedback/")


def test_validate_status_transition_rules():
    validate_status_transition("open", "read")
    validate_status_transition("read", "resolved")
    validate_status_transition("resolved", "read")
    with pytest.raises(HTTPException):
        validate_status_transition("open", "resolved")  # must read first
    with pytest.raises(HTTPException):
        validate_status_transition("open", "open")
    with pytest.raises(HTTPException):
        validate_status_transition("resolved", "resolved")
