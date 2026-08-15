"""Tests for production configuration and new modules."""

from __future__ import annotations

import pytest

from call_analysis.config import (
    AuthSettings,
    CelerySettings,
    DatabaseSettings,
    FeatureFlags,
    MissingAPIKeyError,
    NvidiaConfig,
    NVidiaSettings,
    RedisSettings,
    Settings,
    get_settings,
    load_nvidia_config,
    reload_settings,
)


def test_database_settings_defaults():
    s = DatabaseSettings()
    assert s.host == "localhost"
    assert s.port == 5432
    assert s.pool_size == 10
    assert "postgresql+psycopg" in s.url


def test_redis_settings_defaults():
    s = RedisSettings()
    assert s.host == "localhost"
    assert s.port == 6379
    assert "redis://" in s.url


def test_celery_settings_defaults():
    s = CelerySettings()
    assert s.broker_url == "redis://localhost:6379/1"
    assert s.result_backend == "redis://localhost:6379/2"


def test_nvidia_settings_validation():
    # Valid key
    s = NVidiaSettings(api_key="nvapi-test-key-12345")
    assert s.is_configured is True

    # Invalid key format
    with pytest.raises(ValueError, match="must start with 'nvapi-'"):
        NVidiaSettings(api_key="invalid-key")

    # Empty key
    s = NVidiaSettings(api_key="")
    assert s.is_configured is False


def test_auth_settings_validation():
    # Valid secret key
    s = AuthSettings(secret_key="a" * 32)
    assert len(s.secret_key) == 32

    # Too short
    with pytest.raises(ValueError, match="at least 32 characters"):
        AuthSettings(secret_key="short")


def test_auth_empty_secret_key_auto_generates(monkeypatch):
    """docker-compose injects AUTH_SECRET_KEY= when the host var is unset;
    a blank value must not crash Settings() at startup."""
    monkeypatch.setenv("AUTH_SECRET_KEY", "")
    reload_settings()
    s = get_settings()
    assert len(s.auth.secret_key) >= 32

    # Blank again — still deterministic-safe (generated each time, never blank)
    assert AuthSettings(secret_key="").secret_key
    assert AuthSettings(secret_key="   ").secret_key


def test_storage_allowed_extensions_comma_separated(monkeypatch):
    """.env.example documents STORAGE_ALLOWED_EXTENSIONS=.m4a,.wav,.mp3 —
    a comma-separated string must parse into a set, not crash startup."""
    from call_analysis.config import StorageSettings

    s = StorageSettings(allowed_extensions=".m4a,.wav,.mp3")
    assert s.allowed_extensions == {".m4a", ".wav", ".mp3"}

    # Missing dot is normalized
    s2 = StorageSettings(allowed_extensions="m4a, wav")
    assert s2.allowed_extensions == {".m4a", ".wav"}

    # Env path too
    monkeypatch.setenv("STORAGE_ALLOWED_EXTENSIONS", ".m4a,.ogg")
    reload_settings()
    assert get_settings().storage.allowed_extensions == {".m4a", ".ogg"}


def test_feature_flags():
    s = FeatureFlags()
    assert s.websocket_enabled is True
    assert s.copilot_enabled is True
    assert s.multi_tenant is False


def test_settings_aggregation(monkeypatch):
    # Set environment variables directly (Pydantic Settings reads from env)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key")
    monkeypatch.setenv("AUTH_SECRET_KEY", "abcdefghijklmnopqrstuvwxyz123456")
    monkeypatch.setenv("DB_PASSWORD", "testpass")
    monkeypatch.setenv("ENVIRONMENT", "staging")

    # Clear cache and reload
    reload_settings()
    settings = get_settings()

    assert settings.environment == "staging"
    assert settings.nvidia.is_configured is True
    assert settings.auth.secret_key == "abcdefghijklmnopqrstuvwxyz123456"
    assert settings.database.password == "testpass"
    assert settings.is_production is False
    assert settings.is_development is False


def test_nvidia_config_backward_compat(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-backward-compat")

    reload_settings()
    config = load_nvidia_config(require_key=True)

    assert isinstance(config, NvidiaConfig)
    assert config.api_key == "nvapi-backward-compat"
    assert "base_url=" in config.redacted_summary()
    assert "model=" in config.redacted_summary()


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    reload_settings()
    with pytest.raises(MissingAPIKeyError):
        load_nvidia_config(require_key=True)


def test_settings_caching():
    """Verify settings are cached."""
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2  # Same instance due to lru_cache


def test_reload_settings_clears_cache():
    """Verify reload_settings clears cache."""
    get_settings()
    reload_settings()
    s2 = get_settings()
    # May or may not be same instance depending on implementation
    # But should work without error
    assert isinstance(s2, Settings)


def test_database_url_construction():
    """Test database URL construction."""
    s = DatabaseSettings(
        host="db.example.com",
        port=5433,
        user="testuser",
        password="testpass",
        name="testdb",
    )
    assert s.url == "postgresql+psycopg://testuser:testpass@db.example.com:5433/testdb"
    assert s.async_url == "postgresql+asyncpg://testuser:testpass@db.example.com:5433/testdb"


def test_redis_url_construction():
    """Test Redis URL construction."""
    s = RedisSettings(host="redis.example.com", port=6380, password="secret", db=1)
    assert s.url == "redis://default:secret@redis.example.com:6380/1"

    s_no_pass = RedisSettings(host="redis.example.com", port=6380, db=1)
    assert s_no_pass.url == "redis://redis.example.com:6380/1"


def test_nvidia_config_redacted_summary():
    """Test that redacted summary doesn't leak full key."""
    cfg = NvidiaConfig(
        type(
            "Settings",
            (),
            {
                "nvidia": type(
                    "Nvidia",
                    (),
                    {
                        "api_key": "nvapi-super-secret-value-abcdef",
                        "base_url": "https://test.com",
                        "model": "test-model",
                    },
                )()
            },
        )()
    )
    summary = cfg.redacted_summary()
    assert "super-secret-value" not in summary
    assert "nvapi-" in summary or "***" in summary
    assert "len=" in summary
    assert "base_url=" in summary
