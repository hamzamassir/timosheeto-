#!/usr/bin/env python3
"""Page through open Redmine issues assigned to the API key owner.

Projects in the snapshot are only those that own at least one of those issues.
Credentials come from .env (REDMINE_URL, REDMINE_API_KEY). The key is sent as
X-Redmine-API-Key and is never written to data/ or logs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
PAGE_LIMIT = 100


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"Missing {path.name}. Copy .env.example and set REDMINE_API_KEY.")
    env: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    url = env.get("REDMINE_URL", "").rstrip("/")
    api_key = env.get("REDMINE_API_KEY", "")
    if not url or not api_key:
        raise SystemExit("REDMINE_URL and REDMINE_API_KEY must both be set in .env.")
    return {"REDMINE_URL": url, "REDMINE_API_KEY": api_key}


class RedmineClient:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self._api_key = api_key

    def get_json(self, path: str, params: dict[str, str | int] | None = None) -> dict:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = urllib.request.Request(
            url,
            headers={
                "X-Redmine-API-Key": self._api_key,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            raise SystemExit(f"Redmine {path} returned HTTP {exc.code}.") from None
        except urllib.error.URLError as exc:
            raise SystemExit(f"Could not reach Redmine: {exc.reason}") from None

    def paginate(self, path: str, collection: str, params: dict[str, str | int]) -> tuple[list, int]:
        items: list = []
        offset = 0
        total = 0
        while True:
            page_params = {**params, "limit": PAGE_LIMIT, "offset": offset}
            payload = self.get_json(path, page_params)
            batch = payload.get(collection) or []
            total = int(payload.get("total_count", len(batch)))
            items.extend(batch)
            offset += len(batch)
            if not batch or offset >= total:
                break
        if len(items) != total:
            raise SystemExit(
                f"{path} pagination stopped at {len(items)} of {total} {collection}."
            )
        return items, total


def public_user(user: dict) -> dict:
    return {
        "id": user.get("id"),
        "login": user.get("login"),
        "firstname": user.get("firstname"),
        "lastname": user.get("lastname"),
    }


def projects_for_issues(client: RedmineClient, issues: list) -> list:
    counts: dict[int, int] = {}
    order: list[int] = []
    stubs: dict[int, dict] = {}
    for issue in issues:
        project = issue.get("project") or {}
        project_id = project.get("id")
        if project_id is None:
            continue
        project_id = int(project_id)
        if project_id not in counts:
            order.append(project_id)
            stubs[project_id] = {"id": project_id, "name": project.get("name")}
        counts[project_id] = counts.get(project_id, 0) + 1

    projects: list = []
    for project_id in order:
        try:
            payload = client.get_json(f"/projects/{project_id}.json")
            project = payload.get("project") or dict(stubs[project_id])
        except SystemExit:
            project = dict(stubs[project_id])
        project.pop("api_key", None)
        project["assigned_issue_count"] = counts[project_id]
        projects.append(project)
    return projects


def sync_once(client: RedmineClient) -> dict:
    user_payload = client.get_json("/users/current.json")
    user = user_payload.get("user") or {}
    user.pop("api_key", None)

    issues, issue_total = client.paginate(
        "/issues.json",
        "issues",
        {
            "assigned_to_id": "me",
            "sort": "priority:desc,updated_on:desc",
        },
    )
    projects = projects_for_issues(client, issues)

    return {
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "redmine_url": client.base_url,
        "user": public_user(user),
        "issue_total": issue_total,
        "project_total": len(projects),
        "issues": issues,
        "projects": projects,
    }


def write_snapshot(snapshot: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = SNAPSHOT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    os.replace(temporary, SNAPSHOT_PATH)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync assigned Redmine issues and projects.")
    parser.add_argument(
        "--interval",
        type=int,
        default=0,
        help="Repeat every N seconds. Default is a single run.",
    )
    args = parser.parse_args()
    if args.interval < 0:
        raise SystemExit("--interval must be >= 0.")

    env = load_env(ENV_PATH)
    client = RedmineClient(env["REDMINE_URL"], env["REDMINE_API_KEY"])

    while True:
        snapshot = sync_once(client)
        write_snapshot(snapshot)
        user = snapshot["user"]
        name = f"{user.get('firstname', '')} {user.get('lastname', '')}".strip()
        print(
            f"Wrote {SNAPSHOT_PATH.relative_to(ROOT)}: "
            f"{snapshot['issue_total']} open issues, "
            f"{snapshot['project_total']} projects with an assigned issue, "
            f"for {name}."
        )
        if args.interval == 0:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
