# Step 4: polish the index, then run the full evaluation (about 40 minutes on an 8 GB laptop).
# Usage:  powershell -NoExit -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\run_eval.ps1
#         add -RetrievalOnly to skip the Gemini part
param([switch]$RetrievalOnly)

$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$Root\_bootstrap" | Out-Null
$LogFile = "$Root\_bootstrap\eval_log_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
Start-Transcript -Path $LogFile -Force | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"
$env:PYTHONFAULTHANDLER = "1"

# Free memory: the evaluation loads its own copy of the models.
Write-Host "Stopping the HanRAG API and web app (start them again later with run_app.ps1)..." -ForegroundColor Cyan
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match "uvicorn" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" | Where-Object { $_.CommandLine -match "next" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

& "$Root\scripts\start_db.ps1"
Set-Location "$Root\backend"
uv sync -q

Write-Host "`n==== 1/3 Index polish (re-index PDFs with the improved parser) ====" -ForegroundColor Cyan
uv run python -m scripts.rebuild_samples
uv run python -m scripts.reembed

Write-Host "`n==== 2/3 Tests ====" -ForegroundColor Cyan
uv run pytest -q

Write-Host "`n==== 3/3 Evaluation ====" -ForegroundColor Cyan
if ($RetrievalOnly) {
    uv run python -m scripts.run_eval --retrieval
} else {
    uv run python -m scripts.run_eval
}

Write-Host "`nResults: $Root\eval\results\RESULTS.md" -ForegroundColor Green
Write-Host "Start the app again with scripts\run_app.ps1 and open the Evaluation page."
Write-Host "Log saved to $LogFile"
Stop-Transcript | Out-Null
