import json
import os
import datetime
import uuid
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# Maximum characters to keep from tool result content in the audit log
MAX_RESULT_PREVIEW = 500

SENSITIVE_PATTERNS = [
    re.compile(r'password', re.IGNORECASE),
    re.compile(r'secret', re.IGNORECASE),
    re.compile(r'token', re.IGNORECASE),
    re.compile(r'api[_-]?key', re.IGNORECASE),
    re.compile(r'auth', re.IGNORECASE),
    re.compile(r'credential', re.IGNORECASE),
    re.compile(r'private[_-]?key', re.IGNORECASE),
]


def redact_value(data: Any) -> Any:
    """Recursively redact sensitive keys in dicts and lists."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            if any(p.search(k) for p in SENSITIVE_PATTERNS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_value(v)
        return redacted
    elif isinstance(data, list):
        return [redact_value(item) for item in data]
    else:
        return data


def truncate_content(data: Any, max_len: int = MAX_RESULT_PREVIEW) -> Any:
    """Truncate string content for audit logging. Preserves structure."""
    if isinstance(data, str) and len(data) > max_len:
        return data[:max_len] + f"... [truncated, {len(data)} chars total]"
    elif isinstance(data, dict):
        return {k: truncate_content(v, max_len) for k, v in data.items()}
    elif isinstance(data, list):
        return [truncate_content(item, max_len) for item in data]
    return data


class AuditLogger:
    def __init__(self, log_dir: Optional[str] = None, server_command: Optional[str] = None,
                 policy_path: Optional[str] = None):
        from pathlib import Path

        self.log_dir = log_dir or os.path.join(Path.home(), ".tracegate", "sessions")
        self.session_id = (
            f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            f"_{uuid.uuid4().hex[:8]}"
        )
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, f"session_{self.session_id}.jsonl")
        self.sequence = 0
        self._server_command = server_command
        self._policy_path = policy_path
        
        from tracegate.store import get_store
        self.store = get_store(self.log_dir)

    def log_session_start(self):
        """Emit a session_start event with metadata."""
        self.log_event("session_start", {
            "server_command": self._server_command,
            "policy_path": self._policy_path,
            "log_file": self.log_file,
        })

    def log_session_end(self, exit_code: Optional[int] = None):
        """Emit a session_end event."""
        self.log_event("session_end", {
            "exit_code": exit_code,
            "total_events": self.sequence,  # will be incremented by log_event, so this is pre-increment
        })

    def log_event(self, event_type: str, payload: Any):
        """Logs an event to the JSONL file. Handles dicts, lists, and primitives."""
        self.sequence += 1
        redacted_payload = redact_value(payload) if isinstance(payload, (dict, list)) else payload

        event = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "session_id": self.session_id,
            "sequence": self.sequence,
            "event_type": event_type,
            "payload": redacted_payload,
        }

        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
            
            # Write to SQLite store
            self.store.log_event(event)
        except Exception as e:
            logger.error(f"Failed to write to audit log: {e}")

    async def log_event_async(self, event_type: str, payload: Any):
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.log_event, event_type, payload)

    def log_tool_call(self, tool_name: str, arguments: Dict[str, Any], call_id: Any):
        self.log_event("tool_call", {
            "id": call_id,
            "name": tool_name,
            "arguments": arguments,
        })

    async def log_tool_call_async(self, tool_name: str, arguments: Dict[str, Any], call_id: Any):
        await self.log_event_async("tool_call", {
            "id": call_id,
            "name": tool_name,
            "arguments": arguments,
        })

    def log_tool_result(self, call_id: Any, result: Any = None, error: Any = None):
        payload: Dict[str, Any] = {"id": call_id}
        if result is not None:
            payload["result"] = truncate_content(result)
        if error is not None:
            payload["error"] = error
        self.log_event("tool_result", payload)

    async def log_tool_result_async(self, call_id: Any, result: Any = None, error: Any = None):
        payload: Dict[str, Any] = {"id": call_id}
        if result is not None:
            payload["result"] = truncate_content(result)
        if error is not None:
            payload["error"] = error
        await self.log_event_async("tool_result", payload)

    def log_policy_decision(
        self, call_id: Any, tool_name: str, action: str,
        rule_id: Optional[str], message: str,
        risk_level: Optional[str] = None, risk_tags: Optional[List[str]] = None,
    ):
        payload: Dict[str, Any] = {
            "id": call_id,
            "name": tool_name,
            "action": action,
            "rule_id": rule_id,
            "message": message,
        }
        if risk_level:
            payload["risk_level"] = risk_level
        if risk_tags:
            payload["risk_tags"] = risk_tags
        self.log_event("policy_decision", payload)

    async def log_policy_decision_async(
        self, call_id: Any, tool_name: str, action: str,
        rule_id: Optional[str], message: str,
        risk_level: Optional[str] = None, risk_tags: Optional[List[str]] = None,
    ):
        payload: Dict[str, Any] = {
            "id": call_id,
            "name": tool_name,
            "action": action,
            "rule_id": rule_id,
            "message": message,
        }
        if risk_level:
            payload["risk_level"] = risk_level
        if risk_tags:
            payload["risk_tags"] = risk_tags
        await self.log_event_async("policy_decision", payload)
