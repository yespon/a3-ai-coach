"""Auth integration tests — real JWT + PostgreSQL flow.

These tests exercise the actual auth endpoints (register, login, refresh, me)
without any dependency_overrides. They require a running PostgreSQL instance
and will be automatically skipped when PG is unavailable.
"""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token, create_refresh_token
from app.core.config import settings

# ---------------------------------------------------------------------------
# Module-level skip: if PG is not reachable, every test in this file is skipped.
# ---------------------------------------------------------------------------
_pg_available = False

try:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    _engine = create_async_engine(settings.database_url)

    async def _ping():
        async with _engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            return True

    _pg_available = asyncio.run(asyncio.wait_for(_ping(), timeout=3))
    _engine.dispose()
except Exception:
    _pg_available = False

pytestmark = pytest.mark.skipif(not _pg_available, reason="PostgreSQL not available")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UNIQUE_EMAIL_COUNTER = 0


def _unique_email() -> str:
    """Generate a unique email per test run to avoid collisions."""
    global _UNIQUE_EMAIL_COUNTER
    _UNIQUE_EMAIL_COUNTER += 1
    return f"auth_test_{_UNIQUE_EMAIL_COUNTER}_{uuid.uuid4().hex[:8]}@example.com"


def _register_user(client: TestClient, email: str | None = None, password: str = "secret123", nickname: str | None = "TestUser"):
    """Register a user via the /api/v1/auth/register endpoint and return the response."""
    email = email or _unique_email()
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "nickname": nickname},
    )
    return resp, email


def _login_user(client: TestClient, email: str, password: str = "secret123"):
    """Login via /api/v1/auth/login and return the response."""
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_register_success(auth_client):
    """Registering a new user returns 201 with access + refresh tokens."""
    resp, email = _register_user(auth_client)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email(auth_client):
    """Registering the same email twice returns 409."""
    email = _unique_email()
    resp1, _ = _register_user(auth_client, email=email)
    assert resp1.status_code == 201

    resp2, _ = _register_user(auth_client, email=email)
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "email_already_exists"


def test_login_success(auth_client):
    """Login with correct credentials returns 200 with tokens."""
    email = _unique_email()
    reg_resp, _ = _register_user(auth_client, email=email)
    assert reg_resp.status_code == 201

    login_resp = _login_user(auth_client, email)
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(auth_client):
    """Login with wrong password returns 401."""
    email = _unique_email()
    reg_resp, _ = _register_user(auth_client, email=email)
    assert reg_resp.status_code == 201

    login_resp = _login_user(auth_client, email, password="wrong_password")
    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "invalid_credentials"


def test_login_nonexistent_user(auth_client):
    """Login with an email that doesn't exist returns 401."""
    login_resp = _login_user(auth_client, "nonexistent@example.com")
    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "invalid_credentials"


def test_refresh_token(auth_client):
    """Refreshing with a valid refresh token returns new tokens."""
    reg_resp, _ = _register_user(auth_client)
    assert reg_resp.status_code == 201
    refresh_token = reg_resp.json()["refresh_token"]

    refresh_resp = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    data = refresh_resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    # New tokens should differ from the originals
    assert data["access_token"] != reg_resp.json()["access_token"]


def test_refresh_with_access_token_fails(auth_client):
    """Using an access token (instead of refresh) on /refresh returns 401."""
    reg_resp, _ = _register_user(auth_client)
    assert reg_resp.status_code == 201
    access_token = reg_resp.json()["access_token"]

    refresh_resp = auth_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )
    assert refresh_resp.status_code == 401
    assert refresh_resp.json()["detail"] == "invalid_token_type"


def test_me_endpoint(auth_client):
    """GET /me with a valid access token returns the user profile."""
    reg_resp, email = _register_user(auth_client, nickname="AuthTestNick")
    assert reg_resp.status_code == 201
    access_token = reg_resp.json()["access_token"]

    me_resp = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == email
    assert data["nickname"] == "AuthTestNick"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


def test_me_without_token(auth_client):
    """GET /me without an Authorization header returns 401."""
    me_resp = auth_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401


def test_me_expired_token(auth_client):
    """GET /me with an expired access token returns 401."""
    # Create a token that expired 1 second ago
    from datetime import timedelta
    expired_token = create_access_token(
        str(uuid.uuid4()), expires_delta=timedelta(seconds=-1)
    )
    me_resp = auth_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert me_resp.status_code == 401
    assert me_resp.json()["detail"] == "令牌已过期"
