# Launch Call Analysis dashboard (Windows PowerShell) - Production Version
Set-Location $PSScriptRoot
$env:PYTHONPATH = "src;$env:PYTHONPATH"

# Load .env file
if (Test-Path .env) {
  Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
    $k, $v = $_.Split('=', 2)
    [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process')
  }
}

# Check for NVIDIA API key
if (-not $env:NVIDIA_API_KEY) {
  Write-Warning "NVIDIA_API_KEY not set. Please configure in .env file or environment."
  Write-Host "Get a free key at: https://build.nvidia.com" -ForegroundColor Cyan
}

Write-Host "Starting Call Analysis at http://127.0.0.1:8787/" -ForegroundColor Green
Write-Host "Environment: $env:ENVIRONMENT" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Gray

python -m call_analysis.serve --port 8787