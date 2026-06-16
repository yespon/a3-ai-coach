import uuid

import pytest
from sqlalchemy import text

from app.models.db_models import ManagedUserDB, User
from app.services.user_service import upsert_sso_user
from tests.unit.test_managed_user_service import FakeDb


class FakeResult:
    def __init__(self, user): self.user = user
    def scalar_one_or_none(self): return self.user


class FakeSession:
    def __init__(self, user=None, existing_email_users=None):
        self.user = user; self.added = None
        self._existing = existing_email_users or []
        self._execute_calls = 0
    async def execute(self, stmt):
        self._execute_calls += 1
        if self._execute_calls == 1:
            return FakeResult(self.user)
        return FakeListResult(self._existing)
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
    local_user = User(email="liuyanpeng@ruijie.com.cn", provider="local")
    local_user.id = uuid.uuid4()
    db = FakeSession(existing_email_users=[local_user])
    user = await upsert_sso_user(db, "R09438", {"RJEMAIL": "liuyanpeng@ruijie.com.cn", "RJXM": "A"}, is_admin=False)
    assert user.email is None


@pytest.mark.asyncio
async def test_existing_sso_user_keeps_email_when_same_email_belongs_to_itself():
    existing = User(provider="cas", provider_user_id="R09438", email="liuyanpeng@ruijie.com.cn", password_hash=None)
    existing.id = uuid.uuid4()
    db = FakeSession(existing, existing_email_users=[existing])
    user = await upsert_sso_user(db, "R09438", {"RJEMAIL": "liuyanpeng@ruijie.com.cn", "RJXM": "A"}, is_admin=False)
    assert user.email == "liuyanpeng@ruijie.com.cn"


@pytest.mark.asyncio
async def test_existing_sso_user_preserves_old_email_when_new_email_belongs_to_other_user():
    existing = User(provider="cas", provider_user_id="R09438", email="old@ruijie.com.cn", password_hash=None)
    existing.id = uuid.uuid4()
    other = User(email="liuyanpeng@ruijie.com.cn", provider="local")
    other.id = uuid.uuid4()
    db = FakeSession(existing, existing_email_users=[other])
    user = await upsert_sso_user(db, "R09438", {"RJEMAIL": "liuyanpeng@ruijie.com.cn", "RJXM": "A"}, is_admin=False)
    assert user.email == "old@ruijie.com.cn"


@pytest.mark.asyncio
async def test_upsert_sso_user_links_managed_profile_on_create():
    profile = ManagedUserDB(employee_no="1001", email="a@example.com", name="张三")
    db = FakeDb([None, None])
    user = await upsert_sso_user(db, "1001", {"RJEMAIL": "a@example.com", "RJXM": "张三"}, managed_user=profile)
    assert user.managed_user is profile
    assert user.managed_user_id == profile.id


@pytest.mark.asyncio
async def test_upsert_sso_user_links_managed_profile_on_existing_user():
    profile = ManagedUserDB(employee_no="1001", email="a@example.com", name="张三")
    user = User(provider="cas", provider_user_id="1001", email="old@example.com", nickname="Old", password_hash=None)
    db = FakeDb([user, None])
    updated = await upsert_sso_user(db, "1001", {"RJEMAIL": "a@example.com", "RJXM": "张三"}, managed_user=profile)
    assert updated is user
    assert updated.managed_user is profile
    assert updated.managed_user_id == profile.id

