"""Hosted NVIDIA NIM chat-completions client (OpenAI-compatible)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from call_analysis.config import NvidiaConfig

DEFAULT_TIMEOUT_S = 120.0
CHAT_COMPLETIONS_PATH = "/chat/completions"


class NimError(RuntimeError):
    """Base error for NIM client failures."""


class NimAuthError(NimError):
    """401/403 style authentication failure."""


class NimHTTPError(NimError):
    """Non-success HTTP status from the NIM endpoint."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(f"NIM HTTP {status_code}: {message}")


class NimResponseError(NimError):
    """Response body missing or malformed (no usable completion text)."""


@dataclass(frozen=True)
class NimCompletionResult:
    """Parsed successful chat completion."""

    text: str
    model: str
    status_code: int
    raw: Mapping[str, Any]

    @property
    def ok(self) -> bool:
        return bool(self.text and self.text.strip())


def build_chat_completion_request(
    config: NvidiaConfig,
    *,
    prompt: str = "Reply with exactly one word: pong",
    system: str | None = None,
    messages: Sequence[Mapping[str, str]] | None = None,
    max_tokens: int = 32,
    temperature: float = 0.0,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """
    Build OpenAI-compatible chat/completions URL, headers, and JSON body.

    Pure helper — no network I/O. Returns (url, headers, body).
    """
    if not config.api_key:
        raise NimAuthError("Cannot build NIM request without an API key")

    if messages is not None:
        msg_list = [dict(m) for m in messages]
    else:
        if not prompt or not str(prompt).strip():
            raise ValueError("prompt must be a non-empty string")
        msg_list = []
        if system:
            msg_list.append({"role": "system", "content": system})
        msg_list.append({"role": "user", "content": prompt})

    if not msg_list:
        raise ValueError("messages must be non-empty")

    url = f"{config.base_url.rstrip('/')}{CHAT_COMPLETIONS_PATH}"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    body: dict[str, Any] = {
        "model": config.model,
        "messages": msg_list,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }
    return url, headers, body


def parse_chat_completion_response(
    payload: Mapping[str, Any] | str | bytes,
    *,
    status_code: int = 200,
) -> NimCompletionResult:
    """
    Extract completion text from an OpenAI-compatible chat completion body.

    Raises NimResponseError when choices/content are missing or empty.
    """
    if isinstance(payload, (str, bytes)):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise NimResponseError(f"Invalid JSON in NIM response: {exc}") from exc
    else:
        data = dict(payload)

    if not isinstance(data, dict):
        raise NimResponseError("NIM response must be a JSON object")

    choices = data.get("choices")
    if not choices or not isinstance(choices, list):
        raise NimResponseError("NIM response missing non-empty 'choices' array")

    first = choices[0]
    if not isinstance(first, dict):
        raise NimResponseError("NIM choice entry is not an object")

    text = ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(str(part.get("text") or ""))
                elif isinstance(part, str):
                    parts.append(part)
            text = "".join(parts)
    if not text and isinstance(first.get("text"), str):
        text = first["text"]

    text = (text or "").strip()
    if not text:
        raise NimResponseError(
            "NIM response has empty completion content "
            f"(status={status_code}, model={data.get('model')!r})"
        )

    model = str(data.get("model") or "")
    return NimCompletionResult(
        text=text,
        model=model,
        status_code=status_code,
        raw=data,
    )


def _classify_http_error(status_code: int, body_text: str) -> NimError:
    snippet = (body_text or "").strip().replace("\n", " ")[:300]
    if status_code in (401, 403):
        return NimAuthError(
            f"Authentication failed (HTTP {status_code}). "
            f"Check NVIDIA_API_KEY. Body: {snippet or '(empty)'}"
        )
    return NimHTTPError(status_code, snippet or "(empty body)")


def chat_completion(
    config: NvidiaConfig,
    *,
    prompt: str | None = None,
    system: str | None = None,
    messages: Sequence[Mapping[str, str]] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    timeout: float = DEFAULT_TIMEOUT_S,
    client: httpx.Client | None = None,
) -> NimCompletionResult:
    """POST a chat completion to hosted NIM and return parsed text."""
    url, headers, body = build_chat_completion_request(
        config,
        prompt=prompt or " ",
        system=system,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # When messages provided, rebuild without dummy prompt path issues
    if messages is not None:
        url, headers, body = build_chat_completion_request(
            config,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=timeout)

    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.RequestError as exc:
        raise NimError(f"Network error calling NIM at {url}: {exc}") from exc
    finally:
        if owns_client:
            client.close()

    status = response.status_code
    if status >= 400:
        raise _classify_http_error(status, response.text)

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise NimResponseError(
            f"Non-JSON success body (HTTP {status}): {response.text[:200]!r}"
        ) from exc

    return parse_chat_completion_response(payload, status_code=status)


def validate_nim_completion(
    config: NvidiaConfig,
    *,
    prompt: str = "Reply with exactly one word: pong",
    timeout: float = DEFAULT_TIMEOUT_S,
    client: httpx.Client | None = None,
) -> NimCompletionResult:
    """Smoke-test: simple completion (Phase 1 entry point)."""
    return chat_completion(
        config,
        prompt=prompt,
        max_tokens=32,
        temperature=0.0,
        timeout=timeout,
        client=client,
    )


def extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort extract of a JSON object from model output."""
    text = (text or "").strip()
    if not text:
        raise NimResponseError("Empty text; cannot parse JSON")

    # Strip markdown fences
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as exc:
            raise NimResponseError(f"Could not parse JSON object: {exc}") from exc

    raise NimResponseError(f"No JSON object found in model output: {text[:200]!r}")


def chat_json(
    config: NvidiaConfig,
    *,
    system: str,
    prompt: str,
    max_tokens: int = 1200,
    temperature: float = 0.1,
    timeout: float = DEFAULT_TIMEOUT_S,
    client: httpx.Client | None = None,
) -> tuple[dict[str, Any], str]:
    """Chat completion expecting JSON; returns (parsed_dict, raw_text)."""
    result = chat_completion(
        config,
        system=system,
        prompt=prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
        client=client,
    )
    return extract_json_object(result.text), result.text
