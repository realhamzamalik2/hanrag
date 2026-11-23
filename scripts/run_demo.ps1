# Start the database, index the sample documents and ask test questions.
# Usage:  powershell -NoExit -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\run_demo.ps1

$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$Root\_bootstrap" | Out-Null
$LogFile = "$Root\_bootstrap\demo_log_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
Start-Transcript -Path $LogFile -Force | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

& "$Root\scripts\start_db.ps1"

Set-Location "$Root\backend"
uv run pytest -q -m db
uv run python -m scripts.ingest_cli ../data/samples
uv run python -m scripts.ask_cli "한글은 누가 만들었나요?" --no-llm
uv run python -m scripts.ask_cli "Who created Hangul?" --no-llm
uv run python -m scripts.ask_cli "경복궁은 언제 지어졌나요?" --no-llm

$envText = Get-Content "$Root\.env" -Raw
if ($envText -match "GEMINI_API_KEY=\S+" -and $envText -match "GEMINI_MODEL=\S+") {
    uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"
    uv run python -m scripts.ask_cli "Who created Hangul?"
    uv run python -m scripts.ask_cli "What is the population of Busan?"
} else {
    Write-Host "Skipped LLM answers (GEMINI_API_KEY / GEMINI_MODEL not set in .env)." -ForegroundColor Yellow
}
Write-Host "Log saved to $LogFile"
Stop-Transcript | Out-Null
