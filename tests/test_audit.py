import os
import json
import pytest
from tracegate.audit import AuditLogger, redact_value, truncate_content


class TestRedactValue:
    def test_redacts_sensitive_keys(self):
        raw = {
            "normal_arg": "hello",
            "api_key": "sk-12345",
            "nested": {
                "password": "my_super_secret",
                "safe": 42,
            },
        }
        redacted = redact_value(raw)
        assert redacted["normal_arg"] == "hello"
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["nested"]["password"] == "[REDACTED]"
        assert redacted["nested"]["safe"] == 42

    def test_redacts_lists_of_dicts(self):
        """Regression: redact_dict (old name) didn't handle lists."""
        raw = {
            "items": [
                {"token": "secret123", "name": "safe"},
                {"api_key": "sk-abc", "value": 42},
            ]
        }
        redacted = redact_value(raw)
        assert redacted["items"][0]["token"] == "[REDACTED]"
        assert redacted["items"][0]["name"] == "safe"
        assert redacted["items"][1]["api_key"] == "[REDACTED]"
        assert redacted["items"][1]["value"] == 42

    def test_handles_primitives(self):
        assert redact_value("hello") == "hello"
        assert redact_value(42) == 42
        assert redact_value(None) is None

    def test_handles_empty_dict(self):
        assert redact_value({}) == {}

    def test_handles_nested_lists(self):
        raw = [{"secret": "abc"}, [{"password": "xyz"}]]
        redacted = redact_value(raw)
        assert redacted[0]["secret"] == "[REDACTED]"
        assert redacted[1][0]["password"] == "[REDACTED]"


class TestTruncateContent:
    def test_truncates_long_strings(self):
        long_str = "x" * 1000
        result = truncate_content(long_str, max_len=100)
        assert len(result) < 200
        assert "truncated" in result

    def test_preserves_short_strings(self):
        assert truncate_content("short") == "short"

    def test_truncates_nested(self):
        data = {"content": "x" * 1000}
        result = truncate_content(data, max_len=100)
        assert "truncated" in result["content"]


class TestAuditLogger:
    def test_creates_log_file(self, tmp_path):
        log_dir = str(tmp_path / "logs")
        al = AuditLogger(log_dir=log_dir)
        al.log_tool_call("fetch", {"url": "https://example.com"}, call_id="1")

        assert os.path.exists(al.log_file)
        with open(al.log_file) as f:
            lines = f.readlines()
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["event_type"] == "tool_call"

    def test_session_start_end(self, tmp_path):
        al = AuditLogger(
            log_dir=str(tmp_path),
            server_command="python server.py",
            policy_path="policy.yaml",
        )
        al.log_session_start()
        al.log_session_end(exit_code=0)

        with open(al.log_file) as f:
            lines = f.readlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event_type"] == "session_start"
        assert json.loads(lines[1])["event_type"] == "session_end"

    def test_log_tool_result_with_string(self, tmp_path):
        """Regression: old audit crashed when result was a string, not a dict."""
        al = AuditLogger(log_dir=str(tmp_path))
        al.log_tool_result(call_id="1", result="some string result")

        with open(al.log_file) as f:
            event = json.loads(f.readline())
        assert event["payload"]["result"] == "some string result"

    def test_log_tool_result_truncates_large_content(self, tmp_path):
        al = AuditLogger(log_dir=str(tmp_path))
        al.log_tool_result(call_id="1", result={"content": "x" * 5000})

        with open(al.log_file) as f:
            event = json.loads(f.readline())
        assert "truncated" in event["payload"]["result"]["content"]

    def test_full_flow(self, tmp_path):
        al = AuditLogger(log_dir=str(tmp_path))
        al.log_tool_call("fetch", {"url": "https://example.com"}, call_id="1")
        al.log_policy_decision("1", "fetch", "allow", "rule_1", "Allowed by rule")
        al.log_tool_result("1", result={"status": 200})

        with open(al.log_file) as f:
            lines = f.readlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["event_type"] == "tool_call"
        assert json.loads(lines[1])["event_type"] == "policy_decision"
        assert json.loads(lines[2])["event_type"] == "tool_result"

    def test_policy_decision_includes_risk(self, tmp_path):
        al = AuditLogger(log_dir=str(tmp_path))
        al.log_policy_decision(
            "1", "run_command", "deny", "block-rm", "Blocked",
            risk_level="high", risk_tags=["destructive"],
        )
        with open(al.log_file) as f:
            event = json.loads(f.readline())
        assert event["payload"]["risk_level"] == "high"
        assert event["payload"]["risk_tags"] == ["destructive"]
