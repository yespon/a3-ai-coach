"""Admin API — requires admin role."""

from io import BytesIO
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.db_models import SsoUserWhitelistDB, User
from app.services.whitelist_service import (
    MAX_WHITELIST_UPLOAD_BYTES,
    build_whitelist_template,
    normalize_employee_no,
    parse_whitelist_excel,
    upsert_whitelist_entry,
)

router = APIRouter(prefix="/admin", tags=["admin"])


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin_required")
    return user


class WhitelistCreateRequest(BaseModel):
    employee_no: str
    email: str | None = None


class WhitelistPatchRequest(BaseModel):
    enabled: bool | None = None
    email: str | None = None


def _row(e: SsoUserWhitelistDB) -> dict:
    return {
        "id": str(e.id),
        "employee_no": e.employee_no,
        "email": e.email,
        "enabled": e.enabled,
        "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@router.get("/whitelist")
async def list_whitelist(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    result = await db.execute(select(SsoUserWhitelistDB).order_by(SsoUserWhitelistDB.updated_at.desc()))
    return [_row(e) for e in result.scalars().all()]


@router.post("/whitelist")
async def add_whitelist(
    body: WhitelistCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    employee_no = normalize_employee_no(body.employee_no)
    if not employee_no:
        raise HTTPException(status_code=400, detail="工号不能为空")
    entry, _created = await upsert_whitelist_entry(db, employee_no, body.email.strip() if body.email else None, "manual", admin.id)
    await db.commit(); await db.refresh(entry)
    return _row(entry)


@router.patch("/whitelist/{entry_id}")
async def patch_whitelist(
    entry_id: uuid.UUID,
    body: WhitelistPatchRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    entry = await db.get(SsoUserWhitelistDB, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="not_found")
    if body.enabled is not None:
        entry.enabled = body.enabled
    if body.email is not None:
        entry.email = body.email.strip() or None
    await db.commit(); await db.refresh(entry)
    return _row(entry)


@router.get("/whitelist/template")
async def whitelist_template(admin: User = Depends(require_admin)):
    return StreamingResponse(
        BytesIO(build_whitelist_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=whitelist-template.xlsx"},
    )


@router.post("/whitelist/import")
async def import_whitelist(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")
    raw = await file.read(MAX_WHITELIST_UPLOAD_BYTES + 1)
    if len(raw) > MAX_WHITELIST_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="文件过大")
    parsed = parse_whitelist_excel(raw)
    created = updated = 0
    for row in parsed.rows:
        entry, was_created = await upsert_whitelist_entry(db, row["employee_no"], row["email"], "excel", admin.id)
        created += 1 if was_created else 0
        updated += 0 if was_created else 1
    await db.commit()
    return {"created": created, "updated": updated, "skipped": len(parsed.errors), "errors": parsed.errors}
