"""CallRepository unit tests (file backend)."""

from pathlib import Path

from call_analysis.models import CallRecord, JobStatus
from call_analysis.repository import FileCallRepository
from call_analysis.storage import CallStore


def test_file_repository_register_and_list(tmp_path: Path) -> None:
    store = CallStore(data_dir=tmp_path)
    repo = FileCallRepository(store)
    audio = tmp_path / "tone.wav"
    audio.write_bytes(b"RIFF....")
    rec = repo.register_upload(audio, copy=True, filename="tone.wav")
    assert len(rec.id) >= 32
    got = repo.get(rec.id)
    assert got is not None
    records, total = repo.list_calls(limit=10)
    assert total == 1
    assert records[0].filename == "tone.wav"


def test_file_repository_filter_status(tmp_path: Path) -> None:
    store = CallStore(data_dir=tmp_path)
    repo = FileCallRepository(store)
    rec = CallRecord(
        id=store.new_id(),
        filename="a.wav",
        source_path=str(tmp_path / "a.wav"),
        status=JobStatus.COMPLETED.value,
    )
    repo.save(rec)
    pending = CallRecord(
        id=store.new_id(),
        filename="b.wav",
        source_path=str(tmp_path / "b.wav"),
        status=JobStatus.PENDING.value,
    )
    repo.save(pending)
    completed, _ = repo.list_calls(status=JobStatus.COMPLETED.value)
    assert len(completed) == 1
    assert completed[0].filename == "a.wav"
