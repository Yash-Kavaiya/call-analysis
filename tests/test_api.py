"""API structural tests with TestClient (no live ASR)."""

from pathlib import Path
from typing import Any

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
    # The API must never leak key material (was api_key_hint in earlier builds)
    assert "api_key_hint" not in body
    assert "api_key" not in str(body).lower()

    r2 = client.get("/api/calls")
    assert r2.status_code == 200
    assert r2.json()["calls"] == []


def test_health_does_not_leak_api_key_hint(tmp_path: Path, monkeypatch):
    """Even with a real key configured, /api/health must not expose it."""
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-super-secret-test-key-1234567890")
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["nvidia_key_configured"] is True
    assert "api_key_hint" not in body
    assert "super-secret" not in str(body)


def test_recovery_lock_is_released_between_calls(tmp_path: Path):
    """The recovery lock file must be released after each pass so the next
    worker (or the next test run) can acquire it without deadlocking."""
    store = CallStore(data_dir=tmp_path)
    _stuck_record(store, JobStatus.PENDING.value, "pending1")
    enqueued: list[str] = []
    _, count = recover_interrupted_jobs(store, enqueued.append)
    assert count == 1
    # A second pass acquires the lock again fine (it was released), and still
    # re-queues the untouched pending record (recovery semantics).
    _, count2 = recover_interrupted_jobs(store, enqueued.append)
    assert count2 == 1


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


def test_import_folder_registers_audio(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "a.m4a").write_bytes(b"fake-audio")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.wav").write_bytes(b"fake-audio")
    (folder / "notes.txt").write_text("ignore me")

    r = client.post("/api/calls/import-folder", json={"path": str(folder), "analyze": False})
    assert r.status_code == 200
    body = r.json()
    assert {i["filename"] for i in body["imported"]} == {"a.m4a", "b.wav"}
    assert body["skipped"] == []

    # Non-recursive only picks up the top-level file (skip_existing off so
    # the already-imported a.m4a is imported again)
    r2 = client.post(
        "/api/calls/import-folder",
        json={
            "path": str(folder),
            "analyze": False,
            "recursive": False,
            "skip_existing": False,
        },
    )
    assert r2.status_code == 200
    assert {i["filename"] for i in r2.json()["imported"]} == {"a.m4a"}


def test_import_folder_missing_returns_400(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.post(
        "/api/calls/import-folder",
        json={"path": str(tmp_path / "nope"), "analyze": False},
    )
    assert r.status_code == 400
    assert "Folder not found" in r.json()["detail"]


def test_import_folder_no_audio_returns_404(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "notes.txt").write_text("no audio here")
    r = client.post(
        "/api/calls/import-folder",
        json={"path": str(empty), "analyze": False},
    )
    assert r.status_code == 404


def test_import_huggingface_downloads_audio(tmp_path: Path, monkeypatch):
    import httpx

    from call_analysis import ingest as ingest_mod

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/tree/main"):
            return httpx.Response(
                200,
                json=[
                    {"type": "directory", "path": "data"},
                    {"type": "file", "path": "data/sample1.flac", "size": 123},
                    {"type": "file", "path": "data/readme.txt", "size": 10},
                ],
            )
        if "/resolve/main/" in request.url.path:
            return httpx.Response(200, content=b"fake-audio")
        raise AssertionError(f"unexpected URL {request.url}")

    transport = httpx.MockTransport(handler)
    # Inject the mock transport only for ingest-originated clients; TestClient
    # also builds httpx clients and passes its own transport kwarg.
    real_client = ingest_mod.httpx.Client

    def factory(*args: Any, **kw: Any) -> Any:
        if kw.get("transport") is None:
            kw["transport"] = transport
        return real_client(*args, **kw)

    monkeypatch.setattr(ingest_mod.httpx, "Client", factory)

    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.post(
        "/api/calls/import-hf",
        json={"dataset": "org/demo", "analyze": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["imported"]) == 1
    assert body["imported"][0]["filename"] == "sample1.flac"


def test_import_huggingface_invalid_dataset_returns_400(tmp_path: Path):
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.post(
        "/api/calls/import-hf",
        json={"dataset": "../bad path", "analyze": False},
    )
    assert r.status_code == 400
    assert "Invalid dataset id" in r.json()["detail"]


def test_import_kaggle_downloads_audio(tmp_path: Path, monkeypatch):
    import io
    import zipfile

    import httpx

    from call_analysis import ingest as ingest_mod

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/v1/datasets/download/"):
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("call1.mp3", b"fake-audio")
                zf.writestr("notes.txt", "ignore")
            return httpx.Response(200, content=buf.getvalue())
        raise AssertionError(f"unexpected URL {request.url}")

    transport = httpx.MockTransport(handler)
    real_client = ingest_mod.httpx.Client

    def factory(*args: Any, **kw: Any) -> Any:
        if kw.get("transport") is None:
            kw["transport"] = transport
        return real_client(*args, **kw)

    monkeypatch.setattr(ingest_mod.httpx, "Client", factory)
    monkeypatch.setenv("KAGGLE_USERNAME", "user")
    monkeypatch.setenv("KAGGLE_KEY", "secret")

    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.post(
        "/api/calls/import-kaggle",
        json={"dataset": "user/calls", "analyze": False},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["imported"]) == 1
    assert body["imported"][0]["filename"] == "call1.mp3"


def test_import_kaggle_missing_credentials_returns_400(tmp_path: Path, monkeypatch):
    from call_analysis import ingest as ingest_mod

    # Deterministic: simulate missing credentials regardless of a real
    # ~/.kaggle/kaggle.json on the dev machine.
    def _no_creds() -> None:
        raise RuntimeError("Kaggle credentials not found.")

    monkeypatch.setattr(ingest_mod, "kaggle_credentials", _no_creds)
    store = CallStore(data_dir=tmp_path)
    app = create_app(store=store)
    client = TestClient(app)
    r = client.post(
        "/api/calls/import-kaggle",
        json={"dataset": "user/calls", "analyze": False},
    )
    assert r.status_code == 400
    assert "Kaggle credentials" in r.json()["detail"]
