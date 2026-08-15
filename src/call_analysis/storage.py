"""Local JSON storage for call records (gitignored data/)."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from call_analysis.models import CallRecord, JobStatus, utc_now_iso

if TYPE_CHECKING:
    from collections.abc import Iterable


def default_data_dir() -> Path:
    # Overridable so the Electron shell can keep data under the OS user-data
    # folder (CALL_ANALYSIS_DATA_DIR or STORAGE_DATA_DIR take precedence).
    for key in ("CALL_ANALYSIS_DATA_DIR", "STORAGE_DATA_DIR"):
        value = os.environ.get(key)
        if value:
            path = Path(value)
            path.mkdir(parents=True, exist_ok=True)
            (path / "uploads").mkdir(exist_ok=True)
            (path / "calls").mkdir(exist_ok=True)
            (path / "audio").mkdir(exist_ok=True)
            return path
    # Project root: src/call_analysis/storage.py → parents[2]
    root = Path(__file__).resolve().parents[2]
    path = root / "data"
    path.mkdir(parents=True, exist_ok=True)
    (path / "uploads").mkdir(exist_ok=True)
    (path / "calls").mkdir(exist_ok=True)
    (path / "audio").mkdir(exist_ok=True)
    return path


class CallStore:
    """Filesystem-backed store for analyzed calls."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.uploads_dir = self.data_dir / "uploads"
        self.calls_dir = self.data_dir / "calls"
        self.audio_dir = self.data_dir / "audio"
        for d in (self.uploads_dir, self.calls_dir, self.audio_dir):
            d.mkdir(parents=True, exist_ok=True)

    def _call_path(self, call_id: str) -> Path:
        return self.calls_dir / f"{call_id}.json"

    def new_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def save(self, record: CallRecord) -> CallRecord:
        record.touch()
        path = self._call_path(record.id)
        path.write_text(
            json.dumps(record.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return record

    def get(self, call_id: str) -> CallRecord | None:
        path = self._call_path(call_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return CallRecord.from_dict(data)

    def list_calls(self) -> list[CallRecord]:
        records: list[CallRecord] = []
        for path in sorted(
            self.calls_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(CallRecord.from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return records

    def delete(self, call_id: str) -> bool:
        path = self._call_path(call_id)
        audio = self.audio_dir / call_id
        ok = False
        if path.is_file():
            path.unlink()
            ok = True
        if audio.exists():
            shutil.rmtree(audio, ignore_errors=True)
        return ok

    def register_upload(
        self,
        source: Path,
        *,
        copy: bool = True,
        filename: str | None = None,
    ) -> CallRecord:
        """Register a local recording (copy into data/uploads unless copy=False)."""
        source = Path(source)
        if not source.is_file():
            raise FileNotFoundError(f"Audio file not found: {source}")
        call_id = self.new_id()
        name = filename or source.name
        if copy:
            dest = self.uploads_dir / f"{call_id}_{_safe_name(name)}"
            shutil.copy2(source, dest)
            stored = dest
        else:
            stored = source.resolve()
        record = CallRecord(
            id=call_id,
            filename=name,
            source_path=str(stored),
            status=JobStatus.PENDING.value,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        return self.save(record)

    def audio_work_dir(self, call_id: str) -> Path:
        d = self.audio_dir / call_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def iter_project_recordings(
        self,
        root: Path | None = None,
        *,
        limit: int | None = None,
        extensions: Iterable[str] = (".m4a", ".wav", ".mp3", ".ogg", ".flac"),
    ) -> list[Path]:
        root = root or Path(__file__).resolve().parents[2]
        exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in extensions}
        files = [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in exts]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if limit is not None:
            files = files[:limit]
        return files


def _safe_name(name: str) -> str:
    keep = []
    for ch in name:
        if ch.isalnum() or ch in "._- +()":
            keep.append(ch)
        else:
            keep.append("_")
    out = "".join(keep).strip("._ ") or "audio"
    return out[:180]
