# T4-2: stream done payload semantics.

import json


def _extract_sse_payloads(raw_text: str) -> list[dict]:
    payloads: list[dict] = []
    for line in raw_text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        payloads.append(json.loads(data))
    return payloads


def test_chat_stream_emits_done_with_reply_and_history(client):
    created = client.post("/api/sessions", json={"show_context_in_history": False})
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    response = client.post(
        "/api/chat/stream",
        data={"session_id": session_id, "message": "请简单回复一个词"},
    )
    assert response.status_code == 200

    payloads = _extract_sse_payloads(response.text)
    assert any(p.get("type") == "delta" for p in payloads)

    done = next((p for p in payloads if p.get("type") == "done"), None)
    assert done is not None
    assert isinstance(done.get("reply"), str)
    assert len(done["reply"]) > 0
    assert isinstance(done.get("history"), list)
