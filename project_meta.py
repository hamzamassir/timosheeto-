"""Project colors, logos, and app settings (SQLite)."""

from __future__ import annotations

import re
from pathlib import Path

from envfile import read_env
from store import connect
from sync import DATA_DIR

LOGO_DIR = DATA_DIR / "logos"
ALLOWED_MODELS = (
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-pro-latest",
)
DEFAULT_HEX = (
    "#5B8DEF",
    "#9B6BFF",
    "#3CCB7F",
    "#F5A524",
    "#F45B69",
    "#2EC4B6",
    "#FF8FAB",
    "#8ECAE6",
    "#E9C46A",
    "#90BE6D",
)


def ensure_meta_tables() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS project_meta (
                project_id INTEGER PRIMARY KEY,
                color TEXT NOT NULL,
                logo_ext TEXT
            );
            """
        )


def default_color(project_id: int) -> str:
    return DEFAULT_HEX[project_id % len(DEFAULT_HEX)]


def normalize_color(value: str, project_id: int) -> str:
    cleaned = value.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", cleaned):
        return cleaned.upper()
    return default_color(project_id)


def get_setting(key: str, default: str = "") -> str:
    ensure_meta_tables()
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    ensure_meta_tables()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def get_gemini_model() -> str:
    stored = get_setting("gemini_model", "").strip()
    if stored:
        return stored
    return (read_env().get("GEMINI_MODEL") or "gemini-flash-latest").strip()


def project_color(project_id: int | None) -> str:
    ensure_meta_tables()
    if project_id is None:
        return default_color(0)
    with connect() as conn:
        row = conn.execute(
            "SELECT color FROM project_meta WHERE project_id = ?",
            (int(project_id),),
        ).fetchone()
    if row:
        return normalize_color(row["color"], int(project_id))
    return default_color(int(project_id))


def set_project_color(project_id: int, color: str) -> None:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color.strip()):
        raise ValueError("Color must be #RRGGBB.")
    ensure_meta_tables()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO project_meta (project_id, color, logo_ext)
            VALUES (?, ?, NULL)
            ON CONFLICT(project_id) DO UPDATE SET color = excluded.color
            """,
            (int(project_id), color.strip().upper()),
        )


def logo_path(project_id: int) -> Path | None:
    ensure_meta_tables()
    with connect() as conn:
        row = conn.execute(
            "SELECT logo_ext FROM project_meta WHERE project_id = ?",
            (int(project_id),),
        ).fetchone()
    if not row or not row["logo_ext"]:
        return None
    path = LOGO_DIR / f"{int(project_id)}{row['logo_ext']}"
    return path if path.is_file() else None


def save_logo(project_id: int, data: bytes, content_type: str) -> None:
    if len(data) > 500_000:
        raise ValueError("Logo must be under 500 KB.")
    mapping = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
    }
    ext = mapping.get(content_type.split(";")[0].strip().lower())
    if not ext:
        raise ValueError("Logo must be PNG, JPEG, or WebP.")
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    pid = int(project_id)
    for old in LOGO_DIR.glob(f"{pid}.*"):
        old.unlink(missing_ok=True)
    (LOGO_DIR / f"{pid}{ext}").write_bytes(data)
    color = project_color(pid)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO project_meta (project_id, color, logo_ext)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET logo_ext = excluded.logo_ext
            """,
            (pid, color, ext),
        )


def all_project_meta(projects: list[dict]) -> list[dict]:
    return [
        {
            "id": int(p.get("id") or 0),
            "name": p.get("name") or "",
            "color": project_color(int(p.get("id") or 0)),
            "has_logo": logo_path(int(p.get("id") or 0)) is not None,
        }
        for p in projects
    ]
