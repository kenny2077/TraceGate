import sqlite3
import json
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
        
    def get_connection(self):
        """Get a new SQLite connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency since proxy writes while dashboard reads
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
        
    def _init_db(self):
        """Create schema if it doesn't exist."""
        with self.get_connection() as conn:
            # Sessions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    server_command TEXT,
                    policy_path TEXT,
                    log_file TEXT,
                    exit_code INTEGER,
                    end_time TEXT
                )
            """)
            
            # Events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions (session_id)
                )
            """)
            
            # Indexes for faster dashboard queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session_id ON events(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
            
    def log_event(self, event: Dict[str, Any]):
        """Store an event in the SQLite database."""
        event_type = event.get("event_type")
        session_id = event.get("session_id")
        timestamp = event.get("timestamp")
        payload = event.get("payload", {})
        
        try:
            with self.get_connection() as conn:
                # Upsert session first to satisfy foreign key constraints
                if event_type == "session_start":
                    conn.execute(
                        "INSERT OR IGNORE INTO sessions (session_id, start_time, server_command, policy_path, log_file) VALUES (?, ?, ?, ?, ?)",
                        (session_id, timestamp, payload.get("server_command"), payload.get("policy_path"), payload.get("log_file"))
                    )
                    # In case it already existed via another event, update fields
                    conn.execute(
                        "UPDATE sessions SET start_time=?, server_command=?, policy_path=?, log_file=? WHERE session_id=?",
                        (timestamp, payload.get("server_command"), payload.get("policy_path"), payload.get("log_file"), session_id)
                    )
                else:
                    # Create a skeleton session if it doesn't exist yet
                    conn.execute(
                        "INSERT OR IGNORE INTO sessions (session_id, start_time) VALUES (?, ?)",
                        (session_id, timestamp)
                    )
                    
                if event_type == "session_end":
                    conn.execute(
                        "UPDATE sessions SET exit_code = ?, end_time = ? WHERE session_id = ?",
                        (payload.get("exit_code"), timestamp, session_id)
                    )
                    
                # Now insert the event
                conn.execute(
                    "INSERT INTO events (session_id, sequence, timestamp, event_type, payload) VALUES (?, ?, ?, ?, ?)",
                    (session_id, event.get("sequence"), timestamp, event_type, json.dumps(payload))
                )
        except Exception as e:
            logger.error(f"Failed to log event to SQLite: {e}")
            
    def backfill_from_jsonl(self, jsonl_file: str):
        """Parse a JSONL file and backfill any missing events into the SQLite DB."""
        import os
        if not os.path.exists(jsonl_file):
            return
            
        with open(jsonl_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    # We can rely on UNIQUE constraints/upserts if we want, but since
                    # events don't have a unique ID other than session_id + sequence,
                    # we should check if it exists first to be safe during backfill.
                    with self.get_connection() as conn:
                        cur = conn.execute(
                            "SELECT 1 FROM events WHERE session_id = ? AND sequence = ?",
                            (event["session_id"], event["sequence"])
                        )
                        if not cur.fetchone():
                            self.log_event(event)
                except Exception as e:
                    logger.debug(f"Backfill skipped malformed line: {e}")

_global_store = None

def get_store(log_dir: str) -> SQLiteStore:
    global _global_store
    if _global_store is None:
        import os
        db_path = os.path.join(log_dir, "tracegate.db")
        _global_store = SQLiteStore(db_path)
    return _global_store
