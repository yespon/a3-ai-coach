"""Integration tests for CAS SSO authentication flow.

Tests cover:
- CAS login redirect
- CAS ticket exchange (with mocked SID)
- Single logout (SLO) back-channel
- Session cookie auth (get_current_user)
- Expired / revoked session handling
- auth_mode switch behavior
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import pg_available

pytestmark = pytest.mark.skipif(
    not pg_available(), reason="PostgreSQL not available"
)


# ---- Fixtures ----

@pytest.fixture()
def cas_client():
    """TestClient with no dependency overrides — real DB + session auth."""
    import main
    # Ensure no overrides so we get real get_db and get_current_user
    main.app.dependency_overrides.clear()
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


# ---- Helpers ----

MOCK_VALIDATE_RESPONSE_XML = """\
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationSuccess>
    <cas:user>EMP001</cas:user>
    <cas:attributes>
      <cas:RJXM>张三</cas:RJXM>
      <cas:RJEMAIL>zhangsan@ruijie.com.cn</cas:RJEMAIL>
      <cas:RJGH>EMP001</cas:RJGH>
    </cas:attributes>
  </cas:authenticationSuccess>
</cas:serviceResponse>"""

MOCK_VALIDATE_FAILURE_XML = """\
<cas:serviceResponse xmlns:cas="http://www.yale.edu/tp/cas">
  <cas:authenticationFailure code="INVALID_TICKET">
    Ticket ST-FAKE is not recognized
  </cas:authenticationFailure>
</cas:serviceResponse>"""

SAML_LOGOUT_REQUEST = """\
<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="_123" Version="2.0" IssueInstant="2026-06-13T12:00:00Z">
  <samlp:SessionIndex>ST-VALID-TICKET</samlp:SessionIndex>
</samlp:LogoutRequest>"""


def _mock_httpx_response(text: str, status_code: int = 200):
    """Create a mock httpx.Response-like object."""
    class MockResponse:
        def __init__(self):
            self.text = text
            self.status_code = status_code
    return MockResponse()


# ---- Test: CAS login redirect ----

def test_cas_login_redirect(cas_client: TestClient):
    """GET /api/v1/cas/login should return 302 to SID."""
    resp = cas_client.get("/api/v1/cas/login", follow_redirects=False)
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "sid.ruijie.com.cn/login" in location
    assert "service=" in location


# ---- Test: CAS ticket exchange ----

def test_cas_exchange_success(cas_client: TestClient):
    """POST /api/v1/cas/exchange with valid ticket should set session cookie."""
    mock_response = _mock_httpx_response(MOCK_VALIDATE_RESPONSE_XML)

    with patch("app.services.cas_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = cas_client.post(
            "/api/v1/cas/exchange",
            json={"ticket": "ST-VALID-TICKET"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["user"]["nickname"] == "张三"
    assert data["user"]["email"] == "zhangsan@ruijie.com.cn"

    # Check session cookie was set
    assert "sid_session" in resp.cookies

    # Check CSRF cookie was set (non-httponly)
    assert "csrf_token" in resp.cookies


def test_cas_exchange_invalid_ticket(cas_client: TestClient):
    """POST /api/v1/cas/exchange with invalid ticket should return 401."""
    mock_response = _mock_httpx_response(MOCK_VALIDATE_FAILURE_XML)

    with patch("app.services.cas_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        resp = cas_client.post(
            "/api/v1/cas/exchange",
            json={"ticket": "ST-FAKE"},
        )

    assert resp.status_code == 401


# ---- Test: Session cookie auth ----

def test_session_cookie_auth(cas_client: TestClient):
    """Authenticated request with valid session cookie should return user info."""
    # First do a CAS exchange to get a session
    mock_response = _mock_httpx_response(MOCK_VALIDATE_RESPONSE_XML)

    with patch("app.services.cas_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        exchange_resp = cas_client.post(
            "/api/v1/cas/exchange",
            json={"ticket": "ST-SESSION-TEST"},
        )
    assert exchange_resp.status_code == 200

    # Now use the session cookie to hit /auth/me
    session_cookie = exchange_resp.cookies.get("sid_session")
    assert session_cookie is not None

    me_resp = cas_client.get(
        "/api/v1/auth/me",
        cookies={"sid_session": session_cookie},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["nickname"] == "张三"


def test_no_cookie_returns_401(cas_client: TestClient):
    """Request without session cookie should return 401."""
    resp = cas_client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_invalid_cookie_returns_401(cas_client: TestClient):
    """Request with invalid session cookie should return 401."""
    resp = cas_client.get(
        "/api/v1/auth/me",
        cookies={"sid_session": "totally-bogus-token"},
    )
    assert resp.status_code == 401


# ---- Test: SLO ----

def test_cas_slo_revokes_session(cas_client: TestClient):
    """POST /api/v1/cas/slo with SAML LogoutRequest should revoke session."""
    # First create a session via exchange
    mock_response = _mock_httpx_response(MOCK_VALIDATE_RESPONSE_XML)

    with patch("app.services.cas_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        exchange_resp = cas_client.post(
            "/api/v1/cas/exchange",
            json={"ticket": "ST-VALID-TICKET"},
        )
    assert exchange_resp.status_code == 200
    session_cookie = exchange_resp.cookies.get("sid_session")

    # Now send SLO
    slo_resp = cas_client.post(
        "/api/v1/cas/slo",
        data={"logoutRequest": SAML_LOGOUT_REQUEST},
    )
    assert slo_resp.status_code == 200

    # Session should now be revoked — /auth/me should fail
    me_resp = cas_client.get(
        "/api/v1/auth/me",
        cookies={"sid_session": session_cookie},
    )
    assert me_resp.status_code == 401


# ---- Test: auth_mode switch ----

def test_auth_mode_sso_blocks_local(cas_client: TestClient):
    """When auth_mode=sso, local auth endpoints should return 403."""
    from app.core.config import settings

    original = settings.auth_mode
    try:
        settings.auth_mode = "sso"
        resp = cas_client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "pass123456"},
        )
        assert resp.status_code == 403
    finally:
        settings.auth_mode = original


def test_auth_mode_local_blocks_cas(cas_client: TestClient):
    """When auth_mode=local, CAS endpoints should return 403."""
    from app.core.config import settings

    original = settings.auth_mode
    try:
        settings.auth_mode = "local"
        resp = cas_client.get("/api/v1/cas/login", follow_redirects=False)
        assert resp.status_code == 403
    finally:
        settings.auth_mode = original


# ---- Test: Logout ----

def test_logout_revokes_session_and_redirects(cas_client: TestClient):
    """POST /auth/logout should revoke session, clear cookie, redirect to SID."""
    # Create a session via exchange
    mock_response = _mock_httpx_response(MOCK_VALIDATE_RESPONSE_XML)

    with patch("app.services.cas_service.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_cls.return_value = mock_client

        exchange_resp = cas_client.post(
            "/api/v1/cas/exchange",
            json={"ticket": "ST-LOGOUT-TEST"},
        )
    assert exchange_resp.status_code == 200
    session_cookie = exchange_resp.cookies.get("sid_session")

    # Logout
    logout_resp = cas_client.post(
        "/api/v1/auth/logout",
        cookies={"sid_session": session_cookie},
        follow_redirects=False,
    )
    # Should redirect to SID logout (auth_mode=both by default)
    assert logout_resp.status_code == 302
    assert "sid.ruijie.com.cn/logout" in logout_resp.headers["location"]
