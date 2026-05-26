import pytest
import json
import os


@pytest.fixture
def sample_policy_yaml(tmp_path):
    """Creates a sample policy YAML file and returns its path."""
    content = """
version: 1
defaultAction: ask
rules:
  - id: allow-safe-fetch
    tool: fetch
    match_args:
      url: "https://api.github.com/*"
    action: allow
    message: "Safe github fetch"
  - id: deny-rm
    tool: execute_command
    match_args:
      command: "rm -rf *"
    action: deny
    message: "Recursive delete blocked"
  - id: allow-all-ls
    tool: list_dir
    action: allow
"""
    path = tmp_path / "policy.yaml"
    path.write_text(content)
    return str(path)


@pytest.fixture
def sample_session_log(tmp_path):
    """Creates a sample JSONL session log and returns (session_id, log_dir)."""
    session_id = "20260526_120000_test1234"
    log_file = tmp_path / f"session_{session_id}.jsonl"

    events = [
        {
            "timestamp": "2026-05-26T12:00:00Z",
            "session_id": session_id,
            "sequence": 1,
            "event_type": "session_start",
            "payload": {"server_command": "python server.py", "policy_path": "policy.yaml"},
        },
        {
            "timestamp": "2026-05-26T12:00:01Z",
            "session_id": session_id,
            "sequence": 2,
            "event_type": "tool_call",
            "payload": {"id": 1, "name": "read_file", "arguments": {"path": "/tmp/foo"}},
        },
        {
            "timestamp": "2026-05-26T12:00:01Z",
            "session_id": session_id,
            "sequence": 3,
            "event_type": "policy_decision",
            "payload": {
                "id": 1, "name": "read_file", "action": "allow",
                "rule_id": None, "message": "Default allow",
                "risk_level": "low", "risk_tags": ["safe"],
            },
        },
        {
            "timestamp": "2026-05-26T12:00:02Z",
            "session_id": session_id,
            "sequence": 4,
            "event_type": "tool_result",
            "payload": {"id": 1, "result": {"content": "file contents"}},
        },
        {
            "timestamp": "2026-05-26T12:00:05Z",
            "session_id": session_id,
            "sequence": 5,
            "event_type": "session_end",
            "payload": {"exit_code": 0, "total_events": 4},
        },
    ]

    with open(log_file, "w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")

    return session_id, str(tmp_path)
