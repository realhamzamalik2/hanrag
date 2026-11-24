# Start the database and the HanRAG API on http://localhost:8000 (docs at /docs).
# Usage:  powershell -NoExit -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\run_api.ps1
# Output is also saved to _bootstrap\api_log.txt

$Root = Split-Path -Parent $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONFAULTHANDLER = "1"
& "$Root\scripts\start_db.ps1"
Set-Location "$Root\backend"
Write-Host "`nAPI docs: http://localhost:8000/docs  (models load in the background, ~30 s)" -ForegroundColor Cyan
$log = "$Root\_bootstrap\api_log.txt"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath $log
Write-Host "`nThe API stopped (exit code $LASTEXITCODE). Log: $log" -ForegroundColor Yellow
