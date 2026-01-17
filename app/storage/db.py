import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, Iterable

DB_PATH = os.path.join(os.path.dirname(__file__), "ht_content.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            progress INTEGER NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS artifacts (
            job_id TEXT NOT NULL,
            type TEXT NOT NULL,
            path TEXT NOT NULL,
            metadata TEXT,
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
        """
    )
    conn.commit()
    conn.close()


def execute(query: str, params: Iterable[Any] = ()) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    conn.commit()
    conn.close()


def fetch_one(query: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(query, tuple(params))
    row = cur.fetchone()
    conn.close()
    return row


def insert_job(job_id: str, status: str, progress: int) -> None:
    execute(
        "INSERT INTO jobs (id, status, progress, started_at) VALUES (?, ?, ?, ?)",
        (job_id, status, progress, datetime.utcnow().isoformat()),
    )


def update_job(
    job_id: str,
    status: str | None = None,
    progress: int | None = None,
    error: str | None = None,
    finished: bool = False,
) -> None:
    updates = []
    params: list[Any] = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if error is not None:
        updates.append("error = ?")
        params.append(error)
    if finished:
        updates.append("finished_at = ?")
        params.append(datetime.utcnow().isoformat())
    if not updates:
        return
    params.append(job_id)
    query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = ?"
    execute(query, params)


def insert_artifact(job_id: str, artifact_type: str, path: str, metadata: Dict[str, Any]) -> None:
    execute(
        "INSERT INTO artifacts (job_id, type, path, metadata) VALUES (?, ?, ?, ?)",
        (job_id, artifact_type, path, json.dumps(metadata, ensure_ascii=True)),
    )


def fetch_job(job_id: str) -> sqlite3.Row | None:
    return fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))


def fetch_artifacts(job_id: str) -> list[sqlite3.Row]:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM artifacts WHERE job_id = ? ORDER BY rowid ASC", (job_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


init_db()
