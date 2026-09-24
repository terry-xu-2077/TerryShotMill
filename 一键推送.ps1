$ErrorActionPreference = "Stop"
$Utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8NoBom
[Console]::OutputEncoding = $Utf8NoBom
$global:OutputEncoding = $Utf8NoBom
chcp.com 65001 > $null

function Fail([string]$Message) {
    Write-Host "[失败] $Message" -ForegroundColor Red
    Write-Host ""
    Read-Host "按回车退出"
    exit 1
}

$repo = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repo ".git"))) {
    Fail "当前目录不是 Git 仓库：$repo"
}

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    Fail "找不到 Git。请确认 Git 已安装并加入 PATH。"
}

Set-Location -LiteralPath $repo

try {
    $branch = (& git branch --show-current).Trim()
    if ([string]::IsNullOrWhiteSpace($branch)) {
        Fail "当前处于 detached HEAD，无法确定要推送的分支。"
    }

    $remote = (& git remote get-url origin 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($remote)) {
        Fail "没有配置 origin 远端。请先为仓库配置远端地址。"
    }

    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  ShotMill 一键推送" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "仓库：$repo"
    Write-Host "分支：$branch"
    Write-Host "远端：$remote"
    Write-Host ""

    Write-Host "当前状态：" -ForegroundColor Yellow
    & git status -sb
    if ($LASTEXITCODE -ne 0) { Fail "无法读取 Git 状态。" }
    Write-Host ""

    $answer = Read-Host "确认推送当前分支 '$branch' 到 origin？(Y/N)"
    if ($answer -notmatch "^(y|yes|是)$") {
        Write-Host "已取消。"
        exit 0
    }

    Write-Host ""
    Write-Host "正在暂存所有改动……" -ForegroundColor Yellow
    & git add --all
    if ($LASTEXITCODE -ne 0) {
        Fail "无法暂存改动。"
    }

    $staged = (& git diff --cached --name-only)
    if (-not $staged) {
        Write-Host "没有新的文件改动，直接检查远端同步状态。" -ForegroundColor Yellow
    }
    else {
        Write-Host ""
        Write-Host "已暂存文件：" -ForegroundColor Yellow
        $staged | ForEach-Object { Write-Host "  $_" }
        $message = Read-Host "请输入提交说明（直接回车使用：Update ShotMill）"
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = "Update ShotMill"
        }

        & git commit -m $message
        if ($LASTEXITCODE -ne 0) {
            Fail "提交失败。暂存内容已保留，你可以检查 Git 输出后重试。"
        }
    }

    Write-Host ""
    Write-Host "正在推送……" -ForegroundColor Yellow
    & git push --set-upstream origin $branch
    if ($LASTEXITCODE -ne 0) {
        Fail "推送失败。请根据上方 Git 错误检查登录、网络、权限或远端分支状态。"
    }

    Write-Host ""
    & git status -sb
    Write-Host ""
    Write-Host "[完成] 当前分支已推送到 origin/$branch。" -ForegroundColor Green
    Read-Host "按回车退出"
}
catch {
    Fail $_.Exception.Message
}
