"""Local auth endpoints — register, login, refresh, logout, me."""

import hashlib
from datetime import UTC, datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.db_models import AuthSessionDB, User
from app.models.schema import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.user_service import authenticate_user, create_user


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local registration disabled, use SSO login")
    try:
        user = await create_user(db, body.email, body.password, body.nickname)
    except ValueError as exc:
        if str(exc) == "email_already_exists":
            raise HTTPException(status_code=409, detail="email_already_exists")
        raise
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Local login disabled, use SSO login")
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    if settings.auth_mode == "sso":
        raise HTTPException(status_code=403, detail="Token refresh disabled")
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid_token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="invalid_token_type")
    return TokenResponse(
        access_token=create_access_token(payload["sub"]),
        refresh_token=create_refresh_token(payload["sub"]),
    )


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
