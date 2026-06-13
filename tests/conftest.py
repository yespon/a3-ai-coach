import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import main
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.db_models import User
from app.services.session_service import SESSION_CACHE
from app.services.context_service import MATERIALS_CONTEXT_CACHE

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_test_user() -> User:
    """Create a User instance for dependency override (no DB needed)."""
    user = User()
    user.id = TEST_USER_ID
    user.email = "test@example.com"
    user.nickname = "TestUser"
    user.provider = "local"
    user.provider_user_id = None
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def isolate_runtime_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("MATERIALS_AUTOLOAD", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "materials_autoload", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    SESSION_CACHE.clear()
    MATERIALS_CONTEXT_CACHE.clear()
    yield
    SESSION_CACHE.clear()
    MATERIALS_CONTEXT_CACHE.clear()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """TestClient with auth overrides — no real DB or session cookies needed."""
    test_user = _make_test_user()
    main.app.dependency_overrides[get_current_user] = lambda: test_user
    main.app.dependency_overrides[get_db] = lambda: None
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def pg_available() -> bool:
    """Check whether PostgreSQL is reachable at the configured database URL."""
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    try:
        engine = create_async_engine(settings.database_url)
        async def _ping():
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                return True
        asyncio.run(asyncio.wait_for(_ping(), timeout=3))
        engine.dispose()
        return True
    except Exception:
        return False


def pytest_configure(config):
    """Register the requires_pg marker so pytest doesn't warn about unknown markers."""
    config.addinivalue_line("markers", "requires_pg: skip test if PostgreSQL is unavailable")


@pytest.fixture()
def auth_client() -> Generator[TestClient, None, None]:
    """TestClient that does NOT override auth — real session cookie + DB flow.
    Automatically skips if PostgreSQL is not reachable."""
    if not pg_available():
        pytest.skip("PostgreSQL not available")
    # No dependency overrides — we want the real get_db and get_current_user
    with TestClient(main.app) as c:
        yield c
