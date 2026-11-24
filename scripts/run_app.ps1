# Start everything: database, API (new window) and the web app on http://localhost:3000
# Usage:  powershell -NoExit -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\run_app.ps1
#         add -Dev for hot reload while editing the frontend (uses more memory)
param([switch]$Dev)

$Root = Split-Path -Parent $PSScriptRoot
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

& "$Root\scripts\start_db.ps1"

# API in its own window so its logs stay readable
$apiRunning = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -match "uvicorn" }
if (-not $apiRunning) {
    Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "`"$Root\scripts\run_api.ps1`""
    Write-Host "Started the API in a new window (http://localhost:8000/docs)."
} else {
    Write-Host "API already running."
}

Set-Location "$Root\frontend"
if (-not (Test-Path node_modules)) {
    Write-Host "Installing frontend packages (first run only)..." -ForegroundColor Cyan
    npm install --no-fund --no-audit
}
if ($Dev) {
    npm run dev
} else {
    # Production mode: compiled once, much lighter on RAM than the dev server.
    npm run build
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`nOpen http://localhost:3000" -ForegroundColor Green
        npm run start
    }
}
