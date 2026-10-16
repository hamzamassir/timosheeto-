#!/usr/bin/env python3
"""Desktop work log on port 8090. Basic auth from .env."""

from __future__ import annotations

import base64
import html
import os
import secrets
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode

from brief import load_snapshot, refresh_snapshot
from envfile import read_env
from store import entries_by_date, init_db
from worklog import (
    format_saved,
    issues_for_project,
    projects_from_snapshot,
    resolve_issue_choices,
    resolve_project_choice,
    save_work_log,
)

HOST = "0.0.0.0"
PORT = 8090

PAGE_CSS = """
:root {
  color-scheme: light dark;
  --bg: #eceef2;
  --surface: #ffffff;
  --border: #d4d8e0;
  --ink: #1a1f2b;
  --muted: #5c6578;
  --accent: #2f5fd4;
  --accent-soft: #e8eefb;
  --danger: #b42318;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151c;
    --surface: #1b2029;
    --border: #2e3544;
    --ink: #e8ebf2;
    --muted: #9aa3b5;
    --accent: #6b9fff;
    --accent-soft: #243044;
    --danger: #ff8f85;
  }
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  min-width: 1100px;
  color: var(--ink);
  background: var(--bg);
  font: 14px/1.4 "Segoe UI", system-ui, sans-serif;
}
.app {
  display: grid;
  grid-template-columns: 240px 1fr;
  min-height: 100vh;
}
nav {
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 20px 16px;
}
nav h1 {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: 0.02em;
}
nav .sub { color: var(--muted); font-size: 12px; margin-bottom: 20px; }
nav a, nav button.link {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  margin-bottom: 4px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--ink);
  text-decoration: none;
  font: inherit;
  cursor: pointer;
}
nav a.active, nav a:hover, nav button.link:hover {
  background: var(--accent-soft);
}
main { padding: 24px 28px 40px; }
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}
.toolbar h2 { margin: 0; font-size: 20px; font-weight: 600; }
.muted { color: var(--muted); }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px 18px;
  margin-bottom: 16px;
}
.steps {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--muted);
}
.steps span.on { color: var(--accent); font-weight: 600; }
label { display: block; font-weight: 600; margin-bottom: 6px; }
select, textarea, input[type="text"], input[type="date"], input[type="number"] {
  width: 100%;
  max-width: 640px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
}
textarea { min-height: 120px; resize: vertical; }
.row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; }
button.primary {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 8px 14px;
  font: inherit;
  cursor: pointer;
}
button.secondary {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 14px;
  font: inherit;
  cursor: pointer;
  color: var(--ink);
}
.issue-pick { max-height: 280px; overflow: auto; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
.issue-pick label { font-weight: 400; display: flex; gap: 8px; padding: 4px 0; }
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th, td {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  vertical-align: top;
}
th { color: var(--muted); font-weight: 600; font-size: 12px; }
.day-title {
  margin: 18px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}
.error { color: var(--danger); margin-top: 10px; }
.ok { color: var(--accent); }
ul.bullets { margin: 8px 0 0; padding-left: 18px; }
"""


def setting(env: dict[str, str], key: str) -> str:
    return env.get(key) or os.environ.get(key) or ""


def esc(value: object) -> str:
    return html.escape(str(value))


def render_layout(active: str, body: str, snapshot_note: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Work log</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <div class="app">
    <nav>
      <h1>Timosheeto</h1>
      <p class="sub">{esc(snapshot_note)}</p>
      <a href="/" class="{'active' if active == 'home' else ''}">Journal</a>
      <a href="/log" class="{'active' if active == 'log' else ''}">Log work</a>
      <form method="post" action="/sync"><button type="submit" class="link">Refresh tickets</button></form>
    </nav>
    <main>{body}</main>
  </div>
</body>
</html>
"""


def render_home(snapshot: dict | None, error: str = "", ok: str = "") -> str:
    note = "No Redmine snapshot"
    if snapshot:
        note = f"{snapshot.get('issue_total', 0)} open tickets · {snapshot.get('project_total', 0)} projects"
    grouped = entries_by_date()
    blocks: list[str] = []
    if error:
        blocks.append(f"<p class='error'>{esc(error)}</p>")
    if ok:
        blocks.append(f"<p class='ok'>{esc(ok)}</p>")
    if not grouped:
        blocks.append(
            "<div class='card'><p class='muted'>No entries yet. Use <strong>Log work</strong> "
            "or Telegram <code>/log</code>.</p></div>"
        )
    else:
        for day, entries in grouped.items():
            rows = []
            for entry in entries:
                tickets = ", ".join(f"#{i}" for i in entry["issue_ids"]) or "—"
                mins = entry["minutes"] if entry["minutes"] is not None else "—"
                bullets = "".join(f"<li>{esc(b)}</li>" for b in entry["bullets"])
                rows.append(
                    "<tr>"
                    f"<td>{esc(entry['created_at'][:16].replace('T', ' '))}</td>"
                    f"<td>{esc(entry['period'] or '—')}</td>"
                    f"<td>{esc(entry['project_name'])}</td>"
                    f"<td>{esc(tickets)}</td>"
                    f"<td>{esc(mins)}</td>"
                    f"<td><strong>{esc(entry['summary'])}</strong>"
                    f"<ul class='bullets'>{bullets}</ul></td>"
                    "</tr>"
                )
            blocks.append(
                f"<div class='day-title'>{esc(day)}</div>"
                "<div class='card'><table>"
                "<thead><tr><th>Logged</th><th>Period</th><th>Project</th>"
                "<th>Tickets</th><th>Min</th><th>Summary</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table></div>"
            )
    body = (
        "<div class='toolbar'><h2>Journal</h2>"
        "<span class='muted'>What you did, by day — from the local database</span></div>"
        + "".join(blocks)
    )
    return render_layout("home", body, note)


def render_log(
    snapshot: dict | None,
    step: int,
    form: dict[str, str],
    error: str = "",
    saved: dict | None = None,
) -> str:
    note = "Snapshot missing — refresh tickets first"
    if snapshot:
        note = f"{snapshot.get('issue_total', 0)} tickets in cache"
    if saved:
        body = (
            "<div class='toolbar'><h2>Saved</h2></div>"
            f"<div class='card'><pre style='white-space:pre-wrap;margin:0'>"
            f"{esc(format_saved(saved))}</pre></div>"
            "<p><a href='/log'>Log another</a> · <a href='/'>Back to journal</a></p>"
        )
        return render_layout("log", body, note)

    projects = []
    if snapshot:
        try:
            projects = projects_from_snapshot()
        except RuntimeError:
            projects = []

    step_labels = ["Project", "Ticket?", "Tickets", "Describe"]
    steps_html = "".join(
        f"<span class='{'on' if index == step else ''}'>{index + 1}. {label}</span>"
        for index, label in enumerate(step_labels)
    )

    inner = ""
    if step == 0:
        options = "".join(
            f"<option value='{index}' {'selected' if form.get('project_index') == str(index) else ''}>"
            f"{esc(p.get('name'))} ({p.get('assigned_issue_count', 0)} open)</option>"
            for index, p in enumerate(projects, start=1)
        )
        inner = (
            f"<label for='project_index'>Project</label>"
            f"<select name='project_index' id='project_index' required>{options}</select>"
            "<div class='row'><button class='primary' type='submit'>Next</button></div>"
        )
    elif step == 1:
        inner = (
            "<p>Link this entry to an open ticket?</p>"
            "<div class='row'>"
            "<button class='primary' name='ticket_mode' value='yes' type='submit'>Yes</button>"
            "<button class='secondary' name='ticket_mode' value='no' type='submit'>No ticket</button>"
            "</div>"
        )
    elif step == 2:
        project = resolve_project_choice(form.get("project_index", ""))
        issues = issues_for_project(int(project["id"])) if project else []
        checks = []
        selected = {s.strip() for s in (form.get("issue_pick") or "").split(",") if s.strip()}
        for index, issue in enumerate(issues, start=1):
            iid = str(issue.get("id"))
            checked = "checked" if iid in selected or str(index) in selected else ""
            checks.append(
                f"<label><input type='checkbox' name='issue_id' value='{esc(iid)}' {checked}> "
                f"#{esc(iid)} — {esc((issue.get('subject') or '')[:90])}</label>"
            )
        inner = (
            "<div class='issue-pick'>" + ("".join(checks) or "<p class='muted'>No tickets.</p>") + "</div>"
            "<div class='row'>"
            "<button class='primary' type='submit'>Next</button>"
            "<button class='secondary' name='skip_tickets' value='1' type='submit'>Skip</button>"
            "</div>"
        )
    else:
        inner = (
            f"<label for='work_date'>Date</label>"
            f"<input type='date' name='work_date' id='work_date' value='{esc(form.get('work_date') or date.today().isoformat())}'>"
            "<label for='paragraph'>What you did</label>"
            f"<textarea name='paragraph' id='paragraph' required>{esc(form.get('paragraph', ''))}</textarea>"
            "<div class='row'><button class='primary' type='submit'>Save with Gemini</button></div>"
        )

    preserve = {k: v for k, v in form.items() if k not in {"paragraph", "issue_id", "ticket_mode", "skip_tickets"}}
    hidden_inputs = "".join(
        f"<input type='hidden' name='{esc(k)}' value='{esc(v)}'>" for k, v in preserve.items()
    )
    body = (
        "<div class='toolbar'><h2>Log work</h2>"
        "<span class='muted'>Test flow — scheduling comes later</span></div>"
        f"<div class='steps'>{steps_html}</div>"
        f"{'<p class=\"error\">' + esc(error) + '</p>' if error else ''}"
        f"<form class='card' method='post' action='/log'>"
        f"<input type='hidden' name='step' value='{step}'>"
        f"{hidden_inputs}{inner}</form>"
    )
    return render_layout("log", body, note)


class App(BaseHTTPRequestHandler):
    server_version = "timosheeto"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send_html(render_home(self._snapshot()))
            return
        if path == "/log":
            query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
            form = {k: v[0] for k, v in query.items()}
            step = int(form.get("step", "0") or 0)
            self._send_html(render_log(self._snapshot(), step, form))
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        fields = {k: v[0] if len(v) == 1 else v for k, v in parse_qs(raw).items()}
        query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        form = {k: v[0] for k, v in query.items()}
        for key, value in fields.items():
            if key == "issue_id" and "issue_id" in fields:
                form["issue_pick"] = ",".join(fields["issue_id"])  # type: ignore[arg-type]
            elif isinstance(value, str):
                form[key] = value

        if path == "/sync":
            try:
                refresh_snapshot()
            except Exception as exc:  # noqa: BLE001
                self._send_html(render_home(self._snapshot(), error=str(exc)))
                return
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if path == "/log":
            self._handle_log_post(form, fields)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _handle_log_post(self, form: dict[str, str], fields: dict) -> None:
        step = int(form.get("step", "0") or 0)
        try:
            if step == 0:
                if not form.get("project_index"):
                    raise RuntimeError("Pick a project.")
                nxt = {**form, "step": "1"}
                self._redirect("/log?" + urlencode(nxt))
                return
            if step == 1:
                mode = form.get("ticket_mode", "")
                if mode == "no":
                    nxt = {**form, "step": "3", "ticket_mode": "no"}
                    self._redirect("/log?" + urlencode(nxt))
                    return
                if mode == "yes":
                    nxt = {**form, "step": "2", "ticket_mode": "yes"}
                    self._redirect("/log?" + urlencode(nxt))
                    return
                raise RuntimeError("Choose yes or no.")
            if step == 2:
                project = resolve_project_choice(form.get("project_index", ""))
                if not project:
                    raise RuntimeError("Invalid project.")
                if form.get("skip_tickets"):
                    issues = []
                else:
                    ids = fields.get("issue_id", [])
                    if isinstance(ids, str):
                        ids = [ids]
                    text = ",".join(ids) if ids else form.get("issue_pick", "")
                    issues = resolve_issue_choices(text or "/skip", int(project["id"])) or []
                nxt = {**form, "step": "3", "issue_pick": ",".join(str(i.get("id")) for i in issues)}
                self._redirect("/log?" + urlencode(nxt))
                return
            if step == 3:
                project = resolve_project_choice(form.get("project_index", ""))
                if not project:
                    raise RuntimeError("Invalid project.")
                paragraph = form.get("paragraph", "").strip()
                if len(paragraph) < 8:
                    raise RuntimeError("Write a bit more detail.")
                pick = form.get("issue_pick", "")
                issues = resolve_issue_choices(pick or "/skip", int(project["id"])) if pick else []
                if issues is None:
                    issues = []
                saved = save_work_log(
                    project,
                    issues or [],
                    paragraph,
                    work_date=form.get("work_date"),
                )
                self._send_html(render_log(self._snapshot(), 3, form, saved=saved))
                return
        except RuntimeError as exc:
            self._send_html(render_log(self._snapshot(), step, form, error=str(exc)))
            return
        self._send_html(render_log(self._snapshot(), step, form, error="Unknown step."))

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _snapshot(self) -> dict | None:
        try:
            return load_snapshot()
        except RuntimeError:
            return None

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
        self.send_header("WWW-Authenticate", 'Basic realm="work log"')
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        body = b"Authentication required"
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        return False

    def _send_html(self, page: str) -> None:
        self._send(200, page.encode(), "text/html; charset=utf-8")

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
    init_db()
    env = read_env()
    user = setting(env, "WEB_USER")
    password = setting(env, "WEB_PASSWORD")
    if not user or not password:
        raise SystemExit("Set WEB_USER and WEB_PASSWORD in .env before starting the web app.")
    server = ThreadingHTTPServer((HOST, PORT), App)
    server.web_user = user  # type: ignore[attr-defined]
    server.web_password = password  # type: ignore[attr-defined]
    print(f"Work log UI on http://{HOST}:{PORT}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
