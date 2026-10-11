@echo off
setlocal
cd /d "%~dp0"
set "PWSH=C:\Program Files\PowerShell\7\pwsh.exe"
if not exist "%PWSH%" (
  echo PowerShell 7 was not found: "%PWSH%"
  pause
  exit /b 1
)
"%PWSH%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-portable.ps1" %*
set "BUILD_EXIT=%ERRORLEVEL%"
if not "%BUILD_EXIT%"=="0" echo Build failed. Review the messages above.
pause
exit /b %BUILD_EXIT%
