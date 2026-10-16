# Handoff — redmine-sync

Paste this into a new Cursor chat, with this folder as the workspace:

> Read `/Users/mac/perso/redmine-sync/HANDOFF.md` and continue the Redmine sync. Credentials live only in `/Users/mac/perso/redmine-sync/.env`. Read that file locally. Do not print the API key, do not commit `.env`, and do not ask me to paste the key in chat.

## Goal

Keep a local, updated copy of **issues assigned to me** and **projects assigned to me**. The site address stays in `.env` as `REDMINE_URL`. This is a source of tickets, not a second Redmine UI.

## Where the code lives

| | |
|---|---|
| Project | `/Users/mac/perso/redmine-sync` |
| Git | `main`, initialized, **no commits yet**, **no remote yet** |
| Dashboard repo | `/Users/mac/perso/monitorzed` → `github.com/hamzamassir/monitorzed` |

Leave `monitorzed` alone. It already has its own remote. This sync is a separate process, not a tab on the dashboard (`:8080`).

## Deploy (X260 homelab)

Edit on the Mac → commit + push → on the X260 `git pull --ff-only` → restart **this** process.

| | |
|---|---|
| SSH | `ssh hamza@100.95.212.44` (`x260.tail07c06e.ts.net`) |
| User | `hamza` |
| Do not | `pkill uvicorn` (that also kills Musico), wipe `~/torrents`, commit `.env` |

Nothing is deployed yet. After the first push, clone or pull into a new directory on the X260. Do not drop this into `~/monitorzed`.

## Auth

`.env` is gitignored and already filled in on this Mac. The example shape is:

```bash
REDMINE_URL=
REDMINE_API_KEY=
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
WEB_USER=
WEB_PASSWORD=
```

The key comes from Redmine → **My account** → **API access key**. If that box is missing, an admin must enable **Administration → Settings → API → Enable REST web service**.

Send the key as `X-Redmine-API-Key`. A browser `_redmine_session` cookie is the wrong credential: on 16 Oct 2026, `GET /issues.json` and `GET /projects.json` returned **401** with a live session cookie, while the HTML issues page returned **200**. A session cookie was pasted into the previous chat; the user should log out of Redmine so that session dies. Do not reuse it.

## What the list looks like

Checked 16 Oct 2026 against the HTML issues page (`assigned_to_id=me`, sort `priority:desc,updated_on:desc`):

- **67** issues assigned to the logged-in user
- **25** per page (`1-25/67`), and the page has a per-page control
- Page 1 has no `page=` links in the HTML; later pages still exist

A sync must walk every page. On the JSON API that is `limit` + `offset` until `offset >= total_count`. On HTML that is `page=2`, `page=3`, and so on. One response is only the first 25 issues.

## Sync

`.env` exists locally and is gitignored. `python3 sync.py` pages `assigned_to_id=me` (open issues, 67 on 16 Oct 2026) and writes `data/snapshot.json`. Projects in that file are only the ones that have at least one of those issues, not every membership. `--interval N` repeats the sync.

`web.py` (port 8090, basic auth) and `bot.py` (Telegram long polling) both read that snapshot. Bullet points go through `brief.py` and Gemini Flash. `.env` also has empty `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `WEB_USER`, and `WEB_PASSWORD` until those are filled in. Nothing is committed or deployed yet. Do not put this repo in `~/monitorzed`.
