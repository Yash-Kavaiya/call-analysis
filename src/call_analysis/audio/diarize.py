"""Multi-speaker diarization heuristics for contact-center turns."""

from __future__ import annotations

from call_analysis.models import TranscriptSegment

# Lightweight turn-taking diarization without pyannote GPU deps.
# Alternates speakers on long pauses and dialogue cues; good enough for QA UI.


def diarize_segments(
    segments: list[TranscriptSegment],
    *,
    pause_threshold: float = 0.8,
    max_speakers: int = 2,
) -> list[TranscriptSegment]:
    """
    Assign SPEAKER_00 / SPEAKER_01 (agent/customer style) using pause gaps
    and simple role heuristics. Mutates copies — returns new list.
    """
    if not segments:
        return []

    speakers = [f"SPEAKER_{i:02d}" for i in range(max(1, min(max_speakers, 4)))]
    out: list[TranscriptSegment] = []
    current_idx = 0
    prev_end = segments[0].start

    agent_cues = (
        "thank you for calling",
        "how may i",
        "how can i help",
        "my name is",
        "this is",
        "calling from",
        "account number",
        "is there anything else",
        "i can help",
        "let me check",
        "i understand",
    )
    customer_cues = (
        "i have a problem",
        "i need help",
        "my bill",
        "cancel",
        "refund",
        "not working",
        "i want to",
        "please help",
        "complaint",
    )

    for i, seg in enumerate(segments):
        text_l = seg.text.lower()
        gap = seg.start - prev_end if i > 0 else 0.0

        forced: int | None = None
        if any(c in text_l for c in agent_cues):
            forced = 0
        elif any(c in text_l for c in customer_cues):
            forced = 1 if len(speakers) > 1 else 0

        if forced is not None:
            current_idx = forced
        elif i > 0 and gap >= pause_threshold:
            current_idx = (current_idx + 1) % len(speakers)

        out.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text,
                speaker=speakers[current_idx],
                sentiment=seg.sentiment,
            )
        )
        prev_end = seg.end

    return out


def format_diarized_transcript(segments: list[TranscriptSegment]) -> str:
    """Human-readable multi-speaker transcript."""
    lines: list[str] = []
    for seg in segments:
        t0 = _fmt_ts(seg.start)
        t1 = _fmt_ts(seg.end)
        lines.append(f"[{t0}-{t1}] {seg.speaker}: {seg.text}")
    return "\n".join(lines)


def _fmt_ts(sec: float) -> str:
    sec = max(0.0, float(sec))
    m = int(sec // 60)
    s = int(sec % 60)
    return f"{m:02d}:{s:02d}"
