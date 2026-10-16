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

## Web app and Telegram bot

Both clients read `data/snapshot.json` and share one Gemini Flash call (`brief.py`). Fill `GEMINI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `WEB_USER`, and `WEB_PASSWORD` in `.env`.

```bash
python3 web.py    # http://0.0.0.0:8090/  (basic auth)
python3 bot.py    # long polling; /sync refreshes, any other text returns bullets
```

Port 8090 stays clear of the dashboard (`:8080`), qBittorrent (`:8081`), and Musico (`:8765`). On the X260, after `git pull --ff-only` in this repo (not `~/monitorzed`), restart `web.py` and `bot.py`.
