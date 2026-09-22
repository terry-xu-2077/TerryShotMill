# ShotMill

ShotMill 是面向 AI 视频生产的素材生成工作台。当前推进 V0.4 批量生产流程，默认界面为项目首页、项目工作台和任务编辑弹窗。

## 当前进展（2026-09-20）

- 已接通本地 AI 增强、人工审核、单任务生成和批量视频生成；增强与视频使用独立的持久化队列。
- 应用通过 ShotMill Bridge API 与 ComfyUI 通信。工作流保留在 ComfyUI 端，应用只读取经过标记节点过滤的目录及输入槽位信息。
- 槽位支持可选图片、视频和音频，先填充资产再从 `@` 引用。H3 执行时按实际非空输入适配引用编号，不修改任务原文。
- 支持亮暗主题、任务视图切换、应用设置、工作流配置、实际结果播放及媒体规格显示。
- “异星边境”8 个任务已用 `异星边境_稳定720P.json` 全部生成，完成解码、播放、文件一致性和服务重启后的读取验收。该文件的默认实际输出为 **864×480、24fps、8 秒**，不是文件名中的 720P；未为验收降低工作流参数。
- 全量验证七阶段通过，含 28 项桌面/移动端 E2E。详细记录和未完成项见 [验收记录](docs/UX_ACCEPTANCE_BASELINE.md)。数值端口绑定、通用工作流时长控制和部分交互完善仍在后续计划中。

## ComfyUI Bridge

将 [`integrations/comfyui_shotmill`](integrations/comfyui_shotmill) 整个目录复制为 ComfyUI 的 `custom_nodes/ComfyUI-ShotMill`，包括 `web/`，然后在队列空闲时重启 ComfyUI。升级前备份旧节点包及 `output/shotmill/jobs.json`，旧版本迁移见 [Bridge 文档](integrations/comfyui_shotmill/README.md)。

在左下角设置中配置 ComfyUI 地址、AI 增强和生成工作流。ShotMill 复用已有 ComfyUI，不会自行关闭或重启它；工作流所需模型及第三方节点仍需在 ComfyUI 端安装。生成结果隔离保存在 `output/shotmill/results/<job-id>/`，原生保存节点添加的序号不会造成任务之间覆盖。

共享 UI 依赖采用仓库内固定版本包，来源、源码补丁与重建方式见 [`frontend/vendor/README.md`](frontend/vendor/README.md)。安装无需临时源码目录或运行时修改 `node_modules`。

## 开发环境

- Node.js 20+
- pnpm 10+
- Python 3.11+
- Rust stable（Tauri 桌面壳需要；一键启动器在 Windows 上可自动安装 Rust）

## 一键启动

Windows 真实联调直接双击根目录的 `启动 ShotMill（前端+后端）.bat`，它负责同时管理 FastAPI 后端与 Tauri 前端。

启动器会自动完成：

- 检查 Node.js、pnpm、Python 3.11+ 与 Rust/Cargo；缺少 Rust 时自动安装 stable toolchain。
- 创建或修复项目根目录 `.venv`。
- 仅在 `pyproject.toml` 发生变化时安装/更新 Python 后端与开发依赖。
- 仅在 `frontend/package.json` 或 `pnpm-lock.yaml` 发生变化时安装/更新前端依赖。
- 检测本机 `127.0.0.1:7897` 开发代理；依赖直连失败时自动通过该代理重试。
- 检查 `8765`：若已经是 ShotMill 后端则复用；若被其他程序占用则明确报错。
- 自动在一个标题为 `ShotMill Backend` 的可见控制台中启动 FastAPI，并等待 `/health` 真正就绪。
- 检查 `1420`：若已经是 ShotMill Vite 前端则复用，避免重复启动；若属于其他程序则报错。
- Tauri 窗口关闭时，会结束本次启动器创建的后端控制台及其 Uvicorn 进程树。
- 后端控制台还会监视主启动器 PID；即使主启动器被直接关闭，也会自动清理自己的后端进程树。
- 如果启动前 `8765` 已经有一个健康的 ShotMill 后端，启动器只复用它，不会在退出时结束用户原本运行的后端。

开发地址：

- 后端 API：`http://127.0.0.1:8765`
- 健康检查：`http://127.0.0.1:8765/health`
- 前端开发服务：`http://127.0.0.1:1420/dev/ui`；默认监听 `0.0.0.0`，同一局域网手机可用 `http://<电脑局域网 IP>:1420/dev/ui` 访问。
- 后端生命周期日志：`.shotmill/logs/backend-lifecycle.log`

首次启动可能需要下载 Python、前端与 Rust 依赖；之后会通过依赖指纹跳过不必要的重复安装。

## 假数据 UI 模式

只打磨 UI 或验证交互时，双击 `启动 ShotMill（假数据）.bat`。它会打开浏览器版 UI，并连接后端提供的独立假 API：

- 前端仍使用正式 `HttpProjectGateway` 和 `/api/v1`，没有第二套 UI 数据逻辑。
- 假 API 复用正式路由、Schema、SQLite 和业务 Service，并预置项目、任务、资产和 AI 增强历史。
- 当前会话内的保存和编辑真实生效；关闭启动器后临时数据自动清理。
- 不需要启动 ComfyUI，也不会调用外部 Prompt AI。

假数据 API 默认地址为 `http://127.0.0.1:8766`。启动器会记录自己创建的进程 ID 和启动时间，下次运行先精确清理异常退出留下的服务；对没有记录的占用者还会验证服务页面、进程类型和项目路径，只有确认属于当前 ShotMill 项目才会结束，否则安全顺延到空闲端口。详细契约见 [`contracts/README.md`](contracts/README.md)。

## 其他启动方式

浏览器 UI 调试仍可单独运行：

```powershell
& .\Start-UI.ps1
```

`Start-UI.ps1` 只负责浏览器 UI；需要完整前后端联调时使用 `启动 ShotMill（前端+后端）.bat`。

也可以分别手动启动。

后端：

```powershell
python -m pip install -e ".[dev]"
python -m uvicorn shotmill.app:app --app-dir backend --host 127.0.0.1 --port 8765 --reload
```

前端：

```powershell
pnpm --dir frontend dev
```

前端开发服务默认只把浏览器入口暴露到局域网，后端仍监听本机 `127.0.0.1:8765`，由 Vite 代理 `/api` 与 `/media`。后续接入登录或访问令牌前，不要把后端直接改为公网或全网段监听。

桌面壳：

```powershell
pnpm --dir frontend tauri dev
```

## 启动器预检

只检查环境和端口，不安装依赖、不启动程序：

```powershell
& .\scripts\start-dev.ps1 -CheckOnly
```

## 验收

```powershell
python scripts/verify.py
python scripts/verify.py --area backend
python scripts/verify.py --area frontend
python scripts/verify.py --full
```

产品与开发文档见 [`docs/README.md`](docs/README.md)，当前实施进度见 [`docs/DEVELOPMENT_LOG.md`](docs/DEVELOPMENT_LOG.md)。
