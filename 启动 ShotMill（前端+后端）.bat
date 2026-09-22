@echo off
setlocal
cd /d "%~dp0"

rem Keep the user's configured mirror as the primary index, but let pip fall back to
rem official PyPI for build-only packages that some mirrors may not carry.
set "PIP_EXTRA_INDEX_URL=https://pypi.org/simple"

"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\ensure-frontend-deps.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)

"C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"
if errorlevel 1 pause
endlocal
