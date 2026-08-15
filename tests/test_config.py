"""Unit tests for NVIDIA credential loading (no live network)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from call_analysis.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    MissingAPIKeyError,
    NvidiaConfig,
    load_nvidia_config,
)


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    # Point dotenv away from any real project .env
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    with pytest.raises(MissingAPIKeyError, match="NVIDIA_API_KEY"):
        load_nvidia_config(env_file=empty_env, require_key=True)


def test_blank_key_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "   ")
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    with pytest.raises(MissingAPIKeyError):
        load_nvidia_config(env_file=empty_env, require_key=True)


def test_load_key_from_environ(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-key-12345")
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    cfg = load_nvidia_config(env_file=empty_env, require_key=True)
    assert cfg.api_key == "nvapi-test-key-12345"
    assert cfg.base_url == DEFAULT_BASE_URL
    assert cfg.model == DEFAULT_MODEL


def test_load_key_from_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NVIDIA_API_KEY=nvapi-from-dotenv\n"
        "NVIDIA_BASE_URL=https://example.invalid/v1\n"
        "NVIDIA_MODEL=org/custom-model\n",
        encoding="utf-8",
    )
    cfg = load_nvidia_config(env_file=env_file, require_key=True)
    assert cfg.api_key == "nvapi-from-dotenv"
    assert cfg.base_url == "https://example.invalid/v1"
    assert cfg.model == "org/custom-model"


def test_redacted_summary_never_leaks_full_key() -> None:
    cfg = NvidiaConfig(api_key="nvapi-super-secret-value-abcdef")
    summary = cfg.redacted_summary()
    assert "super-secret-value" not in summary
    assert "nvapi-" in summary or "***" in summary
    assert "len=" in summary
    assert DEFAULT_BASE_URL in summary or "base_url=" in summary


def test_require_key_false_allows_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    empty_env = tmp_path / ".env"
    empty_env.write_text("", encoding="utf-8")
    cfg = load_nvidia_config(env_file=empty_env, require_key=False)
    assert cfg.api_key == ""


def test_dotenv_overrides_stale_shell_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Project .env should win so key rotation in .env takes effect."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-stale-shell-key")
    env_file = tmp_path / ".env"
    env_file.write_text("NVIDIA_API_KEY=nvapi-fresh-from-dotenv\n", encoding="utf-8")
    cfg = load_nvidia_config(env_file=env_file, require_key=True, override_env=True)
    assert cfg.api_key == "nvapi-fresh-from-dotenv"
