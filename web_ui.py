"""HTML layout, journal, analytics, settings."""

from __future__ import annotations

import html
import json

from analytics import chart_payload
from project_meta import (
    ALLOWED_MODELS,
    all_project_meta,
    get_gemini_model,
    logo_path,
    phosphor_for,
    project_color,
)
from store import entries_by_date

HEAD_ASSETS = """
<link href="https://cdn.jsdelivr.net/npm/remixicon@4.6.0/fonts/remixicon.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@phosphor-icons/web@2.1.2/src/duotone/style.css">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" defer></script>
"""

PAGE_SCRIPTS = """
<script>
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('[data-copy]');
  if (!btn) return;
  const text = btn.getAttribute('data-copy');
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    const icon = btn.querySelector('i');
    if (icon) {
      const prev = icon.className;
      icon.className = 'ri-check-line';
      setTimeout(() => { icon.className = prev; }, 3000);
    }
    showToast('Copied');
  } catch (_) {
    showToast('Copy failed');
  }
});
</script>
"""

EXTRA_CSS = """
.nav-item i { font-size: 18px; width: 22px; text-align: center; }
.brand-mark i { font-size: 20px; }
.entry-card {
  border-left: 4px solid var(--entry-accent);
  padding: 14px 16px;
  margin-bottom: 10px;
}
.entry-top {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  justify-content: space-between;
}
.entry-project {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.project-logo {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  object-fit: cover;
  border: 1px solid var(--line);
}
.ph-badge {
  font-size: 26px;
  color: var(--entry-accent);
  line-height: 1;
}
.entry-meta { font-size: 12px; color: var(--muted); margin-top: 4px; }
.copy-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
}
.copy-line.summary-line {
  font-weight: 600;
  font-size: 15px;
  margin-top: 10px;
}
.copy-btn {
  flex-shrink: 0;
  border: 1px solid var(--line);
  background: var(--glass-mid);
  backdrop-filter: blur(8px);
  color: var(--muted);
  border-radius: 8px;
  width: 32px;
  height: 32px;
  cursor: pointer;
  display: grid;
  place-items: center;
}
.copy-btn:hover { color: var(--accent); border-color: var(--accent); }
#toast {
  position: fixed;
  bottom: 24px;
  right: 28px;
  padding: 10px 16px;
  border-radius: 12px;
  background: var(--glass-top);
  backdrop-filter: blur(16px);
  border: 1px solid var(--line);
  box-shadow: var(--shadow);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity .2s, transform .2s;
  pointer-events: none;
  z-index: 50;
}
#toast.show { opacity: 1; transform: translateY(0); }
.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.chart-card { min-height: 280px; }
.chart-card canvas { max-height: 240px; }
.settings-project {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  gap: 12px;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}
@media (max-width: 1200px) {
  .chart-grid { grid-template-columns: 1fr; }
}
"""


def esc(value: object) -> str:
    return html.escape(str(value))


def copy_btn(text: str) -> str:
    safe = esc(text).replace("\n", " ")
    return (
        f'<button type="button" class="copy-btn" data-copy="{safe}" '
        f'aria-label="Copy"><i class="ri-file-copy-line"></i></button>'
    )


def render_layout(
    active: str, body: str, snapshot_note: str, base_css: str, extra_css: str = EXTRA_CSS
) -> str:
    nav = (
        nav_item("/", "ri-book-open-line", "Journal", active, "home")
        + nav_item("/log", "ri-edit-2-line", "Log work", active, "log")
        + nav_item("/tickets", "ri-ticket-2-line", "Tickets", active, "tickets")
        + nav_item("/analytics", "ri-bar-chart-grouped-line", "Analytics", active, "analytics")
        + nav_item("/settings", "ri-settings-3-line", "Settings", active, "settings")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Timosheeto</title>
  {HEAD_ASSETS}
  <style>{base_css}{extra_css}</style>
</head>
<body>
  <div id="toast" role="status" aria-live="polite"></div>
  <div class="app">
    <aside class="sidebar-wrap">
      <div class="sidebar">
        <div class="layer"></div>
        <div class="layer mid"></div>
        <div class="sidebar-inner">
          <div class="brand">
            <div class="brand-mark"><i class="ri-time-line" aria-hidden="true"></i></div>
            <div>
              <h1>Timosheeto</h1>
              <p class="sub">{esc(snapshot_note)}</p>
            </div>
          </div>
          {nav}
        </div>
      </div>
    </aside>
    <main>{body}</main>
  </div>
  {PAGE_SCRIPTS}
</body>
</html>
"""


def nav_item(href: str, remix: str, label: str, active: str, tab: str) -> str:
    cls = "nav-item active" if active == tab else "nav-item"
    return f'<a href="{href}" class="{cls}"><i class="{remix}" aria-hidden="true"></i><span>{esc(label)}</span></a>'


def entry_card(entry: dict) -> str:
    pid = entry.get("project_id")
    color = project_color(pid)
    ph = phosphor_for(pid)
    logo_html = (
        f'<img class="project-logo" src="/logo/{int(pid)}" alt="">'
        if pid and logo_path(int(pid))
        else f'<i class="ph-duotone {ph} ph-badge" aria-hidden="true"></i>'
    )
    tickets = ", ".join(f"#{i}" for i in entry["issue_ids"]) or "No ticket"
    mins = entry["minutes"] if entry["minutes"] is not None else "—"
    period = entry.get("period") or "—"
    bullets = "".join(
        f'<div class="copy-line"><span>{esc(b)}</span>{copy_btn(b)}</div>' for b in entry["bullets"]
    )
    return (
        f'<article class="glass-card entry-card" style="--entry-accent:{esc(color)}">'
        '<div class="entry-top">'
        f'<div class="entry-project">{logo_html}<div>'
        f'<div><strong>{esc(entry["project_name"])}</strong></div>'
        f'<div class="entry-meta"><i class="ri-time-line"></i> {esc(mins)} min · '
        f'<i class="ri-sun-line"></i> {esc(period)} · <i class="ri-ticket-line"></i> {esc(tickets)}</div>'
        "</div></div>"
        f'<span class="pill">{esc(entry["created_at"][:16].replace("T", " "))}</span>'
        "</div>"
        f'<div class="copy-line summary-line"><span>{esc(entry["summary"])}</span>'
        f'{copy_btn(entry["summary"])}</div>'
        f"{bullets}"
        "</article>"
    )


def render_home(snapshot_note: str, error: str = "", ok: str = "") -> str:  # noqa: ARG001
    grouped = entries_by_date()
    blocks: list[str] = []
    if error:
        blocks.append(f'<p class="error glass-card">{esc(error)}</p>')
    if ok:
        blocks.append(f'<p class="ok glass-card">{esc(ok)}</p>')
    if not grouped:
        blocks.append(
            '<div class="glass-card empty">'
            '<p><i class="ri-journal-line"></i> No journal entries yet.</p>'
            '<p class="muted">Use <strong>Log work</strong> or Telegram <code>/log</code>.</p>'
            "</div>"
        )
    else:
        for day, entries in grouped.items():
            cards = "".join(entry_card(e) for e in entries)
            blocks.append(
                f'<div class="day-title"><i class="ri-calendar-line"></i> {esc(day)}</div>{cards}'
            )
    body = (
        '<div class="page-head"><div><h2><i class="ri-book-open-line"></i> Journal</h2>'
        '<p class="muted">Your work timeline — copy any line with one click</p></div></div>'
        + "".join(blocks)
    )
    return body


def render_analytics(snapshot_note: str, base_css: str) -> str:
    data = chart_payload()
    payload = json.dumps(data)
    total_h = round((data["total_minutes"] or 0) / 60, 1)
    body = f"""
    <div class="page-head">
      <div>
        <h2><i class="ri-bar-chart-grouped-line"></i> Analytics</h2>
        <p class="muted">{data['entry_count']} entries · {total_h} h logged (with minutes)</p>
      </div>
    </div>
    <div class="chart-grid">
      <div class="glass-card chart-card"><h3>Time by project</h3><canvas id="chartProjects"></canvas></div>
      <div class="glass-card chart-card"><h3>Time by day</h3><canvas id="chartDays"></canvas></div>
      <div class="glass-card chart-card"><h3>Morning / afternoon / evening</h3><canvas id="chartPeriod"></canvas></div>
    </div>
    <script>
    document.addEventListener('DOMContentLoaded', () => {{
      const d = {payload};
      const opts = {{ responsive: true, plugins: {{ legend: {{ labels: {{ color: '#9aa3b5' }} }} }} }};
      new Chart(document.getElementById('chartProjects'), {{
        type: 'doughnut',
        data: {{ labels: d.project_labels, datasets: [{{ data: d.project_minutes, backgroundColor: d.project_colors }}] }},
        options: opts
      }});
      new Chart(document.getElementById('chartDays'), {{
        type: 'bar',
        data: {{ labels: d.day_labels, datasets: [{{ label: 'Minutes', data: d.day_minutes, backgroundColor: '#7eb4ff' }}] }},
        options: {{ responsive: true, scales: {{ x: {{ ticks: {{ color: '#9aa3b5' }} }}, y: {{ ticks: {{ color: '#9aa3b5' }} }} }} }}
      }});
      new Chart(document.getElementById('chartPeriod'), {{
        type: 'polarArea',
        data: {{ labels: d.period_labels, datasets: [{{ data: d.period_minutes, backgroundColor: ['#7eb4ff','#b794f4','#8fd9b0','#f0b429'] }}] }},
        options: opts
      }});
    }});
    </script>
    """
    return render_layout("analytics", body, snapshot_note, base_css)


def render_settings(
    snapshot: dict | None, snapshot_note: str, base_css: str, error: str = "", ok: str = ""
) -> str:
    projects = (snapshot or {}).get("projects") or []
    meta = all_project_meta(projects)
    model = get_gemini_model()
    options = "".join(
        f'<option value="{esc(m)}" {"selected" if m == model else ""}>{esc(m)}</option>'
        for m in ALLOWED_MODELS
    )
    project_fields = []
    for item in meta:
        pid = item["id"]
        logo_src = f"/logo/{pid}" if item["has_logo"] else ""
        logo_preview = (
            f'<img src="{logo_src}" class="project-logo" alt="">' if logo_src else
            f'<i class="ph-duotone {item["phosphor"]} ph-badge" style="color:{esc(item["color"])}"></i>'
        )
        project_fields.append(
            f'<div class="settings-project">'
            f"{logo_preview}"
            f"<div><strong>{esc(item['name'])}</strong>"
            f'<div class="muted">Color <input type="color" name="color_{pid}" value="{esc(item["color"])}"></div></div>'
            f'<a class="secondary" style="text-decoration:none;display:inline-flex;align-items:center;gap:6px;padding:9px 14px;border-radius:999px;border:1px solid var(--line)" '
            f'href="#logo-{pid}"><i class="ri-image-add-line"></i> Logo below</a></div>'
        )
    logo_forms = []
    for item in meta:
        pid = item["id"]
        logo_forms.append(
            f'<form id="logo-{pid}" class="glass-card row" method="post" action="/settings/logo" '
            f'enctype="multipart/form-data" style="margin-top:8px;align-items:center">'
            f'<strong>{esc(item["name"])}</strong>'
            f'<input type="hidden" name="project_id" value="{pid}">'
            f'<input type="file" name="logo" accept="image/png,image/jpeg,image/webp" required>'
            f'<button type="submit" class="secondary"><i class="ri-upload-2-line"></i> Upload logo</button>'
            f"</form>"
        )
    err = f'<p class="error">{esc(error)}</p>' if error else ""
    okp = f'<p class="ok">{esc(ok)}</p>' if ok else ""
    body = (
        '<div class="page-head"><div>'
        '<h2><i class="ri-settings-3-line"></i> Settings</h2>'
        '<p class="muted">Gemini model, project colors, logos</p></div></div>'
        + err
        + okp
        + f'<form class="glass-card" method="post" action="/settings">'
        '<label for="gemini_model"><i class="ri-robot-2-line"></i> Gemini model</label>'
        f'<select name="gemini_model" id="gemini_model">{options}</select>'
        "<h3 style='margin-top:18px'>Projects</h3>"
        + "".join(project_fields)
        + '<div class="row"><button class="primary" type="submit"><i class="ri-save-line"></i> Save</button></div>'
        "</form>"
        + "".join(logo_forms)
    )
    return render_layout("settings", body, snapshot_note, base_css)


def render_home_page(snapshot_note: str, base_css: str, error: str = "", ok: str = "") -> str:
    return render_layout("home", render_home(snapshot_note, error, ok), snapshot_note, base_css)
