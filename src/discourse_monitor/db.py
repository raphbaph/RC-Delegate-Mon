from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .client import UserTotals


@dataclass(frozen=True)
class SnapshotRow:
    id: int
    username: str
    captured_at_utc: datetime
    total_time_read_seconds: int
    total_likes_received: int


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            captured_at_utc TEXT NOT NULL,
            total_time_read_seconds INTEGER NOT NULL,
            total_likes_received INTEGER NOT NULL,
            source_endpoint TEXT NOT NULL,
            created_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        CREATE INDEX IF NOT EXISTS idx_snapshots_username_captured_at
            ON snapshots (username, captured_at_utc);

        CREATE TABLE IF NOT EXISTS metric_diffs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            captured_at_utc TEXT NOT NULL,
            snapshot_id INTEGER NOT NULL,
            previous_snapshot_id INTEGER,
            diff_time_read_seconds INTEGER NOT NULL,
            diff_likes_received INTEGER NOT NULL,
            is_baseline INTEGER NOT NULL DEFAULT 0,
            created_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
            FOREIGN KEY (previous_snapshot_id) REFERENCES snapshots(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_metric_diffs_username_captured_at
            ON metric_diffs (username, captured_at_utc);
        """
    )
    conn.commit()


def _parse_utc(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def get_latest_snapshot(conn: sqlite3.Connection, username: str) -> SnapshotRow | None:
    row = conn.execute(
        """
        SELECT id, username, captured_at_utc, total_time_read_seconds, total_likes_received
        FROM snapshots
        WHERE username = ?
        ORDER BY captured_at_utc DESC, id DESC
        LIMIT 1
        """,
        (username,),
    ).fetchone()

    if row is None:
        return None

    return SnapshotRow(
        id=row["id"],
        username=row["username"],
        captured_at_utc=_parse_utc(row["captured_at_utc"]),
        total_time_read_seconds=row["total_time_read_seconds"],
        total_likes_received=row["total_likes_received"],
    )


def insert_snapshot_and_diff(conn: sqlite3.Connection, totals: UserTotals) -> tuple[int, int]:
    captured_at_iso = totals.captured_at_utc.isoformat().replace("+00:00", "Z")

    previous = get_latest_snapshot(conn, totals.username)

    cur = conn.execute(
        """
        INSERT INTO snapshots (
            username,
            captured_at_utc,
            total_time_read_seconds,
            total_likes_received,
            source_endpoint
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            totals.username,
            captured_at_iso,
            totals.time_read_seconds,
            totals.likes_received,
            totals.source_endpoint,
        ),
    )
    snapshot_id = cur.lastrowid

    if previous is None:
        diff_time = 0
        diff_likes = 0
        previous_id = None
        is_baseline = 1
    else:
        diff_time = totals.time_read_seconds - previous.total_time_read_seconds
        diff_likes = totals.likes_received - previous.total_likes_received
        previous_id = previous.id
        is_baseline = 0

    conn.execute(
        """
        INSERT INTO metric_diffs (
            username,
            captured_at_utc,
            snapshot_id,
            previous_snapshot_id,
            diff_time_read_seconds,
            diff_likes_received,
            is_baseline
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            totals.username,
            captured_at_iso,
            snapshot_id,
            previous_id,
            diff_time,
            diff_likes,
            is_baseline,
        ),
    )

    conn.commit()
    return diff_time, diff_likes


def query_diffs(
    conn: sqlite3.Connection,
    start_iso_utc: str,
    end_iso_utc: str,
    usernames: list[str] | None = None,
) -> list[sqlite3.Row]:
    if usernames:
        placeholders = ",".join("?" for _ in usernames)
        sql = f"""
            SELECT
                username,
                SUM(diff_time_read_seconds) AS time_read_seconds,
                SUM(diff_likes_received) AS likes_received,
                MIN(captured_at_utc) AS first_capture,
                MAX(captured_at_utc) AS last_capture,
                COUNT(*) AS points
            FROM metric_diffs
            WHERE captured_at_utc >= ?
              AND captured_at_utc <= ?
              AND username IN ({placeholders})
            GROUP BY username
            ORDER BY username
        """
        params = [start_iso_utc, end_iso_utc, *usernames]
    else:
        sql = """
            SELECT
                username,
                SUM(diff_time_read_seconds) AS time_read_seconds,
                SUM(diff_likes_received) AS likes_received,
                MIN(captured_at_utc) AS first_capture,
                MAX(captured_at_utc) AS last_capture,
                COUNT(*) AS points
            FROM metric_diffs
            WHERE captured_at_utc >= ?
              AND captured_at_utc <= ?
            GROUP BY username
            ORDER BY username
        """
        params = [start_iso_utc, end_iso_utc]

    return conn.execute(sql, params).fetchall()
