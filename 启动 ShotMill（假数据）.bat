@echo off
setlocal
cd /d "%~dp0"

"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-frontend-deps.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)

"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-mock-ui.ps1"
if errorlevel 1 pause
endlocal
