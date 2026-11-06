import os
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(os.getenv("AUDIT_DB", "audit.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    alert TEXT NOT NULL,
    model TEXT NOT NULL,
    diagnosis TEXT NOT NULL,
    proposed_action TEXT NOT NULL,
    status TEXT NOT NULL,
    decided_by TEXT,
    decided_at TEXT,
    result TEXT
)
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_incident(alert: str, model: str, diagnosis: str, action: str, status: str) -> int:
    """Store a new incident and return its id."""
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO incidents "
            "(created_at, alert, model, diagnosis, proposed_action, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), alert, model, diagnosis, action, status),
        )
        return cursor.lastrowid


def record_decision(incident_id: int, status: str, decided_by: str, result: str = "") -> bool:
    """Record a human decision. Only a pending incident can be decided, once."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE incidents SET status = ?, decided_by = ?, decided_at = ?, result = ? "
            "WHERE id = ? AND status = 'pending'",
            (status, decided_by, _now(), result, incident_id),
        )
        return cursor.rowcount == 1


def list_incidents(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    for item in list_incidents(10):
        print(
            f"#{item['id']} {item['created_at']} {item['status']:<12} "
            f"action={item['proposed_action']:<9} by={item['decided_by'] or '-'}"
        )