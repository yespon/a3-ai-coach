# T-1: chat attachment upload size limit

import asyncio
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

import app.extractors.manager as manager_module


class _DummyUploadFile:
    def __init__(self, filename: str, content_type: str, raw_bytes: bytes):
        self.filename = filename
        self.content_type = content_type
        self._raw_bytes = raw_bytes

    async def read(self) -> bytes:
        return self._raw_bytes


async def _run_save(session_id: str, files, **patches):
    """Helper: run _save_attachments with isolated tmp dir and optional patches."""
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    orig_base = manager_module.BASE_DIR
    orig_upload = manager_module.UPLOAD_ROOT

    manager_module.BASE_DIR = tmp
    manager_module.UPLOAD_ROOT = tmp / "uploads"

    # Apply optional patches
    saved = {}
    for key, val in patches.items():
        saved[key] = getattr(manager_module, key)
        setattr(manager_module, key, val)

    try:
        return await manager_module._save_attachments(session_id=session_id, files=files)
    finally:
        manager_module.BASE_DIR = orig_base
        manager_module.UPLOAD_ROOT = orig_upload
        for key, val in saved.items():
            setattr(manager_module, key, val)


# ---------- Test: oversized file raises HTTPException ----------

async def test_save_attachments_rejects_oversized_file():
    from fastapi import HTTPException

    big_bytes = b"x" * (5 * 1024 * 1024 + 1)  # 5 MB + 1 byte
    f = _DummyUploadFile("huge.xlsx", "application/octet-stream", big_bytes)

    try:
        await _run_save(
            "s1",
            [f],
            ATTACHMENT_EXCERPT_CHARS=0,
            ATTACHMENT_HINT_CHARS=0,
            ATTACHMENT_SHOW_META=False,
            MAX_CHAT_ATTACHMENT_BYTES=5 * 1024 * 1024,
        )
        assert False, "Expected HTTPException was not raised"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "附件大小超限" in exc.detail


# ---------- Test: file at exact limit is accepted ----------

async def test_save_attachments_accepts_file_at_limit():
    exact_bytes = b"x" * (5 * 1024 * 1024)  # exactly 5 MB
    f = _DummyUploadFile("exact.xlsx", "application/octet-stream", exact_bytes)

    saved, hints = await _run_save(
        "s1",
        [f],
        ATTACHMENT_EXCERPT_CHARS=0,
        ATTACHMENT_HINT_CHARS=0,
        ATTACHMENT_SHOW_META=False,
        MAX_CHAT_ATTACHMENT_BYTES=5 * 1024 * 1024,
    )

    assert len(saved) == 1
    assert saved[0]["size"] == 5 * 1024 * 1024


# ---------- Test: limit=0 means no limit ----------

async def test_save_attachments_no_limit_when_zero():
    big_bytes = b"x" * (10 * 1024 * 1024)  # 10 MB
    f = _DummyUploadFile("big.xlsx", "application/octet-stream", big_bytes)

    saved, hints = await _run_save(
        "s1",
        [f],
        ATTACHMENT_EXCERPT_CHARS=0,
        ATTACHMENT_HINT_CHARS=0,
        ATTACHMENT_SHOW_META=False,
        MAX_CHAT_ATTACHMENT_BYTES=0,  # 0 = no limit
    )

    assert len(saved) == 1


# ---------- Run ----------

if __name__ == "__main__":
    import sys

    asyncio.run(test_save_attachments_rejects_oversized_file())
    print("PASS: oversized file rejected")

    asyncio.run(test_save_attachments_accepts_file_at_limit())
    print("PASS: file at limit accepted")

    asyncio.run(test_save_attachments_no_limit_when_zero())
    print("PASS: no limit when 0")

    print("\nAll tests passed ✓")
