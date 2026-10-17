# redmine-sync

Local copy of Redmine issues and projects assigned to you. The site address is `REDMINE_URL` in `.env`.

This is separate from the `monitorzed` dashboard. Edit on the Mac, push to GitHub, then pull on the X260 and restart this process. Do not put the API key in git.

## Credentials

Copy `.env.example` to `.env` and set `REDMINE_API_KEY`. The browser session cookie is not the credential: `GET /issues.json` returned 401 with that cookie. Redmine’s REST API wants the personal API key (`X-Redmine-API-Key`).

## Pagination

The assigned-issues HTML list is 25 rows per page. The last check showed **67 issues** (`1-25/67`), so a sync has to walk every page (`offset` / `limit` on the JSON API, or `page` on HTML). Stopping after the first response drops the rest.

## Sync

```bash
python3 sync.py
```

That writes `data/snapshot.json` (gitignored): every open issue with `assigned_to_id=me`, and only the projects those issues belong to. Membership in a project is not enough. Redmine’s default issue filter is open tickets only; closed tickets are a separate, larger set. Repeat on a timer with `python3 sync.py --interval 900`.

## Work log (web + Telegram)

Redmine stays **read-only**: `data/snapshot.json` is the ticket cache. Your journal lives in **`data/worklog.db`** (SQLite, gitignored) for fast history.

- **Web** (`python3 web.py`, port **8090**): desktop journal + step-by-step “Log work”. Gemini only on the final paragraph (structured JSON → DB).
- **Telegram**: `/log` (guided flow), `/today`, `/sync`, `/cancel`, `/help`.

On the X260, one-time sudoers (exact paths, no password for deploy after this):

```bash
sudo bash ~/redmine-sync/deploy/fix-sudoers.sh
```

Then deploy without typing your password:

```bash
~/redmine-sync/deploy/deploy.sh
```

That runs `git pull --ff-only` and restarts `redmine-sync-web` + `redmine-sync-bot`.

Port 8090 is separate from the dashboard (`:8080`), qBittorrent (`:8081`), and Musico (`:8765`). Do not use this repo inside `~/monitorzed`.
