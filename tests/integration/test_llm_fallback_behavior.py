# T4-3: fallback behavior when OPENAI_API_KEY is missing.


def test_chat_falls_back_without_openai_key(client):
    created = client.post("/api/sessions", json={"show_context_in_history": False})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    response = client.post(
        "/api/chat",
        data={"session_id": session_id, "message": "测试fallback"},
    )
    assert response.status_code == 200

    reply = response.json().get("reply", "")
    assert "当前未配置 OPENAI_API_KEY" in reply
