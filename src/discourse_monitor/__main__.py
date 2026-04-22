from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, time, timezone

from .client import DiscourseAPIError, fetch_user_totals
from .config import ConfigError, load_settings
from .db import connect, ensure_schema, insert_snapshot_and_diff, query_diffs


def _parse_start_datetime(raw: str) -> datetime:
    value = raw.strip()
    if "T" not in value:
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return datetime.combine(d, time.min, tzinfo=timezone.utc)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_end_datetime(raw: str) -> datetime:
    value = raw.strip()
    if "T" not in value:
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return datetime.combine(d, time.max, tzinfo=timezone.utc)
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def run_collect() -> int:
    settings = load_settings()
    conn = connect(settings.database_path)
    ensure_schema(conn)

    failed = False
    for username in settings.monitored_usernames:
        try:
            totals = fetch_user_totals(settings, username)
            diff_time, diff_likes = insert_snapshot_and_diff(conn, totals)
            print(
                f"{username}: total_time={totals.time_read_seconds}s "
                f"total_likes={totals.likes_received} "
                f"diff_time={diff_time}s diff_likes={diff_likes}"
            )
        except DiscourseAPIError as exc:
            failed = True
            print(f"ERROR {username}: {exc}", file=sys.stderr)

    conn.close()
    return 1 if failed else 0


def run_query(start: str, end: str, usernames_raw: str | None) -> int:
    settings = load_settings()
    conn = connect(settings.database_path)
    ensure_schema(conn)

    start_iso = _to_iso_z(_parse_start_datetime(start))
    end_iso = _to_iso_z(_parse_end_datetime(end))

    usernames: list[str] | None = None
    if usernames_raw:
        usernames = [u.strip() for u in usernames_raw.split(",") if u.strip()]

    rows = query_diffs(conn, start_iso_utc=start_iso, end_iso_utc=end_iso, usernames=usernames)
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "username",
            "time_read_seconds",
            "likes_received",
            "first_capture",
            "last_capture",
            "points",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row["username"],
                row["time_read_seconds"],
                row["likes_received"],
                row["first_capture"],
                row["last_capture"],
                row["points"],
            ]
        )
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="discourse-monitor",
        description="Collect and query Discourse user metric diffs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("collect", help="Fetch current totals and store diffs.")

    query_cmd = sub.add_parser("query", help="Query summed diffs in a timeframe.")
    query_cmd.add_argument(
        "--start",
        required=True,
        help="Inclusive UTC start. Accepts YYYY-MM-DD or full ISO datetime.",
    )
    query_cmd.add_argument(
        "--end",
        required=True,
        help="Inclusive UTC end. Accepts YYYY-MM-DD or full ISO datetime.",
    )
    query_cmd.add_argument(
        "--users",
        required=False,
        help="Optional comma-separated usernames. Defaults to all tracked users in DB.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "collect":
            return run_collect()
        if args.command == "query":
            return run_query(args.start, args.end, args.users)
        parser.print_help()
        return 2
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
