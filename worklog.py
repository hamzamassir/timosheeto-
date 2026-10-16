"""Shared work-log flow for web and Telegram."""

from __future__ import annotations

from brief import load_snapshot, structure_work_note
from store import clear_session, get_session, insert_entry, save_session


def projects_from_snapshot() -> list[dict]:
    snapshot = load_snapshot()
    return list(snapshot.get("projects") or [])


def issues_for_project(project_id: int) -> list[dict]:
    snapshot = load_snapshot()
    pid = int(project_id)
    return [
        issue
        for issue in snapshot.get("issues") or []
        if int((issue.get("project") or {}).get("id") or 0) == pid
    ]


def format_project_menu() -> str:
    lines = ["Choose a project (reply with the number):"]
    for index, project in enumerate(projects_from_snapshot(), start=1):
        count = project.get("assigned_issue_count") or 0
        lines.append(f"{index}. {project.get('name')} ({count} open tickets)")
    return "\n".join(lines)


def format_issue_menu(project_id: int) -> str:
    issues = issues_for_project(project_id)
    if not issues:
        return "No open tickets for this project. Reply /skip to continue without a ticket."
    lines = ["Pick ticket numbers (e.g. 1 or 1,3), or /skip:"]
    for index, issue in enumerate(issues, start=1):
        subject = (issue.get("subject") or "")[:80]
        lines.append(f"{index}. #{issue.get('id')} — {subject}")
    return "\n".join(lines)


def resolve_project_choice(text: str) -> dict | None:
    try:
        index = int(text.strip())
    except ValueError:
        return None
    projects = projects_from_snapshot()
    if index < 1 or index > len(projects):
        return None
    return projects[index - 1]


def resolve_issue_choices(text: str, project_id: int) -> list[dict] | None:
    stripped = text.strip().lower()
    if stripped in {"/skip", "skip", "none", "no"}:
        return []
    issues = issues_for_project(project_id)
    if not issues:
        return []
    parts = [p.strip() for p in text.replace(" ", "").split(",") if p.strip()]
    picked: list[dict] = []
    for part in parts:
        if part.startswith("#"):
            part = part[1:]
        try:
            num = int(part)
        except ValueError:
            return None
        if any(issue.get("id") == num for issue in issues):
            picked.append(next(i for i in issues if i.get("id") == num))
            continue
        if 1 <= num <= len(issues):
            picked.append(issues[num - 1])
            continue
        return None
    return picked


def save_work_log(
    project: dict,
    issues: list[dict],
    paragraph: str,
    work_date: str | None = None,
) -> dict:
    from datetime import date

    day = work_date or date.today().isoformat()
    structured = structure_work_note(
        project_name=project.get("name") or "",
        issue_ids=[int(i["id"]) for i in issues],
        issue_subjects=[i.get("subject") or "" for i in issues],
        paragraph=paragraph,
    )
    entry_id = insert_entry(
        project_id=int(project.get("id") or 0) or None,
        project_name=project.get("name") or "",
        issue_ids=[int(i["id"]) for i in issues],
        linked_ticket=bool(issues),
        raw_description=paragraph,
        summary=structured.get("summary") or "",
        bullets=structured.get("bullets") or [],
        structured=structured,
        minutes=structured.get("minutes"),
        period=structured.get("period"),
        work_date=day,
    )
    return {
        "id": entry_id,
        "work_date": day,
        "project_name": project.get("name") or "",
        "issue_ids": [int(i["id"]) for i in issues],
        **structured,
    }


def format_saved(entry: dict) -> str:
    tickets = ", ".join(f"#{i}" for i in entry.get("issue_ids") or []) or "none"
    minutes = entry.get("minutes")
    duration = f"{minutes} min" if minutes else "duration not set"
    period = entry.get("period") or "unknown"
    bullets = entry.get("bullets") or []
    lines = [
        f"Saved entry #{entry.get('id')}",
        f"Project: {entry.get('project_name')}",
        f"Tickets: {tickets}",
        f"When: {entry.get('work_date')} · {period} · {duration}",
        f"Summary: {entry.get('summary')}",
        "",
        "Bullets:",
    ]
    lines.extend(f"- {b}" for b in bullets)
    return "\n".join(lines)


# --- Telegram state machine ---

STEP_IDLE = "idle"
STEP_PROJECT = "project"
STEP_TICKET_MODE = "ticket_mode"
STEP_TICKETS = "tickets"
STEP_DESCRIBE = "describe"


def bot_help() -> str:
    return (
        "Commands:\n"
        "/log — log what you did (project → ticket? → describe)\n"
        "/today — today's saved entries from the local database\n"
        "/sync — refresh open tickets from Redmine (read only)\n"
        "/cancel — stop the current /log flow\n"
        "/help — this message"
    )


def handle_bot_message(chat_id: int, text: str) -> str:
    stripped = text.strip()
    lower = stripped.lower()
    command = lower.split()[0].split("@", 1)[0] if lower.startswith("/") else ""

    if command == "/start":
        return (
            "What did you do today?\n"
            "Use /log to record work (project → ticket? → your paragraph).\n"
            "/today shows today's journal. /help lists all commands."
        )
    if command == "/help":
        return bot_help()

    if command == "/cancel":
        clear_session(chat_id)
        return "Cancelled. Nothing was saved."

    if command == "/today":
        from store import list_entries
        from datetime import date

        today = date.today().isoformat()
        entries = list_entries(work_date=today)
        if not entries:
            return f"No entries for {today}. Use /log to add one."
        parts = [f"Entries for {today}:"]
        for entry in entries:
            tickets = ", ".join(f"#{i}" for i in entry["issue_ids"]) or "no ticket"
            parts.append(
                f"• [{entry['period'] or '?'}] {entry['project_name']} ({tickets}) — {entry['summary']}"
            )
        return "\n".join(parts)

    if command == "/sync":
        from brief import refresh_snapshot

        snapshot = refresh_snapshot()
        return (
            f"Snapshot updated: {snapshot['issue_total']} open issues, "
            f"{snapshot['project_total']} projects."
        )

    session = get_session(chat_id)
    in_flow = bool(session and session["step"] != STEP_IDLE)
    if command == "/log" or in_flow:
        return _bot_flow(chat_id, stripped, command == "/log")

    return bot_help()


def _bot_flow(chat_id: int, text: str, restart: bool) -> str:
    session = get_session(chat_id)
    if restart or not session or session["step"] == STEP_IDLE:
        try:
            menu = format_project_menu()
        except RuntimeError as exc:
            return str(exc)
        save_session(chat_id, STEP_PROJECT, {})
        return "Let's log your work.\n\n" + menu

    step = session["step"]
    data = session["data"]

    if step == STEP_PROJECT:
        project = resolve_project_choice(text)
        if not project:
            return "Send a number from the project list, or /cancel."
        data["project"] = project
        save_session(chat_id, STEP_TICKET_MODE, data)
        return (
            f"Project: {project.get('name')}\n"
            "Linked to a ticket? Reply yes or no."
        )

    if step == STEP_TICKET_MODE:
        if text.lower() in {"yes", "y", "oui", "o"}:
            data["want_ticket"] = True
            save_session(chat_id, STEP_TICKETS, data)
            return format_issue_menu(int(data["project"]["id"]))
        if text.lower() in {"no", "n", "non"}:
            data["want_ticket"] = False
            data["issues"] = []
            save_session(chat_id, STEP_DESCRIBE, data)
            return "Describe what you did in a short paragraph."
        return "Reply yes or no, or /cancel."

    if step == STEP_TICKETS:
        if text.lower() in {"/skip", "skip"}:
            data["issues"] = []
            save_session(chat_id, STEP_DESCRIBE, data)
            return "Describe what you did in a short paragraph."
        issues = resolve_issue_choices(text, int(data["project"]["id"]))
        if issues is None:
            return "Use ticket numbers from the list, or /skip."
        data["issues"] = issues
        save_session(chat_id, STEP_DESCRIBE, data)
        return "Describe what you did in a short paragraph."

    if step == STEP_DESCRIBE:
        if len(text) < 8:
            return "Write a bit more detail, or /cancel."
        try:
            saved = save_work_log(data["project"], data.get("issues") or [], text)
        except RuntimeError as exc:
            return str(exc)
        clear_session(chat_id)
        return format_saved(saved)

    clear_session(chat_id)
    return bot_help()
