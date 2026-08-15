"""Pipeline: ingest → WAV → ASR → diarize → PII → multi-agent analysis."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from call_analysis.agents.orchestrator import run_all_agents
from call_analysis.audio.asr import transcribe_audio
from call_analysis.audio.diarize import diarize_segments, format_diarized_transcript
from call_analysis.audio.preprocess import extract_waveform_peaks, prepare_wav
from call_analysis.config import NvidiaConfig, load_nvidia_config
from call_analysis.models import CallRecord, JobStatus
from call_analysis.pii.scrubber import scrub_pii
from call_analysis.storage import CallStore

ProgressCb = Callable[[str, float], None]


def process_call(
    call_id: str,
    *,
    store: CallStore | None = None,
    config: NvidiaConfig | None = None,
    skip_agents: bool = False,
    on_progress: ProgressCb | None = None,
    language: str | None = None,
) -> CallRecord:
    """
    Run full analysis for a registered call id.

    Stages: prepare audio → waveform → ASR → diarization → PII → agents.
    """
    store = store or CallStore()
    record = store.get(call_id)
    if record is None:
        raise KeyError(f"Unknown call id: {call_id}")

    def progress(msg: str, pct: float) -> None:
        record.progress_message = msg
        record.progress_pct = float(pct)
        store.save(record)
        if on_progress:
            on_progress(msg, pct)

    record.status = JobStatus.PROCESSING.value
    record.error = None
    record.progress_pct = 0.0
    record.progress_message = "Starting"
    store.save(record)

    try:
        source = Path(record.source_path)
        if not source.is_file():
            raise FileNotFoundError(  # noqa: TRY301 — validation flows to except handler
                f"Source audio missing: {source}"
            ) from None

        work = store.audio_work_dir(call_id)
        wav_path = work / "audio.wav"

        progress("Converting audio", 0.05)
        prepare_wav(source, wav_path)

        progress("Extracting waveform", 0.15)
        peaks, duration = extract_waveform_peaks(wav_path)
        record.waveform_peaks = peaks
        record.duration_sec = duration
        store.save(record)

        progress("Transcribing speech", 0.25)
        asr_lang = language or (record.metadata or {}).get("asr_language")
        asr = transcribe_audio(wav_path, language=asr_lang)
        record.language = asr.language
        record.full_transcript = asr.text
        if asr.duration:
            record.duration_sec = asr.duration
        record.metadata = {
            **record.metadata,
            "asr_device": asr.device,
            "asr_model": asr.model_size,
        }
        store.save(record)

        progress("Diarizing speakers", 0.55)
        diarized = diarize_segments(asr.segments)
        record.segments = diarized
        if diarized:
            record.full_transcript = format_diarized_transcript(diarized)
        store.save(record)

        progress("Scrubbing PII", 0.65)
        plain = " ".join(s.text for s in diarized) if diarized else asr.text
        scrub = scrub_pii(plain, diarized)
        record.scrubbed_transcript = (
            format_diarized_transcript(scrub.scrubbed_segments)
            if scrub.scrubbed_segments
            else scrub.scrubbed_text
        )
        record.pii_findings = scrub.findings
        record.segments = scrub.scrubbed_segments or diarized
        store.save(record)

        if not skip_agents:
            progress("Running AI agents", 0.72)
            cfg = config or load_nvidia_config(require_key=True)
            agents = run_all_agents(
                cfg,
                transcript=record.scrubbed_transcript or plain,
                segments=record.segments,
                filename=record.filename,
            )
            record.agents = agents
            store.save(record)

        progress("Complete", 1.0)
        record.status = JobStatus.COMPLETED.value
        record.error = None
        return store.save(record)

    except Exception as exc:
        record.status = JobStatus.FAILED.value
        record.error = str(exc)
        record.progress_message = f"Failed: {exc}"
        store.save(record)
        raise
