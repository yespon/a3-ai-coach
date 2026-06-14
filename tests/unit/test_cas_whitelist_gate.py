import pytest
from fastapi import HTTPException

from app.api.v1.routes.cas import ensure_sso_allowed


@pytest.mark.asyncio
async def test_admin_employee_bypasses_whitelist(monkeypatch):
    async def boom(db, employee_no):
        raise AssertionError("should not query whitelist")
    monkeypatch.setattr("app.api.v1.routes.cas.is_employee_allowed", boom)
    await ensure_sso_allowed(object(), "1001", True)


@pytest.mark.asyncio
async def test_non_whitelisted_employee_rejected(monkeypatch):
    async def deny(db, employee_no): return False
    monkeypatch.setattr("app.api.v1.routes.cas.is_employee_allowed", deny)
    with pytest.raises(HTTPException) as exc:
        await ensure_sso_allowed(object(), "1002", False)
    assert exc.value.status_code == 403
    assert exc.value.detail == "当前账号未开通岗标 AI 教练访问权限，请联系管理员开通。"


@pytest.mark.asyncio
async def test_whitelisted_employee_allowed(monkeypatch):
    async def allow(db, employee_no): return True
    monkeypatch.setattr("app.api.v1.routes.cas.is_employee_allowed", allow)
    await ensure_sso_allowed(object(), "1003", False)
