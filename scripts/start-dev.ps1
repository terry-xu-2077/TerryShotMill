[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [ValidateRange(1, 65535)]
    [int]$DevPort = 1420,
    [ValidateRange(1, 65535)]
    [int]$BackendPort = 8765,
    [ValidateRange(1, 65535)]
    [int]$ProxyPort = 7897
)

$ErrorActionPreference = 'Stop'

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
chcp.com 65001 > $null

$Root = Split-Path -Parent $PSScriptRoot
$Frontend = Join-Path $Root 'frontend'
$PackageFile = Join-Path $Frontend 'package.json'
$LockFile = Join-Path $Frontend 'pnpm-lock.yaml'
$Modules = Join-Path $Frontend 'node_modules'
$PackageStamp = Join-Path $Modules '.shotmill-package.sha256'
$PyProject = Join-Path $Root 'pyproject.toml'
$Venv = Join-Path $Root '.venv'
$Python = Join-Path $Venv 'Scripts\python.exe'
$PythonStamp = Join-Path $Venv '.shotmill-pyproject.sha256'
$TauriManifest = Join-Path $Frontend 'src-tauri\Cargo.toml'
$ReuseTauriConfig = Join-Path $Frontend 'src-tauri\tauri.reuse-dev.conf.json'
$BackendRunner = Join-Path $PSScriptRoot 'run-backend.ps1'
$DevPath = '/dev/ui'
$DevUrl = "http://127.0.0.1:$DevPort$DevPath"
$BackendBaseUrl = "http://127.0.0.1:$BackendPort"
$BackendHealthUrl = "$BackendBaseUrl/health"
$LogDir = Join-Path $Root '.shotmill\logs'
$BackendLifecycleLog = Join-Path $LogDir 'backend-lifecycle.log'
$DefaultComfyWorkflow = Join-Path $Root 'backend\shotmill\providers\video_generation\workflows\minimax_h3_reference_api.json'
$SiblingComfyRoot = Join-Path (Split-Path -Parent $Root) 'ComfyUI_Codex'
$ProxyHost = '127.0.0.1'
$ProxyUrl = "http://${ProxyHost}:${ProxyPort}"
$RustupUrl = 'https://win.rustup.rs/x86_64'
$BackendProcess = $null
$BackendStartedHere = $false

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
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

function Fail([string]$Text) {
    Write-Host "`n[ERROR] $Text" -ForegroundColor Red
    exit 1
}

function Test-LocalPort([string]$HostName, [int]$Port) {
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Result = $Client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $Result.AsyncWaitHandle.WaitOne(700)) { return $false }
        $Client.EndConnect($Result)
        return $true
    } catch {
        return $false
    } finally {
        $Client.Close()
    }
}

function Clear-ProxyEnv {
    @(
        'HTTP_PROXY',
        'HTTPS_PROXY',
        'ALL_PROXY',
        'CARGO_HTTP_PROXY',
        'GIT_HTTP_PROXY',
        'GIT_HTTPS_PROXY'
    ) | ForEach-Object {
        Remove-Item "Env:$_" -ErrorAction SilentlyContinue
    }
}

function Enable-ProxyEnv {
    $env:HTTP_PROXY = $ProxyUrl
    $env:HTTPS_PROXY = $ProxyUrl
    $env:ALL_PROXY = $ProxyUrl
    $env:CARGO_HTTP_PROXY = $ProxyUrl
    $env:GIT_HTTP_PROXY = $ProxyUrl
    $env:GIT_HTTPS_PROXY = $ProxyUrl
}

function Refresh-RustPath {
    $CargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
    if ((Test-Path -LiteralPath $CargoBin) -and (($env:Path -split ';') -notcontains $CargoBin)) {
        $env:Path = "$CargoBin;$env:Path"
    }
}

function Get-PortOwnerDescription([int]$Port) {
    $Connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($Connections.Count -eq 0) { return 'unknown process' }

    $OwnerIds = @($Connections | Select-Object -ExpandProperty OwningProcess -Unique)
    $Descriptions = foreach ($OwnerId in $OwnerIds) {
        $Process = Get-CimInstance Win32_Process -Filter "ProcessId = $OwnerId" -ErrorAction SilentlyContinue
        if ($null -eq $Process) {
            "PID $OwnerId"
        } else {
            "$($Process.Name) (PID $OwnerId)"
        }
    }
    return ($Descriptions -join ', ')
}

function Get-DevServerState([int]$Port, [string]$Url) {
    try {
        $Response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
        $Content = [string]$Response.Content
        if (($Response.StatusCode -eq 200) -and
            ($Content -match '<title>ShotMill</title>') -and
            ($Content -match '/src/main\.tsx')) {
            return 'shotmill'
        }
        return 'occupied'
    } catch {
        $Connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if ($Connections.Count -eq 0) { return 'free' }
        return 'occupied'
    }
}

function Get-BackendState([int]$Port, [string]$HealthUrl) {
    try {
        $Response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        if (($Response.status -eq 'ok') -and ($Response.service -eq 'shotmill-backend')) {
            return 'shotmill'
        }
    } catch {
        # Fall through to a socket ownership check.
    }

    $Connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if ($Connections.Count -eq 0) { return 'free' }
    return 'occupied'
}

function Test-VenvPython {
    if (-not (Test-Path -LiteralPath $Python)) { return $false }
    try {
        & $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-PythonBootstrap {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            & py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) { return 'py311' }
        } catch {}
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
            if ($LASTEXITCODE -eq 0) { return 'python' }
        } catch {
            return $null
        }
    }
    return $null
}

function Install-RustToolchain {
    Write-Step 'Rust/Cargo not found - installing Rust automatically'
    $InstallerDir = Join-Path $env:TEMP 'shotmill-rustup'
    $Installer = Join-Path $InstallerDir 'rustup-init.exe'
    New-Item -ItemType Directory -Path $InstallerDir -Force | Out-Null
    Remove-Item -LiteralPath $Installer -ErrorAction SilentlyContinue

    Clear-ProxyEnv
    try {
        Write-Host 'Downloading official rustup installer...' -ForegroundColor DarkGray
        Invoke-WebRequest -UseBasicParsing -Uri $RustupUrl -OutFile $Installer -TimeoutSec 60
    } catch {
        if (-not $ProxyAvailable) {
            Remove-Item $InstallerDir -Recurse -Force -ErrorAction SilentlyContinue
            Fail 'Rust could not be downloaded directly and the local development proxy is unavailable.'
        }
        Write-Host "Rust direct download failed. Retrying through $ProxyUrl ..." -ForegroundColor Yellow
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $RustupUrl -OutFile $Installer -Proxy $ProxyUrl -TimeoutSec 90
        } catch {
            Remove-Item $InstallerDir -Recurse -Force -ErrorAction SilentlyContinue
            Fail 'Rust automatic download failed both directly and through the local proxy.'
        }
    }

    if (-not (Test-Path -LiteralPath $Installer)) {
        Remove-Item $InstallerDir -Recurse -Force -ErrorAction SilentlyContinue
        Fail 'Rust installer download did not produce a usable file.'
    }

    & $Installer -y --profile minimal --default-toolchain stable
    $RustupExit = $LASTEXITCODE
    Remove-Item $InstallerDir -Recurse -Force -ErrorAction SilentlyContinue
    if ($RustupExit -ne 0) { Fail "rustup installation failed with exit code $RustupExit." }

    Refresh-RustPath
    if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
        Fail 'Rust was installed, but Cargo is still unavailable in the current process.'
    }
    Write-Host 'Rust/Cargo installed successfully.' -ForegroundColor Green
}

function Get-FrontendFingerprint {
    $PackageHash = (Get-FileHash -LiteralPath $PackageFile -Algorithm SHA256).Hash
    $LockHash = if (Test-Path -LiteralPath $LockFile) {
        (Get-FileHash -LiteralPath $LockFile -Algorithm SHA256).Hash
    } else {
        'NO_LOCKFILE'
    }
    return "$PackageHash`:$LockHash"
}

function Install-PythonBackend {
    Push-Location $Root
    try {
        Clear-ProxyEnv
        & $Python -m pip install --disable-pip-version-check -e '.[dev]'
        if ($LASTEXITCODE -eq 0) { return $true }

        if ($ProxyAvailable) {
            Write-Host "Python dependency install failed directly. Retrying through $ProxyUrl ..." -ForegroundColor Yellow
            Enable-ProxyEnv
            & $Python -m pip install --disable-pip-version-check -e '.[dev]'
            $Ok = $LASTEXITCODE -eq 0
            Clear-ProxyEnv
            return $Ok
        }
        return $false
    } finally {
        Pop-Location
    }
}

function Install-FrontendDependencies {
    Push-Location $Frontend
    try {
        Clear-ProxyEnv
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -eq 0) { return $true }

        if ($ProxyAvailable) {
            Write-Host "pnpm install failed directly. Retrying through $ProxyUrl ..." -ForegroundColor Yellow
            Enable-ProxyEnv
            & pnpm install --frozen-lockfile
            $Ok = $LASTEXITCODE -eq 0
            Clear-ProxyEnv
            return $Ok
        }
        return $false
    } finally {
        Pop-Location
    }
}

function Invoke-CargoFetch([string]$Mode) {
    Write-Step "Preparing Rust dependencies ($Mode)"
    & cargo fetch --locked --manifest-path $TauriManifest
    return $LASTEXITCODE
}

function ConvertTo-PowerShellLiteral([string]$Value) {
    return $Value.Replace("'", "''")
}

function Start-ShotMillBackend {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $PowerShellExe = (Get-Command pwsh.exe -ErrorAction Stop).Source
    $RunnerLiteral = ConvertTo-PowerShellLiteral $BackendRunner
    $PythonLiteral = ConvertTo-PowerShellLiteral $Python
    $RootLiteral = ConvertTo-PowerShellLiteral $Root
    $Command = "& '$RunnerLiteral' -PythonPath '$PythonLiteral' -ProjectRoot '$RootLiteral' -Port $BackendPort -ParentProcessId $PID"
    $EncodedCommand = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($Command))

    return Start-Process `
        -FilePath $PowerShellExe `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $EncodedCommand) `
        -WorkingDirectory $Root `
        -WindowStyle Normal `
        -PassThru
}

function Wait-BackendReady([System.Diagnostics.Process]$Process) {
    $Deadline = (Get-Date).AddSeconds(25)
    while ((Get-Date) -lt $Deadline) {
        $Process.Refresh()
        if ($Process.HasExited) {
            Fail "ShotMill backend console exited before becoming ready. Lifecycle log: $BackendLifecycleLog"
        }
        if ((Get-BackendState -Port $BackendPort -HealthUrl $BackendHealthUrl) -eq 'shotmill') {
            return
        }
        Start-Sleep -Milliseconds 250
    }
    Stop-ShotMillBackend
    Fail "ShotMill backend did not become ready within 25 seconds: $BackendHealthUrl"
}

function Stop-ShotMillBackend {
    if (-not $BackendStartedHere -or $null -eq $BackendProcess) { return }
    Write-Host 'Stopping ShotMill backend console and process tree...' -ForegroundColor DarkGray
    try {
        $BackendProcess.Refresh()
        if (-not $BackendProcess.HasExited) {
            & taskkill.exe /PID $BackendProcess.Id /T /F *> $null
        }
    } catch {
        try {
            Stop-Process -Id $BackendProcess.Id -Force -ErrorAction SilentlyContinue
        } catch {}
    }
}

Set-Location $Root

if (-not $env:SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE -and (Test-Path -LiteralPath $DefaultComfyWorkflow)) {
    $env:SHOTMILL_COMFYUI_WORKFLOW_TEMPLATE = $DefaultComfyWorkflow
}
if (-not $env:SHOTMILL_COMFYUI_ROOT -and (Test-Path -LiteralPath $SiblingComfyRoot)) {
    $env:SHOTMILL_COMFYUI_ROOT = $SiblingComfyRoot
}
if (-not $env:SHOTMILL_COMFYUI_BASE_URL -and (Test-Path -LiteralPath $SiblingComfyRoot)) {
    $env:SHOTMILL_COMFYUI_BASE_URL = 'http://127.0.0.1:8188'
}
if (-not $env:SHOTMILL_PROMPT_AI_BASE_URL -and $env:SHOTMILL_COMFYUI_BASE_URL) {
    $env:SHOTMILL_PROMPT_AI_BASE_URL = $env:SHOTMILL_COMFYUI_BASE_URL
}

if ($env:SHOTMILL_COMFYUI_BASE_URL) {
    Write-Host "ComfyUI: $($env:SHOTMILL_COMFYUI_BASE_URL)" -ForegroundColor DarkGray
    Write-Host 'ComfyUI is reused as an existing process; ShotMill does not start or stop it.' -ForegroundColor Yellow
}
if ($env:SHOTMILL_PROMPT_AI_BASE_URL) {
    Write-Host "Prompt AI endpoint: $($env:SHOTMILL_PROMPT_AI_BASE_URL)" -ForegroundColor DarkGray
}

Write-Host 'ShotMill - Development Launcher' -ForegroundColor Green
Write-Host "Project: $Root"
Write-Host "Frontend: $DevUrl" -ForegroundColor DarkGray
foreach ($LanUrl in @(Get-LanUrls -Port $DevPort -Path $DevPath)) {
    Write-Host "Frontend LAN: $LanUrl" -ForegroundColor DarkGray
}
Write-Host "Backend:  $BackendBaseUrl" -ForegroundColor DarkGray

foreach ($RequiredPath in @($PackageFile, $PyProject, $TauriManifest, $ReuseTauriConfig, $BackendRunner)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        Fail "Required project file was not found: $RequiredPath"
    }
}

$ProxyAvailable = Test-LocalPort $ProxyHost $ProxyPort
if ($ProxyAvailable) {
    Write-Host "Local development proxy available: $ProxyUrl" -ForegroundColor Green
} else {
    Write-Host "Local development proxy unavailable: $ProxyUrl" -ForegroundColor DarkGray
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail 'Node.js was not found. Install Node.js 20+ and run this launcher again.'
}
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    Fail 'pnpm was not found. Install pnpm 10+ and run this launcher again.'
}

$PythonBootstrap = Get-PythonBootstrap
if ($null -eq $PythonBootstrap) {
    Fail 'Python 3.11+ was not found. Install Python 3.11 or newer and run this launcher again.'
}

Refresh-RustPath
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    if ($CheckOnly) { Fail 'Rust/Cargo was not found.' }
    Install-RustToolchain
}

$DevServerState = Get-DevServerState -Port $DevPort -Url $DevUrl
if ($DevServerState -eq 'occupied') {
    $Owner = Get-PortOwnerDescription -Port $DevPort
    Fail "Port $DevPort is already used by $Owner, but it is not the ShotMill frontend. Close that program and run this launcher again."
}
$ReuseDevServer = $DevServerState -eq 'shotmill'
if ($ReuseDevServer) {
    Write-Host "Existing ShotMill frontend detected at $DevUrl." -ForegroundColor Yellow
    Write-Host 'It will be reused; a second Vite server will not be started.' -ForegroundColor DarkGray
} else {
    Write-Host "Development port $DevPort is available." -ForegroundColor DarkGray
}

$BackendState = Get-BackendState -Port $BackendPort -HealthUrl $BackendHealthUrl
if ($BackendState -eq 'occupied') {
    $Owner = Get-PortOwnerDescription -Port $BackendPort
    Fail "Port $BackendPort is already used by $Owner, but it is not the ShotMill backend. Close that program and run this launcher again."
}
if ($BackendState -eq 'shotmill') {
    Write-Host "Existing ShotMill backend detected at $BackendBaseUrl; it will be reused." -ForegroundColor Yellow
} else {
    Write-Host "Backend port $BackendPort is available." -ForegroundColor DarkGray
}

if ($CheckOnly) {
    Write-Host '[CHECK] Launcher preflight passed.' -ForegroundColor Green
    exit 0
}

if ($DevPort -ne 1420) {
    Fail 'A custom DevPort is supported only with -CheckOnly because the Tauri devUrl is fixed to port 1420.'
}

if ((Test-Path -LiteralPath $Venv) -and (-not (Test-VenvPython))) {
    Write-Step 'Existing Python virtual environment is stale - rebuilding it for this computer'
    Remove-Item -LiteralPath $Venv -Recurse -Force -ErrorAction Stop
}
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Step 'Creating Python virtual environment (.venv)'
    if ($PythonBootstrap -eq 'py311') {
        & py -3.11 -m venv $Venv
    } else {
        & python -m venv $Venv
    }
    if ($LASTEXITCODE -ne 0) {
        Fail "Python virtual environment creation failed with exit code $LASTEXITCODE."
    }
}
if (-not (Test-VenvPython)) {
    Fail 'Python virtual environment could not be created or requires Python 3.11+.'
}

$PythonPackageHash = (Get-FileHash -LiteralPath $PyProject -Algorithm SHA256).Hash
$InstalledPythonHash = if (Test-Path -LiteralPath $PythonStamp) {
    (Get-Content -LiteralPath $PythonStamp -Raw).Trim()
} else {
    ''
}
if ($PythonPackageHash -ne $InstalledPythonHash) {
    Write-Step 'Installing/updating Python backend and development dependencies'
    if (-not (Install-PythonBackend)) { Fail 'Python backend dependency installation failed.' }
    Set-Content -LiteralPath $PythonStamp -Value $PythonPackageHash -NoNewline -Encoding UTF8
} else {
    Write-Host 'Python backend dependencies are up to date.' -ForegroundColor DarkGray
}

$ExpectedFingerprint = Get-FrontendFingerprint
$InstalledFingerprint = if (Test-Path -LiteralPath $PackageStamp) {
    (Get-Content -LiteralPath $PackageStamp -Raw).Trim()
} else {
    ''
}
if ((-not (Test-Path -LiteralPath $Modules)) -or ($ExpectedFingerprint -ne $InstalledFingerprint)) {
    Write-Step 'Installing/updating frontend dependencies'
    if (-not (Install-FrontendDependencies)) { Fail 'Frontend dependency installation failed.' }
    New-Item -ItemType Directory -Path $Modules -Force | Out-Null
    Set-Content -LiteralPath $PackageStamp -Value $ExpectedFingerprint -NoNewline -Encoding UTF8
} else {
    Write-Host 'Frontend dependencies are up to date.' -ForegroundColor DarkGray
}

$env:CARGO_HTTP_MULTIPLEXING = 'false'
$env:CARGO_NET_RETRY = '2'
$env:CARGO_HTTP_TIMEOUT = '30'
Clear-ProxyEnv
$FetchCode = Invoke-CargoFetch 'direct'
$NetworkMode = 'direct'
if (($FetchCode -ne 0) -and $ProxyAvailable) {
    Write-Host "Cargo direct fetch failed. Retrying through $ProxyUrl ..." -ForegroundColor Yellow
    Enable-ProxyEnv
    $env:CARGO_NET_RETRY = '3'
    $env:CARGO_HTTP_TIMEOUT = '45'
    $FetchCode = Invoke-CargoFetch "proxy $ProxyUrl"
    $NetworkMode = 'local proxy'
}
if ($FetchCode -ne 0) {
    Clear-ProxyEnv
    Fail "Cargo dependency download failed. Local proxy checked: $ProxyUrl."
}
Clear-ProxyEnv

if ($BackendState -eq 'free') {
    Write-Step 'Starting ShotMill FastAPI backend in a visible console'
    $BackendProcess = Start-ShotMillBackend
    $BackendStartedHere = $true
    Wait-BackendReady -Process $BackendProcess
    Write-Host "ShotMill backend is ready: $BackendHealthUrl" -ForegroundColor Green
    Write-Host 'Backend console title: ShotMill Backend' -ForegroundColor DarkGray
    Write-Host "Backend lifecycle log: $BackendLifecycleLog" -ForegroundColor DarkGray
}

$env:VITE_SHOTMILL_API_BASE_URL = "$BackendBaseUrl/api/v1"
$env:SHOTMILL_DEV_BACKEND_URL = $BackendBaseUrl
$ExitCode = 0

try {
    Write-Step 'Starting ShotMill (Tauri development mode)'
    Write-Host "Rust dependency route used: $NetworkMode" -ForegroundColor DarkGray
    Write-Host "Backend API: $BackendBaseUrl" -ForegroundColor DarkGray
    Write-Host 'Closing the Tauri window also closes the backend started by this launcher.' -ForegroundColor DarkGray

    Push-Location $Frontend
    try {
        if ($ReuseDevServer) {
            & pnpm tauri dev --config $ReuseTauriConfig
        } else {
            & pnpm tauri dev
        }
        $ExitCode = $LASTEXITCODE
    } finally {
        Pop-Location
    }
} finally {
    Stop-ShotMillBackend
}

if ($ExitCode -ne 0) {
    Fail "Tauri exited with code $ExitCode. Backend lifecycle log: $BackendLifecycleLog"
}
