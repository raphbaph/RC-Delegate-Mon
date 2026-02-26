from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from .config import Settings


class DiscourseAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class UserTotals:
    username: str
    time_read_seconds: int
    likes_received: int
    source_endpoint: str
    captured_at_utc: datetime


def _pick_int(payload: dict[str, Any], candidate_paths: list[tuple[str, ...]]) -> int | None:
    for path in candidate_paths:
        current: Any = payload
        matched = True
        for key in path:
            if not isinstance(current, dict) or key not in current:
                matched = False
                break
            current = current[key]
        if matched and isinstance(current, (int, float)):
            return int(current)
    return None


def fetch_user_totals(settings: Settings, username: str, timeout_seconds: int = 30) -> UserTotals:
    endpoint_path = settings.user_endpoint_template.format(username=username)
    url = f"{settings.discourse_base_url}{endpoint_path}"

    response = requests.get(
        url,
        headers={
            "Api-Key": settings.discourse_api_key,
            "Api-Username": settings.discourse_api_username,
            "Accept": "application/json",
        },
        timeout=timeout_seconds,
    )

    if response.status_code >= 400:
        raise DiscourseAPIError(
            f"Failed fetching {username} ({response.status_code}): {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DiscourseAPIError(f"Invalid JSON response for {username}") from exc

    time_read_seconds = _pick_int(
        payload,
        candidate_paths=[
            ("user_summary", "time_read"),
            ("user", "time_read"),
            ("user", "user_stat", "time_read"),
            ("user", "user_stat", "time_read_time"),
        ],
    )

    likes_received = _pick_int(
        payload,
        candidate_paths=[
            ("user_summary", "likes_received"),
            ("user", "likes_received"),
            ("user", "user_stat", "likes_received"),
        ],
    )

    if time_read_seconds is None or likes_received is None:
        raise DiscourseAPIError(
            f"Could not extract required metrics for {username}. "
            "Set DISCOURSE_USER_ENDPOINT_TEMPLATE to an endpoint that returns cumulative "
            "time_read and likes_received."
        )

    return UserTotals(
        username=username,
        time_read_seconds=time_read_seconds,
        likes_received=likes_received,
        source_endpoint=endpoint_path,
        captured_at_utc=datetime.now(timezone.utc),
    )
