import os
import json
import pytest
from tracegate.store import SQLiteStore

def test_store_initialization(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = SQLiteStore(db_path)
    
    assert os.path.exists(db_path)
    
    with store.get_connection() as conn:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row["name"] for row in cur.fetchall()]
        
        assert "sessions" in tables
        assert "events" in tables

def test_log_event(tmp_path):
    db_path = str(tmp_path / "test.db")
    store = SQLiteStore(db_path)
    
    # 1. Log session start
    start_event = {
        "session_id": "sess_123",
        "sequence": 1,
        "timestamp": "2026-05-26T10:00:00Z",
        "event_type": "session_start",
        "payload": {
            "server_command": "test cmd",
            "policy_path": "policy.yaml",
            "log_file": "log.jsonl"
        }
    }
    store.log_event(start_event)
    
    with store.get_connection() as conn:
        # Check sessions table
        cur = conn.execute("SELECT * FROM sessions WHERE session_id = 'sess_123'")
        session = cur.fetchone()
        assert session is not None
        assert session["start_time"] == "2026-05-26T10:00:00Z"
        assert session["server_command"] == "test cmd"
        
        # Check events table
        cur = conn.execute("SELECT * FROM events WHERE session_id = 'sess_123'")
        events = cur.fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "session_start"
        
    # 2. Log regular event
    tool_event = {
        "session_id": "sess_123",
        "sequence": 2,
        "timestamp": "2026-05-26T10:00:01Z",
        "event_type": "tool_call",
        "payload": {
            "name": "my_tool"
        }
    }
    store.log_event(tool_event)
    
    with store.get_connection() as conn:
        cur = conn.execute("SELECT * FROM events WHERE session_id = 'sess_123'")
        assert len(cur.fetchall()) == 2
        
    # 3. Log session end
    end_event = {
        "session_id": "sess_123",
        "sequence": 3,
        "timestamp": "2026-05-26T10:00:02Z",
        "event_type": "session_end",
        "payload": {
            "exit_code": 0
        }
    }
    store.log_event(end_event)
    
    with store.get_connection() as conn:
        cur = conn.execute("SELECT * FROM sessions WHERE session_id = 'sess_123'")
        session = cur.fetchone()
        assert session["exit_code"] == 0
        assert session["end_time"] == "2026-05-26T10:00:02Z"

def test_backfill_from_jsonl(tmp_path):
    db_path = str(tmp_path / "test.db")
    jsonl_path = str(tmp_path / "test.jsonl")
    
    events = [
        {"session_id": "sess_backfill", "sequence": 1, "timestamp": "T1", "event_type": "session_start", "payload": {}},
        {"session_id": "sess_backfill", "sequence": 2, "timestamp": "T2", "event_type": "tool_call", "payload": {}}
    ]
    
    with open(jsonl_path, "w") as f:
        for evt in events:
            f.write(json.dumps(evt) + "\n")
            
    store = SQLiteStore(db_path)
    store.backfill_from_jsonl(jsonl_path)
    
    with store.get_connection() as conn:
        cur = conn.execute("SELECT * FROM events WHERE session_id = 'sess_backfill'")
        assert len(cur.fetchall()) == 2
        
    # Test idempotency (running backfill again shouldn't duplicate events)
    store.backfill_from_jsonl(jsonl_path)
    
    with store.get_connection() as conn:
        cur = conn.execute("SELECT * FROM events WHERE session_id = 'sess_backfill'")
        assert len(cur.fetchall()) == 2
