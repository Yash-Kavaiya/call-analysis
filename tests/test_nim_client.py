"""Unit tests for NIM request building and response parsing (shipped helpers)."""

from __future__ import annotations

import json

import pytest

from call_analysis.config import NvidiaConfig
from call_analysis.nim_client import (
    CHAT_COMPLETIONS_PATH,
    NimAuthError,
    NimResponseError,
    build_chat_completion_request,
    parse_chat_completion_response,
)


def _config(**kwargs: str) -> NvidiaConfig:
    defaults = {
        "api_key": "nvapi-unit-test-key",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.1-8b-instruct",
    }
    defaults.update(kwargs)
    return NvidiaConfig(**defaults)


def test_build_request_shape() -> None:
    cfg = _config()
    url, headers, body = build_chat_completion_request(
        cfg, prompt="hello", max_tokens=16, temperature=0.0
    )
    assert url == f"https://integrate.api.nvidia.com/v1{CHAT_COMPLETIONS_PATH}"
    assert headers["Authorization"] == "Bearer nvapi-unit-test-key"
    assert headers["Content-Type"] == "application/json"
    assert body["model"] == "meta/llama-3.1-8b-instruct"
    assert body["stream"] is False
    assert body["max_tokens"] == 16
    assert body["messages"] == [{"role": "user", "content": "hello"}]


def test_build_request_strips_trailing_slash_on_base() -> None:
    cfg = _config(base_url="https://integrate.api.nvidia.com/v1/")
    url, _, _ = build_chat_completion_request(cfg, prompt="x")
    assert url == "https://integrate.api.nvidia.com/v1/chat/completions"
    assert "//chat" not in url.replace("https://", "")


def test_build_request_rejects_missing_key() -> None:
    cfg = _config(api_key="")
    with pytest.raises(NimAuthError):
        build_chat_completion_request(cfg, prompt="hi")


def test_build_request_rejects_empty_prompt() -> None:
    with pytest.raises(ValueError, match="prompt"):
        build_chat_completion_request(_config(), prompt="  ")


def test_parse_standard_chat_completion() -> None:
    payload = {
        "id": "chatcmpl-test",
        "model": "meta/llama-3.1-8b-instruct",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "  pong  "},
                "finish_reason": "stop",
            }
        ],
    }
    result = parse_chat_completion_response(payload, status_code=200)
    assert result.ok
    assert result.text == "pong"
    assert result.model == "meta/llama-3.1-8b-instruct"
    assert result.status_code == 200


def test_parse_json_string_body() -> None:
    raw = json.dumps(
        {
            "model": "x",
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }
    )
    result = parse_chat_completion_response(raw, status_code=200)
    assert result.text == "ok"


def test_parse_legacy_text_field() -> None:
    payload = {"choices": [{"text": "legacy completion"}]}
    result = parse_chat_completion_response(payload)
    assert result.text == "legacy completion"


def test_parse_rejects_empty_choices() -> None:
    with pytest.raises(NimResponseError, match="choices"):
        parse_chat_completion_response({"choices": []})


def test_parse_rejects_empty_content() -> None:
    with pytest.raises(NimResponseError, match="empty completion"):
        parse_chat_completion_response(
            {"choices": [{"message": {"role": "assistant", "content": "   "}}]}
        )


def test_parse_rejects_invalid_json() -> None:
    with pytest.raises(NimResponseError, match="Invalid JSON"):
        parse_chat_completion_response("{not-json")


def test_parse_multimodal_content_parts() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "hello "},
                        {"type": "text", "text": "world"},
                    ],
                }
            }
        ]
    }
    result = parse_chat_completion_response(payload)
    assert result.text == "hello world"
