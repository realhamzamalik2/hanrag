# HanRAG one-shot setup for Windows (PowerShell 5+).
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\setup_windows.ps1
# Output is also saved to _bootstrap\setup_log_<timestamp>.txt

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$Root\_bootstrap" | Out-Null
$LogFile = "$Root\_bootstrap\setup_log_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
Start-Transcript -Path $LogFile -Force | Out-Null
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = "1"

function Step($msg) { Write-Host "`n==== $msg ====" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Ok($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }

Set-Location $Root

Step "1/8 Tools"
foreach ($t in "git", "uv", "wsl") {
    if (Get-Command $t -ErrorAction SilentlyContinue) { Ok "$t found" } else { Fail "$t not found" }
}

Step "Git: link this folder to github.com/realhamzamalik2/hanrag"
if (-not (Test-Path "$Root\.git")) {
    git init -q -b main
    git remote add origin https://github.com/realhamzamalik2/hanrag.git
    git fetch -q origin main
    git reset -q origin/main          # keep local files, adopt the GitHub history
    git checkout -q -- LICENSE
}
# Commits from this repo use the GitHub noreply address, never a personal email.
git config user.name "realhamzamalik2"
git config user.email "125865129+realhamzamalik2@users.noreply.github.com"
git status --short | Select-Object -First 10
Ok "Git linked (commit email: noreply)"

Step "2/8 .env"
if (-not (Test-Path "$Root\.env")) {
    Copy-Item "$Root\.env.example" "$Root\.env"
    Ok "Created .env from .env.example (add GEMINI_API_KEY and GEMINI_MODEL yourself)"
} else { Ok ".env already exists (left unchanged)" }

Step "3/8 Python environment (uv sync)"
Set-Location "$Root\backend"
uv sync
if ($LASTEXITCODE -ne 0) { Fail "uv sync failed"; Stop-Transcript; exit 1 }
Ok "Dependencies installed in backend\.venv"

Step "4/8 Unit tests"
uv run pytest -q -m "not db"

Step "5/8 PostgreSQL + pgvector in WSL"
$wslConfig = "$env:USERPROFILE\.wslconfig"
if (-not (Test-Path $wslConfig)) {
    Set-Content $wslConfig "[wsl2]`nmemory=1536MB`nswap=2GB"
    Ok "Capped WSL memory at 1.5 GB ($wslConfig)"
    wsl --shutdown
}
$distro = (wsl -e bash -lc "grep PRETTY_NAME /etc/os-release" 2>$null)
if ($LASTEXITCODE -ne 0 -or "$distro" -notmatch "PRETTY_NAME") {
    $distro = $null
    Fail "No WSL Linux distro found. Install Ubuntu on D: with:  wsl --install -d Ubuntu-24.04 --location D:\wsl\ubuntu  then rerun this script."
    Write-Host "Skipping database steps." -ForegroundColor Yellow
    Stop-Transcript | Out-Null
    exit 1
} else {
    Ok "WSL distro: $distro"
    Write-Host "WSL will ask for your Linux (sudo) password once." -ForegroundColor Yellow
    wsl -e bash /mnt/d/projects/hanrag/scripts/setup_postgres_wsl.sh
}

Step "6/8 Start database and keep WSL awake"
& "$Root\scripts\start_db.ps1"

Step "7/8 Health check (first run downloads bge-m3, about 2.3 GB, to D:\dev-cache\fastembed)"
Set-Location "$Root\backend"
uv run python -m scripts.healthcheck
uv run pytest -q -m db

Step "8/8 Sample documents, ingestion and a test question"
uv run python -m scripts.fetch_samples
uv run python -m scripts.ingest_cli ../data/samples
uv run python -m scripts.ask_cli "한글은 누가 만들었나요?" --no-llm
uv run python -m scripts.ask_cli "Who created Hangul?" --no-llm

$envText = Get-Content "$Root\.env" -Raw
if ($envText -match "GEMINI_API_KEY=\S+" -and $envText -match "GEMINI_MODEL=\S+") {
    uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"
    uv run python -m scripts.ask_cli "What is the population of Busan?"
} else {
    Write-Host "Skipped LLM answers: add GEMINI_API_KEY and GEMINI_MODEL to .env, then run:" -ForegroundColor Yellow
    Write-Host '  cd D:\projects\hanrag\backend; uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"'
}

Step "Done"
Write-Host "Log saved to $LogFile"
Stop-Transcript | Out-Null
