#!/usr/bin/env python3
"""Desktop work log on port 8090. Basic auth from .env."""

from __future__ import annotations

import base64
import html
import os
import secrets
from datetime import date, datetime
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

ICON_JOURNAL = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M4 5h16v14H4z"/><path d="M8 5v14M8 9h8M8 13h6"/></svg>"""
ICON_LOG = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>"""
ICON_TICKETS = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>"""
ICON_REFRESH = """<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>"""

PAGE_CSS = """
:root {
  color-scheme: dark;
  --ink: #f4f7fb;
  --muted: rgba(244, 247, 251, 0.68);
  --line: rgba(255, 255, 255, 0.20);
  --glass-deep: rgba(255, 255, 255, 0.05);
  --glass-mid: rgba(255, 255, 255, 0.10);
  --glass-top: rgba(255, 255, 255, 0.18);
  --field: rgba(0, 0, 0, 0.35);
  --accent: #7eb4ff;
  --accent-glow: rgba(126, 180, 255, 0.22);
  --danger: #ff9b94;
  --ok: #8fd9b0;
  --shadow: 0 24px 60px rgba(88, 130, 255, 0.14);
}
@media (prefers-color-scheme: light) {
  :root {
    color-scheme: light;
    --ink: #142033;
    --muted: rgba(20, 32, 51, 0.65);
    --line: rgba(255, 255, 255, 0.55);
    --glass-deep: rgba(255, 255, 255, 0.45);
    --glass-mid: rgba(255, 255, 255, 0.62);
    --glass-top: rgba(255, 255, 255, 0.78);
    --field: rgba(255, 255, 255, 0.55);
    --accent: #2f5fd4;
    --accent-glow: rgba(47, 95, 212, 0.18);
    --danger: #b42318;
    --ok: #067647;
    --shadow: 0 20px 50px rgba(40, 70, 140, 0.10);
  }
}
* { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  min-width: 1180px;
  color: var(--ink);
  font: 14px/1.45 "Segoe UI", system-ui, sans-serif;
  background:
    radial-gradient(900px 520px at 8% -8%, rgba(120, 162, 255, 0.42), transparent 58%),
    radial-gradient(720px 440px at 100% 0%, rgba(186, 124, 255, 0.32), transparent 55%),
    linear-gradient(155deg, #1b2744 0%, #121826 50%, #1a1030 100%);
}
@media (prefers-color-scheme: light) {
  body {
    background:
      radial-gradient(900px 520px at 8% -8%, rgba(120, 162, 255, 0.25), transparent 58%),
      radial-gradient(720px 440px at 100% 0%, rgba(186, 124, 255, 0.18), transparent 55%),
      linear-gradient(155deg, #e8ecf5 0%, #dfe6f2 50%, #e9e2f4 100%);
  }
}
.app {
  display: grid;
  grid-template-columns: 248px 1fr;
  min-height: 100vh;
  gap: 0;
}
.sidebar-wrap {
  padding: 20px 14px 24px;
  position: sticky;
  top: 0;
  height: 100vh;
}
.sidebar {
  position: relative;
  height: 100%;
  border-radius: 22px;
  padding: 18px 12px;
}
.sidebar .layer {
  position: absolute;
  inset: 0;
  border-radius: 22px;
  background: var(--glass-deep);
  backdrop-filter: blur(40px);
  -webkit-backdrop-filter: blur(40px);
  border: 1px solid var(--line);
}
.sidebar .layer.mid {
  inset: 6px;
  border-radius: 18px;
  background: var(--glass-mid);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}
.sidebar-inner { position: relative; z-index: 1; }
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
  padding: 4px 8px 14px;
}
.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--glass-top);
  backdrop-filter: blur(16px);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  color: var(--accent);
  font-weight: 700;
  font-size: 15px;
}
.brand h1 { margin: 0; font-size: 16px; font-weight: 600; letter-spacing: 0.02em; }
.brand .sub { margin: 2px 0 0; font-size: 11px; color: var(--muted); }
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 12px;
  color: var(--ink);
  text-decoration: none;
  border: 1px solid transparent;
  background: transparent;
  font: inherit;
  width: 100%;
  cursor: pointer;
  text-align: left;
}
.nav-item .ico {
  width: 20px;
  height: 20px;
  flex-shrink: 0;
  opacity: 0.85;
}
.nav-item:hover, .nav-item.active {
  background: var(--glass-top);
  backdrop-filter: blur(16px);
  border-color: var(--line);
  box-shadow: var(--shadow);
}
.nav-item.active { color: var(--accent); }
.nav-item.active .ico { opacity: 1; }
main { padding: 24px 28px 48px; }
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
  margin-bottom: 18px;
}
.page-head h2 { margin: 0; font-size: 22px; font-weight: 600; }
.muted { color: var(--muted); }
.glass-card {
  position: relative;
  background: var(--glass-top);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--line);
  border-radius: 16px;
  box-shadow: var(--shadow);
  padding: 16px 18px;
  margin-bottom: 14px;
}
.steps {
  display: flex;
  gap: 14px;
  margin-bottom: 14px;
  font-size: 12px;
  color: var(--muted);
}
.steps span.on { color: var(--accent); font-weight: 600; }
label { display: block; font-weight: 600; margin: 12px 0 6px; }
label:first-child { margin-top: 0; }
select, textarea, input[type="date"] {
  width: 100%;
  max-width: 680px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--field);
  backdrop-filter: blur(8px);
  color: var(--ink);
  font: inherit;
}
textarea { min-height: 130px; resize: vertical; }
.row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 14px; align-items: center; }
button.primary, button.secondary, button.ghost {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 999px;
  padding: 9px 16px;
  font: inherit;
  cursor: pointer;
  border: 1px solid var(--line);
}
button.primary {
  background: linear-gradient(135deg, var(--accent), #6b8cff);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 12px 28px var(--accent-glow);
}
button.secondary {
  background: var(--glass-mid);
  backdrop-filter: blur(12px);
  color: var(--ink);
}
button.ghost {
  background: transparent;
  color: var(--ink);
}
button .ico { width: 16px; height: 16px; }
.issue-pick {
  max-height: 300px;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
  background: var(--field);
  backdrop-filter: blur(8px);
}
.issue-pick label { font-weight: 400; display: flex; gap: 8px; padding: 5px 0; margin: 0; }
table.data {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
table.data th, table.data td {
  text-align: left;
  padding: 9px 10px;
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
table.data th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; }
.day-title {
  margin: 16px 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.project-block { margin-bottom: 12px; }
.project-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.project-head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.pill {
  font-size: 11px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--glass-mid);
  backdrop-filter: blur(8px);
  color: var(--muted);
}
.issue-row {
  display: grid;
  grid-template-columns: 72px 1fr 120px 100px;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px solid var(--line);
  font-size: 13px;
}
.issue-row a { color: var(--accent); text-decoration: none; font-weight: 600; }
.issue-row a:hover { text-decoration: underline; }
.error { color: var(--danger); }
.ok { color: var(--ok); }
ul.bullets { margin: 6px 0 0; padding-left: 18px; }
.empty { padding: 28px; text-align: center; color: var(--muted); }
"""


def setting(env: dict[str, str], key: str) -> str:
    return env.get(key) or os.environ.get(key) or ""


def esc(value: object) -> str:
    return html.escape(str(value))


def format_when(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


def snapshot_note(snapshot: dict | None) -> str:
    if not snapshot:
        return "No ticket cache"
    return f"{snapshot.get('issue_total', 0)} open · {snapshot.get('project_total', 0)} projects"


def nav_link(href: str, icon: str, label: str, active: str, tab: str) -> str:
    cls = "nav-item active" if active == tab else "nav-item"
    return f'<a href="{href}" class="{cls}"><span class="ico">{icon}</span><span>{esc(label)}</span></a>'


def render_layout(active: str, body: str, snapshot: dict | None = None) -> str:
    note = snapshot_note(snapshot)
    nav = (
        nav_link("/", ICON_JOURNAL, "Journal", active, "home")
        + nav_link("/log", ICON_LOG, "Log work", active, "log")
        + nav_link("/tickets", ICON_TICKETS, "Tickets", active, "tickets")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Timosheeto</title>
  <style>{PAGE_CSS}</style>
</head>
<body>
  <div class="app">
    <aside class="sidebar-wrap">
      <div class="sidebar">
        <div class="layer"></div>
        <div class="layer mid"></div>
        <div class="sidebar-inner">
          <div class="brand">
            <div class="brand-mark">T</div>
            <div>
              <h1>Timosheeto</h1>
              <p class="sub">{esc(note)}</p>
            </div>
          </div>
          {nav}
        </div>
      </div>
    </aside>
    <main>{body}</main>
  </div>
</body>
</html>
"""


def render_home(snapshot: dict | None, error: str = "", ok: str = "") -> str:
    grouped = entries_by_date()
    blocks: list[str] = []
    if error:
        blocks.append(f"<p class='error glass-card'>{esc(error)}</p>")
    if ok:
        blocks.append(f"<p class='ok glass-card'>{esc(ok)}</p>")
    if not grouped:
        blocks.append(
            "<div class='glass-card empty'>"
            "<p>No journal entries yet.</p>"
            "<p class='muted'>Use <strong>Log work</strong> or Telegram <code>/log</code>.</p>"
            "</div>"
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
                "<div class='glass-card'><table class='data'>"
                "<thead><tr><th>Logged</th><th>Period</th><th>Project</th>"
                "<th>Tickets</th><th>Min</th><th>Summary</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table></div>"
            )
    body = (
        "<div class='page-head'><div><h2>Journal</h2>"
        "<p class='muted'>What you did — stored locally in SQLite</p></div></div>"
        + "".join(blocks)
    )
    return render_layout("home", body, snapshot)


def render_tickets(snapshot: dict | None, error: str = "", ok: str = "") -> str:
    blocks: list[str] = []
    if error:
        blocks.append(f"<p class='error'>{esc(error)}</p>")
    if ok:
        blocks.append(f"<p class='ok'>{esc(ok)}</p>")

    refresh_btn = (
        f"<form method='post' action='/sync' style='margin:0'>"
        f"<button type='submit' class='primary'><span class='ico'>{ICON_REFRESH}</span>"
        "Refresh from Redmine</button></form>"
    )

    if snapshot is None:
        blocks.append(
            "<div class='glass-card empty'>"
            "<p>No snapshot file yet.</p>"
            "<p class='muted'>Refresh pulls open tickets assigned to you (read only).</p>"
            "</div>"
        )
    else:
        redmine = (snapshot.get("redmine_url") or "").rstrip("/")
        by_project: dict[int, list] = {}
        for issue in snapshot.get("issues") or []:
            pid = int((issue.get("project") or {}).get("id") or 0)
            by_project.setdefault(pid, []).append(issue)
        for project in snapshot.get("projects") or []:
            issues = by_project.get(int(project.get("id") or 0), [])
            issue_rows = []
            for issue in issues:
                iid = issue.get("id")
                link = (
                    f"<a href='{esc(redmine)}/issues/{esc(iid)}' target='_blank' rel='noopener'>#{esc(iid)}</a>"
                    if redmine
                    else f"#{esc(iid)}"
                )
                issue_rows.append(
                    "<div class='issue-row'>"
                    f"{link}"
                    f"<div>{esc(issue.get('subject') or '')}</div>"
                    f"<div class='muted'>{esc((issue.get('priority') or {}).get('name') or '')}</div>"
                    f"<div class='muted'>{esc((issue.get('status') or {}).get('name') or '')}</div>"
                    "</div>"
                )
            blocks.append(
                "<section class='glass-card project-block'>"
                "<div class='project-head'>"
                f"<h3>{esc(project.get('name') or '')}</h3>"
                f"<span class='pill'>{len(issues)} open</span>"
                "</div>"
                + ("".join(issue_rows) or "<p class='muted'>No open tickets.</p>")
                + "</section>"
            )

    synced = esc(format_when(snapshot.get("synced_at") if snapshot else None))
    body = (
        "<div class='page-head'>"
        "<div><h2>Tickets</h2>"
        f"<p class='muted'>Cached sync · last refresh {synced}</p></div>"
        f"{refresh_btn}</div>"
        + "".join(blocks)
    )
    return render_layout("tickets", body, snapshot)


def render_log(
    snapshot: dict | None,
    step: int,
    form: dict[str, str],
    error: str = "",
    saved: dict | None = None,
) -> str:
    if saved:
        body = (
            "<div class='page-head'><h2>Saved</h2></div>"
            f"<div class='glass-card'><pre style='white-space:pre-wrap;margin:0;font:inherit'>"
            f"{esc(format_saved(saved))}</pre></div>"
            "<p class='row'><a class='nav-item' style='display:inline-flex;width:auto' href='/log'>"
            f"<span class='ico'>{ICON_LOG}</span> Log another</a></p>"
        )
        return render_layout("log", body, snapshot)

    projects = []
    if snapshot:
        try:
            projects = projects_from_snapshot()
        except RuntimeError:
            projects = []

    step_labels = ["Project", "Ticket?", "Pick tickets", "Describe"]
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
            "<p class='muted'>Link this entry to an open ticket?</p>"
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
            f"<textarea name='paragraph' id='paragraph' required placeholder='Example: on AGR I helped the client during recette…'>{esc(form.get('paragraph', ''))}</textarea>"
            "<div class='row'><button class='primary' type='submit'>Save with Gemini</button></div>"
        )

    preserve = {k: v for k, v in form.items() if k not in {"paragraph", "issue_id", "ticket_mode", "skip_tickets"}}
    hidden_inputs = "".join(
        f"<input type='hidden' name='{esc(k)}' value='{esc(v)}'>" for k, v in preserve.items()
    )
    body = (
        "<div class='page-head'><div><h2>Log work</h2>"
        "<p class='muted'>Project → ticket → paragraph → structured journal</p></div></div>"
        f"<div class='steps'>{steps_html}</div>"
        f"{'<p class=\"error\">' + esc(error) + '</p>' if error else ''}"
        f"<form class='glass-card' method='post' action='/log'>"
        f"<input type='hidden' name='step' value='{step}'>"
        f"{hidden_inputs}{inner}</form>"
    )
    return render_layout("log", body, snapshot)


class App(BaseHTTPRequestHandler):
    server_version = "timosheeto"

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        path = self.path.split("?", 1)[0]
        query = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        ok = (query.get("ok") or [""])[0]
        if path == "/":
            self._send_html(render_home(self._snapshot(), ok="Snapshot refreshed." if ok else ""))
            return
        if path == "/tickets":
            self._send_html(
                render_tickets(
                    self._snapshot(),
                    ok="Redmine snapshot updated." if ok else "",
                )
            )
            return
        if path == "/log":
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
                self._send_html(render_tickets(self._snapshot(), error=str(exc)))
                return
            self.send_response(303)
            self.send_header("Location", "/tickets?ok=1")
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
                self._redirect("/log?" + urlencode({**form, "step": "1"}))
                return
            if step == 1:
                mode = form.get("ticket_mode", "")
                if mode == "no":
                    self._redirect("/log?" + urlencode({**form, "step": "3", "ticket_mode": "no"}))
                    return
                if mode == "yes":
                    self._redirect("/log?" + urlencode({**form, "step": "2", "ticket_mode": "yes"}))
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
                self._redirect(
                    "/log?"
                    + urlencode(
                        {**form, "step": "3", "issue_pick": ",".join(str(i.get("id")) for i in issues)}
                    )
                )
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
