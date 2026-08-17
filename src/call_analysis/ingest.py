"""Ingest sources for call recordings.

Supported sources:
- Local folders (recursive scan for audio files)
- HuggingFace dataset repos (audio files stored in the repo tree)
- Kaggle datasets (zip archive downloaded via the Kaggle API)

All network access goes through ``httpx`` (already a project dependency), so
no extra packages are required. Public HuggingFace datasets need no
credentials; Kaggle needs ``KAGGLE_USERNAME``/``KAGGLE_KEY`` (or
``~/.kaggle/kaggle.json``).
"""

from __future__ import annotations

import json
import os
import re
import zipfile
from pathlib import Path

import httpx

HF_API_BASE = "https://huggingface.co/api"
HF_DATASETS_BASE = "https://huggingface.co/datasets"
KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"

# Keep in sync with STORAGE_ALLOWED_EXTENSIONS defaults in config.py.
AUDIO_EXTS = (".m4a", ".wav", ".mp3", ".ogg", ".flac", ".webm", ".aac", ".opus")

DOWNLOAD_TIMEOUT = 120.0

DATASET_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?$")


def is_audio_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTS


def validate_dataset_id(dataset: str) -> str:
    """Strip and validate a hub dataset id (org/repo or repo)."""
    dataset = (dataset or "").strip().strip("/")
    if not dataset or not DATASET_ID_RE.fullmatch(dataset):
        raise ValueError(
            "Invalid dataset id. Expected 'owner/dataset' or 'dataset' "
            "(letters, digits, '-', '_', '.')"
        )
    return dataset


# ---------------------------------------------------------------------------
# Local folders
# ---------------------------------------------------------------------------


def iter_folder_audio(root: Path, *, recursive: bool = True) -> list[Path]:
    """Return audio files under ``root``, sorted by path."""
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError(f"Folder not found: {root}")
    pattern = "**/*" if recursive else "*"
    files = [p for p in root.glob(pattern) if p.is_file() and is_audio_path(p)]
    files.sort(key=lambda p: str(p).lower())
    return files


# ---------------------------------------------------------------------------
# HuggingFace datasets
# ---------------------------------------------------------------------------


def list_huggingface_audio(
    dataset: str,
    *,
    revision: str = "main",
    client: httpx.Client | None = None,
) -> list[str]:
    """List remote audio file paths in a HuggingFace dataset repo.

    Uses the public repo-tree API, so datasets whose audio lives as files in
    the repo (e.g. ``data/*.wav``) work without credentials. Datasets that
    only reference audio by URL inside parquet rows are not supported.
    """
    close = client is None
    client = client or httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
    try:
        url = f"{HF_API_BASE}/datasets/{dataset}/tree/{revision}"
        resp = client.get(url, params={"recursive": "true"})
        resp.raise_for_status()
        entries = resp.json()
        files = [
            str(e["path"])
            for e in entries
            if isinstance(e, dict) and e.get("type") == "file" and is_audio_path(e.get("path", ""))
        ]
        files.sort(key=lambda p: p.lower())
        return files
    finally:
        if close:
            client.close()


def fetch_huggingface_audio(
    dataset: str,
    *,
    dest_dir: Path,
    limit: int = 10,
    revision: str = "main",
    client: httpx.Client | None = None,
) -> list[Path]:
    """Download up to ``limit`` audio files from a HuggingFace dataset."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    close = client is None
    client = client or httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
    try:
        remote_files = list_huggingface_audio(dataset, revision=revision, client=client)[:limit]
        downloaded: list[Path] = []
        for idx, remote in enumerate(remote_files, start=1):
            url = f"{HF_DATASETS_BASE}/{dataset}/resolve/{revision}/{remote}"
            resp = client.get(url)
            resp.raise_for_status()
            dest = dest_dir / f"{idx:03d}_{Path(remote).name}"
            dest.write_bytes(resp.content)
            downloaded.append(dest)
        return downloaded
    finally:
        if close:
            client.close()


# ---------------------------------------------------------------------------
# Kaggle datasets
# ---------------------------------------------------------------------------


def kaggle_credentials() -> tuple[str, str]:
    """Resolve Kaggle API credentials from env or ~/.kaggle/kaggle.json."""
    username = os.environ.get("KAGGLE_USERNAME", "")
    key = os.environ.get("KAGGLE_KEY", "")
    if not username or not key:
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if kaggle_json.is_file():
            try:
                data = json.loads(kaggle_json.read_text(encoding="utf-8"))
                username = str(data.get("username") or username)
                key = str(data.get("key") or key)
            except (json.JSONDecodeError, OSError):
                pass
    if not username or not key:
        raise RuntimeError(
            "Kaggle credentials not found. Set KAGGLE_USERNAME and KAGGLE_KEY "
            '(or create ~/.kaggle/kaggle.json with {"username": ..., "key": ...})'
        )
    return username, key


def _extract_safely(archive: Path, dest_dir: Path) -> None:
    """Extract a zip without path traversal (zip-slip)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    root = dest_dir.resolve()
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(root)):
                continue
            zf.extract(member, dest_dir)


def fetch_kaggle_audio(
    dataset: str,
    *,
    dest_dir: Path,
    limit: int = 10,
    client: httpx.Client | None = None,
) -> list[Path]:
    """Download a Kaggle dataset archive and return up to ``limit`` audio files."""
    username, key = kaggle_credentials()
    dest_dir.mkdir(parents=True, exist_ok=True)
    close = client is None
    client = client or httpx.Client(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True)
    try:
        url = f"{KAGGLE_API_BASE}/datasets/download/{dataset}"
        resp = client.get(url, auth=(username, key))
        resp.raise_for_status()
        slug = dataset.rsplit("/", maxsplit=1)[-1]
        archive = dest_dir / f"{slug}.zip"
        archive.write_bytes(resp.content)

        extract_dir = dest_dir / "extracted"
        _extract_safely(archive, extract_dir)
        files = [p for p in extract_dir.rglob("*") if p.is_file() and is_audio_path(p)]
        files.sort(key=lambda p: str(p).lower())
        return files[:limit]
    finally:
        if close:
            client.close()
