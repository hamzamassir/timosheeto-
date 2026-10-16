#!/usr/bin/env python3
"""Telegram bot: a message becomes bullet points from the assigned-issue snapshot."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from brief import bullet_points, refresh_snapshot
from envfile import read_env
from sync import DATA_DIR

OFFSET_PATH = DATA_DIR / "telegram-offset"
TELEGRAM_LIMIT = 4000


def telegram(token: str, method: str, payload: dict | None = None, timeout: int = 60):
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Telegram {method} returned HTTP {exc.code}.") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Telegram {method} failed: {exc.reason}") from None
    if not body.get("ok"):
        raise RuntimeError(f"Telegram {method} was rejected.")
    return body.get("result")


def read_offset() -> int | None:
    if not OFFSET_PATH.is_file():
        return None
    raw = OFFSET_PATH.read_text().strip()
    return int(raw) if raw else None


def write_offset(offset: int) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OFFSET_PATH.write_text(f"{offset}\n")


def reply_text(text: str) -> str:
    stripped = text.strip()
    command, _, rest = stripped.partition(" ")
    name = command.split("@", 1)[0].lower()
    if name in {"/start", "/help"}:
        return (
            "Send a message and I will reply with bullet points from your open assigned issues. "
            "/sync refreshes the snapshot first."
        )
    if name == "/sync":
        snapshot = refresh_snapshot()
        note = (
            f"Refreshed: {snapshot['issue_total']} open issues, "
            f"{snapshot['project_total']} projects."
        )
        if not rest.strip():
            return note
        return note + "\n\n" + bullet_points(rest)
    return bullet_points(stripped)


def send_chunks(token: str, chat_id: int, text: str) -> None:
    remaining = text.strip() or "Empty reply."
    while remaining:
        chunk = remaining[:TELEGRAM_LIMIT]
        if len(remaining) > TELEGRAM_LIMIT:
            split = chunk.rfind("\n")
            if split > 0:
                chunk = chunk[:split]
        telegram(token, "sendMessage", {"chat_id": chat_id, "text": chunk})
        remaining = remaining[len(chunk) :].lstrip("\n")


def drain_pending(token: str) -> None:
    """Skip messages that arrived before this process started."""
    if read_offset() is not None:
        return
    updates = telegram(token, "getUpdates", {"timeout": 0}) or []
    if updates:
        write_offset(updates[-1]["update_id"] + 1)


def main() -> None:
    token = read_env().get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN in .env before starting the bot.")
    drain_pending(token)
    print("Telegram bot is polling.")
    while True:
        offset = read_offset()
        payload: dict = {"timeout": 50}
        if offset is not None:
            payload["offset"] = offset
        try:
            updates = telegram(token, "getUpdates", payload, timeout=70) or []
        except RuntimeError as exc:
            print(exc)
            time.sleep(5)
            continue
        for update in updates:
            write_offset(update["update_id"] + 1)
            message = update.get("message") or {}
            text = message.get("text") or ""
            chat = message.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None or not text:
                continue
            try:
                answer = reply_text(text)
            except Exception as exc:  # noqa: BLE001 — reply with the failure, never the token
                answer = str(exc)
            try:
                send_chunks(token, chat_id, answer)
            except RuntimeError as exc:
                print(exc)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit(130) from None
