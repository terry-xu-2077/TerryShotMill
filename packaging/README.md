# Windows 独立运行时

此目录用于完整 Windows 客户端，不是远程网页壳。当前已验证独立后端目录式 EXE；完整 Tauri 安装包、升级与实际窗口验收仍以 `docs/PROJECT_PORTABILITY_PLAN.md` 为准。

## 构建

从仓库根目录使用 PowerShell 7。构建环境需要项目 Python 依赖；目标机器不需要安装 Python。

```powershell
.venv/Scripts/python.exe -m pip install --no-cache-dir '.[desktop-build]'
$env:SHOTMILL_FFMPEG_ROOT = 'D:/Program Files/ffmpeg'
$env:PYINSTALLER_CONFIG_DIR = 'G:/AIGC/TerryShotMill/.artifacts/pyinstaller-cache'
.venv/Scripts/python.exe -m PyInstaller packaging/shotmill-backend.spec --distpath .artifacts/windows-runtime --workpath .artifacts/pyinstaller --noconfirm
.venv/Scripts/python.exe scripts/verify_desktop_runtime.py .artifacts/windows-runtime/shotmill-backend/shotmill-backend.exe
```

两处构建路径应按本机环境指定，不进入业务数据或最终配置。FFmpeg 发行目录必须有 `bin/ffmpeg.exe`、`bin/ffprobe.exe`、`LICENSE`、`README.txt`。不得仅复制 EXE：必须携带完整 `shotmill-backend` 输出目录（包含 `_internal`）。

验证在临时目录中运行，清除 Python/ShotMill 环境变量，并从 PATH 中移除开发工具；使用内置媒体工具生成/探测短视频，再启动实际冻结后端，核对 API、静态资源、项目持久化和正常退出。它不代替完整前端窗口、真实 Bridge 或干净 Windows 系统验收。

## 桌面壳资源整合

先构建前端，再用 `frontend/src-tauri/tauri.bundle.conf.json` 合并发布配置。此配置关闭隐式前端构建命令，因此必须显式完成 TypeScript/Vite 构建；资源映射把完整后端目录放到 `runtime/`，前端放到 `frontend/`。从 `frontend` 运行：

```powershell
& 'C:/Program Files/nodejs/node.exe' node_modules/typescript/bin/tsc -b --pretty false
# 上一步成功后继续。
& 'C:/Program Files/nodejs/node.exe' node_modules/vite/bin/vite.js build
# 上一步成功后继续。
& 'C:/Program Files/nodejs/node.exe' node_modules/@tauri-apps/cli/tauri.js build --config src-tauri/tauri.bundle.conf.json --bundles nsis --ci -- --offline
```

仅编译可将 `--bundles nsis` 换成 `--no-bundle`。窗口验收额外合并 `--config src-tauri/tauri.smoke.conf.json`，使用独立 `com.terry.shotmill.acceptance` 数据目录及 `ShotMill Acceptance` 产品名称，不迁移正式应用数据，也不共用正式产品的安装记录。验收构建与正式构建共享输出文件名：必须确认构建进程成功退出后才能启动，不能在编译期间打开该路径下的旧 EXE；交付前必须重新使用正式配置构建，不能误发测试标识版本。

## 构建注意

- 2026-09-27 pip 安装曾卡在缓存临时文件创建；已用进程栈确认。关闭缓存后安装成功。遇到等待先检查原进程，不并行向同一环境重复安装。
- 当前构建使用本机已有 FFmpeg 静态发行版，文件较大。已随包保留原许可证和来源说明；对外分发前还必须核对完整第三方许可/对应源码交付材料，不能把本机测试包视作已完成发布合规。
- 用户数据库、项目媒体、设置和凭据不得放进构建资源。
- 启动方必须保持 stdin 管道打开；关闭管道请求正常退出。相同数据目录只允许一个桌面后端。
