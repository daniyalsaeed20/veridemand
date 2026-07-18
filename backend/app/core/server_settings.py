"""Server bootstrap settings (CORS, logging, temp) — outside contracted AppSettings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


def _default_temp_root() -> Path:
    # Repo-relative tmp/sessions when running from backend/; override via TEMP_ROOT.
    return Path(__file__).resolve().parents[3] / "tmp" / "sessions"


class ServerSettings(BaseModel):
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    log_level: str = "INFO"
    app_version: str = "0.0.0-dev"
    temp_root: Path = Field(default_factory=_default_temp_root)
    max_active_sessions: int = 32
    session_cleanup_interval_seconds: int = 60

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> ServerSettings:
        env = environ if environ is not None else dict(os.environ)
        cors_raw = env.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
        temp_raw = env.get("TEMP_ROOT", "").strip()
        temp_root = Path(temp_raw) if temp_raw else _default_temp_root()
        max_sessions = int(env.get("MAX_ACTIVE_SESSIONS", "32") or "32")
        cleanup_interval = int(env.get("SESSION_CLEANUP_INTERVAL_SECONDS", "60") or "60")
        return cls(
            cors_origins=origins,
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            app_version=env.get("APP_VERSION", "0.0.0-dev"),
            temp_root=temp_root,
            max_active_sessions=max_sessions,
            session_cleanup_interval_seconds=max(5, cleanup_interval),
        )


@lru_cache
def get_server_settings() -> ServerSettings:
    return ServerSettings.from_environment()
