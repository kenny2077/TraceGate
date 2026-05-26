import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="TraceGate Dashboard API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEFAULT_LOG_DIR = os.path.join(Path.home(), ".tracegate", "sessions")

from tracegate.store import get_store

@app.on_event("startup")
async def startup_event():
    # Run backfill of old JSONL sessions into SQLite
    if os.path.isdir(DEFAULT_LOG_DIR):
        store = get_store(DEFAULT_LOG_DIR)
        jsonl_files = [f for f in os.listdir(DEFAULT_LOG_DIR) if f.endswith(".jsonl")]
        for fname in jsonl_files:
            store.backfill_from_jsonl(os.path.join(DEFAULT_LOG_DIR, fname))

class SessionSummary(BaseModel):
    id: str
    filename: str
    event_count: int
    first_timestamp: str

@app.get("/api/sessions", response_model=List[SessionSummary])
def get_sessions(log_dir: str = DEFAULT_LOG_DIR):
    if not os.path.isdir(log_dir):
        return []
    
    store = get_store(log_dir)
    sessions = []
    
    try:
        with store.get_connection() as conn:
            # Join with events to get event count
            cur = conn.execute("""
                SELECT s.session_id, s.start_time, s.log_file, COUNT(e.id) as event_count
                FROM sessions s
                LEFT JOIN events e ON s.session_id = e.session_id
                GROUP BY s.session_id
                ORDER BY s.start_time DESC
            """)
            
            for row in cur.fetchall():
                fname = os.path.basename(row["log_file"]) if row["log_file"] else f"session_{row['session_id']}.jsonl"
                
                sessions.append(SessionSummary(
                    id=row["session_id"],
                    filename=fname,
                    event_count=row["event_count"] or 0,
                    first_timestamp=row["start_time"]
                ))
    except Exception as e:
        # Fallback to empty list on error
        pass
        
    return sessions

class GlobalStats(BaseModel):
    total_sessions: int
    total_events: int
    tool_counts: Dict[str, int]
    risk_distribution: Dict[str, int]

@app.get("/api/stats", response_model=GlobalStats)
def get_global_stats(log_dir: str = DEFAULT_LOG_DIR):
    store = get_store(log_dir)
    stats = {
        "total_sessions": 0,
        "total_events": 0,
        "tool_counts": {},
        "risk_distribution": {"critical": 0, "high": 0, "medium": 0, "low": 0, "none": 0}
    }
    
    try:
        with store.get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) as count FROM sessions")
            stats["total_sessions"] = cur.fetchone()["count"]
            
            cur = conn.execute("SELECT COUNT(*) as count FROM events")
            stats["total_events"] = cur.fetchone()["count"]
            
            # Fetch policy decisions to count tool usage and risk
            cur = conn.execute("SELECT payload FROM events WHERE event_type = 'policy_decision'")
            for row in cur.fetchall():
                payload = json.loads(row["payload"])
                tool_name = payload.get("name", "unknown")
                risk = payload.get("risk_level") or "none"
                
                stats["tool_counts"][tool_name] = stats["tool_counts"].get(tool_name, 0) + 1
                if risk in stats["risk_distribution"]:
                    stats["risk_distribution"][risk] += 1
                else:
                    stats["risk_distribution"][risk] = 1
                    
    except Exception as e:
        logger.error(f"Failed to fetch stats: {e}")
        
    return stats

@app.get("/api/sessions/{session_id}")
def get_session_events(session_id: str, log_dir: str = DEFAULT_LOG_DIR):
    store = get_store(log_dir)
    events = []
    
    try:
        with store.get_connection() as conn:
            cur = conn.execute(
                "SELECT timestamp, event_type, payload FROM events WHERE session_id = ? ORDER BY sequence ASC",
                (session_id,)
            )
            rows = cur.fetchall()
            
            if not rows:
                raise HTTPException(status_code=404, detail="Session not found")
                
            for row in rows:
                events.append({
                    "timestamp": row["timestamp"],
                    "event_type": row["event_type"],
                    "payload": json.loads(row["payload"])
                })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return events

# Serve static files for frontend
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)
    
    # Create a basic index.html placeholder
    with open(os.path.join(STATIC_DIR, "index.html"), "w") as f:
        f.write("<html><body><h1>TraceGate Dashboard Starting...</h1></body></html>")

app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

def run_server(host="127.0.0.1", port=8080):
    import uvicorn
    uvicorn.run("tracegate.dashboard.api:app", host=host, port=port, reload=False)
