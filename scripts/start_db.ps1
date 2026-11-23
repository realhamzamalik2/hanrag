# Start PostgreSQL inside WSL and keep the WSL VM alive while you work.
# WSL shuts down when no Linux process is running, which would stop Postgres too.
# Usage:  powershell -ExecutionPolicy Bypass -File D:\projects\hanrag\scripts\start_db.ps1

wsl -u root -e service postgresql start | Out-Host

$alive = Get-CimInstance Win32_Process -Filter "Name = 'wsl.exe'" |
    Where-Object { $_.CommandLine -match "hanrag-keepalive" }
if (-not $alive) {
    Start-Process wsl -ArgumentList "-e", "bash", "-c", "exec -a hanrag-keepalive sleep infinity" -WindowStyle Hidden
    Write-Host "Started hidden WSL keep-alive process."
}
Start-Sleep -Seconds 2
wsl -e pg_isready -h localhost -p 5432 | Out-Host
