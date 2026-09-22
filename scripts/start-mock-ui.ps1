[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$NoBrowser,
    [ValidateRange(1, 65535)]
    [int]$DevPort = 1420,
    [ValidateRange(1, 65535)]
    [int]$MockApiPort = 8766
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
chcp.com 65001 > $null

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root 'frontend'
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Modules = Join-Path $Frontend 'node_modules'
$StateDir = Join-Path $Root '.shotmill'
$StateFile = Join-Path $StateDir 'mock-ui-processes.json'
$ApiProcess = $null
$UiProcess = $null

function Fail([string]$Text) {
    Write-Host "`n[ERROR] $Text" -ForegroundColor Red
    exit 1
}

function Test-LocalPort([int]$Port) {
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Result = $Client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if (-not $Result.AsyncWaitHandle.WaitOne(700)) { return $false }
        $Client.EndConnect($Result)
        return $true
    } catch {
        return $false
    } finally {
        $Client.Close()
    }
}

function Get-AvailablePort([int]$PreferredPort) {
    if (-not (Test-LocalPort $PreferredPort)) { return $PreferredPort }

    $LastPort = [Math]::Min(65535, $PreferredPort + 100)
    for ($Candidate = $PreferredPort + 1; $Candidate -le $LastPort; $Candidate++) {
        if (-not (Test-LocalPort $Candidate)) { return $Candidate }
    }
    return 0
}

function Test-ShotMillFrontendPort([int]$Port) {
    try {
        $Response = Invoke-WebRequest `
            -Uri "http://127.0.0.1:$Port/dev/ui" `
            -UseBasicParsing `
            -TimeoutSec 2
        return (($Response.StatusCode -eq 200) -and
            ($Response.Content -match '<title>ShotMill</title>') -and
            ($Response.Content -match '/src/main\.tsx'))
    } catch {
        return $false
    }
}

function Test-ShotMillMockApiPort([int]$Port) {
    try {
        $Response = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
        return $Response.name -eq 'ShotMill Mock API'
    } catch {
        return $false
    }
}

function Stop-VerifiedResidual([int]$Port, [ValidateSet('ui', 'api')][string]$Kind) {
    $ServiceMatches = if ($Kind -eq 'ui') {
        Test-ShotMillFrontendPort $Port
    } else {
        Test-ShotMillMockApiPort $Port
    }
    if (-not $ServiceMatches) { return $false }

    $Connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    $OwnerIds = @($Connections | Select-Object -ExpandProperty OwningProcess -Unique)
    if ($OwnerIds.Count -eq 0) { return $false }

    $VerifiedIds = @()
    foreach ($OwnerId in $OwnerIds) {
        $Owner = Get-CimInstance `
            Win32_Process `
            -Filter "ProcessId = $OwnerId" `
            -ErrorAction SilentlyContinue
        if ($null -eq $Owner) { return $false }

        $CommandLine = [string]$Owner.CommandLine
        $IsCurrentProject = $CommandLine -match [regex]::Escape($Root)
        $IsExpectedProcess = if ($Kind -eq 'ui') {
            ($Owner.Name -eq 'node.exe') -and ($CommandLine -match 'vite')
        } else {
            ($Owner.Name -eq 'python.exe') -and ($CommandLine -match 'scripts[\\/]mock_api\.py')
        }
        if (-not ($IsCurrentProject -and $IsExpectedProcess)) { return $false }
        $VerifiedIds += $OwnerId
    }

    foreach ($OwnerId in $VerifiedIds) {
        & taskkill.exe /PID $OwnerId /T /F *> $null
    }
    for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
        if (-not (Test-LocalPort $Port)) { return $true }
        Start-Sleep -Milliseconds 100
    }
    return $false
}

function Stop-ProcessTree($Process) {
    if ($null -eq $Process) { return }
    try {
        $Process.Refresh()
        if (-not $Process.HasExited) {
            & taskkill.exe /PID $Process.Id /T /F *> $null
        }
    } catch {
        Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
}

function Get-ProcessIdentity($Process) {
    if ($null -eq $Process) { return $null }
    $Process.Refresh()
    return [pscustomobject]@{
        processId = $Process.Id
        startTimeUtcTicks = $Process.StartTime.ToUniversalTime().Ticks
    }
}

function Get-LanUrls([int]$Port, [string]$Path) {
    $Addresses = @([System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
        Where-Object {
            $_.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork -and
            $_.IPAddressToString -notmatch '^(127\.|169\.254\.)'
        } |
        ForEach-Object { $_.IPAddressToString } |
        Select-Object -Unique)

    foreach ($Address in $Addresses) {
        "http://${Address}:$Port$Path"
    }
}

function Write-LauncherState {
    New-Item -ItemType Directory -Path $StateDir -Force | Out-Null
    $State = [ordered]@{
        projectRoot = $Root
        launcherProcessId = $PID
        api = Get-ProcessIdentity $ApiProcess
        ui = Get-ProcessIdentity $UiProcess
    }
    $State | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $StateFile -Encoding utf8
}

function Stop-TrackedResidual {
    if (-not (Test-Path -LiteralPath $StateFile)) { return }
    try {
        $State = Get-Content -LiteralPath $StateFile -Raw -Encoding utf8 | ConvertFrom-Json
        if ([string]$State.projectRoot -ne $Root) { return }
        foreach ($Identity in @($State.ui, $State.api)) {
            if ($null -eq $Identity) { continue }
            $Tracked = Get-Process -Id ([int]$Identity.processId) -ErrorAction SilentlyContinue
            if ($null -eq $Tracked) { continue }
            $StartTicks = $Tracked.StartTime.ToUniversalTime().Ticks
            if ($StartTicks -eq [long]$Identity.startTimeUtcTicks) {
                & taskkill.exe /PID $Tracked.Id /T /F *> $null
            }
        }
    } catch {
        Write-Host 'Could not read the previous Mock UI process record; using port verification.' -ForegroundColor Yellow
    } finally {
        Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
    }
}

$Host.UI.RawUI.WindowTitle = 'ShotMill - Mock UI'
Write-Host 'ShotMill - Mock UI Launcher' -ForegroundColor Green
Write-Host "Project: $Root" -ForegroundColor DarkGray
Write-Host 'Mode: real frontend HTTP client + backend-owned fake API' -ForegroundColor DarkGray

if (-not $CheckOnly) {
    Stop-TrackedResidual
}

$RequestedDevPort = $DevPort
if ((-not $CheckOnly) -and (Test-LocalPort $RequestedDevPort)) {
    if (Stop-VerifiedResidual -Port $RequestedDevPort -Kind 'ui') {
        Write-Host "Stopped a leftover ShotMill Vite service on UI port $RequestedDevPort." -ForegroundColor Yellow
    }
}
$DevPort = Get-AvailablePort $RequestedDevPort
if ($DevPort -eq 0) {
    Fail "No free UI port was found after $RequestedDevPort."
}
if ($DevPort -ne $RequestedDevPort) {
    Write-Host "UI port $RequestedDevPort is already in use; using UI port $DevPort instead." -ForegroundColor Yellow
}

$RequestedMockApiPort = $MockApiPort
if ((-not $CheckOnly) -and (Test-LocalPort $RequestedMockApiPort)) {
    if (Stop-VerifiedResidual -Port $RequestedMockApiPort -Kind 'api') {
        Write-Host "Stopped a leftover ShotMill fake API on port $RequestedMockApiPort." -ForegroundColor Yellow
    }
}
$MockApiPort = Get-AvailablePort $RequestedMockApiPort
if ($MockApiPort -eq 0) {
    Fail "No free Mock API port was found after $RequestedMockApiPort."
}
if ($MockApiPort -ne $RequestedMockApiPort) {
    Write-Host "Mock API port $RequestedMockApiPort is already in use; using $MockApiPort instead." -ForegroundColor Yellow
}

$UiUrl = "http://127.0.0.1:$DevPort/dev/ui"
$ApiUrl = "http://127.0.0.1:$MockApiPort"

if ($CheckOnly) {
    Write-Host "[CHECK] UI: $UiUrl" -ForegroundColor DarkGray
    Write-Host "[CHECK] Mock API: $ApiUrl" -ForegroundColor DarkGray
    Write-Host '[CHECK] Mock launcher preflight passed.' -ForegroundColor Green
    exit 0
}

if (-not (Test-Path -LiteralPath $Python)) {
    Fail 'Python environment is missing. Run the normal ShotMill launcher once to install dependencies.'
}
if (-not (Test-Path -LiteralPath $Modules)) {
    Fail 'Frontend dependencies are missing. Run the normal ShotMill launcher once to install dependencies.'
}
if (-not (Get-Command pnpm.cmd -ErrorAction SilentlyContinue)) {
    Fail 'pnpm was not found.'
}
$Pnpm = (Get-Command pnpm.cmd).Source

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:SHOTMILL_BACKEND_URL = $ApiUrl
$env:VITE_SHOTMILL_API_BASE_URL = '/api/v1'

try {
    Write-Host "`n==> Starting fake API: $ApiUrl" -ForegroundColor Cyan
    $ApiProcess = Start-Process `
        -FilePath $Python `
        -ArgumentList @('scripts\mock_api.py', '--port', [string]$MockApiPort) `
        -WorkingDirectory $Root `
        -NoNewWindow `
        -PassThru
    Write-LauncherState

    $ApiReady = $false
    for ($Attempt = 0; $Attempt -lt 60; $Attempt++) {
        if ($ApiProcess.HasExited) { Fail "The fake API exited with code $($ApiProcess.ExitCode)." }
        try {
            $Response = Invoke-RestMethod -Uri "$ApiUrl/health" -TimeoutSec 1
            if ($Response.status -eq 'ok') {
                $ApiReady = $true
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (-not $ApiReady) { Fail 'The fake API did not become ready in time.' }

    Write-Host "`n==> Starting UI: $UiUrl" -ForegroundColor Cyan
    $UiProcess = Start-Process `
        -FilePath $Pnpm `
        -ArgumentList @('exec', 'vite', '--host', '0.0.0.0', '--port', [string]$DevPort) `
        -WorkingDirectory $Frontend `
        -NoNewWindow `
        -PassThru
    Write-LauncherState

    $UiReady = $false
    for ($Attempt = 0; $Attempt -lt 80; $Attempt++) {
        if ($UiProcess.HasExited) { Fail "The UI exited with code $($UiProcess.ExitCode)." }
        try {
            $Response = Invoke-WebRequest -Uri $UiUrl -UseBasicParsing -TimeoutSec 1
            if ($Response.StatusCode -eq 200) {
                $UiReady = $true
                break
            }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (-not $UiReady) { Fail 'The UI did not become ready in time.' }

    Write-Host "`nMock UI is ready. Data resets when this launcher stops." -ForegroundColor Green
    Write-Host "Local UI: $UiUrl" -ForegroundColor DarkGray
    foreach ($LanUrl in @(Get-LanUrls -Port $DevPort -Path '/dev/ui')) {
        Write-Host "LAN UI: $LanUrl" -ForegroundColor DarkGray
    }
    Write-Host 'Close this window or press Ctrl+C to stop both services.' -ForegroundColor DarkGray
    if (-not $NoBrowser) {
        Start-Process $UiUrl
    }
    Wait-Process -Id $UiProcess.Id
} finally {
    Stop-ProcessTree $UiProcess
    Stop-ProcessTree $ApiProcess
    Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
}
