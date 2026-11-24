# Step 2 demo: compare retrieval modes, ask questions, test a follow-up via the API.
# Usage:  powershell -NoExit -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\run_demo.ps1

$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$Root\_bootstrap" | Out-Null
$LogFile = "$Root\_bootstrap\demo_log_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
Start-Transcript -Path $LogFile -Force | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

& "$Root\scripts\start_db.ps1"
Set-Location "$Root\backend"
uv sync -q
uv run pytest -q
uv run python -m scripts.healthcheck
uv run python -m scripts.ingest_cli ../data/samples

Write-Host "`n==== Kiwi vs whitespace BM25 (no LLM) ====" -ForegroundColor Cyan
uv run python -m scripts.ask_cli "훈민정음은 언제 반포되었나요?" --mode bm25 --tokenizer whitespace --no-llm
uv run python -m scripts.ask_cli "훈민정음은 언제 반포되었나요?" --mode bm25 --tokenizer kiwi --no-llm

Write-Host "`n==== Hybrid + reranker, cross-lingual, refusal ====" -ForegroundColor Cyan
uv run python -m scripts.ask_cli "Who created Hangul and when was it published?" --debug
uv run python -m scripts.ask_cli "경복궁은 언제 지어졌나요?"
uv run python -m scripts.ask_cli "What is the population of Busan?"

Write-Host "`n==== API smoke test (multi-turn) ====" -ForegroundColor Cyan
$api = Start-Process uv -ArgumentList "run uvicorn app.main:app --port 8000" -PassThru -WindowStyle Hidden
for ($i = 0; $i -lt 90; $i++) {
    Start-Sleep -Seconds 2
    try { $h = Invoke-RestMethod http://127.0.0.1:8000/api/health; if ($h.models_ready) { break } } catch {}
}
Write-Host ("health: " + ($h | ConvertTo-Json -Compress))
$body = @{ question = "그럼 그건 언제 반포됐어?"; history = @(
    @{ role = "user"; content = "훈민정음은 누가 만들었어?" },
    @{ role = "assistant"; content = "세종대왕이 만들었습니다 [1]." }) } | ConvertTo-Json -Depth 5
$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
$r = Invoke-RestMethod http://127.0.0.1:8000/api/chat -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes
Write-Host "standalone: $($r.standalone_query)"
Write-Host "answer:     $($r.answer)"
Write-Host "stages_ms:  $($r.stages_ms | ConvertTo-Json -Compress)"
Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" | Where-Object { $_.CommandLine -match "uvicorn" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Log saved to $LogFile"
Stop-Transcript | Out-Null
