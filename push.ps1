$entry = Join-Path $PSScriptRoot "一键推送.ps1"
if (-not (Test-Path -LiteralPath $entry)) {
    Write-Host "Push script not found: $entry" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
& $entry
exit $LASTEXITCODE
