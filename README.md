# Discourse User Metrics Monitor

Tracks cumulative `time_read` and `likes_received` for selected Discourse users, stores daily diffs, and lets you query totals for any timeframe.

This uses the regular Discourse API with your admin API key, so no Builder plan is required.

## What it does

- `collect`: fetches current totals for each monitored user and writes:
  - a raw cumulative snapshot
  - a diff row versus the previous snapshot
- `query`: sums stored diffs between two UTC datetimes, per user

## Project structure

- `src/discourse_monitor/__main__.py` CLI entrypoint
- `src/discourse_monitor/client.py` Discourse API calls and metric extraction
- `src/discourse_monitor/db.py` SQLite schema + inserts + timeframe queries
- `src/discourse_monitor/config.py` environment configuration loader

## Setup

```bash
cd /Users/raphael/RC-Delegate-Monitor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:

```bash
DISCOURSE_BASE_URL=https://your-forum.example
DISCOURSE_API_KEY=...
DISCOURSE_API_USERNAME=...
DISCOURSE_MONITORED_USERNAMES=user1,user2,user3
# Optional override:
# DISCOURSE_MONITOR_DB_PATH=./data/discourse_monitor.db
# DISCOURSE_USER_ENDPOINT_TEMPLATE=/u/{username}.json
```

## Run collector manually

```bash
set -a; source .env; set +a
PYTHONPATH=src python -m discourse_monitor collect
```

Example output:

```text
alice: total_time=12034s total_likes=420 diff_time=310s diff_likes=3
bob: total_time=9300s total_likes=190 diff_time=120s diff_likes=1
```

## Query timeframe totals

```bash
set -a; source .env; set +a
PYTHONPATH=src python -m discourse_monitor query \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-26T23:59:59Z
```

Optional filter:

```bash
PYTHONPATH=src python -m discourse_monitor query \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-26T23:59:59Z \
  --users alice,bob
```

## Cron on VPS (daily at 00:05 UTC)

1. Place project on VPS (git clone).
2. Create `.venv` and `.env` once.
3. Add cron entry (`crontab -e`):

```cron
5 0 * * * cd /path/to/RC-Delegate-Monitor && /bin/zsh -lc 'source .venv/bin/activate && set -a; source .env; set +a; PYTHONPATH=src python -m discourse_monitor collect >> logs/collect.log 2>&1'
```

Create `logs/` first:

```bash
mkdir -p logs
```

## Notes

- First run creates a baseline diff of `0` (no previous snapshot).
- If Discourse returns a different user payload shape, set `DISCOURSE_USER_ENDPOINT_TEMPLATE` to an endpoint that includes cumulative `time_read` and `likes_received`.
- DB is SQLite by default (`./data/discourse_monitor.db`) and is easy to back up.
