"""Launch the contact-center dashboard (Windows-friendly, production-ready)."""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from threading import Timer

import uvicorn

# Import the app object directly — PyInstaller's static analyser can trace this.
# Passing the string "call_analysis.api.app:app" to uvicorn.run() triggers a
# dynamic import that PyInstaller misses, causing ModuleNotFoundError in the
# frozen exe.
from call_analysis.api.app import app as _fastapi_app
from call_analysis.config import get_settings
from call_analysis.logging_config import setup_logging

# Setup logging early
setup_logging()

_IS_FROZEN = getattr(sys, "frozen", False)


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()

    parser = argparse.ArgumentParser(description="Call Analysis dashboard server")
    parser.add_argument("--host", default=settings.server.host)
    parser.add_argument("--port", type=int, default=settings.server.port)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--reload", action="store_true", default=settings.server.reload)
    parser.add_argument("--workers", type=int, default=settings.server.workers)
    args = parser.parse_args(argv)

    url = f"http://{args.host}:{args.port}/"
    print(f"Starting Call Analysis at {url}")
    print(f"Environment: {settings.environment}")
    print("NVIDIA-themed dashboard · upload or import .m4a recordings")

    if not args.no_browser and os.environ.get("CALL_ANALYSIS_NO_BROWSER") != "1":
        Timer(1.2, lambda: webbrowser.open(url)).start()

    # Reload is impossible inside a frozen PyInstaller exe.
    reload = args.reload and not _IS_FROZEN

    # Use gunicorn in production with multiple workers (not available when frozen).
    if settings.is_production and args.workers > 1 and not _IS_FROZEN:
        import subprocess

        cmd = [
            sys.executable,
            "-m",
            "gunicorn",
            "call_analysis.api.app:app",
            "-w",
            str(args.workers),
            "-k",
            "uvicorn.workers.UvicornWorker",
            "--bind",
            f"{args.host}:{args.port}",
            "--timeout",
            str(settings.server.timeout_keep_alive),
            "--graceful-timeout",
            str(settings.server.timeout_graceful_shutdown),
            "--access-logfile",
            "-",
            "--error-logfile",
            "-",
        ]
        return subprocess.run(cmd, check=False).returncode

    # Pass the app *object* — not a string — so uvicorn never needs a dynamic
    # import. This is the key fix for the PyInstaller frozen build.
    uvicorn.run(
        _fastapi_app,
        host=args.host,
        port=args.port,
        reload=reload,
        log_level="info" if not settings.debug else "debug",
        access_log=settings.server.access_log,
        workers=1,  # must be 1 when passing an app object
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

