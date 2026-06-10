# T2 middleware tests for Commit 1 (config/logger extraction).


from pathlib import Path
import time


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = PROJECT_ROOT / "logs" / "app.log"


def test_request_id_is_echoed_when_provided(client):
    response = client.get("/api/health", headers={"x-request-id": "req-fixed-123"})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == "req-fixed-123"


def test_request_id_is_generated_when_missing(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    request_id = response.headers.get("x-request-id")
    assert isinstance(request_id, str)
    assert len(request_id) == 12


def test_request_logs_started_and_finished(client):
    before = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""
    client.get("/api/health")

    delta = ""
    for _ in range(20):
        after = LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else ""
        delta = after[len(before):]
        if "request_started" in delta and "request_finished" in delta:
            break
        time.sleep(0.05)

    assert "request_started" in delta
    assert "request_finished" in delta
