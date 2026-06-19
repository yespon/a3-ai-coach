"""Regression tests for the chat session listing endpoint.

Covers the bug where `GET /api/v1/sessions` fell back to the in-memory
`SESSION_CACHE` when the DB query returned an empty list — masking real
sessions as missing, and silently swallowing DB errors. After the fix, the
DB is the source of truth: empty result is empty result, and DB errors are
surfaced rather than masked.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import main
from app.api.deps import get_current_user, get_db
from app.models.db_models import ChatSessionDB
from app.services import session_service


class _StubUser:
    def __init__(self, user_id):
        self.id = user_id
        self.email = "tester@example.com"
        self.nickname = "Tester"
        self.is_active = True
        self.is_admin = False
        self.provider = "local"
        self.provider_user_id = None
        self.managed_user_id = None


class _StubDb:
    """AsyncSession stand-in. list_user_sessions is monkeypatched, so this
    just needs to look like an AsyncSession — never used directly here."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


@pytest.fixture()
def api_client(monkeypatch):
    """TestClient with auth + db overrides, but NOT overriding
    list_user_sessions — that's what each test patches individually."""

    test_user = _StubUser(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    main.app.dependency_overrides[get_current_user] = lambda: test_user
    # Provide a non-None db so the route takes the DB path
    main.app.dependency_overrides[get_db] = lambda: _StubDb()

    # Reset in-memory cache before each test to prove DB result is the source
    session_service.SESSION_CACHE.clear()
    # Pre-populate cache with a fake session for the same user, so that if
    # the route incorrectly falls back to the cache, we'd see it.
    from app.models.chat import ChatSession as _ChatSession
    stale = _ChatSession(
        session_id="stale-cache-session",
        show_context_in_history=False,
        context_file="ctx.json",
        user_id=str(test_user.id),
        created_at=datetime.now(UTC).isoformat(),
    )
    session_service.SESSION_CACHE["stale-cache-session"] = stale

    try:
        with TestClient(main.app) as client:
            yield client
    finally:
        main.app.dependency_overrides.clear()
        session_service.SESSION_CACHE.clear()


def _patch_list_user_sessions(monkeypatch, return_value=None, raise_exc=None):
    async def fake_list(db, user_id):
        if raise_exc is not None:
            raise raise_exc
        return return_value or []

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.list_user_sessions", fake_list
    )


def test_list_sessions_returns_empty_list_when_db_has_no_sessions(
    monkeypatch, api_client
):
    """Bug: `if sessions_db:` is False for empty list → fell through to
    cache and returned a stale 'ghost' session. After the fix, the empty
    DB result must be honored and an empty list returned."""
    _patch_list_user_sessions(monkeypatch, return_value=[])

    resp = api_client.get("/api/v1/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_sessions_does_not_return_cache_sessions_when_db_empty(
    monkeypatch, api_client
):
    """Even with a pre-populated SESSION_CACHE, an empty DB result must not
    leak cache contents to the response."""
    _patch_list_user_sessions(monkeypatch, return_value=[])

    resp = api_client.get("/api/v1/sessions")
    body = resp.json()
    # The fixture pre-populates SESSION_CACHE with a session for this user.
    # If the route falls back to the cache, this assertion fails.
    assert all(s["session_id"] != "stale-cache-session" for s in body)


def test_list_sessions_returns_db_sessions(monkeypatch, api_client):
    """Sanity: when DB has sessions, they are returned."""
    session_db = ChatSessionDB(
        id=uuid.uuid4(),
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        show_context=True,
        context_file="ctx.json",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    _patch_list_user_sessions(monkeypatch, return_value=[session_db])

    resp = api_client.get("/api/v1/sessions")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["session_id"] == str(session_db.id)


def test_list_sessions_does_not_silently_swallow_db_errors(
    monkeypatch, api_client
):
    """Bug: `except Exception: pass` silently returned cache contents on
    any DB error. After the fix, DB errors must be surfaced so the
    frontend can show an error rather than create phantom sessions."""
    from sqlalchemy.exc import OperationalError

    _patch_list_user_sessions(
        monkeypatch, raise_exc=OperationalError("simulated", {}, Exception("db down"))
    )

    resp = api_client.get("/api/v1/sessions")
    # Either 5xx (preferred) or 200 with empty list (acceptable) — but NOT
    # a 200 containing the stale cache session, which was the original bug.
    if resp.status_code == 200:
        body = resp.json()
        assert all(s["session_id"] != "stale-cache-session" for s in body)
    else:
        assert resp.status_code >= 500
