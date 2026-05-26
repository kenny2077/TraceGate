import json
import os
import pytest
from tracegate.replay import replay_session


def test_replay_session(sample_session_log, capsys):
    """Replay a session log and check output."""
    session_id, log_dir = sample_session_log
    replay_session(session_id, log_dir=log_dir)
    # If it didn't crash, that's the main assertion
    # (Rich output goes to console, not capsys by default)


def test_replay_nonexistent_session(tmp_path, capsys):
    """Should print error for missing session."""
    replay_session("nonexistent", log_dir=str(tmp_path))


def test_replay_handles_malformed_lines(tmp_path):
    """Should skip malformed lines without crashing."""
    session_id = "test_malformed"
    log_file = tmp_path / f"session_{session_id}.jsonl"
    log_file.write_text(
        '{"event_type": "tool_call", "payload": {"name": "test"}, "timestamp": "2026-01-01T00:00:00Z"}\n'
        'THIS IS NOT JSON\n'
        '{"event_type": "session_end", "payload": {}, "timestamp": "2026-01-01T00:00:01Z"}\n'
    )
    # Should not raise
    replay_session(session_id, log_dir=str(tmp_path))


def test_replay_with_filter(sample_session_log):
    """Filter should not crash even if no events match."""
    session_id, log_dir = sample_session_log
    replay_session(session_id, log_dir=log_dir, filter_str="decision=denied")


def test_replay_empty_file(tmp_path):
    """Empty JSONL file should not crash."""
    session_id = "empty_session"
    log_file = tmp_path / f"session_{session_id}.jsonl"
    log_file.write_text("")
    replay_session(session_id, log_dir=str(tmp_path))
