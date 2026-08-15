"""End-to-end: upload real audio via the API and assert pipeline completion.

Runs the actual pipeline (ffmpeg → whisper-tiny → diarization → PII scrub)
against a short synthetic tone. Skipped when whisper/ffmpeg are unavailable
(e.g. offline CI) so the suite stays green without the model cache.
"""

from __future__ import annotations

import shutil
import wave
from typing import TYPE_CHECKING

import numpy as np
import pytest
from fastapi.testclient import TestClient

from call_analysis.api.app import create_app
from call_analysis.pipeline.runner import process_call
from call_analysis.storage import CallStore

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

E2E_SKIP_REASON = "ffmpeg or faster-whisper not installed — skipping live pipeline E2E"


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    else:
        return True


def _make_tone_wav(path: Path, sample_rate: int = 16000) -> Path:
    """Write bursty, syllable-like audio (mono, 16-bit) that passes VAD.

    A steady sine is filtered out by whisper's VAD (no speech → empty
    transcript). Short pitch-gliding bursts with silence gaps mimic speech
    rhythm, so whisper keeps them and produces a transcript.
    """
    segments: list[np.ndarray] = []
    for i in range(6):
        t = np.linspace(0.0, 0.15, int(sample_rate * 0.15), endpoint=False)
        freq = 180.0 + i * 40.0
        burst = 0.3 * np.sin(2 * np.pi * freq * t + np.pi * i)
        envelope = np.minimum(t / 0.02, 1.0) * np.minimum((0.15 - t) / 0.02, 1.0)
        segments.append(burst * envelope)
        segments.append(np.zeros(int(sample_rate * 0.08)))
    audio = np.concatenate(segments)
    pcm = (audio * 32767.0).astype(np.int16)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path


@pytest.mark.skipif(
    not (_ffmpeg_available() and _whisper_available()),
    reason=E2E_SKIP_REASON,
)
def test_upload_then_pipeline_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Upload a WAV through the API, run the pipeline, assert completion."""
    monkeypatch.setenv("WHISPER_MODEL", "tiny")  # small + cached → fast, offline
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-e2e-test-key")

    wav = _make_tone_wav(tmp_path / "tone.wav")
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)

    # 1. Upload through the real endpoint
    with wav.open("rb") as fh:
        r = client.post(
            "/api/calls/upload?analyze=false",
            files={"file": ("tone.wav", fh, "audio/wav")},
        )
    assert r.status_code == 200, r.text
    call_id = r.json()["id"]
    assert store.get(call_id) is not None

    # 2. Run the full pipeline synchronously (the pytest env disables the
    #    background executor, so we drive it directly)
    result = process_call(call_id, store=store, skip_agents=True)
    assert result.status == "completed", f"pipeline failed: {result.error}"

    # 3. The API reflects completion
    got = client.get(f"/api/calls/{call_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["status"] == "completed"
    assert body["duration_sec"] is not None
    assert body["duration_sec"] > 0.0
    assert body["full_transcript"]
    assert body["language"]
    # Waveform peaks were extracted for the dashboard
    assert body["waveform_peaks"], "expected waveform peaks from the pipeline"

    # 4. Analytics aggregates the completed call
    analytics = client.get("/api/analytics").json()
    assert analytics["completed"] >= 1
    assert analytics["total_calls"] >= 1

    # 5. Cleanup works
    assert client.delete(f"/api/calls/{call_id}").status_code == 204
    assert client.get(f"/api/calls/{call_id}").status_code == 404
