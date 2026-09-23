# ShotMill 前端 UI 微调指南

更新：2026-09-23。面向熟悉 HTML + CSS、希望直接调整当前界面的开发者。

## 1. 先看这几个文件

当前只有“项目首页 → 项目工作台”，任务编辑、项目配置、设置、播放器通过弹窗打开。

| 想调整什么 | 页面结构（相对于 `frontend/src/`） | 主要 CSS（同样相对于 `frontend/src/`） |
| --- | --- | --- |
| 首页、项目文件夹、新建项目弹窗 | `features/projects/ProjectHome.tsx` | `styles/project-workspace.css`、`styles/application-settings.css` 中的 `.project-simple-dialog` |
| 工作台顶部、任务列表/卡片、右侧详情 | `features/projects/ProjectWorkspace.tsx` | `styles/project-workspace.css` |
| 底部状态栏、运行中心 | `features/projects/GlobalStatusbar.tsx`、`RuntimeCenter.tsx` | `styles/project-workspace.css` |
| 任务编辑弹窗 | `features/storyboard/TaskEditorDialog.tsx` | 见下方“任务编辑器样式顺序” |
| 提示词可视化内容、标签 | `components/H3PromptEditor.tsx` | `styles/v0.6-project-prompt.css`、`styles/v0.9-flex-layout-fixes.css` |
| 文本提示词、输入 @ 后的素材菜单 | `components/PromptAssetEditor.tsx` | `styles/prompt-asset-editor.css`、任务编辑器样式 |
| 工作流素材槽位 | `features/storyboard/WorkflowInputSlots.tsx` | 同目录 `WorkflowInputSlots.css` |
| 项目配置、项目素材列表 | `features/projects/ProjectConfigPanel.tsx` | `styles/project-config.css` |
| 项目封面编辑 | `features/projects/ProjectCoverEditor.tsx` | `styles/project-config.css` |
| 设置中的 AI / 通信 / 工作流 / 外观 | `features/settings/ApplicationSettingsPanel.tsx` | `styles/application-settings.css` |
| 配色编辑区 | `features/settings/ThemePaletteEditor.tsx` | 同目录 `ThemePaletteEditor.css` |
| 视频播放器 | `features/projects/TaskResultPlayer.tsx` | `styles/v0.6-project-prompt.css` 中 `.task-player-*` |
| 新结果贴纸、风险贴纸、生成进度 | `features/projects/TaskNewResults.tsx`、`TaskRiskSticker.tsx`、`GenerationProgress.tsx` | `styles/project-workspace.css` |
| 全局颜色、字体、圆角、阴影 | `ui/theme.ts` + `styles/tokens.css` | `styles/tokens.css` |
| 弹窗外框、遮罩、右键菜单 | `ui/overlay/` | `styles/overlays.css`，紧凑尺寸另见 `styles/v0.9-compact-density.css` |
| 按钮、输入框、复选框、两类标签 | `ui/primitives/` | `ui/primitives/styles/`，入口为 `ui/primitives/style.css` |
| 下拉、滑块、区间滑块、开关 | `ui/Select.tsx`、`Slider.tsx`、`RangeSlider.tsx`、`BoolSwitch.tsx` | 各自同名 `.css` |

`ProjectWorkspaceV2.tsx` 已整理为 `ProjectWorkspace.tsx`。不要寻找另一套旧工作台。

## 2. 启动与预览

在 PowerShell 7 中，从项目根目录运行。推荐用独立假数据服务调整 UI：

```powershell
Set-Location G:\AIGC\TerryShotMill
& "C:\Program Files\PowerShell\7\pwsh.exe" -NoLogo -NoProfile -File .\scripts\start-mock-ui.ps1
```

脚本会检查依赖并输出实际预览地址。默认前端端口 1420、假 API 端口 8766；占用时可能选择其他端口。以启动输出为准。

如果已有开发服务运行，直接打开它的地址，修改 TSX/CSS 后 Vite 会热更新；无需每次打包。弹窗草稿或页面状态在组件结构变化后可能需要重新打开。

连接正式数据并启动桌面开发环境使用 `scripts/start-dev.ps1`。只调样式时优先假数据环境；实际后端中的保存、生成、删除都会产生真实操作。

`/dev/ui` 和 `/` 当前进入同一套 App，不是旧版“故事板 / 生产 / 素材”演示页面。

## 3. TSX 就是带表达式的页面结构

`frontend/index.html` 只有挂载入口，实际页面在 `.tsx` 文件中。可以先只看组件的 `return (...)`，把它当 HTML 阅读。

| HTML 写法 | TSX 写法 | 说明 |
| --- | --- | --- |
| `class="task-list-row"` | `className="task-list-row"` | CSS 仍使用 `.task-list-row` |
| `for="title"` | `htmlFor="title"` | label 关联输入框 |
| 内联字符串样式 | `style={{ gap: 12, minWidth: 0 }}` | 属性为驼峰；通常优先改 CSS |
| 文本插值 | `{task.title}` | 显示当前数据 |
| 条件内容 | `{open && <div>内容</div>}` | 条件成立才渲染 |
| 重复列表 | `{tasks.map(task => <div key={task.id}>...</div>)}` | 每项要有稳定 key |
| 自定义标签 | `<Button>保存</Button>` | 是组件，其真实 DOM 由组件文件负责 |

示例，仅说明写法，不是让你替换当前任务列表：

```tsx
<section className="task-summary">
  <h2>{task.title}</h2>
  <span className="task-summary-note">{task.summary}</span>
</section>
```

```css
.task-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.task-summary-note { color: var(--sm-text-muted); }
```

调整布局一般不需要改 `useState`、`useEffect`、Gateway 或数据类型。保留事件处理器、`aria-*`、`role`、`data-testid`、`key`，避免外观微调影响交互和测试。

## 4. 页面从哪里开始

```text
index.html
└─ src/main.tsx：加载样式、初始化主题、挂载 React
   └─ src/App.tsx：获取数据、切换首页/工作台、连接保存操作
      ├─ ProjectHome.tsx：项目首页 + 新建项目弹窗
      ├─ ProjectWorkspace.tsx：列表/卡片 + 只读详情 + 各业务弹窗
      │  ├─ TaskEditorDialog.tsx
      │  ├─ ProjectConfigPanel.tsx
      │  └─ TaskResultPlayer.tsx
      └─ GlobalStatusbar.tsx：底部状态、设置、运行中心
```

`features/storyboard/` 这个目录名仍保留，但当前主要是任务编辑器、素材槽位和任务辅助逻辑，并不表示还存在独立故事板页面。

弹窗通过 Portal 挂载，实际 DOM 不一定在你看到的业务父元素内部。不要靠 `.project-workspace-page .sm-dialog` 这样的祖先选择器控制弹窗；使用弹窗自身类名或已有的 `:has(.simple-task-editor)` 等作用域。

## 5. CSS 怎么找，怎样避免改了没效果

1. 在浏览器开发者工具中选中目标元素。
2. 查看 Styles / Computed，找到最终生效的属性和来源文件。
3. 在编辑器全局搜索该 `className` 或 CSS 类名。
4. 修改现有规则；不要在文件末尾反复追加同一选择器“压过去”。
5. 同时检查亮/暗主题和窄窗口。

全局 CSS 的加载顺序以 `src/main.tsx` 为准，只有这一条全局入口。不要另往 `index.html` 加同一份 CSS 的 `<link>`。组件同目录 CSS 由对应组件 import。

### 任务编辑器样式顺序

这些文件仍有实际作用，版本号不代表废弃。相同优先级下，后加载规则覆盖前面的规则：

| 顺序 | 文件（`src/styles/`） | 主要职责 |
| --- | --- | --- |
| 1 | `simple-editor.css` | 编辑窗框架、上方提示词区、下方折叠参数区、底部操作 |
| 2 | `task-editor-polish.css` | 标题、底部操作、提示词来源状态 |
| 3 | `v0.6-project-prompt.css` | H3 标签、视频播放器、任务导航确认 |
| 4 | `v0.7-controls-polish.css` | 承接时间轴及区间控件宿主 |
| 5 | `v0.8-ai-enhance.css` | AI 历史、空状态、增强操作区 |
| 6 | `v0.9-flex-layout-fixes.css` | 提示词区的弹性尺寸、素材菜单图片 |
| 7 | `v0.9-compact-density.css` | 紧凑弹窗尺寸、提示词区间距 |
| 8 | `task-editor-feedback.css` | 当前提示词标题与 AI 空状态的最终布局 |
| 9 | `batch-review.css` | 批量弹窗、任务前后导航等 |

目前这部分还保留分层覆盖，不能假定只改 `simple-editor.css` 就一定生效。修改前用 Computed 确认最终来源。本次没有为了清理文件名而改变这些仍生效的规则顺序。

### 常用工作台选择器

在 `project-workspace.css` 中直接搜索：

| 区域 | 选择器 |
| --- | --- |
| 顶栏 | `.project-workspace-topbar` |
| 左右区域分配 | `.project-workspace-body` |
| 任务主区 | `.project-task-column`、`.project-task-area` |
| 列表行 | `.task-list-row`、`.task-list-copy`、`.task-list-params` |
| 卡片网格 | `.task-card-view`、`.task-card-item` |
| 任务缩略图 | `.task-preview` |
| 右侧详情 | `.project-task-info`、`.project-info-block` |
| 底栏 | `.project-workspace-statusbar` |
| 首页文件夹 | `.project-folder-grid`、`.project-folder-card`、`.project-folder-front` |

例如要让任务行更紧凑，先改现有 `.task-list-row` 的 `padding`、`gap` 和相关预览尺寸，不要先缩小所有文字。

## 6. 主题：五个输入颜色，派生全站颜色

`ui/theme.ts` 保存默认值、读取本地配色并把颜色写到 `<html style="...">`。`styles/tokens.css` 负责从这些颜色派生页面背景、文字、边框和阴影。

| 基础变量 | 作用 |
| --- | --- |
| `--tc-base` | 底色 |
| `--tc-accent` | 强调色、主操作、选中态 |
| `--tc-effect` | 焦点和有限高光 |
| `--tc-text-main` | 普通文字 |
| `--tc-text-bright` | 高亮文字 |

业务 CSS 优先用 `--sm-bg`、`--sm-surface-1/2/3`、`--sm-text`、`--sm-text-muted`、`--sm-border`、`--sm-accent`、`--sm-radius` 等语义变量。

当前用户确认的亮色计算是：

```css
--sm-bg: color-mix(in srgb, var(--tc-base) 16%, white);
--sm-surface-base-weight: 12%;
--sm-surface-mix: white;
```

也就是背景为 **16% 底色 + 84% 白色**；面板继续保持原有混白层次。暗色背景直接用底色。

想调整亮色底色的影响强度，改 `tokens.css` 中亮色块的 `16%`。想改默认颜色，同时检查 `ui/theme.ts` 的 `paletteDefaults` 和 `tokens.css` 默认值。

如果修改默认色后没变化，检查设置里是否保存过自定义配色。它以 inline CSS variable 覆盖样式表默认值，亮暗分别保存在 `shotmill.palette.light` / `shotmill.palette.dark`。在“设置 → 外观”点击“恢复当前模式默认配色”即可恢复当前模式默认值。

## 7. 基础控件与布局边界

当前实际运行的是仓库内 `ui/primitives/` 和 `ui/` 的本地控件。`tc-` 前缀是保留的命名，不意味着仍从外部 UI 包加载。旧 `vendor/*.tgz` 已移除；不要改 `node_modules`。

- 调整所有按钮的圆角、高度、内部间距：找 `ui/primitives/styles/button.css`。
- 调整按钮在某一行的位置：改业务容器的 Flex/Grid。
- 调整下拉框的内部外观：找 `ui/Select.css`。
- 用户/AI、可视化/文本是 `SegmentedControl`；密集参数切换使用 `SlidingTabs`。
- 业务 CSS 不应穿透 `.tc-*` 内部结构。控件内部样式回控件自己的文件修改。

优先使用 `display: flex/grid`、`min-width: 0`、`min-height: 0`、`minmax(0, 1fr)`。同一行控件用 `align-items: center`，不要用负 margin 或 translate 补位置。

任务缩略图用 `cover`，完整图片和视频播放器保留原比例。窗口变小时先让现有布局收缩，不用页面整体滚动掩盖溢出；长任务列表、长参数或长文本本身可以有业务需要的局部滚动。

## 8. 验证与截图

项目根目录，推荐使用项目已有 Python 环境：

```powershell
.\.venv\Scripts\python.exe scripts/verify.py --area frontend
```

验证类型检查、单元测试和构建。文件引用审计：

```powershell
Set-Location frontend
node scripts/audit-source-files.mjs
```

审计从正式入口、单元测试、测试 setup 和类型声明出发，检查静态文件引用。它不会因为测试数据不在生产入口里就误删测试数据，也不证明每个导出或每条 CSS 选择器都用到了。未来引入非字面量动态加载时，需要补充入口识别。

涉及交互或大范围样式清理，从项目根目录运行隔离的端到端验证：

```powershell
.\.venv\Scripts\python.exe scripts/run_e2e.py e2e/app-shell.spec.ts e2e/workspace-controls.spec.ts --project desktop
.\.venv\Scripts\python.exe scripts/run_e2e.py --project mobile
```

该脚本启动独立测试后端和临时数据库，不需要在真实项目上测试生成/删除操作。

已有前端服务时，可以生成当前界面的亮暗截图：

```powershell
Set-Location frontend
$env:SHOTMILL_UI_URL = 'http://127.0.0.1:1420'
node scripts/capture-dev-ui.mjs
```

输出在项目根目录 `.artifacts/ui-current/`。有项目时会打开第一个项目并捕获工作台，有任务时再捕获编辑窗；不会保存草稿或提交生成。首页与外观设置始终截图。实际需要后端可连接，空项目不会生成任务截图。

手工检查建议覆盖 1440×960、1366×768、窄窗口；观察有无截断、层级错乱、弹窗尺寸跳动、菜单被裁切、输入内容丢失。改主题时同时检查设置页、列表、卡片、任务编辑窗和下拉菜单。

## 9. 本次清理范围

- 移除未接入当前入口的旧 TaskComposer、独立故事板、素材库/素材选择弹窗、结果审核工作台、StoryReel、剧本拆任务页面及其专属实现和测试。
- 从旧工作台提取当前首页和新建项目弹窗；保留唯一正式工作台。
- 移除旧 MockStoryboardRepository、旧场景生成器、旧卡片类型。
- 移除旧 `app.css`、`storyboard.css`、`director.css`、`director-dialogs.css`；从旧 `composer.css` 提取仍用到的素材引用菜单样式。
- 移除无调用的 StatusPill、旧全屏预览、旧浮层 Tooltip、PortalSelect 兼容包装；浮层回归测试直接验证当前 Select。
- 移除未被依赖声明或安装脚本引用的 UI 包归档和补丁；更新截图脚本，移除绑定旧演示数据的临时响应式截图脚本。
- 正式项目视图类型移到 `features/projects/projectTypes.ts`，不再放在 mock 文件中。

`mock/`、`mockProjectGateway.ts`、`storyboardExecution.ts` 等仍被有效单元测试引用的辅助实现保留。不要把“生产页面不引用”直接等同于“整个工程未引用”。后端领域、任务历史、资产文件和项目数据不在本次清理范围内。

本次通过项及完整 E2E 尚未通过的项目见 [清理验证记录](FRONTEND_CLEANUP_VERIFICATION.md)。

更完整的产品约束仍见 [UI 开发规则](UI_DEVELOPMENT_RULES.md) 与 [UI/UX 规范](UI_UX_SPEC.md)。本指南描述当前代码怎么修改，不恢复历史文档中的旧页面。
