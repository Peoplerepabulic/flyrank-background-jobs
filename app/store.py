"""SQLite job store (stdlib sqlite3 only). All SQL lives in this module."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        INTEGER NOT NULL DEFAULT 0,
    result_json     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON jobs(status, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create data/ dir and the jobs table if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if d.get("result_json"):
        d["result"] = json.loads(d["result_json"])
    else:
        d["result"] = None
    d.pop("result_json", None)
    d["job_id"] = d.pop("id")
    return d


def create_job(job_id: str, idempotency_key: Optional[str]) -> dict[str, Any]:
    with _connect() as conn:
        now = _now()
        conn.execute(
            "INSERT INTO jobs (id, idempotency_key, status, progress, result_json, created_at, updated_at)"
            " VALUES (?, ?, 'pending', 0, NULL, ?, ?)",
            (job_id, idempotency_key, now, now),
        )
    return get_job(job_id)  # type: ignore[return-value]


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row) if row else None


def find_by_idempotency_key(key: str) -> Optional[dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE idempotency_key = ?", (key,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def set_status(job_id: str, status: str, progress: int) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, progress = ?, updated_at = ? WHERE id = ?",
            (status, progress, _now(), job_id),
        )


def complete_job(job_id: str, result: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'complete', progress = 100, result_json = ?, updated_at = ?"
            " WHERE id = ?",
            (json.dumps(result), _now(), job_id),
        )


def fail_job(job_id: str, error: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', result_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps({"error": error}), _now(), job_id),
        )


def cleanup_finished(older_than_hours: int = 1) -> int:
    """Delete complete/failed jobs older than the cutoff. Returns rows deleted."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM jobs WHERE status IN ('complete', 'failed') AND updated_at < ?",
            (cutoff,),
        )
        return cur.rowcount
