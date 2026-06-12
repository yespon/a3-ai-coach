from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.db_models import User
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
    user = await authenticate_user(db, body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
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


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout():
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        nickname=current_user.nickname,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )
