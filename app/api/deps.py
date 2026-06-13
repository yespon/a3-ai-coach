"""Auth dependencies — session-cookie-based authentication."""

import hashlib
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import get_component_logger
from app.models.db_models import AuthSessionDB, User

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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="not logged in"
        )

    token_hash = hashlib.sha256(sid_session.encode()).hexdigest()
    result = await db.execute(
        select(AuthSessionDB).where(AuthSessionDB.session_token == token_hash)
    )
    sess = result.scalar_one_or_none()

    now = datetime.now(UTC)
    if not sess or sess.revoked_at is not None or sess.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
        )

    user = await db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="user not found or disabled",
        )

    # Sliding refresh: update last_seen_at if stale
    if now - sess.last_seen_at > SLIDING_REFRESH:
        sess.last_seen_at = now
        await db.commit()

    return user


def get_current_user_id(user: User = Depends(get_current_user)) -> str:
    return str(user.id)


async def verify_csrf(request: Request):
    """Verify double-submit CSRF token for state-changing requests.

    Safe methods (GET, HEAD, OPTIONS) are exempt.
    For write methods, the CSRF cookie value must match the X-CSRF-Token header.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    csrf_cookie = request.cookies.get(settings.csrf_cookie_name)
    csrf_header = request.headers.get(settings.csrf_header_name)

    if not csrf_cookie or not csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token missing")

    if csrf_cookie != csrf_header:
        raise HTTPException(status_code=403, detail="CSRF token mismatch")
