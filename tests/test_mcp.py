import pytest
import json
from tracegate.mcp import parse_message, JsonRpcRequest, JsonRpcResponse


class TestParseMessage:
    def test_parses_request(self):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "read_file", "arguments": {"path": "/tmp/foo"}},
        }).encode()
        msg = parse_message(payload)
        assert isinstance(msg, JsonRpcRequest)
        assert msg.method == "tools/call"
        assert msg.id == 1
        assert msg.params["name"] == "read_file"

    def test_parses_response_with_result(self):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "hello"}]},
        }).encode()
        msg = parse_message(payload)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.id == 1
        assert msg.result is not None

    def test_parses_response_with_error(self):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32600, "message": "Invalid Request"},
        }).encode()
        msg = parse_message(payload)
        assert isinstance(msg, JsonRpcResponse)
        assert msg.error["code"] == -32600

    def test_parses_notification(self):
        """JSON-RPC notifications have no id."""
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }).encode()
        msg = parse_message(payload)
        assert isinstance(msg, JsonRpcRequest)
        assert msg.id is None
        assert msg.method == "notifications/initialized"

    def test_returns_none_for_invalid_json(self):
        assert parse_message(b"not json") is None

    def test_returns_none_for_empty(self):
        assert parse_message(b"") is None

    def test_returns_none_for_non_jsonrpc(self):
        """A valid JSON object but not JSON-RPC."""
        payload = json.dumps({"key": "value"}).encode()
        assert parse_message(payload) is None

    def test_handles_string_id(self):
        payload = json.dumps({
            "jsonrpc": "2.0",
            "id": "abc-123",
            "method": "tools/call",
            "params": {},
        }).encode()
        msg = parse_message(payload)
        assert msg.id == "abc-123"
