# T5-1: /api and /api/v1 parity checks.


def test_health_v1_matches_legacy(client):
    legacy = client.get("/api/health")
    v1 = client.get("/api/v1/health")

    assert legacy.status_code == 200
    assert v1.status_code == 200
    assert v1.json() == legacy.json()


def test_create_session_v1_contract_matches_legacy(client):
    legacy = client.post("/api/sessions", json={"show_context_in_history": False})
    v1 = client.post("/api/v1/sessions", json={"show_context_in_history": False})

    assert legacy.status_code == 200
    assert v1.status_code == 200

    legacy_data = legacy.json()
    v1_data = v1.json()

    assert set(v1_data.keys()) == set(legacy_data.keys())
    assert v1_data["show_context_in_history"] == legacy_data["show_context_in_history"]
    assert isinstance(v1_data["session_id"], str)
    assert isinstance(v1_data["created_at"], str)
    assert isinstance(v1_data["history"], list)


def test_chat_fallback_v1_matches_legacy_semantics(client):
    legacy_created = client.post("/api/sessions", json={"show_context_in_history": False})
    v1_created = client.post("/api/v1/sessions", json={"show_context_in_history": False})

    legacy_session_id = legacy_created.json()["session_id"]
    v1_session_id = v1_created.json()["session_id"]

    legacy = client.post(
        "/api/chat",
        data={"session_id": legacy_session_id, "message": "测试fallback"},
    )
    v1 = client.post(
        "/api/v1/chat",
        data={"session_id": v1_session_id, "message": "测试fallback"},
    )

    assert legacy.status_code == 200
    assert v1.status_code == 200
    assert "当前未配置 OPENAI_API_KEY" in legacy.json().get("reply", "")
    assert "当前未配置 OPENAI_API_KEY" in v1.json().get("reply", "")
