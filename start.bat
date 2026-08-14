@echo off
REM Launch Call Analysis dashboard (Windows) - Production Version
cd /d "%~dp0"
set PYTHONPATH=src;%PYTHONPATH%

REM Load .env file
if exist ".env" (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

REM Check for NVIDIA API key
if "%NVIDIA_API_KEY%"=="" (
  echo WARNING: NVIDIA_API_KEY not set. Please configure in .env file or environment.
  echo Get a free key at: https://build.nvidia.com
)

echo Starting Call Analysis at http://127.0.0.1:8787/
echo Environment: %ENVIRONMENT%
echo Press Ctrl+C to stop
echo.

python -m call_analysis.serve --port 8787
pause