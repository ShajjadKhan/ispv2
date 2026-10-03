@echo off
REM Start OLT Real-time Telemetry Poller detached via WMI
powershell.exe -NoProfile -Command "Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CommandLine = 'powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File C:\Users\SHAJJA~1\TSERVE~1\isp_v2\scripts\olt_sync_agent.ps1 -IntervalSeconds 60' } | Out-Null"
echo [OK] OLT Live Sync Agent started in background.
