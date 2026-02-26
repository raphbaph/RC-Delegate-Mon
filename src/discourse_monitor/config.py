from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    discourse_base_url: str
    discourse_api_key: str
    discourse_api_username: str
    monitored_usernames: list[str]
    database_path: Path
    user_endpoint_template: str


class ConfigError(RuntimeError):
    pass


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> Settings:
    base_url = _required_env("DISCOURSE_BASE_URL").rstrip("/")
    api_key = _required_env("DISCOURSE_API_KEY")
    api_user = _required_env("DISCOURSE_API_USERNAME")

    usernames_csv = _required_env("DISCOURSE_MONITORED_USERNAMES")
    usernames = [u.strip() for u in usernames_csv.split(",") if u.strip()]
    if not usernames:
        raise ConfigError("DISCOURSE_MONITORED_USERNAMES did not contain any usernames")

    default_db = Path("./data/discourse_monitor.db")
    db_path = Path(os.getenv("DISCOURSE_MONITOR_DB_PATH", str(default_db))).expanduser()

    endpoint_template = os.getenv("DISCOURSE_USER_ENDPOINT_TEMPLATE", "/u/{username}.json").strip()
    if "{username}" not in endpoint_template:
        raise ConfigError("DISCOURSE_USER_ENDPOINT_TEMPLATE must include '{username}'")

    return Settings(
        discourse_base_url=base_url,
        discourse_api_key=api_key,
        discourse_api_username=api_user,
        monitored_usernames=usernames,
        database_path=db_path,
        user_endpoint_template=endpoint_template,
    )
