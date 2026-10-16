# Main task — web app and Telegram bot

The Redmine snapshot is the data source. The product is two clients on the X260 that share it: a small web app and a Telegram bot. Both turn a message into bullet points with a free Gemini API call.

## Already done

`python3 sync.py` writes `data/snapshot.json` (gitignored). Last run: **67** open issues assigned to the API key owner, across **10** projects (24 Wafasalaf TMA, 16 Corporate RMA TMA, 13 CMI TMA, seven smaller). Projects in the file are only those with at least one of those open issues. The API key is in `.env` and is not inside the snapshot.

Snapshot keys: `synced_at`, `redmine_url`, `user`, `issue_total`, `project_total`, `issues`, `projects`.

Each issue has `id`, `subject`, `description`, `status`, `priority`, `tracker`, `project`, `assigned_to`, `author`, `due_date`, `done_ratio`, `updated_on`. Each project has `id`, `name`, `identifier`, `assigned_issue_count`.

`sync.py` already pages with `limit` + `offset`. Leave that script as the refresher (`python3 sync.py`, or `--interval 900`).

## What to build

Both clients live in this repo (`/Users/mac/perso/redmine-sync`) and share one Gemini call:

1. Load the latest snapshot.
2. Send the user's message plus a fixed prompt to Gemini.
3. Return bullet points.
4. The prompt tells the model to use only the assigned open issues in the snapshot when it names a ticket or project, and to say when a message matches none of them.

### Web app

A page on port **8090** (the dashboard already owns `:8080`, qBittorrent owns `:8081`, Musico owns `:8765`).

- List the 10 projects and their open assigned issues from `data/snapshot.json` (subject, id, priority, status, updated time, link to `{REDMINE_URL}/issues/<id>`).
- A text box: submit a message, show the bullet points on the page.
- A control that runs the same refresh as `python3 sync.py` and reloads the list.
- HTTP basic auth from `WEB_USER` and `WEB_PASSWORD` in `.env`.
- Reach it at `http://x260.tail07c06e.ts.net:8090/` after deploy.

### Telegram bot

Same bullet-point flow in chat. The user sends a message, the bot replies with the bullets. A `/sync` command refreshes the snapshot before answering. Bot token from BotFather, stored as `TELEGRAM_BOT_TOKEN` in `.env`.

Model: Gemini Flash through the Google AI Studio free API (`generativelanguage.googleapis.com`). The X260 does not run a local model. A student Gemini chat login is not an API key. The key is created in [Google AI Studio](https://aistudio.google.com/) and stored as `GEMINI_API_KEY` in `.env`.

`.env` shape (values stay on disk, never in git, never printed):

```bash
REDMINE_URL=
REDMINE_API_KEY=
GEMINI_API_KEY=
TELEGRAM_BOT_TOKEN=
WEB_USER=
WEB_PASSWORD=
```

## Deploy

This repo is separate from `/Users/mac/perso/monitorzed` (`github.com/hamzamassir/monitorzed`, dashboard on `:8080`). Edit on the Mac, commit and push, then on the X260 `git pull --ff-only` and restart the web app and the bot. SSH: `ssh hamza@100.95.212.44`. Do not `pkill uvicorn`. Do not commit `.env` or `data/`.

Git on this folder: `main`, no remote yet, no commits yet.

## Out of scope

Editing tickets in Redmine, closed tickets, and projects that have no open issue assigned to the user.
