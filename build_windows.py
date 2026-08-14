#!/usr/bin/env python
"""Build Windows installer for Call Analysis."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path | None = None) -> int:
    """Run command and return exit code."""
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    return result.returncode


def main() -> int:
    project_root = Path(__file__).parent
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    # Clean previous builds
    for d in (dist_dir, build_dir):
        if d.exists():
            shutil.rmtree(d)

    # Install build dependencies
    print("Installing build dependencies...")
    if run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel", "pyinstaller"]) != 0:
        return 1

    # Install project in development mode
    print("Installing project...")
    if run_cmd([sys.executable, "-m", "pip", "install", "-e", "."]) != 0:
        return 1

    # PyInstaller spec
    spec_content = f'''
# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/call_analysis/serve.py'],
    pathex=['{project_root.as_posix()}'],
    binaries=[],
    datas=[
        ('src/call_analysis/web', 'call_analysis/web'),
        ('src/call_analysis/alembic', 'call_analysis/alembic'),
    ],
    hiddenimports=[
        'sqlalchemy.dialects.postgresql',
        'celery.loaders.default',
        'opentelemetry.instrumentation.fastapi',
        'opentelemetry.instrumentation.sqlalchemy',
        'opentelemetry.instrumentation.redis',
        'opentelemetry.instrumentation.httpx',
        'prometheus_client',
        'structlog',
        'passlib.handlers.bcrypt',
        'jose.backends.rsa_backend',
        'faster_whisper',
        'numpy',
        'librosa',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['pytest', 'mkdocs', 'sphinx', 'black', 'ruff', 'mypy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='CallAnalysis',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if Path('assets/icon.ico').exists() else None,
)
'''

    spec_file = project_root / "CallAnalysis.spec"
    spec_file.write_text(spec_content)

    # Run PyInstaller
    print("Building executable with PyInstaller...")
    if run_cmd(["pyinstaller", "--clean", str(spec_file)]) != 0:
        return 1

    # Create installer using NSIS if available
    nsis_script = project_root / "installer.nsi"
    if nsis_script.exists():
        print("Creating NSIS installer...")
        if run_cmd(["makensis", str(nsis_script)]) != 0:
            print("NSIS installer creation failed (makensis not found or script error)")
    else:
        print("NSIS script not found, skipping installer creation")

    print(f"\nBuild complete! Executable at: {dist_dir / 'CallAnalysis.exe'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())