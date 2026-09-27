"""Environment-based settings for the local service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _path(name: str, default: str) -> Path:
    value = Path(os.environ.get(name, default)).expanduser()
    return value if value.is_absolute() else ROOT_DIR / value


@dataclass(frozen=True)
class Settings:
    host: str = os.environ.get("HOST", "127.0.0.1")
    port: int = int(os.environ.get("PORT", "8123"))
    database_path: Path = _path("DATABASE_PATH", "data/google-flow-music.db")
    request_timeout: float = float(os.environ.get("FLOWMUSIC_REQUEST_TIMEOUT", "90"))
    poll_interval: float = float(os.environ.get("FLOWMUSIC_POLL_INTERVAL", "5"))
    poll_timeout: float = float(os.environ.get("FLOWMUSIC_POLL_TIMEOUT", "900"))
    auth_retry_limit: int = int(os.environ.get("FLOWMUSIC_AUTH_RETRY_LIMIT", "3"))
    expected_clips: int = int(os.environ.get("FLOWMUSIC_EXPECTED_CLIPS", "2"))


settings = Settings()
