#!/usr/bin/env python3
"""Assigned-issue browser on port 8090. Basic auth comes from .env."""

from __future__ import annotations

import base64
import html
import os
import secrets
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from brief import bullet_points, load_snapshot, refresh_snapshot
from envfile import read_env

HOST = "0.0.0.0"
PORT = 8090

PAGE_CSS = """
:root {
  color-scheme: dark;
  --ink: #f4f7fb;
  --muted: rgba(244, 247, 251, 0.72);
  --glass: rgba(0, 0, 0, 0.40);
  --glass-deep: rgba(255, 255, 255, 0.05);
  --glass-top: rgba(255, 255, 255, 0.10);
  --line: rgba(255, 255, 255, 0.20);
  --shadow: 0 24px 60px rgba(88, 130, 255, 0.16);
  --field: rgba(0, 0, 0, 0.40);
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --ink: #142033;
    --muted: rgba(20, 32, 51, 0.72);
    --glass: rgba(255, 255, 255, 0.80);
    --glass-deep: rgba(255, 255, 255, 0.50);
    --glass-top: rgba(255, 255, 255, 0.80);
    --line: rgba(255, 255, 255, 0.20);
    --shadow: 0 24px 50px rgba(40, 70, 140, 0.12);
    --field: rgba(255, 255, 255, 0.55);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  font: 16px/1.45 "Segoe UI", sans-serif;
  background:
    radial-gradient(900px 480px at 10% -10%, rgba(120, 162, 255, 0.45), transparent 60%),
    radial-gradient(700px 420px at 100% 0%, rgba(186, 124, 255, 0.35), transparent 55%),
    linear-gradient(160deg, #1b2744 0%, #121826 48%, #1a1030 100%);
}
main { max-width: 980px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 1.8rem; margin: 0 0 6px; }
h2 { font-size: 1.15rem; margin: 0 0 12px; }
p { margin: 0; }
a { color: inherit; }
.muted { color: var(--muted); }
.stack { position: relative; margin: 22px 0; }
.stack .layer {
  position: absolute;
  inset: 0;
  border-radius: 28px;
  background: var(--glass-deep);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
}
.stack .mid {
  inset: 8px;
  border-radius: 22px;
  background: var(--glass);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}
.panel, .project {
  position: relative;
  background: var(--glass-top);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--line);
  border-radius: 18px;
  box-shadow: var(--shadow);
}
.panel { padding: 18px; }
header.panel { margin-bottom: 8px; }
.project { padding: 16px 16px 8px; margin-top: 14px; }
.head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-end; }
label { display: block; margin-bottom: 8px; }
textarea, button {
  font: inherit;
  color: var(--ink);
}
textarea {
  width: 100%;
  min-height: 96px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--field);
  backdrop-filter: blur(8px);
  resize: vertical;
}
.actions { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
button {
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.16);
  backdrop-filter: blur(12px);
  border-radius: 999px;
  padding: 8px 16px;
  box-shadow: var(--shadow);
  cursor: pointer;
}
.bullets { margin: 12px 0 0; padding-left: 18px; }
.bullets li { margin: 6px 0; }
.issue {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--line);
}
.meta { color: var(--muted); font-size: 0.85rem; }
.count {
  font-size: 0.85rem;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.08);
}
.error { color: #ffb4b4; margin-top: 10px; }
"""


def setting(env: dict[str, str], key: str) -> str:
    return env.get(key) or os.environ.get(key) or ""


def format_when(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def bullet_items(reply: str) -> list[str]:
    items: list[str] = []
    for line in reply.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            stripped = stripped[2:].strip()
        items.append(stripped)
    return items or [reply.strip()]


def render_page(snapshot: dict | None, message: str = "", reply: str = "", error: str = "") -> str:
    if snapshot is None:
        body = "<p class='muted'>No snapshot yet. Refresh to pull assigned open issues.</p>"
        summary = "No snapshot"
    else:
        redmine = (snapshot.get("redmine_url") or "").rstrip("/")
        by_project: dict[int, list] = {}
        for issue in snapshot.get("issues") or []:
            project_id = int((issue.get("project") or {}).get("id") or 0)
            by_project.setdefault(project_id, []).append(issue)
        blocks: list[str] = []
        for project in snapshot.get("projects") or []:
            issues = by_project.get(int(project.get("id") or 0), [])
            rows: list[str] = []
            for issue in issues:
                issue_id = issue.get("id")
                priority = html.escape((issue.get("priority") or {}).get("name") or "")
                status = html.escape((issue.get("status") or {}).get("name") or "")
                updated = html.escape(format_when(issue.get("updated_on")))
                rows.append(
                    "<article class='issue'>"
                    f"<a href='{html.escape(redmine)}/issues/{html.escape(str(issue_id))}'>#{html.escape(str(issue_id))}</a>"
                    "<div>"
                    f"<div>{html.escape(issue.get('subject') or '')}</div>"
                    f"<div class='meta'>{priority} · {status} · {updated}</div>"
                    "</div></article>"
                )
            blocks.append(
                "<section class='project'>"
                f"<div class='head'><h2>{html.escape(project.get('name') or '')}</h2>"
                f"<span class='count'>{len(issues)} open</span></div>"
                f"{''.join(rows)}</section>"
            )
        synced = html.escape(format_when(snapshot.get("synced_at")))
        summary = (
            f"{snapshot.get('issue_total', 0)} open issues · "
            f"{snapshot.get('project_total', 0)} projects · synced {synced}"
        )
        body = "".join(blocks)

    reply_html = ""
    if reply:
        items = "".join(f"<li>{html.escape(item)}</li>" for item in bullet_items(reply))
        reply_html = f"<ul class='bullets'>{items}</ul>"
    error_html = f"<p class='error'>{html.escape(error)}</p>" if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Assigned issues</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <main>
    <header class="head panel">
      <div>
        <h1>Assigned issues</h1>
        <p class="muted">{summary}</p>
      </div>
      <form method="post" action="/sync"><button type="submit">Refresh snapshot</button></form>
    </header>
    <div class="stack">
      <div class="layer"></div>
      <div class="layer mid"></div>
      <form class="panel" method="post" action="/ask">
        <label for="message">Message</label>
        <textarea id="message" name="message" placeholder="Ask about the open tickets">{html.escape(message)}</textarea>
        <div class="actions"><button type="submit">Bullet points</button></div>
        {error_html}
        {reply_html}
      </form>
    </div>
    {body}
  </main>
</body>
</html>
"""


class App(BaseHTTPRequestHandler):
    server_version = "redmine-sync"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        if self.path.split("?", 1)[0] != "/":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        self._send_page()

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path == "/sync":
            try:
                refresh_snapshot()
            except Exception as exc:  # noqa: BLE001 — show the failure on the page
                self._send_page(error=str(exc))
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if path == "/ask":
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            message = (parse_qs(raw).get("message") or [""])[0]
            try:
                reply = bullet_points(message)
            except Exception as exc:  # noqa: BLE001
                self._send_page(message=message, error=str(exc))
                return
            self._send_page(message=message, reply=reply)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization") or ""
        scheme, _, encoded = header.partition(" ")
        supplied = b""
        if scheme.lower() == "basic" and encoded:
            try:
                supplied = base64.b64decode(encoded.strip(), validate=True)
            except ValueError:
                supplied = b""
        expected = f"{self.server.web_user}:{self.server.web_password}".encode()  # type: ignore[attr-defined]
        if len(supplied) == len(expected) and secrets.compare_digest(supplied, expected):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="assigned issues"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        body = b"Authentication required"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _send_page(self, message: str = "", reply: str = "", error: str = "") -> None:
        try:
            snapshot = load_snapshot()
        except RuntimeError:
            snapshot = None
        page = render_page(snapshot, message, reply, error).encode()
        self._send(200, page, "text/html; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        return


def main() -> None:
    env = read_env()
    user = setting(env, "WEB_USER")
    password = setting(env, "WEB_PASSWORD")
    if not user or not password:
        raise SystemExit("Set WEB_USER and WEB_PASSWORD in .env before starting the web app.")
    server = ThreadingHTTPServer((HOST, PORT), App)
    server.web_user = user  # type: ignore[attr-defined]
    server.web_password = password  # type: ignore[attr-defined]
    print(f"Assigned issues on http://{HOST}:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
