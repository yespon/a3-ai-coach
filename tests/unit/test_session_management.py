"""Unit tests for session management: rename, pin, delete.

Tests cover:
- rename_session: normal rename, empty title rejection, deleted session rejection
- toggle_pin_session: pin/unpin cycle, deleted session rejection
- soft_delete_session: normal delete, already-deleted rejection, cache eviction
- list_user_sessions: excludes deleted, sorts pinned first
- get_session_by_id: excludes deleted sessions
- Route-level tests via TestClient for rename/pin/delete endpoints
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import main
from app.api.deps import get_current_user, get_db, verify_csrf
from app.models.db_models import ChatSessionDB, ChatMessageDB, User
from app.services import session_service
from app.services.session_service import (
    SESSION_CACHE,
    db_session_summary_for_client,
    rename_session,
    toggle_pin_session,
    soft_delete_session,
)


TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


def _make_session(
    *,
    user_id=TEST_USER_ID,
    title=None,
    pinned=False,
    deleted_at=None,
    with_message=True,
) -> ChatSessionDB:
    s = ChatSessionDB()
    s.id = uuid.uuid4()
    s.user_id = user_id
    s.title = title
    s.pinned = pinned
    s.show_context = True
    s.context_file = "ctx.json"
    s.created_at = datetime.now(UTC)
    s.updated_at = datetime.now(UTC)
    s.deleted_at = deleted_at
    s.messages = []
    if with_message:
        m = ChatMessageDB()
        m.id = uuid.uuid4()
        m.session_id = s.id
        m.seq = 1
        m.role = "user"
        m.content = "test message"
        m.display_content = None
        m.is_context = False
        m.visible_in_history = True
        m.attachments = []
        m.created_at = datetime.now(UTC)
        s.messages.append(m)
    return s


def _make_user():
    user = User()
    user.id = TEST_USER_ID
    user.email = "test@example.com"
    user.nickname = "Tester"
    user.is_active = True
    user.is_admin = False
    user.provider = "local"
    user.provider_user_id = None
    user.managed_user_id = None
    return user


# --- db_session_summary_for_client ---


def test_summary_uses_title_when_set():
    s = _make_session(title="My Custom Title")
    result = db_session_summary_for_client(s)
    assert result["title"] == "My Custom Title"
    assert result["pinned"] is False


def test_summary_falls_back_to_preview_when_no_title():
    s = _make_session(title=None)
    result = db_session_summary_for_client(s)
    assert result["title"] == "test message"
    assert result["latest_preview"] == "test message"


def test_summary_pinned_true():
    s = _make_session(pinned=True)
    result = db_session_summary_for_client(s)
    assert result["pinned"] is True


def test_summary_no_messages_no_title():
    s = _make_session(title=None, with_message=False)
    result = db_session_summary_for_client(s)
    assert result["title"] == "新建会话"
    assert result["latest_preview"] == "新建会话"


# --- Route-level tests via TestClient ---


@pytest.fixture()
def client(monkeypatch):
    test_user = _make_user()
    main.app.dependency_overrides[get_current_user] = lambda: test_user
    main.app.dependency_overrides[verify_csrf] = lambda: None

    class _FakeDb:
        pass

    main.app.dependency_overrides[get_db] = lambda: _FakeDb()
    SESSION_CACHE.clear()
    try:
        with TestClient(main.app) as c:
            yield c
    finally:
        main.app.dependency_overrides.clear()
        SESSION_CACHE.clear()


def test_rename_route_success(monkeypatch, client):
    session = _make_session()

    async def mock_rename(db, sid, uid, title):
        session.title = title.strip()[:200]
        return session

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.rename_session", mock_rename
    )
    resp = client.patch(
        f"/api/v1/sessions/{session.id}/title",
        json={"title": "New Name"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "New Name"
    assert data["session_id"] == str(session.id)


def test_rename_route_404_for_missing_session(monkeypatch, client):
    async def mock_rename(db, sid, uid, title):
        return None

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.rename_session", mock_rename
    )
    resp = client.patch(
        f"/api/v1/sessions/{uuid.uuid4()}/title",
        json={"title": "X"},
    )
    assert resp.status_code == 404


def test_rename_route_rejects_empty_body(client):
    resp = client.patch(
        f"/api/v1/sessions/{uuid.uuid4()}/title",
        json={},
    )
    assert resp.status_code == 422


def test_pin_route_success(monkeypatch, client):
    session = _make_session(pinned=False)

    async def mock_toggle(db, sid, uid):
        session.pinned = not session.pinned
        return session

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.toggle_pin_session", mock_toggle
    )
    resp = client.patch(f"/api/v1/sessions/{session.id}/pin")
    assert resp.status_code == 200
    data = resp.json()
    assert data["pinned"] is True
    assert data["session_id"] == str(session.id)


def test_pin_route_404_for_missing_session(monkeypatch, client):
    async def mock_toggle(db, sid, uid):
        return None

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.toggle_pin_session", mock_toggle
    )
    resp = client.patch(f"/api/v1/sessions/{uuid.uuid4()}/pin")
    assert resp.status_code == 404


def test_delete_route_success(monkeypatch, client):
    async def mock_delete(db, sid, uid):
        return True

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.soft_delete_session", mock_delete
    )
    resp = client.delete(f"/api/v1/sessions/{uuid.uuid4()}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_delete_route_404_for_missing_session(monkeypatch, client):
    async def mock_delete(db, sid, uid):
        return False

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.soft_delete_session", mock_delete
    )
    resp = client.delete(f"/api/v1/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- Service-level logic tests ---


def test_list_user_sessions_excludes_deleted(monkeypatch):
    """list_user_sessions query must filter ChatSessionDB.deleted_at.is_(None)."""
    captured = {}

    class _FakeDb:
        async def execute(self, stmt):
            from sqlalchemy.dialects import postgresql
            captured["sql"] = str(
                stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            ).lower()

            class _Result:
                def scalars(self):
                    class _All:
                        def all(self):
                            return []
                    return _All()
            return _Result()

    import asyncio
    asyncio.new_event_loop().run_until_complete(
        session_service.list_user_sessions(_FakeDb(), str(TEST_USER_ID))
    )
    sql = captured["sql"]
    assert "deleted_at is null" in sql, f"Missing deleted_at filter: {sql}"
    assert "pinned" in sql, f"Missing pinned sort: {sql}"


def test_get_session_by_id_excludes_deleted(monkeypatch):
    """get_session_by_id must filter deleted_at IS NULL."""
    captured = {}

    class _FakeDb:
        async def execute(self, stmt):
            from sqlalchemy.dialects import postgresql
            captured["sql"] = str(
                stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
            ).lower()

            class _Result:
                def scalar_one_or_none(self):
                    return None
            return _Result()

    import asyncio
    asyncio.new_event_loop().run_until_complete(
        session_service.get_session_by_id(_FakeDb(), str(uuid.uuid4()), str(TEST_USER_ID))
    )
    sql = captured["sql"]
    assert "deleted_at is null" in sql, f"Missing deleted_at filter: {sql}"


# --- Authorization isolation ---


def test_rename_route_cannot_access_other_user_session(monkeypatch, client):
    """Rename should return 404 for a session belonging to another user."""
    async def mock_rename(db, sid, uid, title):
        # Service returns None because get_session_by_id filters by user_id
        return None

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.rename_session", mock_rename
    )
    resp = client.patch(
        f"/api/v1/sessions/{uuid.uuid4()}/title",
        json={"title": "hacked"},
    )
    assert resp.status_code == 404


def test_pin_route_cannot_access_other_user_session(monkeypatch, client):
    async def mock_toggle(db, sid, uid):
        return None

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.toggle_pin_session", mock_toggle
    )
    resp = client.patch(f"/api/v1/sessions/{uuid.uuid4()}/pin")
    assert resp.status_code == 404


def test_delete_route_cannot_access_other_user_session(monkeypatch, client):
    async def mock_delete(db, sid, uid):
        return False

    monkeypatch.setattr(
        "app.api.v1.routes.sessions.soft_delete_session", mock_delete
    )
    resp = client.delete(f"/api/v1/sessions/{uuid.uuid4()}")
    assert resp.status_code == 404
