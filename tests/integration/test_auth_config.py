"""GET /auth/config exposes auth_mode to the login page (pre-auth, public)."""


def test_auth_config_returns_mode(client):
    resp = client.get("/api/v1/auth/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "auth_mode" in body
    assert body["auth_mode"] in ("sso", "local", "both")


def test_auth_config_reflects_setting(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "auth_mode", "sso")
    resp = client.get("/api/v1/auth/config")
    assert resp.status_code == 200
    assert resp.json()["auth_mode"] == "sso"
