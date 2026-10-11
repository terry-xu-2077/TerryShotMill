# Windows 绿色版

绿色版是解压后直接运行的完整 Windows 客户端，不需要安装器。双击仓库根目录的 `打包绿色版.bat` 即可打包；该入口调用 `scripts/build-portable.ps1`，与 TerryComfyLauncher 的方式相同。也可使用 PowerShell 7 在仓库根目录直接执行：

```powershell
& .\scripts\build-portable.ps1
```

脚本依次冻结后端、检查冻结运行时、构建前端、编译正式 Tauri 程序，并组装与压缩绿色版。构建机需要项目 `.venv`、前端 `node_modules`、Node.js、Rust/Cargo 和完整 FFmpeg 发行目录；目标机器不需要这些开发环境。默认读取 `D:\Program Files\ffmpeg`，也可传入 `-FfmpegRoot` 或设置 `SHOTMILL_FFMPEG_ROOT`。发行目录须包含 `bin/ffmpeg.exe`、`bin/ffprobe.exe`、`LICENSE`、`README.txt`。

产物参照 Rulesmd Editor 测试版放在仓库的 `release/` 下，目录和同名 ZIP 并列：

```text
release/
  ShotMill 测试版/
    ShotMill.exe
    使用说明.txt
    resources/        前端生产资源
    runtime/          完整冻结后端、_internal 和内置媒体工具
  ShotMill 测试版.zip
```

复制或解压时须保留整个目录。脚本只收集构建产物和使用说明，不把项目、素材、数据库、应用设置或日志打入包内。项目由用户选定位置保存为 `.shotmill` 文件，生成结果写在工程旁的 `.files/outputs/`；本机导入素材仍引用原文件。应用设置独立保存在当前用户的 Windows 应用数据目录。项目 ZIP 是另一个功能，它会收集项目依赖文件供跨机器使用，不承担日常工程保存。

构建中的冻结后端专项检查覆盖内置媒体工具、API、前端静态资源、普通工程文件和正常退出。正式桌面程序还需从组装后的目录做启动检查；`--no-bundle` 编译成功本身不代表绿色包可用。此前 2026-10-11 的完整包位于 `.artifacts/portable/`，保留为历史证据；此后以 `release/` 为交付位置。

当前 FFmpeg 发行版随包保留原许可证和来源说明；对外分发前仍须单独核对完整第三方许可及对应源码交付材料。本机测试包不等于对外发布。
