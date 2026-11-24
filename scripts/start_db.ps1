# Start PostgreSQL inside WSL and keep the WSL VM alive while you work.
# WSL shuts Ubuntu down when no Linux process is running, which would stop Postgres too.
# Usage:  powershell -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\start_db.ps1

$Distro = "Ubuntu-24.04"
$Root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$Root\_bootstrap" | Out-Null
Start-Transcript -Path "$Root\_bootstrap\start_db_log.txt" -Force | Out-Null
# Postgres usually starts on its own (systemd). Full path: "wsl -e" has no /usr/sbin in PATH.
wsl -d $Distro -u root -e /usr/sbin/service postgresql start | Out-Host
# Ensure the separate test database exists (tests truncate tables, never touch "hanrag").
$wslRoot = "/mnt/" + $Root.Substring(0, 1).ToLower() + $Root.Substring(2).Replace("\", "/")
wsl -d $Distro -u postgres -e bash "$wslRoot/scripts/ensure_test_db.sh" | Out-Host

# One hidden "sleep infinity" process keeps the distro (and Postgres) running.
# Note: pass ONE argument string; Start-Process does not quote array items.
$alive = Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" |
    Where-Object { $_.CommandLine -match "sleep infinity" }
if (-not $alive) {
    Start-Process wsl -ArgumentList "-d $Distro -e sleep infinity" -WindowStyle Hidden
    Write-Host "Started hidden WSL keep-alive process."
} else {
    Write-Host "WSL keep-alive already running."
}
Start-Sleep -Seconds 2
wsl -d $Distro -e pg_isready -h localhost -p 5432 | Out-Host
Stop-Transcript | Out-Null
