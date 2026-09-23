@echo off
chcp 65001 >nul
setlocal

REM ===== 仓库目录（按实际路径修改）=====
set "REPO=G:\AIGC\TerryShotMill"

cd /d "%REPO%" || (
    echo [FAIL] 无法进入仓库目录: %REPO%
    pause
    exit /b 1
)

echo ============================================
echo   ShotMill 一键推送  ->  origin/main
echo ============================================
echo.

echo [1/3] 设置 Git 传输后端为 OpenSSL（规避 schannel TLS 错误 SEC_E_MESSAGE_ALTERED）
git config http.sslBackend openssl
git config http.postBuffer 524288000
echo.

echo [2/3] 当前状态：
git status -sb
echo.

echo [3/3] 推送到 origin/main ...
git push origin main
if errorlevel 1 (
    echo.
    echo [FAIL] 推送失败，请查看上方错误信息。
    pause
    exit /b 1
)

echo.
echo [OK] 已推送，正在刷新本地跟踪引用（不影响远端）...
git fetch origin main >nul 2>&1

echo.
git status -sb
echo.
echo [OK] 完成！仓库已与 origin/main 同步。
echo.
pause
