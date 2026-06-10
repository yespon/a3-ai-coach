# T3-1: session response contract snapshot.


def test_session_create_contract_keys(client):
    response = client.post("/api/sessions", json={"show_context_in_history": True})
    assert response.status_code == 200

    data = response.json()
    assert set(data.keys()) == {
        "session_id",
        "show_context_in_history",
        "created_at",
        "history",
    }
    assert isinstance(data["session_id"], str)
    assert isinstance(data["created_at"], str)
    assert isinstance(data["history"], list)
