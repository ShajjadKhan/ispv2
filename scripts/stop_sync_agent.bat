@echo off
REM Stop running OLT Live Sync Agent processes
powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*olt_sync_agent.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] Stopped process ' + $_.ProcessId) }"
echo [OK] OLT Live Sync Agent stopped.
