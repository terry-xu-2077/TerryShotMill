[CmdletBinding()]
param(
    [switch]$Desktop,
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
chcp.com 65001 > $null

$ProjectRoot = $PSScriptRoot
$FrontendRoot = Join-Path $ProjectRoot 'frontend'
$UiPath = '/dev/ui'
$UiUrl = "http://127.0.0.1:1420$UiPath"

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

if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'package.json'))) {
    throw "未找到前端工程：$FrontendRoot"
}

if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw '未找到 pnpm。请先安装 Node.js 20+ 与 pnpm 10+。'
}

if (-not (Test-Path -LiteralPath (Join-Path $FrontendRoot 'node_modules'))) {
    Write-Host '首次启动，正在安装前端依赖……' -ForegroundColor Yellow
    & pnpm --dir $FrontendRoot install
    if ($LASTEXITCODE -ne 0) { throw '前端依赖安装失败。' }
}

Write-Host ''
Write-Host 'ShotMill UI 开发环境' -ForegroundColor Yellow
Write-Host "项目：$ProjectRoot"

if ($Desktop) {
    Write-Host '模式：Tauri 桌面壳（支持热更新）'
    Write-Host '按 Ctrl+C 停止。' -ForegroundColor DarkGray
    & pnpm --dir $FrontendRoot tauri dev
    if ($LASTEXITCODE -ne 0) { throw 'Tauri UI 开发环境异常退出。' }
    return
}

Write-Host "本机地址：$UiUrl"
$LanUrls = @(Get-LanUrls -Port 1420 -Path $UiPath)
foreach ($LanUrl in $LanUrls) {
    Write-Host "局域网地址：$LanUrl"
}
Write-Host '模式：浏览器 UI 工作台（支持热更新）'
Write-Host '按 Ctrl+C 停止。' -ForegroundColor DarkGray

if ($NoBrowser) {
    & pnpm --dir $FrontendRoot dev
    if ($LASTEXITCODE -ne 0) { throw '浏览器 UI 开发环境异常退出。' }
    return
}

& pnpm --dir $FrontendRoot dev -- --open /dev/ui
if ($LASTEXITCODE -ne 0) { throw '浏览器 UI 开发环境异常退出。' }
