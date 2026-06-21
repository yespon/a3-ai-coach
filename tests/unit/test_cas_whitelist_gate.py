import pytest
from fastapi import HTTPException

from app.api.v1.routes.cas import ensure_sso_allowed
from app.models.db_models import ManagedUserDB


@pytest.mark.asyncio
async def test_admin_employee_uses_managed_user_gate(monkeypatch):
    profile = ManagedUserDB(employee_no="1001", primary_role="admin", enabled=True)

    async def allow(db, employee_no, is_admin_employee_no):
        assert employee_no == "1001"
        assert is_admin_employee_no is True
        return profile

    monkeypatch.setattr("app.api.v1.routes.cas.ensure_managed_user_allowed", allow)
    assert await ensure_sso_allowed(object(), "1001", True) is profile


def test_normalize_employee_no_trims_whitespace():
    from app.api.v1.routes.cas import normalize_employee_no
    assert normalize_employee_no(" 1001 \n") == "1001"


@pytest.mark.asyncio
async def test_non_managed_employee_rejected(monkeypatch):
    async def deny(db, employee_no, is_admin_employee_no):
        raise PermissionError("当前账号未开通 A3工作法AI教练 访问权限，请联系管理员开通。")

    monkeypatch.setattr("app.api.v1.routes.cas.ensure_managed_user_allowed", deny)
    with pytest.raises(HTTPException) as exc:
        await ensure_sso_allowed(object(), "1002", False)
    assert exc.value.status_code == 403
    assert exc.value.detail == "当前账号未开通 A3工作法AI教练 访问权限，请联系管理员开通。"


@pytest.mark.asyncio
async def test_managed_employee_allowed(monkeypatch):
    profile = ManagedUserDB(employee_no="1003", primary_role="student", enabled=True)

    async def allow(db, employee_no, is_admin_employee_no):
        return profile

    monkeypatch.setattr("app.api.v1.routes.cas.ensure_managed_user_allowed", allow)
    assert await ensure_sso_allowed(object(), "1003", False) is profile
