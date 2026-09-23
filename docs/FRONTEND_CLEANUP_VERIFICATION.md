# 前端旧实现清理验证记录

日期：2026-09-23。使用方法见 [前端 UI 微调指南](FRONTEND_UI_DEVELOPMENT.md)。

## 清理依据

从 `src/main.tsx` 跟踪 TS/TSX import、re-export、CSS import，同时把测试入口、测试 setup、类型声明纳入引用分析。对仅被自身专属测试引用的退役 UI，删除实现与对应测试；对当前功能仍使用的测试辅助模块保留。

旧 `ProjectWorkspace.tsx` 不能直接删除，因为首页和新建项目弹窗仍在使用。已把这两项提取为 `ProjectHome.tsx`，将当前 `ProjectWorkspaceV2.tsx` 整理为唯一的 `ProjectWorkspace.tsx`，移除旧工作台函数及其私有辅助函数。

保留了当前用户未提交的其他开发内容；本轮不修改后端或项目数据。旧素材引用 CSS 中仍生效的部分迁入 `prompt-asset-editor.css`，按钮有效间距迁回其组件样式文件。

## 已完成的验证

- `python scripts/verify.py --area frontend`：类型检查、单元测试、生产构建通过。
- `node frontend/scripts/audit-source-files.mjs`：正式应用引用图 97 个文件；含测试共 130 个文件；未发现游离源文件。此检查不等价于逐导出或逐 CSS 规则使用率检查。
- 当前截图脚本已在隔离 E2E 服务上执行，生成亮暗两种模式的首页、外观设置、工作台、任务编辑窗截图；已查看亮色编辑窗和暗色工作台。
- 滑块/保存入口等旧测试定位已迁移到实际使用的控件；没有放宽测试数值阈值。
- 定向复跑中区间拖动、工作流菜单、编辑窗布局、素材绑定和提示词切换通过；最后再跑首页/保存/编辑主流程、素材菜单键盘操作和移动端，共 10 项全部通过。

## 完整桌面测试与待处理项

首次完整桌面运行共 78 项：67 通过、11 失败。失败中 6 项涉及过期测试定位：3 项“保存”匹配到了“保存版本”，2 项区间滑块仍查询旧 `tc-range-slider-*`，1 项秒数滑块仍期待旧类名。相应定位已更新。

保存测试继续执行后，还发现任务提示词正文已移至右侧详情，旧断言仍在列表内找正文。已把断言迁到当前只读详情区，保留内容保存和显示校验。

其余 5 项完整套件失败未在本次清理中改动断言或相关业务行为：

| 测试 | 实测失败 | 后续核查方向 |
| --- | --- | --- |
| `experience-layout.spec.ts`：long folder titles | 首页标题 `text-overflow` 为 `clip`，测试期待 `ellipsis` | 核对当前多行截断设计与旧单行断言；继续核验长标题布局 |
| `generation-risk-warning.spec.ts` | 日期 opacity 为 `0.5`，测试期待 `0.8` | 核对用户确认的日期视觉基线 |
| `task-new-results.spec.ts` | 贴纸几何对齐差值为 9px，断言要求小于 1px | 核对当前贴纸位置设计与测试比较对象 |
| `theme-contrast.spec.ts` | 测量器遇到祖先组透明度，抛出 `Group opacity needs separate compositing review` | 补充组透明度合成测量，不能据此声称对比度合格 |
| `workspace-controls.spec.ts`：single generation | 生成按钮保持 disabled，测试再次点击时超时 | 检查批量选择、活动任务和模拟提交后状态之间的测试场景 |

这些结果不应被描述为“全套 E2E 已通过”。已通过的正式流程包括项目创建、弹窗焦点、项目配置、封面、运行中心、批量增强、播放器、任务导航、用户提示词历史、视频版本和主题切换等。范围外的失败保留，供后续 UI 微调时逐项处理。

截图输出：`.artifacts/ui-current/`。Playwright 的 `frontend/test-results/` 会被下一次运行刷新；本文件保留完整运行的失败摘要。
