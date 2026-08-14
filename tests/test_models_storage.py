"""Model serialization and storage tests."""

from pathlib import Path

from call_analysis.models import AgentResult, CallRecord, TranscriptSegment
from call_analysis.storage import CallStore


def test_call_record_roundtrip():
    rec = CallRecord(
        id="abc123",
        filename="test.m4a",
        source_path="/tmp/x.m4a",
        segments=[TranscriptSegment(0, 1, "hi", "SPEAKER_00")],
        agents={"qa_scorecard": AgentResult(name="qa_scorecard", summary="ok", score=88)},
    )
    data = rec.to_dict()
    back = CallRecord.from_dict(data)
    assert back.id == "abc123"
    assert back.segments[0].text == "hi"
    assert back.agents["qa_scorecard"].score == 88


def test_store_save_get(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    # create dummy file
    audio = tmp_path / "sample.wav"
    audio.write_bytes(b"RIFF....")  # not real wav — register only
    rec = store.register_upload(audio, copy=True, filename="sample.wav")
    got = store.get(rec.id)
    assert got is not None
    assert got.filename == "sample.wav"
    listed = store.list_calls()
    assert any(c.id == rec.id for c in listed)
    assert store.delete(rec.id)
    assert store.get(rec.id) is None
