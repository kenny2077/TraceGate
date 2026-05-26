import json
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

try:
    from tracegate.sse import app, state, run_sse_proxy
    from tracegate.policy import PolicyEngine
    from tracegate.audit import AuditLogger
except ImportError:
    app = None

@pytest.fixture
def mock_state(tmp_path):
    log_dir = tmp_path / "sessions"
    log_dir.mkdir()
    
    state.target_url = "http://fake-target:8000"
    state.policy_engine = None
    state.audit_logger = AuditLogger(log_dir=str(log_dir), server_command="test")
    state.target_post_url = "http://fake-target:8000/message"
    state.pending_requests = {}
    state.session_memory = {}
    return state

@pytest.mark.asyncio
@pytest.mark.skipif(app is None, reason="Dashboard dependencies not installed")
async def test_sse_message_endpoint_allow(mock_state):
    # Mock the client post method to simulate successful forward
    mock_post = AsyncMock()
    mock_post.return_value.status_code = 200
    mock_post.return_value.content = b"OK"
    mock_post.return_value.headers = {}
    
    mock_state.client = AsyncMock()
    mock_state.client.post = mock_post
    
    client = TestClient(app)
    
    msg = {
        "jsonrpc": "2.0",
        "id": "req-1",
        "method": "tools/call",
        "params": {
            "name": "safe_tool",
            "arguments": {}
        }
    }
    
    # Since we are testing with TestClient synchronously, we need to mock out the async _forward_to_target
    with patch("tracegate.sse._forward_to_target") as mock_forward:
        mock_forward.return_value = "Forwarded"
        response = client.post("/message", json=msg)
        
        assert response.status_code == 200
        mock_forward.assert_called_once()
        assert "req-1" in mock_state.pending_requests

@pytest.mark.asyncio
@pytest.mark.skipif(app is None, reason="Dashboard dependencies not installed")
async def test_sse_message_endpoint_deny(mock_state, tmp_path):
    policy_file = tmp_path / "policy.yaml"
    policy_file.write_text("""
version: 1
rules:
  - id: "block_unsafe"
    tool: unsafe_tool
    action: deny
""")
    mock_state.policy_engine = PolicyEngine(str(policy_file))
    
    client = TestClient(app)
    
    msg = {
        "jsonrpc": "2.0",
        "id": "req-2",
        "method": "tools/call",
        "params": {
            "name": "unsafe_tool",
            "arguments": {}
        }
    }
    
    response = client.post("/message", json=msg)
    
    assert response.status_code == 403
    assert "TraceGate blocked" in response.json()["detail"]
    assert "req-2" not in mock_state.pending_requests
