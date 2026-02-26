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


def _extract_metrics(payload: dict[str, Any]) -> tuple[int | None, int | None]:
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
            ("user_summary", "stats", "likes_received"),
        ],
    )

    return time_read_seconds, likes_received


def _fetch_payload(
    settings: Settings,
    endpoint_path: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = f"{settings.discourse_base_url}{endpoint_path}"
    try:
        response = requests.get(
            url,
            headers={
                "Api-Key": settings.discourse_api_key,
                "Api-Username": settings.discourse_api_username,
                "Accept": "application/json",
            },
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        raise DiscourseAPIError(f"Request failed for endpoint {endpoint_path}: {exc}") from exc

    if response.status_code >= 400:
        raise DiscourseAPIError(
            f"Failed fetching endpoint {endpoint_path} ({response.status_code}): {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise DiscourseAPIError(f"Invalid JSON response from endpoint {endpoint_path}") from exc

    if not isinstance(payload, dict):
        raise DiscourseAPIError(f"Unexpected JSON structure from endpoint {endpoint_path}")
    return payload


def fetch_user_totals(settings: Settings, username: str, timeout_seconds: int = 30) -> UserTotals:
    primary_endpoint = settings.user_endpoint_template.format(username=username)
    tried_endpoints: list[str] = [primary_endpoint]

    payload = _fetch_payload(settings, primary_endpoint, timeout_seconds)
    time_read_seconds, likes_received = _extract_metrics(payload)

    # Many Discourse instances expose these metrics at /u/{username}/summary.json.
    if time_read_seconds is None or likes_received is None:
        summary_endpoint = f"/u/{username}/summary.json"
        if summary_endpoint not in tried_endpoints:
            tried_endpoints.append(summary_endpoint)
            summary_payload = _fetch_payload(settings, summary_endpoint, timeout_seconds)
            summary_time, summary_likes = _extract_metrics(summary_payload)
            if time_read_seconds is None:
                time_read_seconds = summary_time
            if likes_received is None:
                likes_received = summary_likes

    if time_read_seconds is None or likes_received is None:
        raise DiscourseAPIError(
            f"Could not extract required metrics for {username}. "
            f"Tried endpoints: {', '.join(tried_endpoints)}. "
            "Set DISCOURSE_USER_ENDPOINT_TEMPLATE to an endpoint that returns cumulative "
            "time_read and likes_received, or share one JSON payload so I can adapt extraction."
        )

    return UserTotals(
        username=username,
        time_read_seconds=time_read_seconds,
        likes_received=likes_received,
        source_endpoint=",".join(tried_endpoints),
        captured_at_utc=datetime.now(timezone.utc),
    )
