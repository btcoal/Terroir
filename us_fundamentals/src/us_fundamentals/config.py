"""Typed configuration profiles.

Profiles are `development`, `test`, `backfill`, and `production`. Values come
from environment variables with development-safe defaults; nothing secret is
committed. `production` and `backfill` refuse to start without an explicit
SEC contact and Postgres DSN so a misconfigured host cannot silently fall
back to development settings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from us_fundamentals.errors import ConfigurationError

PROFILES = ("development", "test", "backfill", "production")

_ENV_PREFIX = "TERROIR_"


@dataclass(frozen=True)
class SecTransportConfig:
    user_agent: str
    max_requests_per_second: float = 8.0
    max_retries: int = 5
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class AppConfig:
    profile: str
    data_root: Path
    postgres_dsn: str
    sec: SecTransportConfig
    log_level: str = "INFO"
    dataset_version: str = "dev-0"
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def bronze_dir(self) -> Path:
        return self.data_root / "bronze"

    @property
    def silver_dir(self) -> Path:
        return self.data_root / "silver"

    @property
    def gold_dir(self) -> Path:
        return self.data_root / "gold"

    @property
    def taxonomy_cache_dir(self) -> Path:
        return self.data_root / "taxonomy_packages"


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(_ENV_PREFIX + name, default)


def load_config(profile: str | None = None) -> AppConfig:
    resolved = profile or _env("PROFILE", "development") or "development"
    if resolved not in PROFILES:
        raise ConfigurationError(
            f"unknown profile {resolved!r}; expected one of {PROFILES}"
        )

    strict = resolved in ("backfill", "production")

    user_agent = _env("SEC_USER_AGENT")
    if user_agent is None:
        if strict:
            raise ConfigurationError(
                "TERROIR_SEC_USER_AGENT is required in "
                f"{resolved} (format: 'Org Name contact@example.com')"
            )
        user_agent = "Terroir-dev dev@localhost"
    if "@" not in user_agent:
        raise ConfigurationError(
            "TERROIR_SEC_USER_AGENT must include an administrative contact "
            "email, e.g. 'Terroir Research admin@example.com'"
        )

    dsn = _env("PG_DSN")
    if dsn is None:
        if strict:
            raise ConfigurationError(f"TERROIR_PG_DSN is required in {resolved}")
        dsn = f"dbname=terroir_{resolved}"

    default_root = {
        "development": "data/dev",
        "test": "data/test",
        "backfill": "data/backfill",
        "production": "data/production",
    }[resolved]
    data_root = Path(_env("DATA_ROOT", default_root) or default_root)

    rate = float(_env("SEC_MAX_RPS", "8.0") or "8.0")
    if not (0 < rate < 10):
        raise ConfigurationError(f"TERROIR_SEC_MAX_RPS must be in (0, 10); got {rate}")

    return AppConfig(
        profile=resolved,
        data_root=data_root,
        postgres_dsn=dsn,
        sec=SecTransportConfig(user_agent=user_agent, max_requests_per_second=rate),
        log_level=_env("LOG_LEVEL", "INFO") or "INFO",
        dataset_version=_env("DATASET_VERSION", "dev-0") or "dev-0",
    )
