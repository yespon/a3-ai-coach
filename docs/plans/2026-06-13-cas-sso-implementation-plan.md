CAS SSO Implementation Plan - Ruijie SID (CAS) + Postgres Server-Side Session

> Based on design doc: docs/plans/2026-06-12-cas-sso-session-design.md
> Based on checklist: docs/plans/2026-06-12-sid-integration-checklist.md
> Based on fix plan: docs/plans/2026-06-13-fix-integration-tests-and-next-phases.md (Task 9 skeleton)
> Date: 2026-06-13
> Estimated tasks: 10 Tasks in 4 Phases
> Prerequisite: Phase 6-7 (integration test fix + E2E verification) completed

---

## Overview

The design doc Section 11 lists 8 implementation steps. This plan splits them into 10 independently executable, testable Tasks organized by dependency into 4 Phases:

| Phase | Task | Content | Dependencies |
|---|---|---|---|
| 1 Infrastructure | 1 | auth_sessions table + ORM + migration | None |
| 1 Infrastructure | 2 | CAS config items + auth_mode switch | None |
| 1 Infrastructure | 3 | User model refactor (add provider/provider_user_id) | Task 1 |
| 2 Core Flow | 4 | validate_ticket + upsert_sso_user service | Task 2, 3 |
| 2 Core Flow | 5 | CAS endpoints: /cas/login + /cas/exchange + /cas/slo | Task 4 |
| 2 Core Flow | 6 | get_current_user refactor (JWT -> session cookie) | Task 1, 3 |
| 3 Security & Cleanup | 7 | CSRF double-submit token + cookie security attributes | Task 6 |
| 3 Security & Cleanup | 8 | Session expiry/sliding refresh + periodic cleanup task | Task 1, 6 |
| 3 Security & Cleanup | 9 | Local auth endpoint disposition (auth_mode switch control) | Task 2, 6 |
| 4 Acceptance | 10 | Integration tests + local debugging guide doc | Task 5-9 |

---

## Phase 1: Infrastructure (Data Models + Config)

### Task 1: auth_sessions table + ORM + Alembic migration

**Goal:** Create server-side session table for CAS SSO session storage.

**Files:**
- app/models/db_models.py (add AuthSessionDB model)
- alembic/versions/002_auth_sessions_table.py (add migration)

**Steps:**

1. Add AuthSessionDB model to app/models/db_models.py (per design doc Section 2.1):

```python
class AuthSessionDB(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    cas_ticket: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 max 45 chars

    user: Mapped["User"] = relationship()  # Single direction, not named "sessions" (occupied by chat_sessions)
```

2. Add Alembic migration 002_auth_sessions_table.py:

- Create auth_sessions table with all columns above
- Add indexes: ix_auth_sessions_user_id, ix_auth_sessions_cas_ticket, ix_auth_sessions_expires
- down_revision = "001_initial", revision = "002_auth_sessions"

**Verification:** `alembic upgrade head` succeeds, auth_sessions table exists in PG with correct indexes.

**Commit:** `feat(cas): add auth_sessions table + ORM model + migration`

---

### Task 2: CAS config items + auth_mode switch

**Goal:** Add CAS/SSO config to Settings, including auth_mode switch for local auth vs SSO toggle.

**Files:**
- app/core/config.py (add config items)
- .env.example (add config item comments)

**Steps:**

1. Add these fields to Settings class:

```python
    # --- CAS / SSO ---
    auth_mode: str = "both"  # "sso" | "local" | "both"; production default sso, transition period both
    sid_base_url: str = "https://sid.ruijie.com.cn"
    sid_service_url: str = "https://gangbiao-ai-coach.ruijie.com.cn/login"
    sid_logout_url: str = "https://sid.ruijie.com.cn/logout"
    session_cookie_name: str = "sid_session"
    session_cookie_secure: bool = True  # Production HTTPS must be True
    session_cookie_samesite: str = "Lax"
    session_ttl_hours: int = 8  # Aligned with SID TGC 8h
    session_sliding_refresh_minutes: int = 30  # last_seen refresh threshold
    cas_validate_timeout_seconds: int = 5  # ST only 10s, timeout must be short
```

2. Update .env.example with these new config items (with comments).

**Verification:** Settings() correctly reads new fields from .env, defaults are reasonable.

**Commit:** `feat(cas): add SSO/CAS config settings + auth_mode switch`

---

### Task 3: User model refactor (add provider / provider_user_id)

**Goal:** Refactor User model to support SSO users (CAS employee number as primary identifier), while remaining compatible with existing local password users.

**Files:**
- app/models/db_models.py (refactor User model)
- alembic/versions/003_user_sso_fields.py (add migration)
- app/services/user_service.py (add upsert_sso_user)
- app/models/schema.py (add CASUserResponse)

**Steps:**

1. Refactor User model (design doc Section 3.1):

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(...)  # unchanged
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)  # nullable (supplier has no email)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # nullable (SSO user has no local password)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)  # unchanged
    provider: Mapped[str] = mapped_column(String(20), server_default=text("'local'"))  # NEW: "local" | "cas"
    provider_user_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)  # NEW: CAS employee number
    is_active: Mapped[bool] = mapped_column(...)  # unchanged
    is_admin: Mapped[bool] = mapped_column(...)  # unchanged
    created_at: Mapped[datetime] = mapped_column(...)  # unchanged
    updated_at: Mapped[datetime] = mapped_column(...)  # unchanged

    sessions: Mapped[list["ChatSessionDB"]] = relationship(...)  # unchanged
```

2. Add migration 003_user_sso_fields.py:

- ALTER TABLE users ALTER COLUMN email DROP NOT NULL
- ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL
- ADD COLUMN provider VARCHAR(20) DEFAULT 'local' NOT NULL
- ADD COLUMN provider_user_id VARCHAR(100) NULL UNIQUE
- Set provider = 'local' for all existing data (all current users are local password users)
- Add unique index on (provider, provider_user_id) for SSO queries

3. Add upsert_sso_user to app/services/user_service.py (design doc Section 3.2):

```python
async def upsert_sso_user(db: AsyncSession, employee_no: str, attrs: dict) -> User:
    result = await db.execute(
        select(User).where(User.provider == "cas", User.provider_user_id == employee_no)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            provider="cas",
            provider_user_id=employee_no,
            email=attrs.get("RJEMAIL"),      # Supplier: None, allowed
            nickname=attrs.get("RJXM") or employee_no,
            password_hash=None,               # SSO user has no local password
        )
        db.add(user)
    else:
        # Refresh attributes on each login
        if attrs.get("RJXM"):   user.nickname = attrs["RJXM"]
        if attrs.get("RJEMAIL"): user.email = attrs["RJEMAIL"]
    await db.commit()
    await db.refresh(user)
    return user
```

4. Add CASUserResponse to app/models/schema.py:

```python
class CASUserResponse(BaseModel):
    ok: bool = True
    user: UserResponse | None = None
```

**Verification:** Migration succeeds, existing users all have provider='local', upsert_sso_user correctly creates/updates CAS users.

**Commit:** `feat(cas): add provider/provider_user_id to User model + upsert_sso_user service`

---

## Phase 2: Core Flow (CAS Endpoints + Auth Refactor)

### Task 4: validate_ticket + CAS service layer

**Goal:** Implement CAS ticket validation core logic (validate_ticket function) and session creation/management service.

**Files:**
- app/services/cas_service.py (new)

**Steps:**

1. Create app/services/cas_service.py with validate_ticket (design doc Section 5.1):

```python
import httpx
from xml.etree import ElementTree as ET
from fastapi import HTTPException

CAS_NS = {"cas": "http://www.yale.edu/tp/cas"}

async def validate_ticket(ticket: str, service_url: str, sid_base_url: str, timeout: int = 5) -> tuple[str, dict]:
    """Validate CAS Service Ticket via /p3/serviceValidate.
    
    Returns (employee_no, attrs_dict).
    Raises HTTPException(401) on validation failure.
    """
    params = {"service": service_url, "ticket": ticket}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"{sid_base_url}/p3/serviceValidate", params=params)
    
    root = ET.fromstring(resp.text)
    success = root.find(".//cas:authenticationSuccess", CAS_NS)
    if success is None:
        failure = root.find(".//cas:authenticationFailure", CAS_NS)
        detail = failure.text if failure is not None else "CAS validation failed"
        raise HTTPException(status_code=401, detail=detail.strip())
    
    employee_no = success.find("cas:user", CAS_NS).text
    attrs = {}
    attr_elements = success.findall(".//cas:attributes/*", CAS_NS)
    for el in attr_elements:
        key = el.tag.split("}")[-1]  # strip namespace
        attrs[key] = el.text
    return employee_no, attrs


def parse_session_index(saml_xml: str) -> str | None:
    """Extract original ST from SAML LogoutRequest for SLO back-channel."""
    root = ET.fromstring(saml_xml)
    si = root.find(".//{urn:oasis:names:tc:SAML:2.0:protocol}SessionIndex")
    return si.text if si is not None else None
```

2. Implement create_auth_session (design doc Section 2.3):

```python
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

async def create_auth_session(db, user_id: uuid.UUID, cas_ticket: str | None = None,
                               user_agent: str | None = None, ip: str | None = None,
                               ttl_hours: int = 8) -> tuple[str, AuthSessionDB]:
    """Create a new server-side session. Returns (raw_token, session_obj).
    
    raw_token is the value set in cookie; session_token in DB is SHA-256 hash of raw_token.
    """
    raw_token = secrets.token_urlsafe(48)  # ~64 chars
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    
    now = datetime.now(UTC)
    session = AuthSessionDB(
        session_token=token_hash,
        user_id=user_id,
        cas_ticket=cas_ticket,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        user_agent=user_agent,
        ip=ip,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return raw_token, session
```

**Verification:** Unit test validate_ticket XML parsing logic (mock httpx response), parse_session_index SAML parsing.

**Commit:** `feat(cas): add cas_service with validate_ticket + session creation`

---

### Task 5: CAS endpoint implementation - /cas/login + /cas/exchange + /cas/slo

**Goal:** Implement complete CAS authentication endpoints: login redirect, ticket exchange, single logout callback.

**Files:**
- app/api/v1/routes/cas.py (new, full implementation)
- app/api/v1/router.py (register CAS routes)

**Steps:**

1. Create app/api/v1/routes/cas.py (design doc Section 1 + Section 5):

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from datetime import UTC, datetime

from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import AuthSessionDB, User
from app.services.cas_service import validate_ticket, parse_session_index, create_auth_session
from app.services.user_service import upsert_sso_user

router = APIRouter(prefix="/cas", tags=["cas"])


class ExchangeRequest(BaseModel):
    ticket: str


@router.get("/login")
async def cas_login(request: Request):
    """Step 2: Redirect browser to SID /login with service URL."""
    redirect_url = f"{settings.sid_base_url}/login?service={settings.sid_service_url}"
    return Response(status_code=302, headers={"Location": redirect_url})


@router.post("/exchange")
async def cas_exchange(body: ExchangeRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Step 5-9: Exchange CAS ticket for server-side session."""
    # Step 6-7: Validate ticket with SID
    employee_no, attrs = await validate_ticket(
        ticket=body.ticket,
        service_url=settings.sid_service_url,
        sid_base_url=settings.sid_base_url,
        timeout=settings.cas_validate_timeout_seconds,
    )
    
    # Step 8: Upsert SSO user
    user = await upsert_sso_user(db, employee_no, attrs)
    
    # Step 9: Create session
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    raw_token, sess = await create_auth_session(
        db, user.id, cas_ticket=body.ticket,
        user_agent=user_agent, ip=ip,
        ttl_hours=settings.session_ttl_hours,
    )
    
    # Step 10: Set session cookie
    response.set_cookie(
        settings.session_cookie_name, raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    
    return {"ok": True, "user": {"id": str(user.id), "nickname": user.nickname, "email": user.email}}


@router.post("/slo")
async def cas_single_logout(logoutRequest: str = Form(...), db: AsyncSession = Depends(get_db)):
    """BACK_CHANNEL SLO: SID POSTs SAML LogoutRequest containing original ST."""
    st = parse_session_index(logoutRequest)
    if not st:
        return Response(status_code=200)  # malformed, ignore
    
    result = await db.execute(
        select(AuthSessionDB).where(AuthSessionDB.cas_ticket == st)
    )
    sess = result.scalar_one_or_none()
    if sess:
        sess.revoked_at = datetime.now(UTC)
        await db.commit()
    return Response(status_code=200)
```

2. Register CAS routes in app/api/v1/router.py:

```python
from app.api.v1.routes.cas import router as cas_router
api_v1_router.include_router(cas_router)
```

**Verification:**
- /cas/login returns 302 + correct SID URL
- /cas/exchange with mock SID response completes ticket -> session -> cookie flow
- /cas/slo extracts ST from SAML XML and revokes corresponding session

**Commit:** `feat(cas): implement /cas/login, /cas/exchange, /cas/slo endpoints`

---

### Task 6: get_current_user refactor (JWT -> session cookie)

**Goal:** Switch auth dependency from JWT header to session cookie query. This is the core seam refactor for CAS SSO. Downstream get_current_user_id and all business routes have zero changes.

**Files:**
- app/api/deps.py (rewrite get_current_user)
- app/api/v1/routes/auth.py (refactor /logout)

**Steps:**

1. Rewrite app/api/deps.py (design doc Section 4):

```python
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import UTC, datetime, timedelta
import hashlib

from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import AuthSessionDB, User
from app.core.logger import get_component_logger

LOGGER = get_component_logger(component="chatbot")

SLIDING_REFRESH = timedelta(minutes=settings.session_sliding_refresh_minutes)


async def get_current_user(
    request: Request,
    sid_session: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Authenticate via server-side session cookie.
    
    Replaces JWT-based auth. Downstream get_current_user_id unchanged.
    """
    if not sid_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in")
    
    token_hash = hashlib.sha256(sid_session.encode()).hexdigest()
    result = await db.execute(
        select(AuthSessionDB).where(AuthSessionDB.session_token == token_hash)
    )
    sess = result.scalar_one_or_none()
    
    now = datetime.now(UTC)
    if not sess or sess.revoked_at is not None or sess.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    
    user = await db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or disabled")
    
    # Sliding refresh: update last_seen_at if stale (throttled to reduce write amplification)
    if now - sess.last_seen_at > SLIDING_REFRESH:
        sess.last_seen_at = now
        await db.commit()
    
    return user


def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    return str(user.id)
```

2. Refactor /logout in auth.py (design doc Section 5.2):

```python
@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    sid_session: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
):
    """Logout: revoke session + redirect to SID logout."""
    if sid_session:
        token_hash = hashlib.sha256(sid_session.encode()).hexdigest()
        result = await db.execute(
            select(AuthSessionDB).where(AuthSessionDB.session_token == token_hash)
        )
        sess = result.scalar_one_or_none()
        if sess:
            sess.revoked_at = datetime.now(UTC)
            await db.commit()
    
    # Clear cookie
    response.delete_cookie(settings.session_cookie_name, path="/")
    
    # Redirect to SID logout (design doc: must not return to app own login page)
    if settings.auth_mode in ("sso", "both"):
        return Response(status_code=302, headers={"Location": settings.sid_logout_url})
    return Response(status_code=204)
```

3. /me endpoint unchanged (already depends on get_current_user, auto-adapts).

**Verification:**
- Request with session cookie correctly returns User
- No cookie returns 401
- Expired/revoked session returns 401
- /logout revokes session + clears cookie + redirects to SID

**Commit:** `feat(cas): rewrite get_current_user to use session cookie auth`

---

## Phase 3: Security & Cleanup

### Task 7: CSRF double-submit token + cookie security attributes

**Goal:** After switching to cookie auth, POST endpoints are exposed to CSRF. Implement SameSite=Lax + double-submit CSRF token protection.

**Files:**
- app/api/deps.py (add CSRF verification dependency)
- app/api/v1/routes/cas.py (issue CSRF token on exchange)
- app/core/config.py (add CSRF config)
- Frontend (needs to read csrf cookie and put in header)

**Steps:**

1. Add to config.py:

```python
    csrf_cookie_name: str = "csrf_token"
    csrf_header_name: str = "X-CSRF-Token"
```

2. In cas.py exchange endpoint, also issue a non-httpOnly CSRF cookie:

```python
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.csrf_cookie_name, csrf_token,
        httponly=False,  # JS must read this
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
```

3. Add verify_csrf dependency in deps.py (only for write operations):

```python
async def verify_csrf(request: Request):
    """Verify double-submit CSRF token for state-changing requests."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return  # Safe methods don't need CSRF check
    
    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get(settings.csrf_header_name)
    
    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    
    if csrf_cookie != csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token mismatch")
```

4. Add verify_csrf to write operation routes (chat.py, sessions.py) dependency chain.

**Verification:**
- GET requests don't check CSRF
- POST without CSRF header returns 403
- POST with correct CSRF header passes

**Commit:** `feat(cas): add CSRF double-submit token protection`

---

### Task 8: Session expiry/sliding refresh + periodic cleanup task

**Goal:** Implement sliding refresh strategy and periodic expired session cleanup.

**Files:**
- app/services/cas_service.py (add cleanup function)
- app/main.py or lifespan (register periodic cleanup task)
- app/core/config.py (add cleanup config)

**Steps:**

1. Add to config.py:

```python
    session_cleanup_interval_minutes: int = 60  # Cleanup every hour
    session_cleanup_grace_days: int = 1  # Keep expired sessions for 1 day before deletion
```

2. Add cleanup_expired_sessions to cas_service.py:

```python
async def cleanup_expired_sessions(db: AsyncSession, grace_days: int = 1):
    """Delete sessions that expired or were revoked more than grace_days ago."""
    cutoff = datetime.now(UTC) - timedelta(days=grace_days)
    await db.execute(
        AuthSessionDB.__table__.delete().where(
            (AuthSessionDB.expires_at < cutoff) | (AuthSessionDB.revoked_at < cutoff)
        )
    )
    await db.commit()
```

3. Register periodic cleanup task in FastAPI lifespan:

```python
import asyncio

async def session_cleanup_task():
    """Background task: periodically clean up expired sessions."""
    while True:
        await asyncio.sleep(settings.session_cleanup_interval_minutes * 60)
        async with async_session_factory() as db:
            await cleanup_expired_sessions(db, settings.session_cleanup_grace_days)

# In lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(session_cleanup_task())
    yield
    cleanup_task.cancel()
```

**Verification:** Expired sessions are deleted after cleanup, active sessions unaffected.

**Commit:** `feat(cas): add session sliding refresh + periodic cleanup task`

---

### Task 9: Local auth endpoint disposition (auth_mode switch control)

**Goal:** Control local auth endpoint availability based on auth_mode config. SSO mode disables register/login/refresh; transition period both mode keeps both.

**Files:**
- app/api/v1/routes/auth.py (add switch checks to endpoints)
- app/api/v1/routes/cas.py (ensure SSO endpoints unavailable in local mode)

**Steps:**

1. Add switch checks to auth.py endpoints:

```python
from app.core.config import settings

@router.post("/register", ...)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local registration disabled, use SSO login")
    # ... original logic unchanged

@router.post("/login", ...)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local login disabled, use SSO login")
    # ... original logic unchanged

@router.post("/refresh", ...)
async def refresh(body: RefreshRequest):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Token refresh disabled")
    # ... original logic unchanged
```

2. Add reverse switch to cas.py:

```python
@router.get("/login")
async def cas_login(request: Request):
    if settings.auth_mode == "local":
        raise HTTPException(status_code=403, detail="SSO not enabled")
    # ... original logic
```

3. /me and /logout unaffected by switch (needed in both modes).

**Verification:**
- auth_mode=sso: local auth endpoints return 403
- auth_mode=local: CAS endpoints return 403
- auth_mode=both: both available

**Commit:** `feat(cas): add auth_mode switch to control local vs SSO auth endpoints`

---

## Phase 4: Acceptance

### Task 10: Integration tests + local debugging guide doc

**Goal:** Write integration tests for CAS SSO flow and create local debugging guide document.

**Files:**
- tests/integration/test_cas.py (new)
- docs/cas-sso-local-debugging-guide.md (new)

**Steps:**

1. Create tests/integration/test_cas.py:

- test_cas_login_redirect: GET /cas/login -> 302 + SID URL
- test_cas_exchange_success: mock validate_ticket -> POST /cas/exchange -> 200 + sid_session cookie
- test_cas_exchange_invalid_ticket: mock SID failure -> 401
- test_cas_slo_revokes_session: POST /cas/slo with SAML LogoutRequest -> session revoked
- test_session_cookie_auth: with cookie GET /auth/me -> 200 + user info
- test_no_cookie_returns_401: no cookie GET /auth/me -> 401
- test_expired_session_returns_401: expired session -> 401
- test_auth_mode_sso_blocks_local: auth_mode=sso -> /auth/register 403
- test_auth_mode_local_blocks_cas: auth_mode=local -> /cas/login 403

2. Create docs/cas-sso-local-debugging-guide.md (based on design doc Section 12):

- hosts mapping config (Windows + Linux)
- mkcert self-signed certificate generation steps
- nginx reverse proxy config (HTTPS -> backend)
- ST 10-second timeout notes
- Production SID direct connection risk warnings
- Debugging checklist

**Verification:** pytest tests/integration/test_cas.py -v all pass.

**Commit:** `test(cas): add CAS SSO integration tests + local debugging guide`

---

## Dependency Graph

```
Task 1 (auth_sessions table) ──────────────────┬──> Task 6 (get_current_user refactor)
                                                │
Task 2 (CAS config) ────────────┬──> Task 4 (validate_ticket) ──> Task 5 (CAS endpoints)
                                │                              │
Task 3 (User model refactor) ───┴──> Task 4 ────────────────────┘
                                                │
Task 6 ──> Task 7 (CSRF) ──> Task 9 (auth_mode switch)
Task 6 ──> Task 8 (session cleanup)
Task 5-9 ──> Task 10 (integration tests)
```

**Parallelization opportunities:**
- Task 1, 2 can run in parallel (no dependencies)
- Task 3 depends on Task 1 (migration order)
- Task 4 depends on Task 2 + 3
- Task 5 depends on Task 4
- Task 6 depends on Task 1 + 3
- Task 7, 8, 9 can run in parallel (all depend on Task 6, but independent of each other)
- Task 10 depends on Task 5-9 all completed

Recommended execution order: Task 1+2 parallel -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7+8+9 parallel -> Task 10

---

## Risks & Notes

1. **ST only 10 seconds:** CAS Service Ticket is one-time and only 10 seconds valid. httpx timeout set to 5s, no retry on failure. Do not add breakpoints in exchange chain during local debugging.
2. **Supplier has no email:** After User.email becomes nullable, all email query logic must tolerate None. upsert_sso_user email=attrs.get("RJEMAIL") can be None.
3. **service URL must match exactly:** /cas/login redirect and /p3/serviceValidate must use the same config constant sid_service_url, cannot use request.url inference.
4. **BACK_CHANNEL SLO message format:** Currently assumed standard SAML LogoutRequest. Actual format needs confirmation from SID contact (checklist Section 4). If different, parse_session_index needs adjustment.
5. **Feishu registration approval:** Complete CAS debugging depends on app registration approval. Skeleton code doesn't affect existing functionality, but debugging requires registration completion.
6. **Frontend changes:** Frontend /login page needs to become CAS landing route (detect ?ticket -> POST exchange; no ticket -> redirect to SID). CSRF token needs frontend cooperation (read cookie -> put in header).
7. **auth_mode=both transition period:** Two auth systems coexist. get_current_user only checks session cookie; local JWT users need additional handling (or keep JWT header as fallback during transition).
8. **Alembic migration order:** 002_auth_sessions -> 003_user_sso_fields, must execute in revision chain order.
9. **Password consistency:** docker-compose PG password gangbiao_dev, .env DATABASE_URL must match.

---

## Execution Method

**Recommended: Subagent-Driven** - Each Task dispatched to an independent subagent, main agent does review checkpoint between Tasks. Parallel Tasks (1+2, 7+8+9) can dispatch multiple subagents simultaneously.

**Alternative: Inline Execution** - Execute Tasks sequentially in current session, git commit + review after each Task.

---

## Relationship to Existing Fix Plan

This plan is the full expansion of Task 9 (CAS skeleton) in 2026-06-13-fix-integration-tests-and-next-phases.md. Recommended execution order:

1. First complete Phase 6-7 (integration test fix + E2E verification), ensure stable baseline
2. Then execute this plan's Phase 1-4 (CAS SSO full implementation)

The ServerSession model in Task 9 skeleton differs from this plan's AuthSessionDB model (field names/structure different). This plan follows the precise specification in design doc Section 2.1.
