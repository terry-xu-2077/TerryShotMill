# Bridge 源码归属与固定依赖

`ComfyUI-TerryFlowBridge` 是 Bridge 的唯一开发仓库：
https://github.com/terry-xu-2077/ComfyUI-TerryFlowBridge.git

`comfyui_shotmill/` 保留旧目录名以兼容现有离线合同测试，是固定版本的完整源码快照，
不是另一份开发源码，也不是运行中 ComfyUI 的安装目录。版本、文件集合及摘要由
`terryflow-bridge.lock.json` 固定；单元测试拒绝快照文件增删或内容偏离。
摘要统一 UTF-8 / LF，避免 Windows 换行转换导致伪差异。

升级顺序：

1. 在独立 Bridge 仓库修改并完成包测试、ShotMill 合同测试。
2. 在独立仓库提交，记录完整 commit ID；确认目标提交已推送后才称为已发布。
3. 从该提交同步完整快照，同时更新 lock 中版本、文件列表和摘要。
4. 运行快照校验、Provider 与后端验收；不能只更新摘要绕过有效回归。
5. 单独进行 ComfyUI 空闲部署、重启及实际执行验收，保留旧包备份和任务数据。

当前固定提交已在本地独立仓库创建，尚未推送。2026-10-11 已在本机空闲 ComfyUI 部署并做局部运行验证；这不是远端发布或异机验收声明。
禁止在两个位置分别修复同一问题。ShotMill Core 不导入该节点包，仅 Provider 通过 HTTP
与运行中的 Bridge 通信。
