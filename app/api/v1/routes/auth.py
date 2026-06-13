"""Auth endpoints — register, login, logout, me.

Both local and SSO auth converge on server-side session cookies.
"""

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import AuthSessionDB, User
from app.models.schema import (
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from app.services.cas_service import create_auth_session
from app.services.user_service import authenticate_user, create_user


router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookies(
    response: Response,
    raw_token: str,
) -> None:
    """Set session + CSRF cookies on a response."""
    response.set_cookie(
        settings.session_cookie_name,
        raw_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
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


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Register a local user and set session cookie."""
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local registration disabled, use SSO login")
    try:
        user = await create_user(db, body.email, body.password, body.nickname)
    except ValueError as exc:
        if str(exc) == "email_already_exists":
            raise HTTPException(status_code=409, detail="email_already_exists")
        raise

    # Create session (same mechanism as CAS exchange)
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    raw_token, _sess = await create_auth_session(
        db, user.id, user_agent=user_agent, ip=ip,
        ttl_hours=settings.session_ttl_hours,
    )
    _set_session_cookies(response, raw_token)

    return {
        "ok": True,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "nickname": user.nickname,
        },
    }


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate with email/password and set session cookie."""
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local login disabled, use SSO login")
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_credentials")

    # Create session (same mechanism as CAS exchange)
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    raw_token, _sess = await create_auth_session(
        db, user.id, user_agent=user_agent, ip=ip,
        ttl_hours=settings.session_ttl_hours,
    )
    _set_session_cookies(response, raw_token)

    return {
        "ok": True,
        "user": {
            "id": str(user.id),
            "email": user.email,
            "nickname": user.nickname,
        },
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    sid_session: str | None = Cookie(default=None, alias=settings.session_cookie_name),
    db: AsyncSession = Depends(get_db),
):
    """Logout: revoke session + clear cookies + redirect to SID logout."""
    if sid_session:
        token_hash = hashlib.sha256(sid_session.encode()).hexdigest()
        result = await db.execute(
            select(AuthSessionDB).where(AuthSessionDB.session_token == token_hash)
        )
        sess = result.scalar_one_or_none()
        if sess:
            sess.revoked_at = datetime.now(UTC)
            await db.commit()

    # Clear cookies
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")

    # Redirect to SID logout
    if settings.auth_mode in ("sso", "both"):
        return Response(status_code=302, headers={"Location": settings.sid_logout_url})
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        nickname=current_user.nickname,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
