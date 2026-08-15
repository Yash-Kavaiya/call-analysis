"""CLI: register and process a local recording through the full pipeline."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows consoles default to cp1252; filenames may contain emoji (e.g. ⛔),
# so force UTF-8 output with lossless escaping to avoid UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
except (AttributeError, ValueError):
    pass

from call_analysis.pipeline.runner import process_call
from call_analysis.storage import CallStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Process a call recording (ASR → diarize → PII → agents)."
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to audio file (.m4a/.wav/…). Omit to use newest project sample.",
    )
    parser.add_argument("--skip-agents", action="store_true", help="ASR+PII only")
    parser.add_argument("--no-copy", action="store_true", help="Reference file in place")
    args = parser.parse_args(argv)

    store = CallStore()
    if args.path:
        src = Path(args.path)
        if not src.is_file():
            print(f"ERROR: file not found: {src}", file=sys.stderr)
            return 2
    else:
        files = store.iter_project_recordings(limit=1)
        if not files:
            print("ERROR: no recordings in project folder", file=sys.stderr)
            return 2
        src = files[0]

    rec = store.register_upload(src, copy=not args.no_copy)
    print(f"Registered {rec.filename} as {rec.id}")

    def on_progress(msg: str, pct: float) -> None:
        print(f"[{pct:5.1%}] {msg}", flush=True)

    try:
        result = process_call(
            rec.id,
            store=store,
            skip_agents=args.skip_agents,
            on_progress=on_progress,
        )
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1

    print(f"STATUS={result.status}")
    print(f"duration={result.duration_sec} language={result.language}")
    print(f"segments={len(result.segments)} pii={len(result.pii_findings)}")
    for name, agent in result.agents.items():
        print(f"  {name}: score={agent.score} | {agent.summary[:100]}")
    print("Open dashboard: python -m call_analysis.serve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
