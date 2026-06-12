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
from app.models.db_models import User
from app.services.session_service import SESSIONS
from app.services.context_service import MATERIALS_CONTEXT_CACHE

TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_test_user() -> User:
    """Create a User instance for dependency override (no DB needed)."""
    user = User()
    user.id = TEST_USER_ID
    user.email = "test@example.com"
    user.is_active = True
    return user


@pytest.fixture(autouse=True)
def isolate_runtime_state(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("MATERIALS_AUTOLOAD", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "materials_autoload", False)
    monkeypatch.setattr(settings, "openai_api_key", "")
    SESSIONS.clear()
    MATERIALS_CONTEXT_CACHE.clear()
    yield
    SESSIONS.clear()
    MATERIALS_CONTEXT_CACHE.clear()


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    # Override auth dependencies so tests don't need a real DB or JWT tokens.
    # get_current_user_id depends on get_current_user, so overriding
    # get_current_user is sufficient — no need to also override get_db.
    # This will be replaced in Task 7 when auth integration tests are added.
    test_user = _make_test_user()
    main.app.dependency_overrides[get_current_user] = lambda: test_user
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
