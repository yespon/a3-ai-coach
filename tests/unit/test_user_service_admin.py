import uuid

import pytest

from app.models.db_models import User
from app.services.user_service import upsert_sso_user


class FakeResult:
    def __init__(self, user): self.user = user
    def scalar_one_or_none(self): return self.user


class FakeSession:
    def __init__(self, user=None): self.user = user; self.added = None
    async def execute(self, stmt): return FakeResult(self.user)
    def add(self, obj): self.added = obj; self.user = obj
    async def commit(self): pass
    async def refresh(self, obj): obj.id = getattr(obj, "id", uuid.uuid4())


@pytest.mark.asyncio
async def test_upsert_sso_user_marks_admin_on_create():
    db = FakeSession()
    user = await upsert_sso_user(db, "1001", {"RJEMAIL": "a@example.com", "RJXM": "A"}, is_admin=True)
    assert user.is_admin is True


@pytest.mark.asyncio
async def test_upsert_sso_user_only_promotes_admin_never_demotes():
    existing = User(provider="cas", provider_user_id="1001", email="a@example.com", password_hash=None)
    existing.is_admin = True
    db = FakeSession(existing)
    user = await upsert_sso_user(db, "1001", {}, is_admin=False)
    assert user.is_admin is True
