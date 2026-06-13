"""CAS SSO endpoints — login redirect, ticket exchange, single logout."""

import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import AuthSessionDB
from app.services.cas_service import (
    create_auth_session,
    parse_session_index,
    validate_ticket,
)
from app.services.user_service import upsert_sso_user

router = APIRouter(prefix="/cas", tags=["cas"])


class ExchangeRequest(BaseModel):
    ticket: str


@router.get("/login")
async def cas_login(request: Request):
    """Redirect browser to SID /login with service URL."""
    if settings.auth_mode == "local":
        raise HTTPException(status_code=403, detail="SSO not enabled")
    redirect_url = f"{settings.sid_base_url}/login?service={settings.sid_service_url}"
    return Response(status_code=302, headers={"Location": redirect_url})


@router.post("/exchange")
async def cas_exchange(
    body: ExchangeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Exchange CAS ticket for server-side session."""
    if settings.auth_mode == "local":
        raise HTTPException(status_code=403, detail="SSO not enabled")

    # Validate ticket with SID
    employee_no, attrs = await validate_ticket(
        ticket=body.ticket,
        service_url=settings.sid_service_url,
        sid_base_url=settings.sid_base_url,
        timeout=settings.cas_validate_timeout_seconds,
    )

    # Upsert SSO user
    user = await upsert_sso_user(db, employee_no, attrs)

    # Create session
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    raw_token, _sess = await create_auth_session(
        db,
        user.id,
        cas_ticket=body.ticket,
        user_agent=user_agent,
        ip=ip,
        ttl_hours=settings.session_ttl_hours,
    )

    # Set session cookie
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )

    # Issue CSRF double-submit cookie (non-httpOnly so JS can read it)
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )

    return {
        "ok": True,
        "user": {
            "id": str(user.id),
            "nickname": user.nickname,
            "email": user.email,
        },
    }


@router.post("/slo")
async def cas_single_logout(
    logoutRequest: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
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
