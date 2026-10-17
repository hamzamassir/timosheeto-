"""Aggregates for charts — reads work_entries only."""

from __future__ import annotations

from collections import defaultdict

from project_meta import project_color
from store import list_entries


def chart_payload(days: int = 21) -> dict:
    entries = list_entries(limit=1000)
    by_project: dict[str, int] = defaultdict(int)
    by_day: dict[str, int] = defaultdict(int)
    by_period: dict[str, int] = defaultdict(int)
    day_set: set[str] = set()

    for entry in entries:
        minutes = entry.get("minutes")
        if minutes is None:
            continue
        minutes = int(minutes)
        name = entry.get("project_name") or "Unknown"
        by_project[name] += minutes
        day = entry.get("work_date") or ""
        if day:
            by_day[day] += minutes
            day_set.add(day)
        period = (entry.get("period") or "unknown").lower()
        by_period[period] += minutes

    sorted_days = sorted(day_set)[-days:]
    project_labels = list(by_project.keys())
    project_values = [by_project[k] for k in project_labels]
    name_to_pid: dict[str, int | None] = {}
    for entry in entries:
        name_to_pid[entry.get("project_name") or ""] = entry.get("project_id")
    project_colors = [
        project_color(name_to_pid.get(name)) for name in project_labels
    ]

    return {
        "project_labels": project_labels,
        "project_minutes": project_values,
        "project_colors": project_colors[: len(project_labels)],
        "day_labels": sorted_days,
        "day_minutes": [by_day.get(d, 0) for d in sorted_days],
        "period_labels": list(by_period.keys()),
        "period_minutes": list(by_period.values()),
        "total_minutes": sum(by_project.values()),
        "entry_count": len(entries),
    }
