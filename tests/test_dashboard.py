import json
import pytest
from fastapi.testclient import TestClient

try:
    from tracegate.dashboard.api import app
except ImportError:
    app = None

@pytest.fixture
def test_sessions_dir(tmp_path):
    log_dir = tmp_path / "sessions"
    log_dir.mkdir()
    
    # Create a dummy session file
    session_file = log_dir / "session_20260526-dummy-1234.jsonl"
    events = [
        {"timestamp": "2026-05-26T10:00:00Z", "event_type": "session_start", "payload": {"server_command": "dummy"}},
        {"timestamp": "2026-05-26T10:00:01Z", "event_type": "tool_call", "payload": {"id": 1, "name": "test_tool", "arguments": {}}},
        {"timestamp": "2026-05-26T10:00:01Z", "event_type": "policy_decision", "payload": {"action": "allow"}},
        {"timestamp": "2026-05-26T10:00:02Z", "event_type": "tool_result", "payload": {"id": 1, "result": "ok"}},
        {"timestamp": "2026-05-26T10:00:02Z", "event_type": "session_end", "payload": {"exit_code": 0}}
    ]
    with open(session_file, "w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")
            
    return log_dir

@pytest.mark.skipif(app is None, reason="Dashboard dependencies not installed")
def test_get_sessions(test_sessions_dir):
    client = TestClient(app)
    response = client.get(f"/api/sessions?log_dir={test_sessions_dir}")
    assert response.status_code == 200
    data = response.json()
    
    assert len(data) == 1
    session = data[0]
    assert session["id"] == "20260526-dummy-1234"
    assert session["event_count"] == 5
    assert "2026-05-26T10:00:00" in session["first_timestamp"]

@pytest.mark.skipif(app is None, reason="Dashboard dependencies not installed")
def test_get_session_events(test_sessions_dir):
    client = TestClient(app)
    response = client.get(f"/api/sessions/20260526-dummy-1234?log_dir={test_sessions_dir}")
    assert response.status_code == 200
    events = response.json()
    
    assert len(events) == 5
    assert events[0]["event_type"] == "session_start"
    assert events[-1]["event_type"] == "session_end"

@pytest.mark.skipif(app is None, reason="Dashboard dependencies not installed")
def test_get_session_events_not_found(test_sessions_dir):
    client = TestClient(app)
    response = client.get(f"/api/sessions/does-not-exist?log_dir={test_sessions_dir}")
    assert response.status_code == 404
