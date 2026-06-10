# T0 baseline tests: health check and session creation contract.


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_session_returns_contract(client):
    response = client.post("/api/sessions", json={"show_context_in_history": False})
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data.get("session_id"), str)
    assert len(data["session_id"]) > 0
    assert data["show_context_in_history"] is False
    assert isinstance(data.get("created_at"), str)
    assert isinstance(data.get("history"), list)
