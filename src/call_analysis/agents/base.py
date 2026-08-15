"""Shared agent helpers for JSON-structured NIM calls."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from call_analysis.models import AgentResult
from call_analysis.nim_client import NimError, chat_json

if TYPE_CHECKING:
    from call_analysis.config import NvidiaConfig


def run_structured_agent(
    config: NvidiaConfig,
    *,
    name: str,
    system: str,
    prompt: str,
    max_tokens: int = 1200,
) -> AgentResult:
    """Call NIM, parse JSON, map to AgentResult with graceful degradation."""
    try:
        data, raw = chat_json(
            config,
            system=system,
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.1,
        )
    except NimError as exc:
        return AgentResult(
            name=name,
            summary=f"Agent unavailable: {exc}",
            score=None,
            details={"error": str(exc)},
            raw_text="",
        )
    except Exception as exc:
        return AgentResult(
            name=name,
            summary=f"Agent failed: {exc}",
            score=None,
            details={"error": str(exc)},
            raw_text="",
        )

    summary = str(data.get("summary") or data.get("overview") or "").strip()
    if not summary:
        summary = str(data)[:400]

    score = data.get("score")
    if score is not None:
        try:
            score = float(score)
            score = max(0.0, min(100.0, score))
        except (TypeError, ValueError):
            score = None

    details = {k: v for k, v in data.items() if k not in ("summary", "overview", "score")}
    return AgentResult(
        name=name,
        summary=summary,
        score=score,
        details=details,
        raw_text=raw,
    )


def transcript_block(transcript: str, *, max_chars: int = 12000) -> str:
    t = (transcript or "").strip()
    if len(t) > max_chars:
        return t[: max_chars - 20] + "\n...[truncated truncated]..."
    return t


def heuristic_sentiment_timeline(
    segments: list[Any],
) -> list[dict[str, Any]]:
    """Keyword sentiment curve when NIM segment scoring is skipped."""
    positive = {
        "thank",
        "thanks",
        "great",
        "good",
        "perfect",
        "appreciate",
        "happy",
        "resolved",
        "excellent",
        "wonderful",
        "please",
        "help",
    }
    negative = {
        "angry",
        "upset",
        "terrible",
        "worst",
        "hate",
        "cancel",
        "refund",
        "complaint",
        "problem",
        "issue",
        "not working",
        "frustrated",
        "scam",
        "spam",
        "useless",
        "ridiculous",
        "delay",
        "wait",
    }
    points: list[dict[str, Any]] = []
    for seg in segments:
        text = (getattr(seg, "text", "") or "").lower()
        score = 0.0
        for w in positive:
            if w in text:
                score += 0.15
        for w in negative:
            if w in text:
                score -= 0.2
        score = max(-1.0, min(1.0, score))
        points.append(
            {
                "t": float(getattr(seg, "start", 0.0)),
                "sentiment": score,
                "speaker": getattr(seg, "speaker", "SPEAKER_00"),
            }
        )
        with contextlib.suppress(Exception):
            seg.sentiment = score
    return points
