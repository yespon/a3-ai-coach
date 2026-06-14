import uuid
from fastapi.testclient import TestClient

import main
from app.api.deps import get_current_user
from app.models.db_models import User


def _user(is_admin: bool):
    u = User(); u.id = uuid.uuid4(); u.email = "a@x.com"; u.is_active = True; u.is_admin = is_admin
    return u


def test_admin_whitelist_requires_admin(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(False)
    resp = client.get("/api/v1/admin/whitelist")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "admin_required"


def test_admin_template_download(client):
    main.app.dependency_overrides[get_current_user] = lambda: _user(True)
    resp = client.get("/api/v1/admin/whitelist/template")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
