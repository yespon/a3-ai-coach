import uuid

import pytest
from sqlalchemy import text

from app.models.db_models import User
from app.services.user_service import upsert_sso_user


class FakeResult:
    def __init__(self, user): self.user = user
    def scalar_one_or_none(self): return self.user


class FakeSession:
    def __init__(self, user=None, existing_email_users=None):
        self.user = user; self.added = None
        self._existing = existing_email_users or []
    async def execute(self, stmt):
        s = str(stmt)
        if "users.provider" in s:
            return FakeResult(self.user)
        if "users.email" in s:
            return FakeListResult(self._existing)
        return FakeResult(self.user)
    def add(self, obj): self.added = obj; self.user = obj
    async def commit(self): pass
    async def refresh(self, obj): obj.id = getattr(obj, "id", uuid.uuid4())


class FakeListResult:
    def __init__(self, users): self.users = users
    def scalar_one_or_none(self): return self.users[0] if self.users else None
    def scalars(self): return FakeScalars(self.users)
    def all(self): return self.users


class FakeScalars:
    def __init__(self, items): self.items = items
    def all(self): return self.items


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


@pytest.mark.asyncio
async def test_create_sso_user_skips_email_when_local_user_has_same_email():
    db = FakeSession(existing_email_users=[User(email="liuyanpeng@ruijie.com.cn", provider="local")])
    user = await upsert_sso_user(db, "R09438", {"RJEMAIL": "liuyanpeng@ruijie.com.cn", "RJXM": "A"}, is_admin=False)
    assert user.email is None

