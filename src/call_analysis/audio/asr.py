"""Speech-to-text via faster-whisper (CPU fallback when GPU unavailable)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from call_analysis.models import TranscriptSegment


@dataclass
class TranscriptionResult:
    text: str
    language: str | None
    segments: list[TranscriptSegment]
    duration: float | None
    device: str
    model_size: str


def _pick_device() -> str:
    """Prefer CUDA when available; otherwise CPU (architecture: GPU then CPU)."""
    forced = (os.environ.get("CALL_ANALYSIS_DEVICE") or "").strip().lower()
    if forced in ("cpu", "cuda"):
        return forced
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def _model_size() -> str:
    return (os.environ.get("WHISPER_MODEL") or "base").strip() or "base"


@lru_cache(maxsize=2)
def _load_model(model_size: str, device: str) -> Any:
    from faster_whisper import WhisperModel

    compute_type = "float16" if device == "cuda" else "int8"
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def transcribe_audio(
    wav_path: Path,
    *,
    model_size: str | None = None,
    device: str | None = None,
    language: str | None = None,
) -> TranscriptionResult:
    """
    Transcribe mono WAV with faster-whisper.

    Returns timed segments (speaker labels assigned later by diarization).
    """
    wav_path = Path(wav_path)
    if not wav_path.is_file():
        raise FileNotFoundError(f"WAV not found: {wav_path}")

    size = model_size or _model_size()
    dev = device or _pick_device()
    model = _load_model(size, dev)

    segments_iter, info = model.transcribe(
        str(wav_path),
        language=language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=False,
    )

    segments: list[TranscriptSegment] = []
    texts: list[str] = []
    for seg in segments_iter:
        text = (seg.text or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(seg.start or 0.0),
                end=float(seg.end or 0.0),
                text=text,
                speaker="SPEAKER_00",
            )
        )
        texts.append(text)

    full = " ".join(texts).strip()
    lang = getattr(info, "language", None)
    duration = getattr(info, "duration", None)
    return TranscriptionResult(
        text=full,
        language=lang,
        segments=segments,
        duration=float(duration) if duration is not None else None,
        device=dev,
        model_size=size,
    )
