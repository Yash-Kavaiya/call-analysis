"""Convert recordings to WAV and extract waveform peaks for the UI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np


class AudioProcessError(RuntimeError):
    """Raised when ffmpeg or audio decoding fails."""


def _which_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise AudioProcessError(
            "ffmpeg not found on PATH. Install ffmpeg and restart the shell."
        )
    return path


def prepare_wav(
    source: Path,
    dest_wav: Path,
    *,
    sample_rate: int = 16000,
) -> Path:
    """
    Convert any ffmpeg-supported audio to mono 16 kHz WAV for ASR.
    """
    source = Path(source)
    dest_wav = Path(dest_wav)
    dest_wav.parent.mkdir(parents=True, exist_ok=True)
    if not source.is_file():
        raise FileNotFoundError(f"Source audio missing: {source}")

    ffmpeg = _which_ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(source),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-c:a",
        "pcm_s16le",
        str(dest_wav),
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioProcessError(f"ffmpeg timed out converting {source.name}") from exc

    if proc.returncode != 0 or not dest_wav.is_file():
        err = (proc.stderr or proc.stdout or "")[-500:]
        raise AudioProcessError(f"ffmpeg failed for {source.name}: {err}")
    return dest_wav


def load_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    """Load a PCM WAV as float32 mono samples and sample rate."""
    import wave

    path = Path(path)
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise AudioProcessError(f"Unsupported sample width: {sampwidth}")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    return data, framerate


def extract_waveform_peaks(
    wav_path: Path,
    *,
    num_peaks: int = 400,
) -> tuple[list[float], float]:
    """
    Downsample absolute amplitude to ``num_peaks`` buckets for UI waveform.

    Returns (peaks in 0..1, duration_seconds).
    """
    samples, sr = load_wav_mono(wav_path)
    duration = float(len(samples) / sr) if sr else 0.0
    if len(samples) == 0:
        return [0.0] * num_peaks, 0.0

    abs_s = np.abs(samples)
    # Bucket max envelope
    bucket = max(1, len(abs_s) // num_peaks)
    peaks: list[float] = []
    for i in range(num_peaks):
        start = i * bucket
        end = min(len(abs_s), start + bucket)
        if start >= len(abs_s):
            peaks.append(0.0)
        else:
            peaks.append(float(abs_s[start:end].max()))

    peak_max = max(peaks) if peaks else 1.0
    if peak_max > 0:
        peaks = [min(1.0, p / peak_max) for p in peaks]
    return peaks, duration
