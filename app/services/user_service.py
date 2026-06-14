from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.db_models import User
from app.core.security import hash_password, verify_password


async def create_user(db: AsyncSession, email: str, password: str, nickname: str | None = None) -> User:
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none():
        raise ValueError("email_already_exists")
    user = User(email=email.lower().strip(), password_hash=hash_password(password), nickname=nickname)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower().strip()))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    return await db.get(User, user_id)


async def upsert_sso_user(db: AsyncSession, employee_no: str, attrs: dict, is_admin: bool = False) -> User:
    """Create or update a CAS SSO user by employee number.

    On first login a new User row is created with provider='cas'.
    On subsequent logins the nickname and email are refreshed from CAS attributes.
    is_admin only promotes — never demotes.
    """
    result = await db.execute(
        select(User).where(User.provider == "cas", User.provider_user_id == employee_no)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            provider="cas",
            provider_user_id=employee_no,
            email=attrs.get("RJEMAIL"),       # Supplier may not have email
            nickname=attrs.get("RJXM") or employee_no,
            password_hash=None,                # SSO user has no local password
            is_admin=is_admin,
        )
        db.add(user)
    else:
        # Refresh attributes on each login
        if attrs.get("RJXM"):
            user.nickname = attrs["RJXM"]
        if attrs.get("RJEMAIL"):
            user.email = attrs["RJEMAIL"]
        if is_admin and not user.is_admin:
            user.is_admin = True
    await db.commit()
    await db.refresh(user)
    return user
