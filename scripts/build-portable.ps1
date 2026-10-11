param(
    [string]$FfmpegRoot = $(if ($env:SHOTMILL_FFMPEG_ROOT) { $env:SHOTMILL_FFMPEG_ROOT } else { 'D:\Program Files\ffmpeg' })
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
chcp.com 65001 > $null

if ($PSVersionTable.PSEdition -ne 'Core' -or $PSVersionTable.PSVersion.Major -ne 7) {
    throw '请使用 PowerShell 7 运行此脚本。'
}

$root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$frontend = Join-Path $root 'frontend'
$python = Join-Path $root '.venv\Scripts\python.exe'
$node = (Get-Command node.exe -ErrorAction SilentlyContinue).Source
$runtime = Join-Path $root '.artifacts\windows-runtime\shotmill-backend'
$frontendDist = Join-Path $frontend 'dist'
$desktopExe = Join-Path $frontend 'src-tauri\target\release\shotmill.exe'
$releaseRoot = Join-Path $root 'release'
$packageName = 'ShotMill 测试版'
$packageDir = Join-Path $releaseRoot $packageName
$zipPath = Join-Path $releaseRoot "$packageName.zip"

function Invoke-BuildStep([string]$name, [string]$executable, [string[]]$arguments, [string]$directory) {
    Write-Host "`n==> $name" -ForegroundColor Cyan
    Push-Location -LiteralPath $directory
    try {
        & $executable @arguments
        if ($LASTEXITCODE -ne 0) { throw "$name 失败（退出码 $LASTEXITCODE）。" }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "缺少项目 Python 环境：$python" }
if (-not $node) { throw '找不到 Node.js。' }
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'node_modules\@tauri-apps\cli\tauri.js') -PathType Leaf)) {
    throw '缺少前端依赖，请先在 frontend 安装项目依赖。'
}
if (-not (Test-Path -LiteralPath (Join-Path $FfmpegRoot 'bin\ffmpeg.exe') -PathType Leaf)) {
    throw "找不到 FFmpeg 发行目录：$FfmpegRoot"
}

$env:SHOTMILL_FFMPEG_ROOT = [System.IO.Path]::GetFullPath($FfmpegRoot)
$env:PYINSTALLER_CONFIG_DIR = Join-Path $root '.artifacts\pyinstaller-cache'
New-Item -ItemType Directory -Path $env:PYINSTALLER_CONFIG_DIR -Force | Out-Null

Invoke-BuildStep '冻结后端' $python @(
    '-m', 'PyInstaller', 'packaging/shotmill-backend.spec',
    '--distpath', '.artifacts/windows-runtime',
    '--workpath', '.artifacts/pyinstaller', '--noconfirm'
) $root

Invoke-BuildStep '检查冻结后端与内置媒体工具' $python @(
    'scripts/verify_desktop_runtime.py', (Join-Path $runtime 'shotmill-backend.exe')
) $root

Invoke-BuildStep '构建前端' $node @('node_modules/typescript/bin/tsc', '-b', '--pretty', 'false') $frontend
Invoke-BuildStep '生成前端资源' $node @('node_modules/vite/bin/vite.js', 'build') $frontend
Invoke-BuildStep '编译桌面程序' $node @(
    'node_modules/@tauri-apps/cli/tauri.js', 'build',
    '--config', 'src-tauri/tauri.bundle.conf.json', '--no-bundle', '--ci', '--', '--offline'
) $frontend

foreach ($path in @($desktopExe, (Join-Path $runtime 'shotmill-backend.exe'), (Join-Path $frontendDist 'index.html'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "构建产物缺失：$path" }
}

Write-Host "`n==> 组装绿色版" -ForegroundColor Cyan
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
if (Test-Path -LiteralPath $packageDir) {
    if ((Get-Item -LiteralPath $packageDir).Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw "拒绝清理链接指向的发布目录：$packageDir"
    }
    $resolved = (Resolve-Path -LiteralPath $packageDir).ProviderPath
    $expected = [System.IO.Path]::GetFullPath($packageDir)
    if ($resolved -ne $expected -or (Split-Path -Parent $resolved) -ne (Resolve-Path -LiteralPath $releaseRoot).ProviderPath) {
        throw "拒绝清理非预期的发布目录：$resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

New-Item -ItemType Directory -Path $packageDir -Force | Out-Null
Copy-Item -LiteralPath $desktopExe -Destination (Join-Path $packageDir 'ShotMill.exe')
Copy-Item -LiteralPath (Join-Path $root 'packaging\使用说明.txt') -Destination $packageDir
foreach ($entry in @(@($runtime, 'runtime'), @($frontendDist, 'resources'))) {
    $destination = Join-Path $packageDir $entry[1]
    New-Item -ItemType Directory -Path $destination -Force | Out-Null
    Get-ChildItem -LiteralPath $entry[0] -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
    }
}

Write-Host "`n==> 压缩绿色版" -ForegroundColor Cyan
Compress-Archive -LiteralPath $packageDir -DestinationPath $zipPath -CompressionLevel Optimal -Force
Write-Host "`n完成：$packageDir" -ForegroundColor Green
Write-Host "压缩包：$zipPath" -ForegroundColor Green
