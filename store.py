"""SQLite work log — fast reads for web and Telegram."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sync import DATA_DIR

DB_PATH = DATA_DIR / "worklog.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    from project_meta import ensure_meta_tables

    ensure_meta_tables()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                work_date TEXT NOT NULL,
                minutes INTEGER,
                period TEXT,
                project_id INTEGER,
                project_name TEXT NOT NULL,
                issue_ids TEXT NOT NULL DEFAULT '[]',
                linked_ticket INTEGER NOT NULL DEFAULT 0,
                raw_description TEXT NOT NULL,
                summary TEXT NOT NULL DEFAULT '',
                bullets TEXT NOT NULL DEFAULT '[]',
                structured TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_work_entries_date
                ON work_entries(work_date DESC, created_at DESC);

            CREATE TABLE IF NOT EXISTS bot_sessions (
                chat_id INTEGER PRIMARY KEY,
                step TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL
            );
            """
        )


def insert_entry(
    *,
    project_id: int | None,
    project_name: str,
    issue_ids: list[int],
    linked_ticket: bool,
    raw_description: str,
    summary: str,
    bullets: list[str],
    structured: dict[str, Any],
    minutes: int | None,
    period: str | None,
    work_date: str | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    day = work_date or date.today().isoformat()
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO work_entries (
                created_at, work_date, minutes, period, project_id, project_name,
                issue_ids, linked_ticket, raw_description, summary, bullets, structured
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                day,
                minutes,
                period,
                project_id,
                project_name,
                json.dumps(issue_ids),
                1 if linked_ticket else 0,
                raw_description,
                summary,
                json.dumps(bullets, ensure_ascii=False),
                json.dumps(structured, ensure_ascii=False),
            ),
        )
        return int(cur.lastrowid)


def list_entries(work_date: str | None = None, limit: int = 200) -> list[dict]:
    with connect() as conn:
        if work_date:
            rows = conn.execute(
                """
                SELECT * FROM work_entries
                WHERE work_date = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (work_date, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM work_entries
                ORDER BY work_date DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [_row_to_entry(row) for row in rows]


def entries_by_date(limit_days: int = 14) -> dict[str, list[dict]]:
    entries = list_entries(limit=500)
    grouped: dict[str, list[dict]] = {}
    for entry in entries:
        day = entry["work_date"]
        grouped.setdefault(day, []).append(entry)
    days = sorted(grouped.keys(), reverse=True)[:limit_days]
    return {day: grouped[day] for day in days}


def get_entry(entry_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM work_entries WHERE id = ?", (entry_id,)).fetchone()
    return _row_to_entry(row) if row else None


def update_entry(
    entry_id: int,
    *,
    work_date: str,
    minutes: int | None,
    period: str | None,
    raw_description: str,
    summary: str,
    bullets: list[str],
    structured: dict[str, Any],
) -> None:
    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE work_entries SET
                work_date = ?, minutes = ?, period = ?, raw_description = ?,
                summary = ?, bullets = ?, structured = ?
            WHERE id = ?
            """,
            (
                work_date,
                minutes,
                period,
                raw_description,
                summary,
                json.dumps(bullets, ensure_ascii=False),
                json.dumps(structured, ensure_ascii=False),
                entry_id,
            ),
        )
        if cur.rowcount == 0:
            raise LookupError("Entry not found.")


def _row_to_entry(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "work_date": row["work_date"],
        "minutes": row["minutes"],
        "period": row["period"],
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "issue_ids": json.loads(row["issue_ids"] or "[]"),
        "linked_ticket": bool(row["linked_ticket"]),
        "raw_description": row["raw_description"],
        "summary": row["summary"],
        "bullets": json.loads(row["bullets"] or "[]"),
        "structured": json.loads(row["structured"] or "{}"),
    }


def get_session(chat_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT step, data FROM bot_sessions WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    if not row:
        return None
    return {"step": row["step"], "data": json.loads(row["data"] or "{}")}


def save_session(chat_id: int, step: str, data: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO bot_sessions (chat_id, step, data, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                step = excluded.step,
                data = excluded.data,
                updated_at = excluded.updated_at
            """,
            (chat_id, step, json.dumps(data), now),
        )


def clear_session(chat_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM bot_sessions WHERE chat_id = ?", (chat_id,))
