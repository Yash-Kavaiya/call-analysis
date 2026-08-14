"""Regex-based PII detection and redaction for contact-center transcripts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from call_analysis.models import PiiFinding, TranscriptSegment


@dataclass
class ScrubResult:
    scrubbed_text: str
    findings: list[PiiFinding]
    scrubbed_segments: list[TranscriptSegment]


# Patterns ordered so more specific matches win when applied left-to-right carefully
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    (
        "EMAIL",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{2,4}\)?[-.\s]?)?\d{3,4}[-.\s]?\d{3,4}(?!\w)"
        ),
        "[PHONE]",
    ),
    (
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        "[CARD]",
    ),
    (
        "SSN",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "[SSN]",
    ),
    (
        "AADHAAR",
        re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
        "[AADHAAR]",
    ),
    (
        "ACCOUNT",
        re.compile(
            r"\b(?:account|acct|a/c|customer\s*id|policy)(?:\s*(?:number|no\.?|#))?\s*[:#]?\s*[A-Za-z0-9-]{6,}\b",
            re.IGNORECASE,
        ),
        "[ACCOUNT]",
    ),
]


def scrub_text(text: str) -> tuple[str, list[PiiFinding]]:
    """Redact PII spans in ``text``; return scrubbed string and findings."""
    if not text:
        return "", []

    findings: list[PiiFinding] = []
    # Collect all matches with positions, resolve overlaps (prefer earlier + longer)
    matches: list[tuple[int, int, str, str]] = []
    for entity_type, pattern, redaction in _PATTERNS:
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            # Avoid over-redacting short digit noise for phone
            if entity_type == "PHONE" and end - start < 8:
                continue
            if entity_type == "CREDIT_CARD":
                digits = re.sub(r"\D", "", m.group(0))
                if len(digits) < 13 or len(digits) > 19:
                    continue
            matches.append((start, end, entity_type, redaction))

    matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    selected: list[tuple[int, int, str, str]] = []
    occupied: list[tuple[int, int]] = []
    for start, end, entity_type, redaction in matches:
        if any(not (end <= a or start >= b) for a, b in occupied):
            continue
        selected.append((start, end, entity_type, redaction))
        occupied.append((start, end))

    selected.sort(key=lambda x: x[0])
    parts: list[str] = []
    cursor = 0
    for start, end, entity_type, redaction in selected:
        parts.append(text[cursor:start])
        parts.append(redaction)
        findings.append(
            PiiFinding(
                entity_type=entity_type,
                start=start,
                end=end,
                redaction=redaction,
            )
        )
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts), findings


def scrub_pii(
    text: str,
    segments: list[TranscriptSegment] | None = None,
) -> ScrubResult:
    """Scrub full transcript and optional diarized segments."""
    scrubbed, findings = scrub_text(text)
    scrubbed_segments: list[TranscriptSegment] = []
    if segments:
        for seg in segments:
            st, _ = scrub_text(seg.text)
            scrubbed_segments.append(
                TranscriptSegment(
                    start=seg.start,
                    end=seg.end,
                    text=st,
                    speaker=seg.speaker,
                    sentiment=seg.sentiment,
                )
            )
    return ScrubResult(
        scrubbed_text=scrubbed,
        findings=findings,
        scrubbed_segments=scrubbed_segments or list(segments or []),
    )
