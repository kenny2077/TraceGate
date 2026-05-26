import asyncio
import json
import pytest
from tracegate.proxy import run_proxy
from tracegate.policy import PolicyEngine
import os

# Dummy server script to test against
DUMMY_SERVER_CODE = """
import sys
import json

def main():
    for line in sys.stdin:
        try:
            req = json.loads(line)
            if req.get("method") == "initialize":
                resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"serverInfo": {"name": "dummy"}}}
            elif req.get("method") == "tools/call":
                resp = {"jsonrpc": "2.0", "id": req["id"], "result": {"content": [{"type": "text", "text": "success"}]}}
            else:
                resp = {"jsonrpc": "2.0", "id": req.get("id"), "error": {"code": -32601, "message": "Method not found"}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
        except:
            pass

if __name__ == "__main__":
    main()
"""

@pytest.mark.asyncio
async def test_proxy_e2e(tmp_path):
    server_path = tmp_path / "dummy_server.py"
    server_path.write_text(DUMMY_SERVER_CODE)
    
    log_dir = tmp_path / "logs"
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text("""
version: 1
defaultAction: ask
rules:
  - id: allow-test
    tool: test_tool
    action: allow
  - id: deny-test
    tool: bad_tool
    action: deny
""")
    
    # We will test the proxy by simulating an agent interacting with it via stdin/stdout
    # We can't easily mock sys.stdin/stdout for run_proxy since it uses sys.stdin directly for pipes,
    # so we will use subprocess to run the tracegate CLI instead.

    import subprocess
    import json
    
    # Run the proxy via subprocess
    proxy_cmd = ["python", "-m", "tracegate.cli", "proxy", "--policy", str(policy_path), "--log-dir", str(log_dir), "--", "python", str(server_path)]
    
    proc = subprocess.Popen(
        proxy_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Send initialize
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}) + "\\n")
    proc.stdin.flush()
    
    resp_init = json.loads(proc.stdout.readline())
    assert resp_init["id"] == 1
    assert "serverInfo" in resp_init["result"]
    
    # Send allowed tool call
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "test_tool"}}) + "\\n")
    proc.stdin.flush()
    
    resp_tool = json.loads(proc.stdout.readline())
    assert resp_tool["id"] == 2
    assert resp_tool["result"]["content"][0]["text"] == "success"
    
    # Send denied tool call
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "bad_tool"}}) + "\\n")
    proc.stdin.flush()
    
    resp_bad = json.loads(proc.stdout.readline())
    assert resp_bad["id"] == 3
    assert "error" in resp_bad
    assert "TraceGate blocked" in resp_bad["error"]["message"]
    
    # Send non-JSON
    proc.stdin.write("THIS IS NOT JSON\\n")
    proc.stdin.flush()
    
    # Non-json line passes through, server drops it, no response. Let's send a valid request to verify it's still alive.
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "test_tool"}}) + "\\n")
    proc.stdin.flush()
    
    resp_tool4 = json.loads(proc.stdout.readline())
    assert resp_tool4["id"] == 4
    
    proc.terminate()
    proc.wait(timeout=5)
    
    # Verify audit logs
    log_files = list(log_dir.glob("*.jsonl"))
    assert len(log_files) == 1
    with open(log_files[0], "r") as f:
        events = [json.loads(line) for line in f]
        
    event_types = [e["event_type"] for e in events]
    assert "session_start" in event_types
    assert "session_init" in event_types
    assert "tool_call" in event_types
    assert "policy_decision" in event_types
    assert "tool_result" in event_types
    assert "request_duration" in event_types
    assert "session_end" in event_types
