"""Auth integration tests — session cookie + PostgreSQL flow.

These tests exercise the actual auth endpoints (register, login, logout, me)
with server-side session cookies. They require a running PostgreSQL instance
and will be automatically skipped when PG is unavailable.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.conftest import pg_available

pytestmark = pytest.mark.skipif(
    not pg_available(), reason="PostgreSQL not available"
)

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
    """Register a user and return (response, email)."""
    email = email or _unique_email()
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "nickname": nickname},
    )
    return resp, email


def _login_user(client: TestClient, email: str, password: str = "secret123"):
    """Login and return the response."""
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_register_success(auth_client):
    """Register returns 201 + session cookie + user info."""
    resp, email = _register_user(auth_client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["ok"] is True
    assert data["user"]["email"] == email
    # Session cookie must be set
    assert "sid_session" in resp.cookies


def test_register_duplicate_email(auth_client):
    """Registering the same email twice returns 409."""
    email = _unique_email()
    resp1, _ = _register_user(auth_client, email=email)
    assert resp1.status_code == 201

    resp2, _ = _register_user(auth_client, email=email)
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "email_already_exists"


def test_login_success(auth_client):
    """Login with correct credentials returns 200 + session cookie."""
    email = _unique_email()
    reg_resp, _ = _register_user(auth_client, email=email)
    assert reg_resp.status_code == 201

    login_resp = _login_user(auth_client, email)
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["ok"] is True
    assert data["user"]["email"] == email
    # Session cookie must be set
    assert "sid_session" in login_resp.cookies


def test_login_wrong_password(auth_client):
    """Login with wrong password returns 401."""
    email = _unique_email()
    reg_resp, _ = _register_user(auth_client, email=email)
    assert reg_resp.status_code == 201

    login_resp = _login_user(auth_client, email, password="wrong_password")
    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "invalid_credentials"


def test_login_nonexistent_user(auth_client):
    """Login with nonexistent email returns 401."""
    login_resp = _login_user(auth_client, "nonexistent@example.com")
    assert login_resp.status_code == 401
    assert login_resp.json()["detail"] == "invalid_credentials"


def test_me_with_session_cookie(auth_client):
    """GET /me with valid session cookie returns user profile."""
    reg_resp, email = _register_user(auth_client, nickname="CookieTestNick")
    assert reg_resp.status_code == 201
    session_cookie = reg_resp.cookies.get("sid_session")
    assert session_cookie is not None

    me_resp = auth_client.get(
        "/api/v1/auth/me",
        cookies={"sid_session": session_cookie},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == email
    assert data["nickname"] == "CookieTestNick"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


def test_me_without_cookie(auth_client):
    """GET /me without session cookie returns 401."""
    me_resp = auth_client.get("/api/v1/auth/me")
    assert me_resp.status_code == 401


def test_logout_revokes_session(auth_client):
    """POST /logout revokes session, /me returns 401 after."""
    reg_resp, _ = _register_user(auth_client)
    assert reg_resp.status_code == 201
    session_cookie = reg_resp.cookies.get("sid_session")

    # Logout
    logout_resp = auth_client.post(
        "/api/v1/auth/logout",
        cookies={"sid_session": session_cookie},
        follow_redirects=False,
    )
    # Should redirect to SID logout (auth_mode=both by default)
    assert logout_resp.status_code == 302

    # Session should now be invalid
    me_resp = auth_client.get(
        "/api/v1/auth/me",
        cookies={"sid_session": session_cookie},
    )
    assert me_resp.status_code == 401
