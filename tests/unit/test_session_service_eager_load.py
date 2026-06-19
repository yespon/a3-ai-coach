"""Verify that session-listing queries eagerly load the `messages` relationship.

Background: in async SQLAlchemy, accessing a lazy-loaded relationship on
an attached instance from synchronous code raises `MissingGreenlet`,
which the FastAPI route would surface as a 500. The summary builder
`db_session_summary_for_client` iterates `session.messages`, so the
listing query MUST eagerly load them.
"""

from app.services import session_service


def _has_eager_load_for(stmt, attr_name: str) -> bool:
    """Check whether the Select statement has an ORM load option whose
    path includes *attr_name* (e.g. ``"messages"``)."""
    for opt in getattr(stmt, "_with_options", ()):
        path = getattr(opt, "path", None)
        if path is not None and attr_name in str(path):
            return True
    return False


def test_list_user_sessions_uses_selectinload():
    """list_user_sessions must eagerly load ChatSessionDB.messages."""
    captured = {}

    class _FakeDb:
        async def execute(self_db, stmt):
            captured["stmt"] = stmt

            class _Result:
                def scalars(self_r):
                    class _All:
                        def all(self_a):
                            return []
                    return _All()
            return _Result()

    import asyncio
    asyncio.new_event_loop().run_until_complete(
        session_service.list_user_sessions(_FakeDb(), "user-id")
    )
    assert _has_eager_load_for(captured["stmt"], "messages"), (
        "list_user_sessions must eagerly load .messages to avoid "
        "MissingGreenlet in async context"
    )


def test_get_session_by_id_uses_selectinload():
    """get_session_by_id must eagerly load ChatSessionDB.messages."""
    captured = {}

    class _FakeDb:
        async def execute(self_db, stmt):
            captured["stmt"] = stmt

            class _Result:
                def scalar_one_or_none(self_r):
                    return None
            return _Result()

    import asyncio
    asyncio.new_event_loop().run_until_complete(
        session_service.get_session_by_id(_FakeDb(), "sid", "user-id")
    )
    assert _has_eager_load_for(captured["stmt"], "messages"), (
        "get_session_by_id must eagerly load .messages to avoid "
        "MissingGreenlet in async context"
    )
