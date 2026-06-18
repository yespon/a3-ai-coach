# Admin Panel UX Iterations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add (1) pagination + multi-dimensional filtering to the user management page, (2) an "AI 速览" button that summarizes a single conversation, and (3) a cross-module feedback system (chat-side submit + admin-side review).

**Architecture:** All three features live alongside the existing `/admin` panel. Stage 1 extends the existing `list_managed_users` API with offset pagination and six filter dimensions. Stage 2 introduces a new `conversation_summary_service` that calls the existing OpenAI-compatible LLM endpoint and adds a single new route. Stage 3 adds two new tables (`feedback_submissions`, `feedback_attachments`), a new service module, a new top-level router, a new chat-page popover entry, and two new admin pages.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic, PostgreSQL, openpyxl (unchanged), pytest, Next.js App Router, React 18, TypeScript.

**Reference Spec:** `docs/superpowers/specs/2026-06-18-admin-panel-ux-iterations-design.md`

---

## File Structure

### Stage 1 — User management (pagination + filtering)

Backend:
- Modify: `app/api/v1/routes/admin.py` — `list_managed_users` gains `page`, `page_size`, and five extra filter params; returns a `Page` envelope.
- Modify: `app/services/managed_user_service.py` — add `_build_managed_user_filtered_stmt(filters)` helper, plus constants for default/max page size.
- Create: `app/api/v1/_pagination.py` — `clamp_page_size`, `clamp_page`, `Page` dataclass.

Tests:
- Create: `tests/unit/test_admin_users_pagination.py` — pure-service tests for the filter builder (no DB; pure SQL string inspection using `stmt.compile(...)`).

Frontend:
- Modify: `frontend/types/admin.ts` — add `Paginated<T>`, `ManagedUserFilters`, `ManagedUserCoachFilter`, `ManagedUserHasEmail`.
- Modify: `frontend/lib/admin.ts` — `listManagedUsers` accepts filters and returns `Paginated<ManagedUser>`.
- Create: `frontend/components/admin/AdminPagination.tsx` — generic page-size-aware pagination control.
- Modify: `frontend/app/admin/users/page.tsx` — filter toolbar above stat grid, pagination control below table; `useEffect` reloads on filter/page/pageSize change.

### Stage 2 — AI 速览

Backend:
- Create: `app/services/conversation_summary_service.py` — `summarize_conversation(db, user, session_id, *, head_keep=5, tail_keep=25)`.
- Modify: `app/api/v1/routes/admin.py` — add `POST /api/v1/admin/conversations/sessions/{session_id}/summary`.
- Modify: `app/services/admin_conversation_service.py` — expose `_resolve_session_for_summary(db, user, session_id) -> ChatSessionDB` helper that the new service reuses for the same permission check as `get_conversation_session`.

Tests:
- Create: `tests/unit/test_conversation_summary_service.py` — patch `_call_llm`; assert short conversation sends all messages, long conversation sends head+tail with the system note; coach permission denied; admin allowed.

Frontend:
- Modify: `frontend/types/admin.ts` — add `ConversationSummary`.
- Modify: `frontend/lib/admin.ts` — add `summarizeConversation(sessionId)`.
- Modify: `frontend/app/admin/conversations/page.tsx` — add "AI 速览" button to dialog header; introduce `ConversationSummaryPanel`; reorganize right pane into summary + message list.

### Stage 3 — Feedback

Backend:
- Create: `alembic/versions/006_feedback_tables.py` — `feedback_submissions` + `feedback_attachments`.
- Modify: `app/models/db_models.py` — add `FeedbackSubmissionDB`, `FeedbackAttachmentDB`.
- Create: `app/services/feedback_service.py` — `create_feedback`, `list_feedback`, `get_feedback`, `mark_status`; constants `MAX_CONTENT_LEN=1000`, `MAX_ATTACHMENTS=5`, `MAX_ATTACHMENT_BYTES=3*1024*1024`, `ALLOWED_EXTS={".png",".jpg",".jpeg",".webp"}`.
- Create: `app/api/v1/routes/feedback.py` — public `POST /api/v1/feedback` (any logged-in user).
- Modify: `app/api/v1/routes/admin.py` — add admin feedback list/detail/patch routes (require_admin).
- Modify: `main.py` — mount `/uploads` as `StaticFiles(directory=UPLOAD_ROOT)` if not already; add explicit `/uploads/feedback/...` route that validates the requested path is inside `UPLOAD_ROOT/feedback/`.
- Modify: `app/api/v1/router.py` — include the new `feedback_router`.

Tests:
- Create: `tests/unit/test_feedback_service.py` — pure-service tests for the status-machine and pagination math (DB seam via in-memory SQLite or fakes — see Task 17 for the chosen pattern).

Frontend:
- Modify: `frontend/types/feedback.ts` (new) — `Feedback`, `FeedbackAttachment`, `FeedbackListItem`, `Paginated<FeedbackListItem>`, `FeedbackStatus`.
- Create: `frontend/lib/feedback.ts` — `submitFeedback`, `adminListFeedback`, `adminGetFeedback`, `adminPatchFeedbackStatus`.
- Create: `frontend/components/FeedbackDialog.tsx` — textarea (max 1000), image picker (max 5, single 3MB, png/jpg/webp), client-side pre-validate.
- Modify: `frontend/app/page.tsx` — popover adds "意见反馈" item, opens `FeedbackDialog`.
- Create: `frontend/app/admin/feedback/page.tsx` — list view with status tabs, search, `AdminPagination` reuse.
- Create: `frontend/app/admin/feedback/[id]/page.tsx` — detail view with status transitions.
- Modify: `frontend/app/admin/layout.tsx` — admin nav adds 意见反馈 between 用户管理 and 对话历史.
- Modify: `frontend/app/admin/page.tsx` — admin modules list adds 意见反馈.
- Modify: `frontend/app/globals.css` — `admin-summary-btn`, `admin-summary-panel`, `admin-conversation-pane` becomes `display:flex; flex-direction:column; gap:10px`; `admin-feedback-*` styles; small toast/banner style for submit success.

### Cross-cutting validation

- Backend unit: `uv run pytest tests/unit -q`
- Backend integration: `uv run pytest tests/integration -q`
- Frontend type check: `cd frontend && npx tsc --noEmit`
- Frontend build: `cd frontend && npm run build`
- Manual: see end of each stage.

---

## Stage 1 — User management: pagination + filtering

### Task 1: Add pagination helper module

**Files:**
- Create: `app/api/v1/_pagination.py`
- Test: covered indirectly by Tasks 2/3 (no separate test for pure clamp logic).

- [ ] **Step 1: Create `app/api/v1/_pagination.py`**

```python
"""Pagination helpers shared by API routes."""

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 30
MAX_PAGE_SIZE = 100


def clamp_page_size(value: int | None, *, default: int = DEFAULT_PAGE_SIZE, maximum: int = MAX_PAGE_SIZE) -> int:
    if value is None or value < 1:
        return default
    return min(value, maximum)


def clamp_page(value: int | None) -> int:
    if value is None or value < 1:
        return 1
    return value


@dataclass
class Page(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int
```

- [ ] **Step 2: Verify module imports cleanly**

Run: `uv run python -c "from app.api.v1._pagination import clamp_page_size, clamp_page, Page; print(clamp_page_size(0), clamp_page_size(500), clamp_page(-3))"`
Expected: `30 100 1`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/_pagination.py
git commit -m "feat(admin): add pagination helper module"
```

---

### Task 2: Add filter-builder + pagination to `list_managed_users`

**Files:**
- Modify: `app/services/managed_user_service.py` — add `_build_managed_user_filtered_stmt(filters)` helper and a `ManagedUserListFilters` dataclass.
- Modify: `app/api/v1/routes/admin.py` — `list_managed_users` accepts new query params, returns `Page`.
- Test: `tests/unit/test_admin_users_pagination.py`.

- [ ] **Step 1: Write failing unit test for filter builder**

Create `tests/unit/test_admin_users_pagination.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.models.db_models import ManagedUserDB
from app.services.managed_user_service import (
    ManagedUserListFilters,
    build_managed_user_filtered_stmt,
)


def _compile_where(stmt):
    compiled = stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled)


def test_filter_builder_text_query_matches_haystack():
    filters = ManagedUserListFilters(q="alice", role=None, enabled=None,
                                     coach_filter="all", department_level1=None, has_email=None)
    stmt = build_managed_user_filtered_stmt(filters)
    sql = _compile_where(stmt).lower()
    assert "lower(" in sql and "alice" in sql


def test_filter_builder_coach_filter_unassigned():
    filters = ManagedUserListFilters(q=None, role=None, enabled=None,
                                     coach_filter="unassigned", department_level1=None, has_email=None)
    stmt = build_managed_user_filtered_stmt(filters)
    sql = _compile_where(stmt).lower()
    assert "coach_id is null" in sql


def test_filter_builder_coach_filter_specific_id():
    cid = uuid.uuid4()
    filters = ManagedUserListFilters(q=None, role=None, enabled=None,
                                     coach_filter=str(cid), department_level1=None, has_email=None)
    stmt = build_managed_user_filtered_stmt(filters)
    sql = _compile_where(stmt)
    assert str(cid) in sql


def test_filter_builder_has_email_true():
    filters = ManagedUserListFilters(q=None, role=None, enabled=None,
                                     coach_filter="all", department_level1=None, has_email=True)
    stmt = build_managed_user_filtered_stmt(filters)
    sql = _compile_where(stmt).lower()
    assert "email is not null" in sql
```

- [ ] **Step 2: Run test to verify it fails (ImportError expected)**

Run: `uv run pytest tests/unit/test_admin_users_pagination.py -q`
Expected: `ImportError: cannot import name 'ManagedUserListFilters' from 'app.services.managed_user_service'`

- [ ] **Step 3: Add `ManagedUserListFilters` + `build_managed_user_filtered_stmt` to `app/services/managed_user_service.py`**

Append at the bottom of the file:

```python
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select


ManagedUserCoachFilter = Literal["all", "unassigned"] | str  # "all" | "unassigned" | "<uuid>"


@dataclass(slots=True)
class ManagedUserListFilters:
    q: str | None = None
    role: str | None = None
    enabled: bool | None = None
    coach_filter: str = "all"  # "all" | "unassigned" | "<uuid>"
    department_level1: str | None = None
    has_email: bool | None = None


def _haystack_columns() -> list:
    return [
        ManagedUserDB.employee_no,
        ManagedUserDB.name,
        ManagedUserDB.email,
        ManagedUserDB.department_level1,
    ]


def build_managed_user_filtered_stmt(filters: ManagedUserListFilters) -> Select:
    """Build a SELECT that already has WHERE applied; callers add LIMIT/OFFSET/ORDER BY."""
    stmt = select(ManagedUserDB).options(selectinload(ManagedUserDB.coach))
    if filters.role:
        stmt = stmt.where(ManagedUserDB.primary_role == filters.role)
    if filters.enabled is not None:
        stmt = stmt.where(ManagedUserDB.enabled.is_(filters.enabled))
    if filters.department_level1:
        stmt = stmt.where(ManagedUserDB.department_level1 == filters.department_level1)
    if filters.has_email is True:
        stmt = stmt.where(ManagedUserDB.email.is_not(None))
    elif filters.has_email is False:
        stmt = stmt.where(ManagedUserDB.email.is_(None))
    if filters.coach_filter == "unassigned":
        stmt = stmt.where(ManagedUserDB.coach_id.is_(None))
    elif filters.coach_filter not in (None, "all", ""):
        try:
            stmt = stmt.where(ManagedUserDB.coach_id == uuid.UUID(filters.coach_filter))
        except ValueError:
            # Invalid UUIDs are treated as "no match" — caller can decide to 400.
            stmt = stmt.where(False)
    if filters.q:
        needle = f"%{filters.q.strip().lower()}%"
        cols = [func.lower(func.cast(c, type_coerce=str)) for c in _haystack_columns()]
        stmt = stmt.where(or_(*[c.like(needle) for c in cols]))
    return stmt
```

Add `from sqlalchemy.orm import selectinload` if not already imported. Add `from sqlalchemy import type_coerce` if not imported.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_admin_users_pagination.py -q`
Expected: `4 passed`

- [ ] **Step 5: Update `list_managed_users` route in `app/api/v1/routes/admin.py`**

Replace the existing `list_managed_users` function with:

```python
@router.get("/users")
async def list_managed_users(
    page: int | None = None,
    page_size: int | None = None,
    q: str | None = None,
    role: str | None = None,
    enabled: bool | None = None,
    coach_filter: str = "all",
    department_level1: str | None = None,
    has_email: bool | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.api.v1._pagination import Page, clamp_page, clamp_page_size
    from app.services.managed_user_service import (
        ManagedUserListFilters,
        build_managed_user_filtered_stmt,
    )

    p = clamp_page(page)
    ps = clamp_page_size(page_size)
    filters = ManagedUserListFilters(
        q=q,
        role=role,
        enabled=enabled,
        coach_filter=coach_filter,
        department_level1=department_level1,
        has_email=has_email,
    )
    stmt = build_managed_user_filtered_stmt(filters)
    # Count BEFORE applying LIMIT/OFFSET, on a fresh select_from.
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    page_stmt = (
        stmt.order_by(ManagedUserDB.updated_at.desc(), ManagedUserDB.employee_no.asc())
        .limit(ps)
        .offset((p - 1) * ps)
    )
    rows = (await db.execute(page_stmt)).scalars().all()
    items = [_managed_user_row(e) for e in rows]
    return {"items": items, "page": p, "page_size": ps, "total": int(total)}
```

Make sure `from sqlalchemy import func` is imported in the route file (it already is, per Task 2/1 inspection).

- [ ] **Step 6: Commit**

```bash
git add app/services/managed_user_service.py app/api/v1/routes/admin.py tests/unit/test_admin_users_pagination.py
git commit -m "feat(admin): paginate and filter list_managed_users"
```

---

### Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/types/admin.ts` — add `Paginated<T>`, `ManagedUserFilters`, `ManagedUserCoachFilter`, `ManagedUserHasEmail`.
- Modify: `frontend/lib/admin.ts` — `listManagedUsers` accepts filters and returns `Paginated<ManagedUser>`.

- [ ] **Step 1: Append new types to `frontend/types/admin.ts`**

```ts
export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export type ManagedUserCoachFilter = "all" | "unassigned" | string; // "all" | "unassigned" | "<uuid>"

export type ManagedUserHasEmail = boolean | null;

export interface ManagedUserFilters {
  q?: string | null;
  role?: "admin" | "coach" | "student" | null;
  enabled?: boolean | null;
  coach_filter?: ManagedUserCoachFilter;
  department_level1?: string | null;
  has_email?: ManagedUserHasEmail;
}
```

- [ ] **Step 2: Update `listManagedUsers` in `frontend/lib/admin.ts`**

Replace:

```ts
export async function listManagedUsers(): Promise<ManagedUser[]> {
  return (await adminFetch("/api/v1/admin/users", { cache: "no-store" })).json();
}
```

With:

```ts
export async function listManagedUsers(
  filters: ManagedUserFilters = {},
  page = 1,
  pageSize = 30,
): Promise<Paginated<ManagedUser>> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  if (filters.role) params.set("role", filters.role);
  if (filters.enabled !== null && filters.enabled !== undefined) params.set("enabled", String(filters.enabled));
  if (filters.coach_filter && filters.coach_filter !== "all") params.set("coach_filter", filters.coach_filter);
  if (filters.department_level1?.trim()) params.set("department_level1", filters.department_level1.trim());
  if (filters.has_email === true || filters.has_email === false) params.set("has_email", String(filters.has_email));
  return (await adminFetch(`/api/v1/admin/users?${params.toString()}`, { cache: "no-store" })).json();
}
```

Add `Paginated, ManagedUserFilters, ManagedUserCoachFilter, ManagedUserHasEmail` to the existing type import at the top of the file.

- [ ] **Step 3: Verify type check passes**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output (success).

- [ ] **Step 4: Commit**

```bash
git add frontend/types/admin.ts frontend/lib/admin.ts
git commit -m "feat(admin-ui): paginated/filtered listManagedUsers client"
```

---

### Task 4: Add `AdminPagination` component

**Files:**
- Create: `frontend/components/admin/AdminPagination.tsx`
- Modify: `frontend/app/globals.css` — add `.admin-pagination` block.

- [ ] **Step 1: Create the component**

```tsx
"use client";

interface AdminPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  pageSizeOptions?: number[];
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  storageKey?: string; // localStorage key to persist page size
}

export default function AdminPagination({
  page,
  pageSize,
  total,
  pageSizeOptions = [10, 30, 50, 100],
  onPageChange,
  onPageSizeChange,
  storageKey,
}: AdminPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const canPrev = page > 1;
  const canNext = page < totalPages;

  function handlePageSizeChange(size: number) {
    onPageSizeChange(size);
    if (storageKey && typeof window !== "undefined") {
      window.localStorage.setItem(storageKey, String(size));
    }
  }

  return (
    <div className="admin-pagination">
      <span className="admin-pagination-info">
        共 {total} 条 · 第 {page} / {totalPages} 页
      </span>
      <button
        type="button"
        className="admin-button admin-button-muted"
        onClick={() => onPageChange(page - 1)}
        disabled={!canPrev}
      >
        上一页
      </button>
      <button
        type="button"
        className="admin-button admin-button-muted"
        onClick={() => onPageChange(page + 1)}
        disabled={!canNext}
      >
        下一页
      </button>
      <label className="admin-pagination-size">
        每页
        <select
          value={pageSize}
          onChange={(event) => handlePageSizeChange(Number(event.target.value))}
        >
          {pageSizeOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Add CSS to `frontend/app/globals.css`**

Append:

```css
.admin-pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 4px 0;
  color: #475569;
  font-size: 12px;
}

.admin-pagination-info {
  margin-right: 4px;
}

.admin-pagination-size {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

.admin-pagination-size select {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 4px 6px;
  font: inherit;
  background: #fff;
  color: #0f172a;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/admin/AdminPagination.tsx frontend/app/globals.css
git commit -m "feat(admin-ui): add AdminPagination component"
```

---

### Task 5: Wire toolbar + pagination into `/admin/users`

**Files:**
- Modify: `frontend/app/admin/users/page.tsx`
- Modify: `frontend/app/globals.css` — add `.admin-user-toolbar` block.

- [ ] **Step 1: Add toolbar styles**

Append to `frontend/app/globals.css`:

```css
.admin-user-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px;
  padding: 12px;
  border: 1px solid rgba(203, 213, 225, 0.85);
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.7);
}

.admin-user-toolbar label {
  display: grid;
  gap: 3px;
  color: #334155;
  font-size: 11px;
  font-weight: 700;
}

.admin-user-toolbar input,
.admin-user-toolbar select {
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 5px 8px;
  font-size: 12px;
  background: #fff;
  color: #0f172a;
  min-width: 120px;
}

.admin-user-toolbar input:focus,
.admin-user-toolbar select:focus {
  outline: none;
  border-color: #0ea5e9;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.16);
}

.admin-user-toolbar .admin-user-toolbar-spacer {
  flex: 1 1 auto;
}
```

- [ ] **Step 2: Refactor `frontend/app/admin/users/page.tsx`**

Replace the entire file with:

```tsx
"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import AdminPagination from "@/components/admin/AdminPagination";
import {
  createManagedUser,
  importManagedUsers,
  listCoachOptions,
  listManagedUsers,
  managedUsersTemplateUrl,
  updateManagedUser,
} from "@/lib/admin";
import type {
  CoachOption,
  ImportResult,
  ManagedUser,
  ManagedUserFilters,
  ManagedUserPayload,
  ManagedUserRole,
} from "@/types/admin";

const roleLabels: Record<ManagedUserRole, string> = {
  admin: "管理员",
  coach: "教练",
  student: "学员",
};

const emptyForm: ManagedUserPayload = {
  employee_no: "",
  name: "",
  email: "",
  department_level1: "",
  primary_role: "student",
  is_coach: false,
  coach_id: null,
  enabled: true,
};

const PAGE_SIZE_STORAGE = "admin.users.pageSize";
const PAGE_SIZE_OPTIONS = [10, 30, 50, 100] as const;

type RoleFilter = "all" | "admin" | "coach" | "student";
type EnabledFilter = "all" | "yes" | "no";
type EmailFilter = "all" | "yes" | "no";

function readPageSize(): number {
  if (typeof window === "undefined") return 30;
  const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE);
  if (!raw) return 30;
  const n = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(n as (typeof PAGE_SIZE_OPTIONS)[number]) ? n : 30;
}

export default function AdminUsersPage() {
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [coaches, setCoaches] = useState<CoachOption[]>([]);
  const [total, setTotal] = useState(0);
  const [form, setForm] = useState<ManagedUserPayload>(emptyForm);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  // Filters
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState<RoleFilter>("all");
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>("all");
  const [coachFilter, setCoachFilter] = useState<"all" | "unassigned" | string>("all");
  const [department, setDepartment] = useState("");
  const [emailFilter, setEmailFilter] = useState<EmailFilter>("all");

  // Pagination
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(30);

  useEffect(() => {
    setPageSize(readPageSize());
  }, []);

  useEffect(() => {
    void refresh();
    // We deliberately depend on the filter/page/pageSize values, not the helpers,
    // so any of those changing triggers a fresh fetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, roleFilter, enabledFilter, coachFilter, department, emailFilter, page, pageSize]);

  useEffect(() => {
    void listCoachOptions().then(setCoaches).catch(() => undefined);
  }, []);

  const coachChoices = useMemo(() => {
    if (!editingUser) return coaches;
    return coaches.filter((coach) => coach.id !== editingUser.id);
  }, [coaches, editingUser]);

  const stats = useMemo(() => {
    const admins = users.filter((user) => user.primary_role === "admin").length;
    const coachesCount = users.filter(
      (user) => user.primary_role === "coach" || user.is_coach,
    ).length;
    const students = users.filter((user) => user.primary_role === "student").length;
    return { total: users.length, admins, coaches: coachesCount, students };
  }, [users]);

  function buildFilters(): ManagedUserFilters {
    return {
      q: q.trim() || null,
      role: roleFilter === "all" ? null : roleFilter,
      enabled: enabledFilter === "all" ? null : enabledFilter === "yes",
      coach_filter: coachFilter,
      department_level1: department.trim() || null,
      has_email: emailFilter === "all" ? null : emailFilter === "yes",
    };
  }

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const result = await listManagedUsers(buildFilters(), page, pageSize);
      setUsers(result.items);
      setTotal(result.total);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setLoading(false);
    }
  }

  function resetFilters() {
    setQ("");
    setRoleFilter("all");
    setEnabledFilter("all");
    setCoachFilter("all");
    setDepartment("");
    setEmailFilter("all");
    setPage(1);
  }

  function changePage(next: number) {
    setPage(next);
  }

  function changePageSize(next: number) {
    setPageSize(next);
    setPage(1);
  }

  // The rest of the page (import, dialog, table) is unchanged from the previous
  // review, so we keep it identical below. Dialog / table open/close logic
  // continues to work because we only refactored the list-fetch path.

  function openCreateDialog() {
    setEditingUser(null);
    setForm(emptyForm);
    setDialogOpen(true);
    setImportResult(null);
    setNotice("");
    setError("");
  }

  function openEditDialog(user: ManagedUser) {
    setEditingUser(user);
    setForm({
      employee_no: user.employee_no,
      name: user.name || "",
      email: user.email || "",
      department_level1: user.department_level1 || "",
      primary_role: user.primary_role,
      is_coach: user.is_coach,
      coach_id: user.coach_id,
      enabled: user.enabled,
    });
    setDialogOpen(true);
    setImportResult(null);
    setNotice("");
    setError("");
  }

  function closeDialog() {
    if (busy) return;
    setDialogOpen(false);
    setEditingUser(null);
    setForm(emptyForm);
  }

  function updateForm<K extends keyof ManagedUserPayload>(key: K, value: ManagedUserPayload[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const payload = normalizePayload(form);
      if (editingUser) {
        await updateManagedUser(editingUser.id, payload);
        setNotice("用户信息已更新");
      } else {
        await createManagedUser(payload);
        setNotice("用户已创建");
      }
      setDialogOpen(false);
      setEditingUser(null);
      setForm(emptyForm);
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function onImport(file: File | null) {
    if (!file) return;
    setBusy(true);
    setError("");
    setNotice("");
    setImportResult(null);
    try {
      const result = await importManagedUsers(file);
      setImportResult(result);
      setNotice("批量导入已完成");
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled(user: ManagedUser, enabled: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await updateManagedUser(user.id, { enabled });
      await refresh();
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header">
        <div>
          <p className="admin-kicker">Managed Users</p>
          <h2>用户管理</h2>
          <p>统一维护账号角色、教练归属和可用状态，确保学员与教练关系清晰。</p>
        </div>
        <div className="admin-actions-row">
          <a className="admin-button admin-button-muted" href={managedUsersTemplateUrl()}>
            下载批量导入模板
          </a>
          <label className={`admin-button admin-button-muted ${busy ? "disabled" : ""}`}>
            上传并导入
            <input
              type="file"
              accept=".xlsx"
              hidden
              disabled={busy}
              onChange={(event) => void onImport(event.target.files?.[0] || null)}
            />
          </label>
          <button className="admin-button admin-button-primary" type="button" onClick={openCreateDialog}>
            添加用户
          </button>
        </div>
      </section>

      <section className="admin-stat-grid" aria-label="用户统计">
        <article className="admin-card admin-stat-card">
          <p className="admin-kicker">Total</p>
          <h3>{total}</h3>
          <p>命中条数</p>
        </article>
        <article className="admin-card admin-stat-card">
          <p className="admin-kicker">Admin</p>
          <h3>{stats.admins}</h3>
          <p>管理员(本页)</p>
        </article>
        <article className="admin-card admin-stat-card">
          <p className="admin-kicker">Coach</p>
          <h3>{stats.coaches}</h3>
          <p>教练(本页)</p>
        </article>
        <article className="admin-card admin-stat-card">
          <p className="admin-kicker">Student</p>
          <h3>{stats.students}</h3>
          <p>学员(本页)</p>
        </article>
      </section>

      <section className="admin-user-toolbar" aria-label="过滤">
        <label>
          关键词
          <input
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="工号 / 姓名 / 邮箱 / 部门"
          />
        </label>
        <label>
          主角色
          <select
            value={roleFilter}
            onChange={(event) => {
              setRoleFilter(event.target.value as RoleFilter);
              setPage(1);
            }}
          >
            <option value="all">全部</option>
            <option value="admin">管理员</option>
            <option value="coach">教练</option>
            <option value="student">学员</option>
          </select>
        </label>
        <label>
          启用状态
          <select
            value={enabledFilter}
            onChange={(event) => {
              setEnabledFilter(event.target.value as EnabledFilter);
              setPage(1);
            }}
          >
            <option value="all">全部</option>
            <option value="yes">已启用</option>
            <option value="no">已禁用</option>
          </select>
        </label>
        <label>
          所属教练
          <select
            value={coachFilter}
            onChange={(event) => {
              setCoachFilter(event.target.value);
              setPage(1);
            }}
          >
            <option value="all">全部</option>
            <option value="unassigned">未分配</option>
            {coaches.map((coach) => (
              <option key={coach.id} value={coach.id}>
                {coach.name || coach.employee_no}
                {coach.department_level1 ? ` · ${coach.department_level1}` : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          一级部门
          <input
            value={department}
            onChange={(event) => {
              setDepartment(event.target.value);
              setPage(1);
            }}
            placeholder="精确匹配"
          />
        </label>
        <label>
          邮箱
          <select
            value={emailFilter}
            onChange={(event) => {
              setEmailFilter(event.target.value as EmailFilter);
              setPage(1);
            }}
          >
            <option value="all">全部</option>
            <option value="yes">有邮箱</option>
            <option value="no">无邮箱</option>
          </select>
        </label>
        <div className="admin-user-toolbar-spacer" />
        <button
          type="button"
          className="admin-button admin-button-muted"
          onClick={resetFilters}
        >
          重置
        </button>
      </section>

      {importResult ? (
        <section className="admin-result-panel">
          <strong>导入完成</strong>
          <span>新增 {importResult.created}</span>
          <span>更新 {importResult.updated}</span>
          <span>跳过 {importResult.skipped}</span>
          {importResult.errors.length > 0 ? (
            <details>
              <summary>查看错误 {importResult.errors.length} 条</summary>
              <ul>
                {importResult.errors.map((item) => (
                  <li key={`${item.row}-${item.reason}`}>第 {item.row} 行：{item.reason}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ) : null}

      {notice ? <div className="admin-notice">{notice}</div> : null}
      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-card admin-table-card">
        <div className="admin-section-head">
          <div>
            <p className="admin-kicker">Directory</p>
            <h3>用户列表</h3>
          </div>
          <span className="admin-count">{users.length} 人</span>
        </div>

        {loading ? (
          <div className="admin-empty-state">正在加载用户数据...</div>
        ) : users.length === 0 ? (
          <div className="admin-empty-state">没有匹配的用户，试试调整过滤条件。</div>
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table managed-users-table">
              <thead>
                <tr>
                  <th>工号</th>
                  <th>姓名</th>
                  <th>邮箱</th>
                  <th>一级部门</th>
                  <th>主角色</th>
                  <th>兼任教练</th>
                  <th>所属教练</th>
                  <th>状态</th>
                  <th>更新时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.employee_no}</td>
                    <td>{user.name || "未填写"}</td>
                    <td>{user.email || "未填写"}</td>
                    <td>{user.department_level1 || "未填写"}</td>
                    <td>
                      <RoleBadge user={user} />
                    </td>
                    <td>{renderCoachCapability(user)}</td>
                    <td>{user.coach_name || "未指定"}</td>
                    <td>
                      <label className="admin-toggle">
                        <input
                          type="checkbox"
                          checked={user.enabled}
                          disabled={busy}
                          onChange={(event) => void toggleEnabled(user, event.target.checked)}
                        />
                        <span>{user.enabled ? "启用" : "禁用"}</span>
                      </label>
                    </td>
                    <td>{formatDate(user.updated_at)}</td>
                    <td>
                      <button
                        className="admin-link-button"
                        type="button"
                        onClick={() => openEditDialog(user)}
                        disabled={busy}
                      >
                        编辑
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <AdminPagination
          page={page}
          pageSize={pageSize}
          total={total}
          pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
          onPageChange={changePage}
          onPageSizeChange={changePageSize}
          storageKey={PAGE_SIZE_STORAGE}
        />
      </section>

      {dialogOpen ? (
        <div className="admin-dialog-backdrop" role="presentation" onClick={closeDialog}>
          <section
            className="admin-dialog"
            role="dialog"
            aria-modal="true"
            aria-label={editingUser ? "编辑用户" : "添加用户"}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="admin-dialog-head">
              <div>
                <p className="admin-kicker">{editingUser ? "Edit User" : "Add User"}</p>
                <h3>{editingUser ? "编辑用户信息" : "添加用户"}</h3>
                <p>
                  {editingUser
                    ? "仅支持修改角色、教练归属和状态"
                    : "录入单条用户信息；批量请使用页面顶部的「上传并导入」。"}
                </p>
              </div>
              <button className="admin-dialog-close" type="button" onClick={closeDialog} aria-label="关闭">
                ×
              </button>
            </div>

            {editingUser?.is_system_admin ? (
              <div className="admin-inline-warning">系统管理员账号不可修改工号、角色或启用状态。</div>
            ) : null}

            <form className="admin-user-form" onSubmit={onSubmit}>
              <div className="admin-form-grid">
                <label>
                  工号
                  <input
                    value={form.employee_no}
                    onChange={(event) => updateForm("employee_no", event.target.value)}
                    placeholder="请输入工号"
                    required
                    disabled={busy || Boolean(editingUser?.is_system_admin)}
                  />
                </label>
                <label>
                  姓名
                  <input
                    value={form.name || ""}
                    onChange={(event) => updateForm("name", event.target.value)}
                    placeholder="请输入姓名"
                    disabled={busy}
                  />
                </label>
                <label>
                  邮箱
                  <input
                    value={form.email || ""}
                    onChange={(event) => updateForm("email", event.target.value)}
                    placeholder="请输入邮箱"
                    type="email"
                    disabled={busy}
                  />
                </label>
                <label>
                  一级部门
                  <input
                    value={form.department_level1 || ""}
                    onChange={(event) => updateForm("department_level1", event.target.value)}
                    placeholder="请输入一级部门"
                    disabled={busy}
                  />
                </label>
                <label>
                  主角色
                  <select
                    value={form.primary_role}
                    onChange={(event) => updateForm("primary_role", event.target.value as ManagedUserRole)}
                    disabled={busy || Boolean(editingUser?.is_system_admin)}
                  >
                    {Object.entries(roleLabels).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
                {form.primary_role === "student" ? (
                  <label>
                    教练归属
                    <select
                      value={form.coach_id || ""}
                      onChange={(event) => updateForm("coach_id", event.target.value || null)}
                      disabled={busy}
                    >
                      <option value="">未指定</option>
                      {coachChoices.map((coach) => (
                        <option key={coach.id} value={coach.id}>
                          {coach.name || coach.employee_no}
                          {coach.department_level1 ? ` · ${coach.department_level1}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>

              <div className="admin-switch-row">
                {form.primary_role === "admin" ? (
                  <label className="admin-switch">
                    <input
                      type="checkbox"
                      checked={form.is_coach}
                      onChange={(event) => updateForm("is_coach", event.target.checked)}
                      disabled={busy}
                    />
                    <span>管理员兼任教练</span>
                  </label>
                ) : null}
                <label className="admin-switch">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(event) => updateForm("enabled", event.target.checked)}
                    disabled={busy || Boolean(editingUser?.is_system_admin)}
                  />
                  <span>启用账号</span>
                </label>
              </div>

              <div className="admin-dialog-actions">
                <button className="admin-button admin-button-muted" type="button" onClick={closeDialog} disabled={busy}>
                  取消
                </button>
                <button className="admin-button admin-button-primary" type="submit" disabled={busy}>
                  {editingUser ? "保存" : "添加用户"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}

function normalizePayload(payload: ManagedUserPayload): ManagedUserPayload {
  const normalizedRole = payload.primary_role;
  const normalizedCoachId = normalizedRole === "student" ? payload.coach_id || null : null;
  return {
    employee_no: payload.employee_no.trim(),
    name: emptyToNull(payload.name),
    email: emptyToNull(payload.email),
    department_level1: emptyToNull(payload.department_level1),
    primary_role: normalizedRole,
    is_coach: normalizedRole === "coach" ? true : normalizedRole === "admin" ? payload.is_coach : false,
    coach_id: normalizedCoachId,
    enabled: payload.enabled,
  };
}

function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

function emptyToNull(value: string | null | undefined): string | null {
  const trimmed = (value || "").trim();
  return trimmed ? trimmed : null;
}

function formatError(err: unknown) {
  return err instanceof Error ? err.message : "请求失败";
}

function RoleBadge({ user }: { user: ManagedUser }) {
  return (
    <>
      <span className="admin-pill">{roleLabels[user.primary_role]}</span>
      {user.is_system_admin ? <span className="admin-pill admin-pill-gold">系统管理员</span> : null}
    </>
  );
}

function renderCoachCapability(user: ManagedUser) {
  if (user.primary_role === "admin") {
    return user.is_coach ? (
      <span className="admin-pill admin-pill-green">是</span>
    ) : (
      <span>否</span>
    );
  }
  if (user.primary_role === "coach") {
    return <span className="admin-pill admin-pill-green">具备</span>;
  }
  return <span aria-label="不具备">—</span>;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Manual verification**

Start the backend (`uv run uvicorn main:app --port 2088`) and frontend (`cd frontend && npm run dev`).
1. With admin auth, navigate to `/admin/users`. Confirm the new toolbar appears above the stat grid and a pagination control below the table.
2. Type a keyword; the table reloads and the toolbar filters stay sticky across page changes.
3. Click a "所属教练" option — the result is filtered; pagination resets to 1.
4. Switch page size to 50; refresh; verify the next page load uses 50 and the choice persists in localStorage.
5. Reset filters; verify the table reverts.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/admin/users/page.tsx frontend/app/globals.css
git commit -m "feat(admin-ui): user management toolbar and pagination"
```

**End of Stage 1.** Move to Stage 2.

---

## Stage 2 — AI 速览

### Task 6: Conversation summary service + permission helper

**Files:**
- Modify: `app/services/admin_conversation_service.py` — add `resolve_session_for_summary`.
- Create: `app/services/conversation_summary_service.py`.
- Test: `tests/unit/test_conversation_summary_service.py`.

- [ ] **Step 1: Add `resolve_session_for_summary` to `app/services/admin_conversation_service.py`**

Append:

```python
async def resolve_session_for_summary(
    db: AsyncSession, user: User, session_id: uuid.UUID
) -> ChatSessionDB:
    """Same permission check as `get_conversation_session`, but returns the ORM row."""
    result = await db.execute(
        select(ChatSessionDB)
        .options(
            selectinload(ChatSessionDB.user).selectinload(User.managed_user),
            selectinload(ChatSessionDB.messages),
        )
        .where(ChatSessionDB.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="session_not_found")
    student = session.user.managed_user
    if student is None:
        raise HTTPException(status_code=404, detail="student_not_found")
    _require_conversation_access(user, student, "all" if is_admin_user(user) else "mine")
    return session
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_conversation_summary_service.py`:

```python
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


def _msg(role: str, content: str):
    return SimpleNamespace(role=role, content=content, created_at=None)


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
```

- [ ] **Step 3: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_conversation_summary_service.py -q`
Expected: ImportError on `app.services.conversation_summary_service`.

- [ ] **Step 4: Implement `app/services/conversation_summary_service.py`**

```python
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


def build_summary_prompt(messages: list[ChatMessageDB], sampled_count: int, total_count: int) -> str:
    """Render messages into a single user-prompt string."""
    if total_count > MAX_SAMPLED_MESSAGES:
        note = f"会话共 {total_count} 条,本次仅采样首 5 与末 25。"
    else:
        note = f"会话共 {total_count} 条。"
    rendered = "\n".join(
        f"[{idx + 1}] {msg.role}: {msg.content}" for idx, msg in enumerate(messages)
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
```

- [ ] **Step 5: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_conversation_summary_service.py -q`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/admin_conversation_service.py app/services/conversation_summary_service.py tests/unit/test_conversation_summary_service.py
git commit -m "feat(admin): conversation summary service"
```

---

### Task 7: Add summary route

**Files:**
- Modify: `app/api/v1/routes/admin.py` — register new endpoint.

- [ ] **Step 1: Add import + route**

In `app/api/v1/routes/admin.py`, add to the imports near the top:

```python
from app.services.conversation_summary_service import summarize_conversation
```

Append after the existing `admin_conversation_session` route:

```python
@router.post("/conversations/sessions/{session_id}/summary")
async def admin_conversation_session_summary(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await summarize_conversation(db, current_user, session_id)
    return {
        "summary": result.summary,
        "sampled_count": result.sampled_count,
        "total_count": result.total_count,
    }
```

- [ ] **Step 2: Type-check the imports**

Run: `uv run python -c "from app.api.v1.routes.admin import router; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/routes/admin.py
git commit -m "feat(admin): POST conversation summary endpoint"
```

---

### Task 8: Frontend types + API client for summary

**Files:**
- Modify: `frontend/types/admin.ts`
- Modify: `frontend/lib/admin.ts`

- [ ] **Step 1: Add `ConversationSummary` type**

In `frontend/types/admin.ts` append:

```ts
export interface ConversationSummary {
  summary: string;
  sampled_count: number;
  total_count: number;
}
```

- [ ] **Step 2: Add `summarizeConversation` client**

In `frontend/lib/admin.ts` add to the imports:

```ts
import type {
  ...,
  ConversationSummary,
} from "@/types/admin";
```

Append:

```ts
export async function summarizeConversation(sessionId: string): Promise<ConversationSummary> {
  return (
    await adminFetch(`/api/v1/admin/conversations/sessions/${sessionId}/summary`, {
      method: "POST",
    })
  ).json();
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/types/admin.ts frontend/lib/admin.ts
git commit -m "feat(admin-ui): summarizeConversation client"
```

---

### Task 9: Frontend dialog: AI 速览 button + summary panel

**Files:**
- Modify: `frontend/app/admin/conversations/page.tsx`
- Modify: `frontend/app/globals.css` — add `.admin-summary-btn`, `.admin-summary-panel` styles.

- [ ] **Step 1: Add CSS**

Append to `frontend/app/globals.css`:

```css
.admin-summary-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: #fff;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.admin-summary-btn:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #94a3b8;
  color: #0f172a;
}

.admin-summary-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.admin-conversation-pane {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 14px;
  background: #fff;
}

.admin-summary-panel {
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
  padding: 12px;
  display: grid;
  gap: 6px;
}

.admin-summary-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #0369a1;
  font-size: 12px;
  font-weight: 800;
}

.admin-summary-panel-body {
  color: #1e293b;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.admin-summary-panel-meta {
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
}

.admin-summary-panel-actions {
  display: inline-flex;
  gap: 6px;
}
```

- [ ] **Step 2: Add the button to the dialog header and a panel to the detail pane**

In `frontend/app/admin/conversations/page.tsx`, add to the imports:

```ts
import { summarizeConversation } from "@/lib/admin";
```

Inside `AdminConversationsPage` add these state hooks near the other useState calls:

```ts
const [summary, setSummary] = useState<{ summary: string; sampled_count: number; total_count: number } | null>(null);
const [summaryLoading, setSummaryLoading] = useState(false);
const [summaryError, setSummaryError] = useState("");
const [summaryCollapsed, setSummaryCollapsed] = useState(false);
```

Add a helper inside the component (right after `selectSession`):

```ts
async function runSummary() {
  if (!selectedSession) return;
  setSummaryLoading(true);
  setSummaryError("");
  setSummaryCollapsed(false);
  try {
    const result = await summarizeConversation(selectedSession.session_id);
    setSummary(result);
  } catch (err) {
    setSummaryError(formatError(err));
  } finally {
    setSummaryLoading(false);
  }
}
```

Modify the existing `selectSession` so it clears the summary state on session change:

```ts
async function selectSession(session: AdminSessionSummary) {
  setSelectedSession(session);
  setDetail(null);
  setSummary(null);
  setSummaryError("");
  setSummaryCollapsed(false);
  setLoadingDetail(true);
  setError("");
  try {
    const conversationDetail = await getConversationSession(session.session_id);
    setDetail(conversationDetail);
  } catch (err) {
    setError(formatError(err));
  } finally {
    setLoadingDetail(false);
  }
}
```

Update the dialog header JSX so the close button block contains the new AI 速览 button. Replace:

```tsx
              <button className="admin-dialog-close" type="button" onClick={closeDialog} aria-label="关闭">
                ×
              </button>
```

With:

```tsx
              <div className="admin-dialog-head-actions">
                <button
                  className="admin-summary-btn"
                  type="button"
                  onClick={() => void runSummary()}
                  disabled={!selectedSession || summaryLoading}
                  aria-label="AI 速览"
                >
                  ✨ AI 速览
                </button>
                <button className="admin-dialog-close" type="button" onClick={closeDialog} aria-label="关闭">
                  ×
                </button>
              </div>
```

Add a `admin-dialog-head-actions` style (append to the same CSS block):

```css
.admin-dialog-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
```

Update the right-hand `admin-conversation-pane` JSX. Replace the existing block that renders the message list with:

```tsx
              <section className="admin-conversation-pane">
                {!selectedSession ? (
                  <div className="admin-empty-state">请选择会话查看详情。</div>
                ) : (
                  <>
                    <ConversationSummarySection
                      summary={summary}
                      loading={summaryLoading}
                      error={summaryError}
                      collapsed={summaryCollapsed}
                      onToggle={() => setSummaryCollapsed((prev) => !prev)}
                      onRetry={() => void runSummary()}
                    />
                    {loadingDetail ? (
                      <div className="admin-empty-state">正在加载会话详情...</div>
                    ) : detail ? (
                      <div className="admin-detail-stack">
                        <div className="admin-detail-meta">
                          <span>{formatUserName(detail.student)}</span>
                          <span>创建：{formatDate(detail.created_at)}</span>
                          <span>更新：{formatDate(detail.updated_at)}</span>
                        </div>
                        <div className="admin-message-list" aria-label="会话消息">
                          {detail.history.length === 0 ? (
                            <div className="admin-empty-state">该会话暂无消息内容。</div>
                          ) : (
                            detail.history.map((message, index) => (
                              <ConversationMessage message={message} index={index} key={`${message.role}-${index}`} />
                            ))
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="admin-empty-state">暂无详情。</div>
                    )}
                  </>
                )}
              </section>
```

Append a new component at the bottom of the file (after the existing helpers):

```tsx
function ConversationSummarySection({
  summary,
  loading,
  error,
  collapsed,
  onToggle,
  onRetry,
}: {
  summary: { summary: string; sampled_count: number; total_count: number } | null;
  loading: boolean;
  error: string;
  collapsed: boolean;
  onToggle: () => void;
  onRetry: () => void;
}) {
  if (!summary && !loading && !error) {
    return (
      <div className="admin-empty-state" style={{ minHeight: 80 }}>
        点击右上角「AI 速览」生成此会话摘要。
      </div>
    );
  }
  return (
    <div className="admin-summary-panel">
      <div className="admin-summary-panel-head">
        <span>AI 速览</span>
        <div className="admin-summary-panel-actions">
          {summary ? (
            <button className="admin-link-button" type="button" onClick={onToggle}>
              {collapsed ? "展开" : "收起"}
            </button>
          ) : null}
          <button className="admin-link-button" type="button" onClick={onRetry} disabled={loading}>
            重新生成
          </button>
        </div>
      </div>
      {error ? <div className="admin-error">{error}</div> : null}
      {loading ? (
        <div className="admin-summary-panel-meta">正在生成速览...</div>
      ) : summary ? (
        <>
          {!collapsed ? (
            <div className="admin-summary-panel-body">{summary.summary}</div>
          ) : null}
          <div className="admin-summary-panel-meta">
            基于 {summary.sampled_count} / {summary.total_count} 条消息
          </div>
        </>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Manual verification**

1. As admin, open a student and a session. Confirm the new "✨ AI 速览" button is visible in the dialog header, to the left of ×.
2. Click the button; the panel appears above the message list with a loading state, then the summary text.
3. Click "重新生成"; the spinner appears, then a new summary text.
4. Click "收起"; the body hides but the meta line stays; click "展开" to bring it back.
5. Switch to another session; the panel clears back to its placeholder state.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/admin/conversations/page.tsx frontend/app/globals.css
git commit -m "feat(admin-ui): AI 速览 button and summary panel"
```

**End of Stage 2.** Move to Stage 3.

---

## Stage 3 — Feedback

### Task 10: Migration for feedback tables

**Files:**
- Create: `alembic/versions/006_feedback_tables.py`

- [ ] **Step 1: Create the migration file**

```python
"""feedback submissions + attachments

Revision ID: 006_feedback_tables
Revises: 005_managed_users
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID


revision: str = "006_feedback_tables"
down_revision: Union[str, Sequence[str], None] = "005_managed_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_submissions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'open'"), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("created_at", TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("read_at", TIMESTAMP(timezone=True), nullable=True),
        sa.Column("resolved_at", TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_feedback_submissions_user_id", "feedback_submissions", ["user_id"])
    op.create_index("ix_feedback_submissions_status", "feedback_submissions", ["status"])
    op.create_index("ix_feedback_submissions_created_at", "feedback_submissions", ["created_at"])

    op.create_table(
        "feedback_attachments",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("feedback_id", UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("saved_path", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(["feedback_id"], ["feedback_submissions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("feedback_id", "position", name="uq_feedback_attachments_feedback_position"),
    )
    op.create_index("ix_feedback_attachments_feedback_id", "feedback_attachments", ["feedback_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_attachments_feedback_id", table_name="feedback_attachments")
    op.drop_table("feedback_attachments")
    op.drop_index("ix_feedback_submissions_created_at", table_name="feedback_submissions")
    op.drop_index("ix_feedback_submissions_status", table_name="feedback_submissions")
    op.drop_index("ix_feedback_submissions_user_id", table_name="feedback_submissions")
    op.drop_table("feedback_submissions")
```

- [ ] **Step 2: Verify alembic sees the new revision**

Run: `uv run alembic heads`
Expected: `006_feedback_tables (head)`

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/006_feedback_tables.py
git commit -m "feat(feedback): add feedback submissions + attachments tables"
```

---

### Task 11: ORM models for feedback

**Files:**
- Modify: `app/models/db_models.py`

- [ ] **Step 1: Add new models at the end of the file**

Append:

```python
class FeedbackSubmissionDB(Base):
    __tablename__ = "feedback_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'open'"), index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("now()"), index=True
    )
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    attachments: Mapped[list["FeedbackAttachmentDB"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        order_by="FeedbackAttachmentDB.position",
    )


class FeedbackAttachmentDB(Base):
    __tablename__ = "feedback_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    feedback_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("feedback_submissions.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    saved_path: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    submission: Mapped["FeedbackSubmissionDB"] = relationship(back_populates="attachments")
```

- [ ] **Step 2: Verify imports cleanly**

Run: `uv run python -c "from app.models.db_models import FeedbackSubmissionDB, FeedbackAttachmentDB; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add app/models/db_models.py
git commit -m "feat(feedback): ORM models for feedback submissions and attachments"
```

---

### Task 12: Feedback service

**Files:**
- Create: `app/services/feedback_service.py`
- Test: `tests/unit/test_feedback_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_feedback_service.py`:

```python
import io
import uuid
from types import SimpleNamespace
from unittest.mock import patch

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
    monkeypatch.setattr(svc, "_persist_attachments", AsyncMock())  # never reached

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
```

Add `from unittest.mock import AsyncMock` to the imports.

- [ ] **Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/test_feedback_service.py -q`
Expected: ImportError.

- [ ] **Step 3: Implement `app/services/feedback_service.py`**

```python
"""Feedback submissions and admin moderation."""

from dataclasses import dataclass
from datetime import UTC, datetime
import os
import re
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, or_, select
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


class AsyncMock:  # placeholder; the real one lives in tests via unittest.mock
    pass


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
    # saved_path is stored relative to BASE_DIR; rebuild an /uploads/... URL.
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
    # open→read, read→resolved, read→open is not allowed, resolved→read allowed.
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
            raise HTTPException(status_code=413, detail=f"单张图片不能超过 3MB")
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

    submission = FeedbackSubmissionDB(
        user_id=user.id,
        content=text,
        status="open",
        user_agent=(user_agent or "")[:255] or None,
        ip=(ip or "")[:64] or None,
    )
    db.add(submission)
    await db.flush()  # populate submission.id

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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/unit/test_feedback_service.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/feedback_service.py tests/unit/test_feedback_service.py
git commit -m "feat(feedback): service with create/list/get/mark_status"
```

---

### Task 13: Public feedback route

**Files:**
- Create: `app/api/v1/routes/feedback.py`
- Modify: `app/api/v1/router.py`

- [ ] **Step 1: Create `app/api/v1/routes/feedback.py`**

```python
"""Public feedback endpoints — any logged-in user can submit."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.deps import get_current_user, get_db
from app.models.db_models import User
from app.services.feedback_service import create_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.post("")
async def submit_feedback(
    request: Request,
    content: Annotated[str, Form(...)],
    images: Annotated[list[UploadFile], File(...)] = [],
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    files = images or []
    submission = await create_feedback(
        db,
        current_user,
        content,
        files,
        user_agent=request.headers.get("user-agent"),
        ip=(request.client.host if request.client else None),
    )
    return {"id": str(submission.id), "created_at": submission.created_at.isoformat()}
```

- [ ] **Step 2: Wire the router into the v1 API**

In `app/api/v1/router.py`, add to the imports:

```python
from app.api.v1.routes.feedback import router as feedback_router
```

And add the include line alongside the others:

```python
api_v1_router.include_router(feedback_router, dependencies=[Depends(verify_csrf)])
```

- [ ] **Step 3: Verify the route is registered**

Run: `uv run python -c "from main import app; print([r.path for r in app.routes if '/feedback' in r.path])"`
Expected: `['/api/v1/feedback']` (or similar list including it).

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/routes/feedback.py app/api/v1/router.py
git commit -m "feat(feedback): public submit endpoint"
```

---

### Task 14: Admin feedback routes (list/detail/patch)

**Files:**
- Modify: `app/api/v1/routes/admin.py`

- [ ] **Step 1: Add the admin feedback endpoints**

In `app/api/v1/routes/admin.py`, add to the imports:

```python
from app.services.feedback_service import get_feedback, list_feedback, mark_status
```

Append at the end of the file:

```python
@router.get("/feedback")
async def admin_list_feedback(
    page: int | None = None,
    page_size: int | None = None,
    status: str = "all",
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    from app.api.v1._pagination import clamp_page, clamp_page_size
    items, total = await list_feedback(
        db,
        page=clamp_page(page),
        page_size=clamp_page_size(page_size),
        status=status,
        q=q,
    )
    return {
        "items": [
            {
                "id": str(item.id),
                "submitter": item.submitter,
                "content_excerpt": item.content_excerpt,
                "attachment_count": item.attachment_count,
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
        "page": clamp_page(page),
        "page_size": clamp_page_size(page_size),
        "total": total,
    }


@router.get("/feedback/{feedback_id}")
async def admin_get_feedback(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    submission = await get_feedback(db, feedback_id)
    profile = None
    if submission.user_id:
        user_row = await db.get(User, submission.user_id)
        if user_row and user_row.managed_user_id:
            from app.models.db_models import ManagedUserDB
            profile = await db.get(ManagedUserDB, user_row.managed_user_id)
    return {
        "id": str(submission.id),
        "submitter": {
            "employee_no": profile.employee_no if profile else None,
            "name": profile.name if profile else None,
            "email": profile.email if profile else None,
            "department_level1": profile.department_level1 if profile else None,
            "primary_role": profile.primary_role if profile else None,
        },
        "content": submission.content,
        "status": submission.status,
        "user_agent": submission.user_agent,
        "ip": submission.ip,
        "created_at": submission.created_at.isoformat() if submission.created_at else None,
        "read_at": submission.read_at.isoformat() if submission.read_at else None,
        "resolved_at": submission.resolved_at.isoformat() if submission.resolved_at else None,
        "attachments": [
            {
                "id": str(att.id),
                "filename": att.filename,
                "content_type": att.content_type,
                "size": att.size,
                "url": build_attachment_url(att.saved_path),
            }
            for att in submission.attachments
        ],
    }


class FeedbackPatchRequest(BaseModel):
    status: str


@router.patch("/feedback/{feedback_id}")
async def admin_patch_feedback(
    feedback_id: uuid.UUID,
    body: FeedbackPatchRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    submission = await mark_status(db, feedback_id, body.status)
    return {"id": str(submission.id), "status": submission.status}
```

- [ ] **Step 2: Verify routes are registered**

Run: `uv run python -c "from main import app; paths = sorted(r.path for r in app.routes if '/feedback' in r.path); print('\n'.join(paths))"`
Expected: at least 4 paths under `/api/v1`:
- `/api/v1/feedback`
- `/api/v1/admin/feedback`
- `/api/v1/admin/feedback/{feedback_id}`

- [ ] **Step 3: Commit**

```bash
git add app/api/v1/routes/admin.py
git commit -m "feat(admin): feedback list/detail/patch endpoints"
```

---

### Task 15: Mount `/uploads/feedback` static serving with path validation

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Read the current mounts in `main.py`**

Look for the existing `app.mount(...)` calls (search for `app.mount` and `StaticFiles`). We need to know whether `/uploads` is already mounted.

- [ ] **Step 2: Add a constrained mount**

If `/uploads` is NOT already mounted, add (near the other `app.include_router` calls):

```python
from fastapi.staticfiles import StaticFiles

# Serve only the feedback subdirectory; reject anything else via custom validation below.
app.mount("/uploads/feedback", StaticFiles(directory=str(UPLOAD_ROOT / "feedback")), name="feedback_uploads")
```

If `/uploads` IS already mounted, do not mount again. Instead, add a guard at the top of the file (or in a new `app/middleware/path_guard.py`) to ensure any path under `/uploads/...` not starting with `/uploads/feedback/...` returns 404.

A simpler approach is to add a FastAPI route that handles the prefix manually:

```python
from fastapi.responses import FileResponse
from fastapi import HTTPException
from pathlib import Path


@app.get("/uploads/{rest_of_path:path}")
async def serve_upload(rest_of_path: str):
    if not rest_of_path.startswith("feedback/"):
        raise HTTPException(status_code=404, detail="not_found")
    target = (UPLOAD_ROOT / rest_of_path).resolve()
    feedback_root = (UPLOAD_ROOT / "feedback").resolve()
    if feedback_root not in target.parents and target != feedback_root:
        raise HTTPException(status_code=404, detail="not_found")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not_found")
    return FileResponse(str(target))
```

Add the import `from app.core.config import UPLOAD_ROOT` (it already exists in `app/core/config.py`).

Pick exactly one of the two approaches based on the current state of `main.py`. If you do the route approach, do NOT also `app.mount(...)` (it would conflict).

- [ ] **Step 3: Manual smoke**

After restarting, `curl -I http://localhost:2088/uploads/feedback/<id>/<file>` should return 200 for a real file, and 404 for `/uploads/anything-else`.

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(feedback): serve feedback uploads under /uploads/feedback only"
```

---

### Task 16: Frontend types + lib for feedback

**Files:**
- Create: `frontend/types/feedback.ts`
- Create: `frontend/lib/feedback.ts`

- [ ] **Step 1: Create the types file**

```ts
import type { Paginated } from "./admin";

export type FeedbackStatus = "open" | "read" | "resolved";

export interface FeedbackAttachment {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  url: string;
}

export interface FeedbackSubmitter {
  employee_no: string | null;
  name: string | null;
  email: string | null;
  department_level1?: string | null;
  primary_role?: "admin" | "coach" | "student" | null;
}

export interface FeedbackListItem {
  id: string;
  submitter: FeedbackSubmitter;
  content_excerpt: string;
  attachment_count: number;
  status: FeedbackStatus;
  created_at: string;
}

export interface FeedbackDetail {
  id: string;
  submitter: FeedbackSubmitter;
  content: string;
  status: FeedbackStatus;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  read_at: string | null;
  resolved_at: string | null;
  attachments: FeedbackAttachment[];
}

export interface FeedbackFilters {
  status?: "all" | FeedbackStatus;
  q?: string | null;
}

export type PaginatedFeedbackList = Paginated<FeedbackListItem>;
```

- [ ] **Step 2: Create the lib file**

```ts
import { getCsrfToken } from "./auth";
import type {
  FeedbackDetail,
  FeedbackFilters,
  FeedbackStatus,
  PaginatedFeedbackList,
} from "@/types/feedback";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") || "";

function jsonHeaders(): HeadersInit {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const csrf = getCsrfToken();
  if (csrf) h["X-CSRF-Token"] = csrf;
  return h;
}

async function send<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: { ...(options.headers || {}), ...jsonHeaders() },
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `请求失败: ${resp.status}`);
  }
  return resp.json();
}

export async function submitFeedback(content: string, images: File[]): Promise<{ id: string; created_at: string }> {
  const form = new FormData();
  form.append("content", content);
  for (const img of images) {
    form.append("images", img);
  }
  const csrf = getCsrfToken();
  const resp = await fetch(`${API_BASE}/api/v1/feedback`, {
    method: "POST",
    credentials: "include",
    headers: csrf ? { "X-CSRF-Token": csrf } : undefined,
    body: form,
  });
  if (!resp.ok) {
    const data = await resp.json().catch(() => ({}));
    throw new Error(data.detail || `提交失败: ${resp.status}`);
  }
  return resp.json();
}

export async function adminListFeedback(
  filters: FeedbackFilters = {},
  page = 1,
  pageSize = 30,
): Promise<PaginatedFeedbackList> {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  if (filters.status && filters.status !== "all") params.set("status", filters.status);
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  return send(`/api/v1/admin/feedback?${params.toString()}`);
}

export async function adminGetFeedback(id: string): Promise<FeedbackDetail> {
  return send(`/api/v1/admin/feedback/${id}`);
}

export async function adminPatchFeedbackStatus(id: string, status: FeedbackStatus): Promise<void> {
  await send(`/api/v1/admin/feedback/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/types/feedback.ts frontend/lib/feedback.ts
git commit -m "feat(feedback): frontend types and lib"
```

---

### Task 17: `FeedbackDialog` component

**Files:**
- Create: `frontend/components/FeedbackDialog.tsx`
- Modify: `frontend/app/globals.css` — add `.feedback-dialog-*` styles.

- [ ] **Step 1: Add styles**

Append to `frontend/app/globals.css`:

```css
.feedback-dialog-form {
  display: grid;
  gap: 12px;
}

.feedback-dialog-textarea {
  width: 100%;
  min-height: 120px;
  resize: vertical;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  padding: 10px 12px;
  font: inherit;
  color: #0f172a;
  background: #fff;
}

.feedback-dialog-textarea:focus {
  outline: none;
  border-color: #0ea5e9;
  box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.16);
}

.feedback-dialog-counter {
  font-size: 11px;
  color: #64748b;
  text-align: right;
}

.feedback-dialog-uploader {
  display: grid;
  gap: 8px;
}

.feedback-dialog-uploader-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.feedback-dialog-file-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px dashed #cbd5e1;
  border-radius: 999px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.feedback-dialog-thumbnails {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.feedback-dialog-thumb {
  position: relative;
  width: 64px;
  height: 64px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  overflow: hidden;
  background: #f1f5f9;
}

.feedback-dialog-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.feedback-dialog-thumb-remove {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  border: none;
  border-radius: 50%;
  background: rgba(15, 23, 42, 0.7);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
}

.feedback-dialog-toast {
  margin-top: 4px;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  background: #dcfce7;
  color: #166534;
  border: 1px solid #86efac;
}
```

- [ ] **Step 2: Create the component**

```tsx
"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { submitFeedback } from "@/lib/feedback";

const MAX_IMAGES = 5;
const MAX_BYTES_PER_IMAGE = 3 * 1024 * 1024;
const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_CONTENT = 1000;

interface FeedbackDialogProps {
  open: boolean;
  onClose: () => void;
}

export default function FeedbackDialog({ open, onClose }: FeedbackDialogProps) {
  const [content, setContent] = useState("");
  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [toast, setToast] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      setContent("");
      images.forEach((_, idx) => URL.revokeObjectURL(previews[idx] || ""));
      setImages([]);
      setPreviews([]);
      setError("");
      setToast("");
      setSubmitting(false);
    }
    // We deliberately only reset on open→close; the cleanup runs unconditionally.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const trimmed = content.trim();
  const canSubmit = !submitting && trimmed.length >= 1 && trimmed.length <= MAX_CONTENT && images.length <= MAX_IMAGES;

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(event.target.files || []);
    if (!picked.length) return;
    const valid: File[] = [];
    let localError = "";
    for (const file of picked) {
      if (!ALLOWED_TYPES.includes(file.type)) {
        localError = `已忽略非图片文件 ${file.name}`;
        continue;
      }
      if (file.size > MAX_BYTES_PER_IMAGE) {
        localError = `已忽略过大文件 ${file.name} (单张不能超过 3MB)`;
        continue;
      }
      valid.push(file);
    }
    setError(localError);
    setImages((prev) => {
      const next = [...prev, ...valid].slice(0, MAX_IMAGES);
      setPreviews(next.map((f) => URL.createObjectURL(f)));
      return next;
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeImage(idx: number) {
    setImages((prev) => {
      const next = prev.filter((_, i) => i !== idx);
      setPreviews(next.map((f) => URL.createObjectURL(f)));
      return next;
    });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError("");
    try {
      await submitFeedback(trimmed, images);
      setToast("感谢你的反馈,我们已收到");
      setTimeout(() => onClose(), 600);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="admin-dialog-backdrop" role="presentation" onClick={onClose}>
      <section
        className="admin-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="意见反馈"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="admin-dialog-head">
          <div>
            <p className="admin-kicker">Feedback</p>
            <h3>意见反馈</h3>
            <p>告诉我们你遇到的问题或建议。最多可附 5 张图(单张 3MB 内)。</p>
          </div>
          <button className="admin-dialog-close" type="button" onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        {toast ? <div className="feedback-dialog-toast">{toast}</div> : null}
        {error ? <div className="admin-error">{error}</div> : null}

        <form className="feedback-dialog-form" onSubmit={onSubmit}>
          <textarea
            className="feedback-dialog-textarea"
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="说说你遇到的问题或建议…"
            maxLength={MAX_CONTENT}
          />
          <div className="feedback-dialog-counter">
            {trimmed.length} / {MAX_CONTENT}
          </div>

          <div className="feedback-dialog-uploader">
            <div className="feedback-dialog-uploader-row">
              <label className="feedback-dialog-file-button">
                添加图片 ({images.length} / {MAX_IMAGES})
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  multiple
                  hidden
                  onChange={handleFileChange}
                />
              </label>
            </div>
            {previews.length > 0 ? (
              <div className="feedback-dialog-thumbnails">
                {previews.map((src, idx) => (
                  <div className="feedback-dialog-thumb" key={src}>
                    <img src={src} alt={`附件 ${idx + 1}`} />
                    <button
                      type="button"
                      className="feedback-dialog-thumb-remove"
                      onClick={() => removeImage(idx)}
                      aria-label={`删除附件 ${idx + 1}`}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>

          <div className="admin-dialog-actions">
            <button
              type="button"
              className="admin-button admin-button-muted"
              onClick={onClose}
              disabled={submitting}
            >
              取消
            </button>
            <button
              type="submit"
              className="admin-button admin-button-primary"
              disabled={!canSubmit}
            >
              {submitting ? "提交中…" : "提交"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/FeedbackDialog.tsx frontend/app/globals.css
git commit -m "feat(feedback): FeedbackDialog component"
```

---

### Task 18: Wire popover entry on chat page

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: Add the dialog state and import**

In `frontend/app/page.tsx`, add to the imports:

```tsx
import FeedbackDialog from "@/components/FeedbackDialog";
```

Inside `HomePage`, add a new state near the other useState calls:

```tsx
const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
```

- [ ] **Step 2: Add a new menu item to the popover**

Locate the existing `user-popover` block (around the existing "管理后台" / "退出登录" buttons) and add a new button between them:

```tsx
<button
  type="button"
  onClick={() => {
    setShowUserMenu(false);
    setShowFeedbackDialog(true);
  }}
>
  意见反馈
</button>
```

- [ ] **Step 3: Render the dialog at the bottom of the component**

Just before the closing `</main>` of `HomePage`, add:

```tsx
<FeedbackDialog open={showFeedbackDialog} onClose={() => setShowFeedbackDialog(false)} />
```

- [ ] **Step 4: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 5: Manual verification**

1. Open `/` while logged in. Click the "⋮" trigger in the sidebar user bar. Confirm "意见反馈" is now a menu item.
2. Click it; the dialog opens.
3. Type 999 chars, attach 4 images, submit; confirm the toast appears and the dialog closes after 600ms.
4. Try attaching a 4MB file; the client refuses it (no upload fires, error message shows).
5. Try a .gif file; the client refuses it.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(chat): add 意见反馈 popover entry"
```

---

### Task 19: Admin feedback list page

**Files:**
- Create: `frontend/app/admin/feedback/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import AdminPagination from "@/components/admin/AdminPagination";
import { adminListFeedback } from "@/lib/feedback";
import { checkAuth } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";
import type { FeedbackListItem, FeedbackStatus } from "@/types/feedback";

const PAGE_SIZE_STORAGE = "admin.feedback.pageSize";
const PAGE_SIZE_OPTIONS = [10, 30, 50, 100] as const;
type StatusFilter = "all" | FeedbackStatus;

function readPageSize(): number {
  if (typeof window === "undefined") return 30;
  const raw = window.localStorage.getItem(PAGE_SIZE_STORAGE);
  if (!raw) return 30;
  const n = Number(raw);
  return PAGE_SIZE_OPTIONS.includes(n as (typeof PAGE_SIZE_OPTIONS)[number]) ? n : 30;
}

const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "全部",
  open: "未读",
  read: "已读",
  resolved: "已处理",
};

export default function AdminFeedbackPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [items, setItems] = useState<FeedbackListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [status, setStatus] = useState<StatusFilter>("all");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void checkAuth().then(setUser);
    setPageSize(readPageSize());
  }, []);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, q, page, pageSize]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const data = await adminListFeedback({ status, q: q.trim() || null }, page, pageSize);
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  const counts = useMemo(() => {
    const acc: Record<StatusFilter, number> = { all: total, open: 0, read: 0, resolved: 0 };
    for (const item of items) {
      acc[item.status] += 1;
    }
    return acc;
  }, [items, total]);

  if (user && !user.is_admin) {
    return (
      <div className="admin-page-stack">
        <div className="admin-error">仅管理员可访问意见反馈模块。</div>
      </div>
    );
  }

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header">
        <div>
          <p className="admin-kicker">Feedback Inbox</p>
          <h2>意见反馈</h2>
          <p>查看用户提交的意见与建议,支持状态流转与附件预览。</p>
        </div>
      </section>

      <section className="admin-stat-grid" aria-label="反馈统计">
        {(["all", "open", "read", "resolved"] as StatusFilter[]).map((key) => (
          <article className="admin-card admin-stat-card" key={key}>
            <p className="admin-kicker">{STATUS_LABELS[key]}</p>
            <h3>{counts[key]}</h3>
            <p>{key === "all" ? "总数" : "本页"}</p>
          </article>
        ))}
      </section>

      <section className="admin-user-toolbar" aria-label="过滤">
        <label>
          关键词
          <input
            value={q}
            onChange={(event) => {
              setQ(event.target.value);
              setPage(1);
            }}
            placeholder="按内容搜索"
          />
        </label>
      </section>

      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-card admin-table-card">
        <div className="admin-section-head">
          <div className="admin-segmented" role="group" aria-label="状态过滤">
            {(["all", "open", "read", "resolved"] as StatusFilter[]).map((key) => (
              <button
                key={key}
                type="button"
                className={status === key ? "active" : ""}
                onClick={() => {
                  setStatus(key);
                  setPage(1);
                }}
              >
                {STATUS_LABELS[key]}
              </button>
            ))}
          </div>
          <span className="admin-count">{items.length} 条</span>
        </div>

        {loading ? (
          <div className="admin-empty-state">正在加载反馈数据…</div>
        ) : items.length === 0 ? (
          <div className="admin-empty-state">没有匹配的反馈。</div>
        ) : (
          <div className="admin-table-wrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>提交时间</th>
                  <th>提交人</th>
                  <th>摘要</th>
                  <th>附件</th>
                  <th>状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>{formatDate(item.created_at)}</td>
                    <td>
                      {item.submitter.name || "未填写"}
                      <br />
                      <small style={{ color: "#94a3b8" }}>{item.submitter.employee_no || "—"}</small>
                    </td>
                    <td>{item.content_excerpt}</td>
                    <td>{item.attachment_count}</td>
                    <td>
                      <span className={statusBadgeClass(item.status)}>{STATUS_LABELS[item.status]}</span>
                    </td>
                    <td>
                      <Link className="admin-link-button" href={`/admin/feedback/${item.id}`}>
                        查看
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <AdminPagination
          page={page}
          pageSize={pageSize}
          total={total}
          pageSizeOptions={[...PAGE_SIZE_OPTIONS]}
          onPageChange={setPage}
          onPageSizeChange={(size) => {
            setPageSize(size);
            setPage(1);
            if (typeof window !== "undefined") {
              window.localStorage.setItem(PAGE_SIZE_STORAGE, String(size));
            }
          }}
          storageKey={PAGE_SIZE_STORAGE}
        />
      </section>
    </div>
  );
}

function statusBadgeClass(status: FeedbackStatus) {
  if (status === "open") return "admin-pill admin-pill-gold";
  if (status === "resolved") return "admin-pill admin-pill-green";
  return "admin-pill";
}

function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/feedback/page.tsx
git commit -m "feat(admin-ui): feedback list page"
```

---

### Task 20: Admin feedback detail page

**Files:**
- Create: `frontend/app/admin/feedback/[id]/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { adminGetFeedback, adminPatchFeedbackStatus } from "@/lib/feedback";
import { checkAuth } from "@/lib/auth";
import type { UserInfo } from "@/types/auth";
import type { FeedbackDetail, FeedbackStatus } from "@/types/feedback";

const STATUS_LABELS: Record<FeedbackStatus, string> = {
  open: "未读",
  read: "已读",
  resolved: "已处理",
};

export default function AdminFeedbackDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [user, setUser] = useState<UserInfo | null>(null);
  const [detail, setDetail] = useState<FeedbackDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void checkAuth().then(setUser);
  }, []);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const data = await adminGetFeedback(id);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  async function transitionStatus(target: FeedbackStatus) {
    setBusy(true);
    setError("");
    try {
      await adminPatchFeedbackStatus(id, target);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  if (user && !user.is_admin) {
    return <div className="admin-error">仅管理员可访问。</div>;
  }

  if (loading) {
    return <div className="admin-empty-state">正在加载反馈详情…</div>;
  }

  if (!detail) {
    return <div className="admin-error">{error || "未找到该反馈。"}</div>;
  }

  const submitter = detail.submitter;

  return (
    <div className="admin-page-stack">
      <section className="admin-page-header">
        <div>
          <p className="admin-kicker">Feedback Detail</p>
          <h2>反馈详情</h2>
          <p>查看完整内容、提交人信息与附件,根据需要切换状态。</p>
        </div>
        <Link className="admin-button admin-button-muted" href="/admin/feedback">
          返回列表
        </Link>
      </section>

      {error ? <div className="admin-error">{error}</div> : null}

      <section className="admin-card">
        <div className="admin-detail-meta" style={{ marginBottom: 8 }}>
          <span>提交时间: {formatDate(detail.created_at)}</span>
          <span>状态: {STATUS_LABELS[detail.status]}</span>
          {detail.read_at ? <span>已读: {formatDate(detail.read_at)}</span> : null}
          {detail.resolved_at ? <span>已处理: {formatDate(detail.resolved_at)}</span> : null}
        </div>
        <div className="admin-detail-meta" style={{ marginBottom: 16 }}>
          <span>IP: {detail.ip || "未记录"}</span>
          <span>UA: {detail.user_agent || "未记录"}</span>
        </div>
        <div className="admin-card" style={{ background: "rgba(241,245,249,0.6)" }}>
          <p className="admin-kicker">Submitter</p>
          <p>
            {submitter.name || "未填写"} ({submitter.employee_no || "无工号"})
            <br />
            {submitter.email || "—"}
            {submitter.department_level1 ? ` · ${submitter.department_level1}` : ""}
            {submitter.primary_role ? ` · ${submitter.primary_role}` : ""}
          </p>
        </div>
      </section>

      <section className="admin-card">
        <p className="admin-kicker">Content</p>
        <pre className="admin-feedback-content">{detail.content}</pre>
      </section>

      {detail.attachments.length > 0 ? (
        <section className="admin-card">
          <p className="admin-kicker">Attachments</p>
          <div className="feedback-dialog-thumbnails">
            {detail.attachments.map((att) => (
              <a key={att.id} href={att.url} target="_blank" rel="noreferrer" className="feedback-dialog-thumb">
                <img src={att.url} alt={att.filename} />
              </a>
            ))}
          </div>
        </section>
      ) : null}

      <section className="admin-card">
        <div className="admin-dialog-actions">
          {detail.status === "open" ? (
            <button
              className="admin-button admin-button-muted"
              type="button"
              onClick={() => void transitionStatus("read")}
              disabled={busy}
            >
              标记为已读
            </button>
          ) : null}
          {detail.status !== "resolved" ? (
            <button
              className="admin-button admin-button-primary"
              type="button"
              onClick={() => void transitionStatus("resolved")}
              disabled={busy}
            >
              标记为已处理
            </button>
          ) : null}
        </div>
      </section>
    </div>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}
```

- [ ] **Step 2: Add CSS for the content pre block**

Append to `frontend/app/globals.css`:

```css
.admin-feedback-content {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
  color: #1e293b;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/admin/feedback/[id]/page.tsx frontend/app/globals.css
git commit -m "feat(admin-ui): feedback detail page"
```

---

### Task 21: Wire admin nav and overview

**Files:**
- Modify: `frontend/app/admin/layout.tsx`
- Modify: `frontend/app/admin/page.tsx`

- [ ] **Step 1: Update admin nav**

In `frontend/app/admin/layout.tsx`, change the `buildNavItems` for the admin branch from:

```ts
{ href: "/admin", label: "概览" },
{ href: "/admin/users", label: "用户管理" },
{ href: "/admin/conversations", label: "对话历史" },
```

to:

```ts
{ href: "/admin", label: "概览" },
{ href: "/admin/users", label: "用户管理" },
{ href: "/admin/feedback", label: "意见反馈" },
{ href: "/admin/conversations", label: "对话历史" },
```

- [ ] **Step 2: Add overview card**

In `frontend/app/admin/page.tsx`, extend the `modules` list for the admin branch to include a third item:

```ts
{
  title: "意见反馈",
  description: "查看用户提交的意见与建议,支持状态流转与附件预览。",
  href: "/admin/feedback",
},
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output.

- [ ] **Step 4: Manual verification**

As admin:
1. Open `/admin`; the overview now shows 3 module cards.
2. Open the sidebar; it now shows 4 nav items (概览 / 用户管理 / 意见反馈 / 对话历史).
3. Click 意见反馈; the list page loads.
4. From a previously submitted feedback, open a row, view attachments, click "标记为已处理"; the status updates and the badge changes.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/admin/layout.tsx frontend/app/admin/page.tsx
git commit -m "feat(admin-ui): register 意见反馈 in nav and overview"
```

**End of Stage 3.**

---

## Final Validation

After all stages are complete:

- [ ] **Run full backend unit suite**: `uv run pytest tests/unit -q`
- [ ] **Run full backend integration suite** (skip if no DB): `uv run pytest tests/integration -q` — confirm no regressions in the existing admin tests.
- [ ] **Type-check frontend**: `cd frontend && npx tsc --noEmit`
- [ ] **Build frontend**: `cd frontend && npm run build`
- [ ] **Manual end-to-end**:
  1. Sign in as admin; open `/admin/users`; confirm toolbar + pagination work as in Task 5 step 4.
  2. Open `/admin/conversations`; click into a session; click "AI 速览"; confirm summary renders.
  3. Open the chat page popover; submit a feedback with 2 images; verify success.
  4. Back in admin `/admin/feedback`; open the new submission; verify the first open flips status open→read; click "标记为已处理"; verify resolved_at is set.
  5. Open an image attachment URL directly in a new tab; verify it loads.
  6. As a non-admin (use a coach account or remove admin flag), confirm `/admin/feedback` is inaccessible and the popover entry still appears.
