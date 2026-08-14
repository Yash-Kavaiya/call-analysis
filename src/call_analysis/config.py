"""Production-ready configuration using Pydantic Settings with validation."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    user: str = "call_analysis"
    password: str = "changeme"
    name: str = "call_analysis"
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False
    echo_pool: bool = False

    @computed_field
    @property
    def url(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @computed_field
    @property
    def async_url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", extra="ignore")

    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    db: int = 0
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    decode_responses: bool = True

    @computed_field
    @property
    def url(self) -> str:
        if self.password:
            return f"redis://default:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class CelerySettings(BaseSettings):
    """Celery task queue settings."""

    model_config = SettingsConfigDict(env_prefix="CELERY_", extra="ignore")

    broker_url: str = "redis://localhost:6379/1"
    result_backend: str = "redis://localhost:6379/2"
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: list[str] = ["json"]
    timezone: str = "UTC"
    enable_utc: bool = True
    task_track_started: bool = True
    task_time_limit: int = 3600
    task_soft_time_limit: int = 3300
    worker_prefetch_multiplier: int = 4
    worker_max_tasks_per_child: int = 100
    result_expires: int = 86400
    beat_schedule_filename: str = "celerybeat-schedule"


class NVidiaSettings(BaseSettings):
    """NVIDIA NIM API settings."""

    model_config = SettingsConfigDict(env_prefix="NVIDIA_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "meta/llama-3.1-8b-instruct"
    timeout: float = 120.0
    max_retries: int = 3
    retry_backoff: float = 1.0

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        v = v.strip()
        if v and not v.startswith("nvapi-"):
            raise ValueError("NVIDIA_API_KEY must start with 'nvapi-'")
        return v

    @computed_field
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("nvapi-"))


class ASRSettings(BaseSettings):
    """ASR (Speech-to-Text) settings."""

    model_config = SettingsConfigDict(env_prefix="ASR_", extra="ignore")

    model_size: Literal["tiny", "base", "small", "medium", "large-v3"] = "base"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    compute_type: Literal["int8", "float16", "float32"] = "int8"
    beam_size: int = 5
    vad_filter: bool = True
    language: str | None = None
    download_root: str | None = None


class DiarizationSettings(BaseSettings):
    """Speaker diarization settings."""

    model_config = SettingsConfigDict(env_prefix="DIARIZATION_", extra="ignore")

    enabled: bool = True
    provider: Literal["heuristic", "pyannote"] = "heuristic"
    hf_token: str | None = None
    min_speakers: int = 2
    max_speakers: int = 4
    pyannote_model: str = "pyannote/speaker-diarization-3.1"


class PIUSettings(BaseSettings):
    """PII detection settings."""

    model_config = SettingsConfigDict(env_prefix="PII_", extra="ignore")

    enabled: bool = True
    custom_patterns: list[str] = []
    ml_model: str | None = None
    confidence_threshold: float = 0.85


class AuthSettings(BaseSettings):
    """Authentication & authorization settings."""

    model_config = SettingsConfigDict(env_prefix="AUTH_", extra="ignore")

    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    api_key_prefix: str = "ca_"
    api_key_length: int = 32
    bcrypt_rounds: int = 12
    jwt_audience: str = "call-analysis"
    jwt_issuer: str = "call-analysis"

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("AUTH_SECRET_KEY must be at least 32 characters")
        return v


class RateLimitSettings(BaseSettings):
    """Rate limiting settings."""

    model_config = SettingsConfigDict(env_prefix="RATELIMIT_", extra="ignore")

    enabled: bool = True
    default_limit: str = "100/minute"
    upload_limit: str = "10/minute"
    analyze_limit: str = "20/minute"
    copilot_limit: str = "30/minute"
    storage_url: str = "memory://"
    strategy: Literal["fixed-window", "sliding-window"] = "sliding-window"


class CorsSettings(BaseSettings):
    """CORS settings."""

    model_config = SettingsConfigDict(env_prefix="CORS_", extra="ignore")

    enabled: bool = True
    allow_origins: list[str] = ["http://localhost:8787", "http://127.0.0.1:8787"]
    allow_origin_regex: str | None = None
    allow_methods: list[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers: list[str] = ["*"]
    allow_credentials: bool = True
    expose_headers: list[str] = ["X-Request-ID"]
    max_age: int = 86400


class LoggingSettings(BaseSettings):
    """Structured logging settings."""

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: Literal["json", "console"] = "console"
    file_path: str | None = None
    file_max_bytes: int = 10_485_760  # 10MB
    file_backup_count: int = 5
    include_trace: bool = True
    redact_keys: list[str] = ["password", "secret", "token", "api_key", "authorization"]


class TelemetrySettings(BaseSettings):
    """OpenTelemetry settings."""

    model_config = SettingsConfigDict(env_prefix="OTEL_", extra="ignore")

    enabled: bool = True
    service_name: str = "call-analysis"
    service_version: str = "0.4.0"
    environment: str = "development"
    exporter_endpoint: str = "http://localhost:4317"
    exporter_headers: dict[str, str] = {}
    traces_sampler: Literal["always_on", "always_off", "parentbased_always_on", "parentbased_always_off", "traceidratio"] = "parentbased_always_on"
    traces_sampler_arg: float = 1.0
    metrics_interval: int = 60
    propagators: list[str] = ["tracecontext", "baggage"]


class StorageSettings(BaseSettings):
    """File storage settings."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_", extra="ignore")

    data_dir: Path = Path("data")
    uploads_dir: Path = Path("data/uploads")
    calls_dir: Path = Path("data/calls")
    audio_dir: Path = Path("data/audio")
    max_upload_size: int = 500 * 1024 * 1024  # 500MB
    allowed_extensions: set[str] = {".m4a", ".wav", ".mp3", ".ogg", ".flac", ".webm"}
    quarantine_dir: Path = Path("data/quarantine")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        for d in (self.data_dir, self.uploads_dir, self.calls_dir, self.audio_dir, self.quarantine_dir):
            d.mkdir(parents=True, exist_ok=True)


class ServerSettings(BaseSettings):
    """HTTP server settings."""

    model_config = SettingsConfigDict(env_prefix="SERVER_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8787
    workers: int = 1
    reload: bool = False
    access_log: bool = True
    proxy_headers: bool = True
    forwarded_allow_ips: str = "*"
    timeout_keep_alive: int = 75
    timeout_graceful_shutdown: int = 30


class FeatureFlags(BaseSettings):
    """Feature flags for gradual rollout."""

    model_config = SettingsConfigDict(env_prefix="FEATURE_", extra="ignore")

    websocket_enabled: bool = True
    copilot_enabled: bool = True
    batch_import_enabled: bool = True
    reanalyze_enabled: bool = True
    export_enabled: bool = False
    webhook_enabled: bool = False
    multi_tenant: bool = False
    advanced_diarization: bool = False


class Settings(BaseSettings):
    """Main application settings aggregating all sub-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    # Application metadata
    app_name: str = "Call Analysis"
    app_version: str = "0.4.0"
    environment: Literal["development", "staging", "production", "testing"] = "development"
    debug: bool = False

    # Sub-settings (auto-loaded from env with prefixes)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    nvidia: NVidiaSettings = Field(default_factory=NVidiaSettings)
    asr: ASRSettings = Field(default_factory=ASRSettings)
    diarization: DiarizationSettings = Field(default_factory=DiarizationSettings)
    pii: PIUSettings = Field(default_factory=PIUSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    ratelimit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        valid = {"development", "staging", "production", "testing"}
        if v not in valid:
            raise ValueError(f"ENVIRONMENT must be one of {valid}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_testing(self) -> bool:
        return self.environment == "testing"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings() -> Settings:
    """Force reload of settings (useful for testing)."""
    get_settings.cache_clear()
    return get_settings()


# Backward compatibility for existing code
class NvidiaConfig:
    """Legacy config object for existing NIM client code."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        if api_key is not None or base_url is not None or model is not None:
            # Direct initialization (old style)
            self.api_key = api_key or ""
            self.base_url = base_url or DEFAULT_BASE_URL
            self.model = model or DEFAULT_MODEL
        else:
            # From Settings (new style)
            s = settings or get_settings()
            self.api_key = s.nvidia.api_key
            self.base_url = s.nvidia.base_url
            self.model = s.nvidia.model

    def redacted_summary(self) -> str:
        key = self.api_key
        if len(key) <= 8:
            masked = "***"
        else:
            masked = f"{key[:6]}...{key[-4:]} (len={len(key)})"
        return f"base_url={self.base_url}\nmodel={self.model}\napi_key={masked}"


class MissingAPIKeyError(RuntimeError):
    """Raised when NVIDIA_API_KEY is absent or blank."""

    pass


def load_nvidia_config(
    *,
    env_file: str | Path | None = None,
    require_key: bool = True,
    override_env: bool = True,
) -> NvidiaConfig:
    """Load NVIDIA config from settings (backward compatible)."""
    if env_file is not None:
        # Load from specific .env file using python-dotenv
        from dotenv import load_dotenv
        load_dotenv(env_file, override=override_env)
        # Reload settings to pick up new environment variables
        settings = reload_settings()
    else:
        settings = get_settings()
    
    if require_key and not settings.nvidia.is_configured:
        raise MissingAPIKeyError(
            "NVIDIA_API_KEY is not set. Export it or put it in a local .env file "
            "(see .env.example). Get a free key at https://build.nvidia.com"
        )
    return NvidiaConfig(settings)


# =============================================================================
# Backward compatibility exports
# =============================================================================

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "meta/llama-3.1-8b-instruct"

__all__ = [
    "Settings",
    "DatabaseSettings",
    "RedisSettings",
    "CelerySettings",
    "NVidiaSettings",
    "ASRSettings",
    "DiarizationSettings",
    "PIUSettings",
    "AuthSettings",
    "RateLimitSettings",
    "CorsSettings",
    "LoggingSettings",
    "TelemetrySettings",
    "FeatureFlags",
    "ServerSettings",
    "StorageSettings",
    "get_settings",
    "reload_settings",
    "NvidiaConfig",
    "MissingAPIKeyError",
    "load_nvidia_config",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
]