"""Launch the contact-center dashboard (Windows-friendly, production-ready)."""

from __future__ import annotations

import argparse
import webbrowser
from threading import Timer

import uvicorn

from call_analysis.config import get_settings
from call_analysis.logging_config import setup_logging

# Setup logging early
setup_logging()


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

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(url)).start()

    # Use gunicorn in production, uvicorn directly in development
    if settings.is_production and args.workers > 1:
        import subprocess
        import sys
        cmd = [
            sys.executable, "-m", "gunicorn",
            "call_analysis.api.app:app",
            "-w", str(args.workers),
            "-k", "uvicorn.workers.UvicornWorker",
            "--bind", f"{args.host}:{args.port}",
            "--timeout", str(settings.server.timeout_keep_alive),
            "--graceful-timeout", str(settings.server.timeout_graceful_shutdown),
            "--access-logfile", "-",
            "--error-logfile", "-",
        ]
        return subprocess.run(cmd).returncode
    else:
        uvicorn.run(
            "call_analysis.api.app:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level="info" if not settings.debug else "debug",
            access_log=settings.server.access_log,
            workers=1 if args.reload else args.workers,
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())