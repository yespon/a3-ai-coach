# 管理员 SSO 白名单 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 管理员维护 SSO 白名单（Excel 增量导入 + 手工新增 + 启用/禁用），SSO 登录时只允许管理员或 enabled 白名单用户进入。

**Architecture:** 新增 `sso_user_whitelist` 独立表和 `whitelist_service`，CAS exchange 在 upsert/session 前做准入校验。新增 `/api/v1/admin/*` 管理接口（require_admin）和前端 `/admin/whitelist` 页面；管理员入口只对 `userInfo.is_admin` 展示。

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + openpyxl；Next.js 15 + React + TypeScript；pytest 后端 TDD，前端用 `tsc` + `next build` + 手动 E2E。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `app/models/db_models.py` | 新增 `SsoUserWhitelistDB` ORM 模型 |
| `alembic/versions/004_sso_user_whitelist.py` | 新表迁移 |
| `app/core/config.py` / `.env.example` | `ADMIN_EMPLOYEE_NOS` 配置 + helper |
| `app/services/user_service.py` | `upsert_sso_user(..., is_admin)` 只升不降 |
| `app/services/whitelist_service.py` | 白名单查询、upsert、Excel 解析、模板生成 |
| `app/api/deps.py` | `require_admin` dependency |
| `app/api/v1/routes/admin.py` | 管理 API |
| `app/api/v1/routes/cas.py` | SSO exchange 白名单 gate |
| `app/api/v1/routes/auth.py` / `app/models/schema.py` | `/me` 返回 `is_admin` |
| `frontend/types/auth.ts` | `UserInfo.is_admin` |
| `frontend/types/admin.ts` | 白名单类型 |
| `frontend/lib/admin.ts` | admin API client |
| `frontend/app/page.tsx` | 管理入口（仅 admin 可见） |
| `frontend/app/admin/whitelist/page.tsx` | 管理页面 |
| `frontend/app/globals.css` | 管理页面样式 |

---

## Task 1: 数据模型 + 迁移（TDD-ish schema smoke）

**Files:**
- Modify: `app/models/db_models.py`
- Create: `alembic/versions/004_sso_user_whitelist.py`
- Test: `tests/unit/test_whitelist_model.py`

- [ ] **Step 1: 写模型 smoke 测试**

```python
# tests/unit/test_whitelist_model.py
from app.models.db_models import SsoUserWhitelistDB


def test_whitelist_model_columns():
    cols = set(SsoUserWhitelistDB.__table__.columns.keys())
    assert {"id", "employee_no", "email", "enabled", "source", "created_by", "created_at", "updated_at"} <= cols
    assert SsoUserWhitelistDB.__tablename__ == "sso_user_whitelist"
```

Run: `.venv/bin/python -m pytest tests/unit/test_whitelist_model.py -q`
Expected: FAIL `ImportError` / class missing.

- [ ] **Step 2: 在 `app/models/db_models.py` 新增模型**

Add after `AuthSessionDB`:

```python
class SsoUserWhitelistDB(Base):
    __tablename__ = "sso_user_whitelist"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    employee_no: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), index=True)
    source: Mapped[str] = mapped_column(String(20), server_default=text("'manual'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), onupdate=datetime.now(UTC)
    )
```

- [ ] **Step 3: 新增迁移 `004_sso_user_whitelist.py`**

```python
"""sso user whitelist

Revision ID: 004_sso_user_whitelist
Revises: 003_user_sso_fields
Create Date: 2026-06-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

revision: str = "004_sso_user_whitelist"
down_revision: Union[str, Sequence[str], None] = "003_user_sso_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sso_user_whitelist",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("employee_no", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("source", sa.String(20), server_default=sa.text("'manual'"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_sso_user_whitelist_employee_no", "sso_user_whitelist", ["employee_no"], unique=True)
    op.create_index("ix_sso_user_whitelist_enabled", "sso_user_whitelist", ["enabled"])


def downgrade() -> None:
    op.drop_index("ix_sso_user_whitelist_enabled", table_name="sso_user_whitelist")
    op.drop_index("ix_sso_user_whitelist_employee_no", table_name="sso_user_whitelist")
    op.drop_table("sso_user_whitelist")
```

- [ ] **Step 4: 验证**

Run: `.venv/bin/python -m pytest tests/unit/test_whitelist_model.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/db_models.py alembic/versions/004_sso_user_whitelist.py tests/unit/test_whitelist_model.py
git commit -m "feat(admin): add SSO whitelist DB model and migration"
```

---

## Task 2: 管理员工号配置 + SSO user 赋权

**Files:**
- Modify: `app/core/config.py`, `.env.example`, `app/services/user_service.py`
- Test: `tests/unit/test_admin_config.py`, `tests/unit/test_user_service_admin.py`

- [ ] **Step 1: 写配置测试**

```python
# tests/unit/test_admin_config.py
from app.core.config import Settings, get_admin_employee_no_set


def test_admin_employee_no_set_parses_and_trims(monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "admin_employee_nos", " 1001,1002 ,, 1003 ")
    assert get_admin_employee_no_set() == {"1001", "1002", "1003"}
```

Run: `.venv/bin/python -m pytest tests/unit/test_admin_config.py -q`
Expected: FAIL helper missing.

- [ ] **Step 2: 实现配置**

In `Settings` add near CAS section:

```python
admin_employee_nos: str = ""
```

After `settings = Settings()` add:

```python
def get_admin_employee_no_set() -> set[str]:
    return {part.strip() for part in settings.admin_employee_nos.split(",") if part.strip()}
```

`.env.example` add:

```bash
# Comma-separated SSO employee numbers that should become administrators.
ADMIN_EMPLOYEE_NOS=
```

- [ ] **Step 3: 写 upsert 管理员测试（mock AsyncSession 简化）**

```python
# tests/unit/test_user_service_admin.py
import uuid
from types import SimpleNamespace

import pytest

from app.models.db_models import User
from app.services.user_service import upsert_sso_user


class FakeResult:
    def __init__(self, user): self.user = user
    def scalar_one_or_none(self): return self.user


class FakeSession:
    def __init__(self, user=None): self.user = user; self.added = None
    async def execute(self, stmt): return FakeResult(self.user)
    def add(self, obj): self.added = obj; self.user = obj
    async def commit(self): pass
    async def refresh(self, obj): obj.id = getattr(obj, "id", uuid.uuid4())


@pytest.mark.asyncio
async def test_upsert_sso_user_marks_admin_on_create():
    db = FakeSession()
    user = await upsert_sso_user(db, "1001", {"RJEMAIL": "a@example.com", "RJXM": "A"}, is_admin=True)
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_upsert_sso_user_only_promotes_admin_never_demotes():
    existing = User(provider="cas", provider_user_id="1001", email="a@example.com", password_hash=None)
    existing.is_admin = True
    db = FakeSession(existing)
    user = await upsert_sso_user(db, "1001", {}, is_admin=False)
    assert user.is_admin is True
```

Run: `.venv/bin/python -m pytest tests/unit/test_user_service_admin.py -q`
Expected: FAIL unexpected `is_admin` kwarg.

- [ ] **Step 4: 修改 `upsert_sso_user`**

Change signature:

```python
async def upsert_sso_user(db: AsyncSession, employee_no: str, attrs: dict, is_admin: bool = False) -> User:
```

In create block add:

```python
is_admin=is_admin,
```

In update block add:

```python
        if is_admin and not user.is_admin:
            user.is_admin = True
```

- [ ] **Step 5: 验证**

Run:
```bash
.venv/bin/python -m pytest tests/unit/test_admin_config.py tests/unit/test_user_service_admin.py -q
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/core/config.py .env.example app/services/user_service.py tests/unit/test_admin_config.py tests/unit/test_user_service_admin.py
git commit -m "feat(admin): configure admin employee numbers and promote SSO admins"
```

---

## Task 3: 白名单 service（查询/upsert/import/template）

**Files:**
- Create: `app/services/whitelist_service.py`
- Test: `tests/unit/test_whitelist_service.py`

- [ ] **Step 1: 写纯函数测试（Excel 解析 + size-independent）**

```python
# tests/unit/test_whitelist_service.py
from io import BytesIO
from openpyxl import Workbook, load_workbook

from app.services.whitelist_service import parse_whitelist_excel, build_whitelist_template


def _xlsx(rows):
    wb = Workbook(); ws = wb.active
    for row in rows: ws.append(row)
    buf = BytesIO(); wb.save(buf); buf.seek(0); return buf.getvalue()


def test_parse_whitelist_excel_valid_rows():
    data = _xlsx([["工号", "邮箱"], ["1001", "a@example.com"], ["1002", None]])
    result = parse_whitelist_excel(data)
    assert result.rows == [{"employee_no": "1001", "email": "a@example.com"}, {"employee_no": "1002", "email": None}]
    assert result.errors == []


def test_parse_whitelist_excel_reports_empty_employee_no():
    data = _xlsx([["工号", "邮箱"], [None, "a@example.com"]])
    result = parse_whitelist_excel(data)
    assert result.rows == []
    assert result.errors == [{"row": 2, "reason": "工号为空"}]


def test_template_contains_expected_headers():
    wb = load_workbook(BytesIO(build_whitelist_template()))
    assert [cell.value for cell in wb.active[1]] == ["工号", "邮箱"]
```

Run: `.venv/bin/python -m pytest tests/unit/test_whitelist_service.py -q`
Expected: FAIL module missing.

- [ ] **Step 2: 创建 service**

```python
# app/services/whitelist_service.py
from dataclasses import dataclass
from io import BytesIO
from typing import Any
import uuid

from openpyxl import Workbook, load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db_models import SsoUserWhitelistDB

WHITELIST_DENY_MESSAGE = "当前账号未开通岗标 AI 教练访问权限，请联系管理员开通。"

@dataclass
class ParseResult:
    rows: list[dict[str, str | None]]
    errors: list[dict[str, Any]]


def _cell_text(value) -> str:
    return str(value).strip() if value is not None else ""


def parse_whitelist_excel(raw: bytes) -> ParseResult:
    wb = load_workbook(BytesIO(raw), read_only=True, data_only=True)
    ws = wb.active
    header = [_cell_text(c.value) for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        emp_idx = header.index("工号")
        email_idx = header.index("邮箱")
    except ValueError:
        return ParseResult(rows=[], errors=[{"row": 1, "reason": "表头必须包含工号、邮箱"}])
    latest: dict[str, str | None] = {}
    errors: list[dict[str, Any]] = []
    for idx, row in enumerate(ws.iter_rows(min_row=2), start=2):
        employee_no = _cell_text(row[emp_idx].value if emp_idx < len(row) else None)
        email = _cell_text(row[email_idx].value if email_idx < len(row) else None) or None
        if not employee_no:
            errors.append({"row": idx, "reason": "工号为空"})
            continue
        latest[employee_no] = email
    rows = [{"employee_no": k, "email": v} for k, v in latest.items()]
    return ParseResult(rows=rows, errors=errors)


def build_whitelist_template() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "白名单"
    ws.append(["工号", "邮箱"])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def is_employee_allowed(db: AsyncSession, employee_no: str) -> bool:
    result = await db.execute(select(SsoUserWhitelistDB).where(
        SsoUserWhitelistDB.employee_no == employee_no,
        SsoUserWhitelistDB.enabled == True,
    ))
    return result.scalar_one_or_none() is not None


async def upsert_whitelist_entry(db: AsyncSession, employee_no: str, email: str | None, source: str, created_by: uuid.UUID | None):
    result = await db.execute(select(SsoUserWhitelistDB).where(SsoUserWhitelistDB.employee_no == employee_no))
    entry = result.scalar_one_or_none()
    if entry is None:
        entry = SsoUserWhitelistDB(employee_no=employee_no, email=email, enabled=True, source=source, created_by=created_by)
        db.add(entry)
        created = True
    else:
        entry.email = email
        entry.enabled = True
        entry.source = source
        created = False
    return entry, created
```

- [ ] **Step 3: 验证**

Run: `.venv/bin/python -m pytest tests/unit/test_whitelist_service.py -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/services/whitelist_service.py tests/unit/test_whitelist_service.py
git commit -m "feat(admin): add whitelist service and Excel parser"
```

---

## Task 4: 后端 admin API + router 注册

**Files:**
- Create: `app/api/v1/routes/admin.py`
- Modify: `app/api/v1/router.py`
- Test: `tests/integration/test_admin_whitelist_api.py`

- [ ] **Step 1: 写集成测试（依赖 override 管理员）**

```python
# tests/integration/test_admin_whitelist_api.py
import uuid
from fastapi.testclient import TestClient

import main
from app.api.deps import get_current_user, get_db, verify_csrf
from app.models.db_models import User


def _user(is_admin: bool):
    u = User(); u.id = uuid.uuid4(); u.email = "admin@example.com"; u.is_active = True; u.is_admin = is_admin
    return u


def test_admin_whitelist_requires_admin(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(False)
    resp = client.get("/api/v1/admin/whitelist")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin_required"


def test_admin_template_download(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    resp = client.get("/api/v1/admin/whitelist/template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
```

Run: `.venv/bin/python -m pytest tests/integration/test_admin_whitelist_api.py -q`
Expected: FAIL route missing.

- [ ] **Step 2: 创建 `admin.py`**

```python
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
from app.services.whitelist_service import build_whitelist_template, parse_whitelist_excel, upsert_whitelist_entry

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
        "id": str(e.id), "employee_no": e.employee_no, "email": e.email,
        "enabled": e.enabled, "source": e.source,
        "created_at": e.created_at.isoformat() if e.created_at else "",
        "updated_at": e.updated_at.isoformat() if e.updated_at else "",
    }


@router.get("/whitelist")
async def list_whitelist(db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    result = await db.execute(select(SsoUserWhitelistDB).order_by(SsoUserWhitelistDB.updated_at.desc()))
    return [_row(e) for e in result.scalars().all()]


@router.post("/whitelist")
async def add_whitelist(body: WhitelistCreateRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    employee_no = body.employee_no.strip()
    if not employee_no:
        raise HTTPException(status_code=400, detail="工号不能为空")
    entry, _created = await upsert_whitelist_entry(db, employee_no, body.email.strip() if body.email else None, "manual", admin.id)
    await db.commit(); await db.refresh(entry)
    return _row(entry)


@router.patch("/whitelist/{entry_id}")
async def patch_whitelist(entry_id: uuid.UUID, body: WhitelistPatchRequest, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
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
async def import_whitelist(file: UploadFile = File(...), db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")
    parsed = parse_whitelist_excel(await file.read())
    created = updated = 0
    for row in parsed.rows:
        entry, was_created = await upsert_whitelist_entry(db, row["employee_no"], row["email"], "excel", admin.id)
        created += 1 if was_created else 0
        updated += 0 if was_created else 1
    await db.commit()
    return {"created": created, "updated": updated, "skipped": len(parsed.errors), "errors": parsed.errors}
```

- [ ] **Step 3: 注册 router**

In `app/api/v1/router.py`:

```python
from app.api.v1.routes.admin import router as admin_router
...
api_v1_router.include_router(admin_router, dependencies=[Depends(verify_csrf)])
```

Place after chat/sessions and before auth/cas. `verify_csrf` no-ops for GET/template/list and protects POST/PATCH.

- [ ] **Step 4: 验证**

Run: `.venv/bin/python -m pytest tests/integration/test_admin_whitelist_api.py -q`
Expected: PASS for auth/template tests.

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/routes/admin.py app/api/v1/router.py tests/integration/test_admin_whitelist_api.py
git commit -m "feat(admin): add whitelist management API"
```

---

## Task 5: CAS exchange 白名单 gate + 管理员 bypass

**Files:**
- Modify: `app/api/v1/routes/cas.py`, `app/services/user_service.py`
- Test: `tests/unit/test_cas_whitelist_gate.py` (or extend existing `tests/integration/test_cas.py`)

- [ ] **Step 1: 写 service-level 测试（mock `is_employee_allowed`）**

Prefer extracting a small helper in `cas.py`:

```python
async def ensure_sso_allowed(db: AsyncSession, employee_no: str, is_admin_employee_no: bool) -> None:
    ...
```

Test:

```python
# tests/unit/test_cas_whitelist_gate.py
import pytest
from fastapi import HTTPException

from app.api.v1.routes.cas import ensure_sso_allowed


@pytest.mark.asyncio
async def test_admin_employee_bypasses_whitelist(monkeypatch):
    async def boom(db, employee_no):
        raise AssertionError("should not query whitelist")
    monkeypatch.setattr("app.api.v1.routes.cas.is_employee_allowed", boom)
    await ensure_sso_allowed(object(), "1001", True)


@pytest.mark.asyncio
async def test_non_whitelisted_employee_rejected(monkeypatch):
    async def deny(db, employee_no): return False
    monkeypatch.setattr("app.api.v1.routes.cas.is_employee_allowed", deny)
    with pytest.raises(HTTPException) as exc:
        await ensure_sso_allowed(object(), "1002", False)
    assert exc.value.status_code == 403
    assert exc.value.detail == "当前账号未开通岗标 AI 教练访问权限，请联系管理员开通。"
```

Run: `.venv/bin/python -m pytest tests/unit/test_cas_whitelist_gate.py -q`
Expected: FAIL helper missing.

- [ ] **Step 2: 实现 gate**

In `cas.py` imports:

```python
from app.core.config import settings, get_admin_employee_no_set
from app.services.whitelist_service import WHITELIST_DENY_MESSAGE, is_employee_allowed
```

Add helper:

```python
async def ensure_sso_allowed(db: AsyncSession, employee_no: str, is_admin_employee_no: bool) -> None:
    if is_admin_employee_no:
        return
    if await is_employee_allowed(db, employee_no):
        return
    raise HTTPException(status_code=403, detail=WHITELIST_DENY_MESSAGE)
```

In `cas_exchange`, after `validate_ticket` and before `upsert_sso_user`:

```python
    is_admin_employee_no = employee_no in get_admin_employee_no_set()
    await ensure_sso_allowed(db, employee_no, is_admin_employee_no)
```

Then update upsert call:

```python
    user = await upsert_sso_user(db, employee_no, attrs, is_admin=is_admin_employee_no)
```

- [ ] **Step 3: 验证**

Run:
```bash
.venv/bin/python -m pytest tests/unit/test_cas_whitelist_gate.py tests/unit/test_user_service_admin.py -q
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/routes/cas.py tests/unit/test_cas_whitelist_gate.py
git commit -m "feat(auth): gate SSO exchange by enabled whitelist"
```

---

## Task 6: `/me` 返回 `is_admin` + 前端类型

**Files:**
- Modify: `app/models/schema.py`, `app/api/v1/routes/auth.py`, `frontend/types/auth.ts`
- Test: update `tests/integration/test_auth.py`

- [ ] **Step 1: 后端类型与返回**

`UserResponse` add:

```python
    is_admin: bool
```

In `auth.py` `/me` response add:

```python
        is_admin=current_user.is_admin,
```

Also add `is_admin` in any `UserResponse(...)` construction if present (only `/me` currently).

- [ ] **Step 2: 前端类型**

`frontend/types/auth.ts`:

```ts
export interface UserInfo {
  id: string;
  email: string | null;
  nickname: string | null;
  is_active: boolean;
  is_admin: boolean;
  created_at: string;
}
```

- [ ] **Step 3: 测试**

In `tests/integration/test_auth.py`, in `test_me_with_session_cookie`, add:

```python
    assert data["is_admin"] is False
```

Run: `.venv/bin/python -m pytest tests/integration/test_auth.py -q`
Expected: skipped if no PG; at least schema import tests should catch via full suite. Also run `.venv/bin/python -m pytest tests/ -q`.

- [ ] **Step 4: Frontend type check**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS (may reveal places needing fallback; fix by checking `userInfo?.is_admin`).

- [ ] **Step 5: Commit**

```bash
git add app/models/schema.py app/api/v1/routes/auth.py frontend/types/auth.ts tests/integration/test_auth.py
git commit -m "feat(auth): include is_admin in current user response"
```

---

## Task 7: 前端 admin API client + types

**Files:**
- Create: `frontend/types/admin.ts`
- Create: `frontend/lib/admin.ts`

- [ ] **Step 1: 添加类型**

```ts
// frontend/types/admin.ts
export interface WhitelistEntry {
  id: string;
  employee_no: string;
  email: string | null;
  enabled: boolean;
  source: "manual" | "excel" | string;
  created_at: string;
  updated_at: string;
}

export interface ImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: { row: number; reason: string }[];
}
```

- [ ] **Step 2: 添加 API client**

```ts
// frontend/lib/admin.ts
import { getCsrfToken } from "./auth";
import type { ImportResult, WhitelistEntry } from "@/types/admin";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";
const endpoint = (path: string) => `${API_BASE}${path}`;

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {};
  const csrf = getCsrfToken();
  if (csrf) h["X-CSRF-Token"] = csrf;
  if (json) h["Content-Type"] = "application/json";
  return h;
}

async function adminFetch(path: string, options: RequestInit = {}) {
  const resp = await fetch(endpoint(path), { ...options, credentials: "include" });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败: ${resp.status}`);
  }
  return resp;
}

export async function listWhitelist(): Promise<WhitelistEntry[]> {
  return (await adminFetch("/api/v1/admin/whitelist", { cache: "no-store" })).json();
}

export async function addWhitelistEntry(employee_no: string, email?: string): Promise<WhitelistEntry> {
  return (await adminFetch("/api/v1/admin/whitelist", {
    method: "POST", headers: headers(), body: JSON.stringify({ employee_no, email: email || null }),
  })).json();
}

export async function setWhitelistEnabled(id: string, enabled: boolean): Promise<WhitelistEntry> {
  return (await adminFetch(`/api/v1/admin/whitelist/${id}`, {
    method: "PATCH", headers: headers(), body: JSON.stringify({ enabled }),
  })).json();
}

export async function importWhitelist(file: File): Promise<ImportResult> {
  const form = new FormData(); form.append("file", file);
  return (await adminFetch("/api/v1/admin/whitelist/import", {
    method: "POST", headers: headers(false), body: form,
  })).json();
}

export function whitelistTemplateUrl(): string {
  return endpoint("/api/v1/admin/whitelist/template");
}
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/types/admin.ts frontend/lib/admin.ts
git commit -m "feat(admin): add whitelist frontend API client"
```

---

## Task 8: 前端管理入口 + 管理页

**Files:**
- Modify: `frontend/app/page.tsx`
- Create: `frontend/app/admin/whitelist/page.tsx`
- Modify: `frontend/app/globals.css`

- [ ] **Step 1: Home user menu 仅 admin 展示入口**

In `frontend/app/page.tsx`, inside `.user-popover` before logout button:

```tsx
{userInfo?.is_admin ? (
  <button type="button" onClick={() => { window.location.href = "/admin/whitelist"; }}>
    白名单管理
  </button>
) : null}
```

- [ ] **Step 2: 创建管理页**

```tsx
// frontend/app/admin/whitelist/page.tsx
"use client";

import { FormEvent, useEffect, useState } from "react";
import { checkAuth } from "@/lib/auth";
import { addWhitelistEntry, importWhitelist, listWhitelist, setWhitelistEnabled, whitelistTemplateUrl } from "@/lib/admin";
import type { UserInfo } from "@/types/auth";
import type { ImportResult, WhitelistEntry } from "@/types/admin";

export default function WhitelistAdminPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [entries, setEntries] = useState<WhitelistEntry[]>([]);
  const [employeeNo, setEmployeeNo] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    checkAuth().then((u) => {
      setUser(u);
      if (u?.is_admin) refresh();
    });
  }, []);

  async function refresh() {
    try { setEntries(await listWhitelist()); } catch (e) { setError(formatError(e)); }
  }

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await addWhitelistEntry(employeeNo, email || undefined);
      setEmployeeNo(""); setEmail("");
      await refresh();
    } catch (e) { setError(formatError(e)); } finally { setBusy(false); }
  }

  async function onImport(file: File | null) {
    if (!file) return;
    setBusy(true); setError(""); setResult(null);
    try { setResult(await importWhitelist(file)); await refresh(); }
    catch (e) { setError(formatError(e)); }
    finally { setBusy(false); }
  }

  if (user && !user.is_admin) {
    return <main className="admin-page"><div className="admin-card"><h1>无权限访问</h1><button onClick={() => { window.location.href = "/"; }}>返回首页</button></div></main>;
  }

  return (
    <main className="admin-page">
      <div className="admin-card">
        <header className="admin-head"><h1>白名单管理</h1><button onClick={() => { window.location.href = "/"; }}>返回首页</button></header>
        <section className="admin-actions">
          <a className="secondary" href={whitelistTemplateUrl()}>下载模板</a>
          <label className="secondary">导入 Excel<input type="file" accept=".xlsx" hidden onChange={(e) => void onImport(e.target.files?.[0] || null)} disabled={busy} /></label>
          <form onSubmit={onAdd} className="admin-add-form">
            <input value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} placeholder="工号" required />
            <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="邮箱（可选）" />
            <button type="submit" disabled={busy}>添加</button>
          </form>
        </section>
        {result ? <div className="admin-result">新增 {result.created}，更新 {result.updated}，跳过 {result.skipped}</div> : null}
        {error ? <div className="auth-error">{error}</div> : null}
        <table className="admin-table"><thead><tr><th>工号</th><th>邮箱</th><th>来源</th><th>更新时间</th><th>启用</th></tr></thead><tbody>
          {entries.map((e) => <tr key={e.id}><td>{e.employee_no}</td><td>{e.email || "-"}</td><td>{e.source}</td><td>{e.updated_at}</td><td><input type="checkbox" checked={e.enabled} onChange={(ev) => void setWhitelistEnabled(e.id, ev.target.checked).then(refresh)} /></td></tr>)}
        </tbody></table>
      </div>
    </main>
  );
}

function formatError(err: unknown) { return err instanceof Error ? err.message : "请求失败"; }
```

- [ ] **Step 3: CSS**

Append to `globals.css`:

```css
.admin-page { min-height: 100vh; padding: 24px; background: var(--bg); }
.admin-card { max-width: 1080px; margin: 0 auto; background: #fff; border: 1px solid var(--line); border-radius: 16px; padding: 20px; }
.admin-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.admin-actions { display: grid; gap: 12px; margin: 16px 0; }
.admin-add-form { display: flex; gap: 8px; flex-wrap: wrap; }
.admin-add-form input { padding: 8px 10px; border: 1px solid var(--line-strong); border-radius: 8px; }
.admin-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.admin-table th, .admin-table td { border-bottom: 1px solid var(--line); padding: 10px; text-align: left; }
.admin-result { color: #0b6b3a; font-size: 13px; }
```

- [ ] **Step 4: 验证**

Run: `cd frontend && npx tsc --noEmit && npx next build`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx frontend/app/admin/whitelist/page.tsx frontend/app/globals.css
git commit -m "feat(admin): add whitelist management page"
```

---

## Task 9: Full verification + security review

- [ ] **Step 1: 后端完整测试**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 2: 前端构建**

Run: `cd frontend && npx tsc --noEmit && npx next build`
Expected: PASS.

- [ ] **Step 3: Manual E2E**

With a reachable PG:
1. Set `ADMIN_EMPLOYEE_NOS=<your employee no>` and login via SSO → `/auth/me` returns `is_admin=true`.
2. User menu shows 「白名单管理」.
3. Download template opens xlsx.
4. Add employee no manually → appears enabled.
5. Toggle off → SSO exchange for that employee returns 403 with Chinese message.
6. Toggle on → SSO exchange allowed.
7. Import xlsx with duplicate/empty rows → stats show created/updated/skipped/errors.
8. Non-admin account menu hides admin entry; direct `/admin/whitelist` shows no permission.

- [ ] **Step 4: Security review**

Use `everything-claude-code:security-reviewer` or `security-review` skill/agent to review:
- admin route authz
- upload parsing constraints
- CSRF on POST/PATCH/import
- no deletion endpoint
- no Excel file persistence

- [ ] **Step 5: Commit docs/test fixes if any**

Only if review finds changes.

---

## Self-Review

- Spec coverage: data model T1; config/admin init T2; parser/template T3; admin API T4; SSO gate T5; is_admin propagation T6; frontend API/types T7; frontend page/entry T8; verification/security T9.
- Placeholder scan: no TBD/TODO; all major code steps include concrete snippets.
- Type consistency: `employee_no`, `enabled`, `source`, `is_admin`, `ImportResult`, `WhitelistEntry` are consistent across backend/frontend.
- Known risk: admin API integration tests with `get_db=None` cannot exercise DB list/upsert; full DB tests depend on reachable PG. Plan uses unit tests for parsing/gate and E2E for DB path.
