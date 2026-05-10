"""Application runtime configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_CORS_ALLOWED_ORIGINS = ",".join(
    [
        "http://localhost:3000",
        "https://readwise.unsultan.cn",
        "https://www.readwise.unsultan.cn",
    ]
)


def _split_csv(value: str) -> list[str]:
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    cors_allowed_origins: list[str]
    cors_allow_credentials: bool


def current_env() -> str:
    return (
        os.getenv("APP_ENV")
        or os.getenv("ENV")
        or os.getenv("RAILWAY_ENVIRONMENT")
        or os.getenv("RAILWAY_ENVIRONMENT_NAME")
        or os.getenv("VERCEL_ENV")
        or "development"
    ).strip().lower()


def is_production_env() -> bool:
    return current_env() in {"prod", "production"}


def load_settings() -> Settings:
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", DEFAULT_CORS_ALLOWED_ORIGINS)
    frontend_url = os.getenv("FRONTEND_URL", "").strip().rstrip("/")
    origins = _split_csv(raw_origins)
    if frontend_url and frontend_url not in origins:
        origins.append(frontend_url)

    allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    return Settings(
        cors_allowed_origins=origins,
        cors_allow_credentials=allow_credentials,
    )

