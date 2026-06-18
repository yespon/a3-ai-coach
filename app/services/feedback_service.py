"""Feedback submissions and admin moderation."""

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import re
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import BASE_DIR, UPLOAD_ROOT
from app.models.db_models import (
    FeedbackAttachmentDB,
    FeedbackSubmissionDB,
    ManagedUserDB,
    User,
)

MAX_CONTENT_LEN = 1000
MAX_ATTACHMENTS = 5
MAX_ATTACHMENT_BYTES = 3 * 1024 * 1024
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_CONTENT_PREFIX = "image/"
FEEDBACK_UPLOAD_DIR = UPLOAD_ROOT / "feedback"

VALID_STATUSES = {"open", "read", "resolved"}


@dataclass(slots=True)
class FeedbackListItem:
    id: uuid.UUID
    submitter: dict
    content_excerpt: str
    attachment_count: int
    status: str
    created_at: datetime


def summarize_excerpt(content: str, *, limit: int = 30) -> str:
    text = content.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def build_attachment_url(saved_path: str) -> str:
    rel = saved_path
    if rel.startswith(str(BASE_DIR)):
        rel = os.path.relpath(saved_path, BASE_DIR)
    rel = rel.replace(os.sep, "/")
    return f"/uploads/{rel.lstrip('/')}"


def validate_status_transition(current: str, target: str) -> None:
    if target not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="invalid_status")
    if current == target:
        raise HTTPException(status_code=400, detail="status_unchanged")
    if current == "open" and target == "resolved":
        raise HTTPException(status_code=400, detail="must_read_before_resolve")
    if current == "open" and target == "read":
        return
    if current == "read" and target == "resolved":
        return
    if current == "resolved" and target == "read":
        return
    raise HTTPException(status_code=400, detail="invalid_transition")


def _check_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=422, detail=f"仅支持图片格式: {', '.join(sorted(ALLOWED_EXTS))}")
    return ext


def _check_content_type(content_type: str | None) -> None:
    if not content_type or not content_type.startswith(ALLOWED_CONTENT_PREFIX):
        raise HTTPException(status_code=422, detail="附件必须为图片")


async def _persist_attachments(
    db: AsyncSession, submission_id: uuid.UUID, files: list[UploadFile]
) -> list[FeedbackAttachmentDB]:
    FEEDBACK_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = FEEDBACK_UPLOAD_DIR / str(submission_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    rows: list[FeedbackAttachmentDB] = []
    for position, f in enumerate(files):
        ext = _check_extension(f.filename or "image")
        _check_content_type(f.content_type)
        raw = await f.read()
        if len(raw) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="单张图片不能超过 3MB")
        safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(f.filename or "image"))
        stored = target_dir / f"{position}_{uuid.uuid4().hex}_{safe_name}"
        stored.write_bytes(raw)
        rows.append(
            FeedbackAttachmentDB(
                feedback_id=submission_id,
                filename=os.path.basename(f.filename or "image"),
                content_type=f.content_type or "image/jpeg",
                size=len(raw),
                saved_path=str(stored.relative_to(BASE_DIR)),
                position=position,
            )
        )
    return rows


async def create_feedback(
    db: AsyncSession,
    user: User,
    content: str,
    files: list[UploadFile],
    *,
    user_agent: str | None = None,
    ip: str | None = None,
) -> FeedbackSubmissionDB:
    text = (content or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="反馈内容不能为空")
    if len(text) > MAX_CONTENT_LEN:
        raise HTTPException(status_code=422, detail=f"反馈内容不能超过 {MAX_CONTENT_LEN} 字")
    if files and len(files) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=422, detail=f"附件最多 {MAX_ATTACHMENTS} 张")

    # Pre-validate file sizes before creating the DB row
    for f in files:
        raw = await f.read()
        if hasattr(f, "seek"):
            await f.seek(0)
        if len(raw) > MAX_ATTACHMENT_BYTES:
            raise HTTPException(status_code=413, detail="单张图片不能超过 3MB")

    submission = FeedbackSubmissionDB(
        user_id=user.id,
        content=text,
        status="open",
        user_agent=(user_agent or "")[:255] or None,
        ip=(ip or "")[:64] or None,
    )
    db.add(submission)
    await db.flush()

    if files:
        attachments = await _persist_attachments(db, submission.id, files)
        db.add_all(attachments)

    await db.commit()
    await db.refresh(submission)
    return submission


async def list_feedback(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 30,
    status: str = "all",
    q: str | None = None,
) -> tuple[list[FeedbackListItem], int]:
    page = max(page, 1)
    page_size = max(min(page_size, 100), 1)

    stmt = select(FeedbackSubmissionDB)
    count_stmt = select(func.count()).select_from(FeedbackSubmissionDB)

    if status in {"open", "read", "resolved"}:
        stmt = stmt.where(FeedbackSubmissionDB.status == status)
        count_stmt = count_stmt.where(FeedbackSubmissionDB.status == status)
    elif status != "all":
        raise HTTPException(status_code=400, detail="invalid_status")

    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(FeedbackSubmissionDB.content.ilike(needle))
        count_stmt = count_stmt.where(FeedbackSubmissionDB.content.ilike(needle))

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        await db.execute(
            stmt.options(selectinload(FeedbackSubmissionDB.attachments))
            .order_by(FeedbackSubmissionDB.created_at.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    submitter_ids = list({row.user_id for row in rows})
    submitter_map: dict[uuid.UUID, ManagedUserDB] = {}
    user_to_managed: dict[uuid.UUID, uuid.UUID] = {}
    if submitter_ids:
        user_rows = (
            await db.execute(select(User).where(User.id.in_(submitter_ids)))
        ).scalars().all()
        user_to_managed = {u.id: u.managed_user_id for u in user_rows}
        managed_ids = [mid for mid in user_to_managed.values() if mid]
        if managed_ids:
            managed_rows = (
                await db.execute(select(ManagedUserDB).where(ManagedUserDB.id.in_(managed_ids)))
            ).scalars().all()
            submitter_map = {m.id: m for m in managed_rows}

    items: list[FeedbackListItem] = []
    for row in rows:
        managed_id = user_to_managed.get(row.user_id)
        profile = submitter_map.get(managed_id) if managed_id else None
        items.append(
            FeedbackListItem(
                id=row.id,
                submitter={
                    "employee_no": profile.employee_no if profile else None,
                    "name": profile.name if profile else None,
                    "email": profile.email if profile else None,
                },
                content_excerpt=summarize_excerpt(row.content),
                attachment_count=len(row.attachments),
                status=row.status,
                created_at=row.created_at,
            )
        )
    return items, int(total)


async def get_feedback(db: AsyncSession, feedback_id: uuid.UUID) -> FeedbackSubmissionDB:
    submission = (
        await db.execute(
            select(FeedbackSubmissionDB)
            .options(selectinload(FeedbackSubmissionDB.attachments))
            .where(FeedbackSubmissionDB.id == feedback_id)
        )
    ).scalar_one_or_none()
    if submission is None:
        raise HTTPException(status_code=404, detail="feedback_not_found")
    if submission.status == "open":
        submission.status = "read"
        submission.read_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(submission)
    return submission


async def mark_status(db: AsyncSession, feedback_id: uuid.UUID, target: str) -> FeedbackSubmissionDB:
    submission = await db.get(FeedbackSubmissionDB, feedback_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="feedback_not_found")
    validate_status_transition(submission.status, target)
    now = datetime.now(UTC)
    if target == "read" and submission.read_at is None:
        submission.read_at = now
    if target == "resolved" and submission.resolved_at is None:
        submission.resolved_at = now
    submission.status = target
    await db.commit()
    await db.refresh(submission)
    return submission
