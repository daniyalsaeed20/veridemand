"""Server bootstrap settings (CORS, logging, app version) for the foundation shell."""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import BaseModel, Field


class ServerSettings(BaseModel):
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    log_level: str = "INFO"
    app_version: str = "0.0.0-dev"

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> ServerSettings:
        env = environ if environ is not None else dict(os.environ)
        cors_raw = env.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
        origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
        return cls(
            cors_origins=origins,
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            app_version=env.get("APP_VERSION", "0.0.0-dev"),
        )


@lru_cache
def get_server_settings() -> ServerSettings:
    return ServerSettings.from_environment()
