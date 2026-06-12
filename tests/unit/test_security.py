from datetime import timedelta, UTC, datetime

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password():
    hashed = hash_password("secret123")
    assert verify_password("secret123", hashed) is True


def test_verify_wrong_password():
    hashed = hash_password("secret123")
    assert verify_password("wrong", hashed) is False


def test_create_access_token_valid():
    token = create_access_token("user-42")
    payload = decode_token(token)
    assert payload["sub"] == "user-42"
    assert payload["type"] == "access"


def test_create_refresh_token_valid():
    token = create_refresh_token("user-42")
    payload = decode_token(token)
    assert payload["sub"] == "user-42"
    assert payload["type"] == "refresh"


def test_expired_token_raises():
    token = create_access_token("user-42", expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_invalid_token_raises():
    with pytest.raises(jwt.InvalidTokenError):
        decode_token("this.is.not.a.jwt")