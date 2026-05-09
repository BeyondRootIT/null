"""Settings: env-driven framework configuration (DB, Redis, obs, archive, security)."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DBSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_DB_", extra="ignore")

    dsn: str = "postgresql+asyncpg://cti_user:cti_pass@postgres:5432/cti"
    pool_size: int = 5
    max_overflow: int = 10


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_REDIS_", extra="ignore")

    url: str = "redis://redis:6379/0"


class ArchiveSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_ARCHIVE_", extra="ignore")

    backend: str = "filesystem"  # "filesystem" | "s3"
    root: str = "/var/lib/cti/raw"
    bucket: str | None = None
    prefix: str = "raw"
    endpoint_url: str | None = None


class ObsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_OBS_", extra="ignore")

    log_level: str = "INFO"
    log_json: bool = True
    metrics_port: int = 9090
    api_port: int = 8080
    otel_endpoint: str | None = None
    service_name: str = "cti"


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_SEC_", extra="ignore")

    api_token_file: str | None = None
    allow_http_egress: bool = False
    egress_extra_allowlist: list[str] = Field(default_factory=list)


class RuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CTI_RUN_", extra="ignore")

    sources_file: str = "config/sources.yaml"
    global_concurrency: int = 50
    default_rps: float = 5.0
    arq_queue: str = "cti:queue"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    db: DBSettings = Field(default_factory=DBSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    archive: ArchiveSettings = Field(default_factory=ArchiveSettings)
    obs: ObsSettings = Field(default_factory=ObsSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    runtime: RuntimeSettings = Field(default_factory=RuntimeSettings)


_cached: Settings | None = None


def get_settings() -> Settings:
    global _cached
    if _cached is None:
        _cached = Settings()
    return _cached


def reset_settings() -> None:
    """Test helper — drops the cached singleton."""
    global _cached
    _cached = None
