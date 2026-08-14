"""API structural tests with TestClient (no live ASR)."""

from pathlib import Path

from fastapi.testclient import TestClient

from call_analysis.api.app import create_app, recover_interrupted_jobs
from call_analysis.models import CallRecord, JobStatus, utc_now_iso
from call_analysis.storage import CallStore


def _stuck_record(store: CallStore, status: str, call_id: str) -> CallRecord:
    rec = CallRecord(
        id=call_id,
        filename=f"{call_id}.m4a",
        source_path=str(store.data_dir / f"{call_id}.m4a"),
        status=status,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
    )
    return store.save(rec)


def test_recover_interrupted_jobs_resets_and_requeues(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    _stuck_record(store, JobStatus.PROCESSING.value, "stuck1")
    _stuck_record(store, JobStatus.PENDING.value, "pending1")
    _stuck_record(store, JobStatus.COMPLETED.value, "done1")

    enqueued: list[str] = []
    reset, count = recover_interrupted_jobs(store, enqueued.append)

    assert reset == 1
    assert count == 2  # stuck1 (reset then requeued) + pending1
    assert sorted(enqueued) == ["pending1", "stuck1"]
    assert store.get("stuck1").status == JobStatus.PENDING.value
    assert store.get("pending1").status == JobStatus.PENDING.value
    assert store.get("done1").status == JobStatus.COMPLETED.value


def test_lifespan_recovers_stuck_records_on_startup(tmp_path: Path):
    """Startup wiring: a record left 'processing' by a dead session is resumed."""
    store = CallStore(data_dir=tmp_path)
    _stuck_record(store, JobStatus.PROCESSING.value, "orphan1")
    app = create_app(store=store)

    with TestClient(app) as client:  # triggers lifespan startup
        assert client.get("/api/health").status_code == 200
        got = store.get("orphan1")
        # reset to pending synchronously; the worker may flip it to failed
        # quickly (source audio is missing), so just require it's not stuck.
        assert got.status in (JobStatus.PENDING.value, JobStatus.FAILED.value)


def test_health_and_list(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "nvidia_key_configured" in body

    r2 = client.get("/api/calls")
    assert r2.status_code == 200
    assert r2.json()["calls"] == []


def test_upload_registers_call(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    # analyze=false so we don't start whisper in unit test
    files = {"file": ("hello.m4a", b"fake-audio-bytes", "audio/mp4")}
    r = client.post("/api/calls/upload?analyze=false", files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["id"]
    assert data["filename"] == "hello.m4a"
    got = client.get(f"/api/calls/{data['id']}")
    assert got.status_code == 200
    assert got.json()["status"] == "pending"


def test_analytics_endpoint(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.get("/api/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["total_calls"] == 0
    assert "avg_qa_score" in body
    assert body["languages"] == {}
