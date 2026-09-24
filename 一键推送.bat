@echo off
setlocal
title ShotMill Push
set "PWSH=C:\Program Files\PowerShell\7\pwsh.exe"

if not exist "%PWSH%" (
    where pwsh.exe >nul 2>&1
    if errorlevel 1 (
        echo PowerShell 7 was not found.
        pause
        exit /b 1
    )
    set "PWSH=pwsh.exe"
)

echo Starting ShotMill push...
"%PWSH%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0push.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
echo.
if "%EXIT_CODE%"=="0" (
    echo Push script finished.
) else (
    echo Push script failed. Exit code: %EXIT_CODE%
)
pause
exit /b %EXIT_CODE%
