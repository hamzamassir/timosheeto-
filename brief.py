"""Redmine snapshot helpers and Gemini structuring for work notes."""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request

from envfile import ENV_PATH, read_env
from sync import SNAPSHOT_PATH, RedmineClient, load_env, sync_once, write_snapshot

DEFAULT_MODEL = "gemini-flash-latest"
FALLBACK_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")
API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_refresh_lock = threading.Lock()

WORK_NOTE_PROMPT = """You turn a messy work note into a clear log entry.

Context:
- Project: {project_name}
- Tickets: {tickets}
- User paragraph: {paragraph}

Return ONLY valid JSON (no markdown fences) with this shape:
{{
  "summary": "one short sentence for a timeline",
  "bullets": ["2 to 5 concise bullets in past tense"],
  "minutes": null or integer estimate of time spent,
  "period": "morning" | "afternoon" | "evening" | "unknown"
}}

Use the user's language when natural. Do not invent ticket ids. If time is unclear, use null for minutes and "unknown" for period.
"""


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.is_file():
        raise RuntimeError("No snapshot yet. Run /sync or refresh from the web app.")
    return json.loads(SNAPSHOT_PATH.read_text())


def refresh_snapshot() -> dict:
    with _refresh_lock:
        env = load_env(ENV_PATH)
        client = RedmineClient(env["REDMINE_URL"], env["REDMINE_API_KEY"])
        snapshot = sync_once(client)
        write_snapshot(snapshot)
        return snapshot


def _gemini_models() -> list[str]:
    env = read_env()
    preferred = (env.get("GEMINI_MODEL") or DEFAULT_MODEL).strip()
    models: list[str] = []
    for name in (preferred, DEFAULT_MODEL, *FALLBACK_MODELS):
        if name and name not in models:
            models.append(name)
    return models


def _gemini_json(prompt: str) -> dict:
    api_key = read_env().get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env.")
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    body: dict | None = None
    last_error = ""
    for model in _gemini_models():
        url = f"{API_BASE}/{model}:generateContent"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode())
                break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            try:
                message = json.loads(detail).get("error", {}).get("message", "")
            except json.JSONDecodeError:
                message = detail[:200]
            last_error = f"{model}: HTTP {exc.code}" + (f" — {message}" if message else "")
            if exc.code in {404, 429, 503}:
                continue
            raise RuntimeError(f"Gemini returned HTTP {exc.code}.") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach Gemini: {exc.reason}") from None
    if body is None:
        raise RuntimeError(
            "Gemini could not run (model unavailable or busy). "
            f"Set GEMINI_MODEL in .env. Last error: {last_error}"
        )
    candidates = body.get("candidates") or []
    parts = ((candidates[0].get("content") or {}).get("parts") if candidates else None) or []
    raw = "\n".join(part.get("text", "") for part in parts if part.get("text")).strip()
    if not raw:
        raise RuntimeError("Gemini returned an empty reply.")
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("Gemini did not return valid JSON.") from None
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini JSON must be an object.")
    return parsed


def structure_work_note(
    *,
    project_name: str,
    issue_ids: list[int],
    issue_subjects: list[str],
    paragraph: str,
) -> dict:
    tickets = "none"
    if issue_ids:
        pairs = [f"#{i} {s}" for i, s in zip(issue_ids, issue_subjects, strict=False)]
        tickets = "; ".join(pairs)
    prompt = WORK_NOTE_PROMPT.format(
        project_name=project_name,
        tickets=tickets,
        paragraph=paragraph.strip(),
    )
    data = _gemini_json(prompt)
    bullets = data.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    bullets = [str(b).strip() for b in bullets if str(b).strip()]
    minutes = data.get("minutes")
    if minutes is not None:
        try:
            minutes = int(minutes)
        except (TypeError, ValueError):
            minutes = None
    period = str(data.get("period") or "unknown").lower()
    if period not in {"morning", "afternoon", "evening", "unknown"}:
        period = "unknown"
    return {
        "summary": str(data.get("summary") or "").strip() or paragraph.strip()[:120],
        "bullets": bullets,
        "minutes": minutes,
        "period": period,
    }
