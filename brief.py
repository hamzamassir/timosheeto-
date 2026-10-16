"""One Gemini bullet-point call over the assigned-issue snapshot."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from envfile import ENV_PATH, read_env
from sync import SNAPSHOT_PATH, RedmineClient, load_env, sync_once, write_snapshot

MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
_refresh_lock = threading.Lock()

PROMPT = """You turn the user's message into bullet points about their open Redmine issues.

Rules:
- Reply with bullet points only. Each line starts with "- ".
- When you name a ticket or a project, use only the assigned open issues listed below.
- If the message matches none of them, say that in one bullet.
- Do not invent issue ids, projects, or statuses.
- Keep each bullet to one sentence.

Assigned open issues:
{issues}

User message:
{message}
"""


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.is_file():
        raise RuntimeError("No snapshot yet. Refresh from the page or run python3 sync.py.")
    return json.loads(SNAPSHOT_PATH.read_text())


def refresh_snapshot() -> dict:
    with _refresh_lock:
        env = load_env(ENV_PATH)
        client = RedmineClient(env["REDMINE_URL"], env["REDMINE_API_KEY"])
        snapshot = sync_once(client)
        write_snapshot(snapshot)
        return snapshot


def _issue_catalog(snapshot: dict) -> str:
    lines: list[str] = []
    for issue in snapshot.get("issues") or []:
        project = (issue.get("project") or {}).get("name") or ""
        priority = (issue.get("priority") or {}).get("name") or ""
        status = (issue.get("status") or {}).get("name") or ""
        description = " ".join((issue.get("description") or "").split())
        if len(description) > 400:
            description = description[:400] + "…"
        lines.append(
            f"#{issue.get('id')} | {project} | {priority} | {status} | "
            f"{issue.get('subject') or ''} | {description}"
        )
    return "\n".join(lines)


def bullet_points(message: str, snapshot: dict | None = None) -> str:
    text = message.strip()
    if not text:
        raise RuntimeError("Write a message first.")
    api_key = read_env().get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env.")
    if snapshot is None:
        snapshot = load_snapshot()
    prompt = PROMPT.format(issues=_issue_catalog(snapshot), message=text)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    request = urllib.request.Request(
        GEMINI_URL,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Gemini returned HTTP {exc.code}.") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Gemini: {exc.reason}") from None
    candidates = body.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") if candidates else None) or []
    reply = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    if not reply:
        raise RuntimeError("Gemini returned an empty reply.")
    return reply
