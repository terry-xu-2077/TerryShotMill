# ShotMill UI / UX 开发规范

> 2026-09-22 产品规则更新：提示词增强和审核均为可选操作，适用于用户界面、Agent、单任务和批量生成。未经增强、未经审核或审核过期不得阻断生成；仅执行校验失败或活动视频任务重复提交可阻断。以下旧版强制审核流程已由此规则覆盖，审核记录及其失效逻辑继续保留。

> 状态：产品规划 / UI 开发基线  
> 最后更新：2026-09-20
> 适用范围：Desktop UI、Mobile Remote Monitor、`/dev/ui` 开发模式页面  
> 默认 UI 库：https://github.com/terry-xu-2077/Terry_React_UI_Library

本文档不是一份单纯的视觉风格说明，而是 **ShotMill 前端实现、交互行为、UI 回归和 Codex 验收的开发协议**。

目标是尽可能在第一版开发前就统一交互规律，避免应用完成后出现大量“每个地方都有一点不顺手、需要逐项描述和返工”的问题。

ShotMill 的 UI 开发采用以下原则：

> **先把交互手感做对，再接真实后端。**

用户应能够在完全不连接真实生成后端的开发模式页面中，反复打磨布局、交互、状态反馈和操作节奏；业务逻辑、Provider、数据库、Scheduler 等不可见部分则由自动测试和 Codex 闭环开发。

---

## 当前视觉增量（2026-09-20）

用户补充的三张参考图确定当前视觉方向：圆角、渐变、半透明、局部发光，并支持亮暗主题。该方向覆盖旧文档中仅采用平面中性色的视觉建议，不改变项目首页、任务工作台和编辑弹窗的结构，也不添加无业务功能的仪表盘内容。

- 最新按钮、图标参考采用文件管理界面的中性灰底、简洁线条图标与蓝色主操作。亮色使用柔白中性表面，暗色使用炭灰表面；不再沿用青绿描边与强发光按钮。
- 首页项目采用电影文件夹造型，缩略图作为露出的内页，前景优先显示项目名称和任务/资产数量；任务卡优先展示媒体。参考图的项目区和任务区分别应用于首页和工作台，不合并为新的仪表盘。
- 主题切换固定在首页和工作台顶栏最右侧，设置“外观”保留入口；作为本机显示偏好立即生效并保存，不属于生成配置。切换不丢失编辑草稿。
- 项目配置按钮放在“返回首页”右侧，项目名仅展示，不提供点击逻辑；改名统一在项目配置中完成。
- 表格/卡片采用任务区域内的单图标按钮，点击时图标旋转、缩放并淡入切换，不使用双项胶囊标签。保留可访问名称和悬停名称，切换保留当前任务和批量选择。
- 操作按钮统一为完整胶囊圆角，通过 UI 库公开的 `--tc-button-radius` 配置；普通卡片和弹窗圆角扩大至 16px。滚动条采用主题派生色，只保留长列表、长文本等必要局部滚动。
- 任务区域提供“生成当前任务”和“队列生成”；前者只处理当前任务，后者在多选时处理选中任务，否则处理整个项目，均通过后端生成资格检查和正式队列提交。确认时仅提交预览中通过检查的任务，不绕过审核；错误在确认窗中显示。
- 生成参数保持默认折叠，展开后保留三个紧凑圆角底色分组：工作流下拉菜单和秒数滑块左右同行；生成模式、上下文承接改用圆角胶囊 SegmentedControl。移除承接详情的空白预留高度，按实际内容分配空间，编辑窗外框与底部按钮位置稳定。
- “生成参数”分组只保留已配置工作流下拉菜单和总秒数滑块，移除分辨率、质量标签。工作流选择保存稳定配置 ID；停用或删除后不得静默回退到另一工作流。总秒数目前保存为任务意图并传给 Bridge，不代表任意工作流已实现时长控制；数值端口绑定及秒数/帧数换算仍需单独实现。
- 使用 UI 库公开的主题容器和模式属性，浮层继承同一主题；禁止业务样式修补共享控件内部结构。
- 已通过用户补充的录屏确认动效参考：面板错峰进入，面板内部数字、条形和圆环随后逐步呈现。产品只借鉴节奏，不复制无关图表或伪造任务进度。
- 项目卡和任务项采用 35ms 间隔的错峰入场，延迟上限 210ms，单项动画 380ms；常规状态刷新、选择和主题切换不重播。参数展开只过渡内容，外框与底部操作区不移动。
- 弹窗进入和退出、参数展开和收起均有过渡；退出期间内容保留但不接收交互，结束后卸载。遵循系统减少动态效果设置（同时清除延迟），不阻塞键盘操作。
- 回归覆盖亮暗两套主题的 1440、1366、390 像素宽度，以及主题持久化、设置草稿保留和减少动效。

---

## 1. 最终产品体验目标

ShotMill 的最终体验不是传统 AI 工具的“参数控制台”，也不是 ComfyUI 的另一层包装。

它应该更接近一个高效、安静、可靠的 **素材生产工作台**：

```text
准备剧本
  ↓
快速创建一批 Task
  ↓
选择 / 继承资产
  ↓
AI 编写 Prompt
  ↓
快速确认
  ↓
全部 Ready
  ↓
一次批量生成
  ↓
离开电脑
  ↓
回来审核结果
  ↓
通过 / 局部返工
```

UI 的首要目标不是展示“功能很多”，而是让这条主流程连续、自然、少打断。

### 1.1 希望呈现的整体气质

- 现代，但不过度装饰。
- 有专业创作工具的秩序感，而不是电商后台感。
- 中性色、低饱和度为主。
- 高饱和颜色只用于：状态、选中、警告、错误、关键操作。
- 禁止泛滥使用“AI 紫蓝渐变”、霓虹描边、过多玻璃拟态。
- 画面、缩略图、视频预览是视觉中心，UI 装饰必须让位于内容。
- 卡片式 UI 主要用于 Task、Asset、Result 等天然“对象型信息”；高密度信息区域允许使用列表、表格、紧凑行布局。
- UI 应有适度留白，但不能为了“高级感”牺牲信息密度。
- 重要操作明显，次要操作克制，低频设置不抢占主界面空间。

### 1.2 “手感”目标

用户连续创建几十个任务时，应产生这样的感觉：

- 我知道下一步在哪里。
- 我不需要反复打开设置页。
- 我不会因为后台刷新而丢失正在输入的内容。
- 我不会因为一个菜单或弹窗被遮挡而中断工作。
- 我不需要猜“单击、双击、右键到底哪个有效”。
- 相同控件在不同页面表现一致。
- 系统状态变化明确，但不会不断弹窗打扰。
- 大部分操作都可以顺着当前视线和鼠标位置完成。

---

## 2. UI 开发方式：先开发模式，后真实业务

### 2.1 `/dev/ui` 是正式开发工具，不是临时 Demo

ShotMill 必须提供独立的 UI Development Mode，例如：

```text
/dev/ui
```

该页面：

- 不连接真实 Prompt Provider。
- 不连接真实 Video Provider。
- 不依赖 ComfyUI。
- 不需要真实项目数据库。
- 使用固定 Mock 数据和可切换场景。
- 可以模拟所有重要 UI 状态。
- 可以修改组件和交互后立即看到效果。

目标是让 UI / UX 调整与后端开发解耦。

### 2.2 推荐开发顺序

```text
UI_UX_SPEC
   ↓
/dev/ui 静态与 Mock 状态
   ↓
人工反复打磨视觉与交互手感
   ↓
冻结基础交互协议
   ↓
Playwright 行为测试 + Visual Regression
   ↓
接入真实 API / WebSocket
   ↓
后端状态替换 Mock 状态
```

严禁在基础交互尚未稳定时就把大量真实业务逻辑绑死在组件内部。

### 2.3 `/dev/ui` 必须覆盖的对象

至少展示：

```text
TaskCard
AssetCard
ResultCard
QueueItem
ContextLink
StatusPill
Progress
Dropdown / Select
Popover
Context Menu
Dialog
Toast
Tabs
Text Input
Multiline Prompt Editor
Asset Picker
Media Preview
Empty State
Loading State
Error State
Mobile Monitor Cards
```

每个对象必须同时展示多种状态，而不是只展示“正常态”。

例如 TaskCard：

```text
Draft
Prompt Generating
Prompt Ready
Ready
Queued
Running 0%
Running 43%
Running 99%
Completed
Failed
Cancelled
Blocked by upstream
Context Stale
Selected
Multi-selected
Disabled
Long title
Missing thumbnail
Many assets
No assets
```

### 2.4 开发模式页面要有状态控制器

推荐 `/dev/ui` 页面带一个固定或可折叠的 Scenario Panel，可切换：

- Desktop / Mobile viewport。
- Light / Dark（如果后续支持）。
- Task 数量。
- 网络在线 / 离线。
- Provider 在线 / 断开。
- Queue 空 / 满载。
- Running 状态。
- Error 状态。
- 超长文本。
- 小窗口。
- 高 DPI / 常见缩放场景。

这样 UI 问题应尽量在接真实后端之前暴露。

---

## 3. Terry React UI Library 使用原则

ShotMill 默认使用：

https://github.com/terry-xu-2077/Terry_React_UI_Library

### 3.1 基本规则

- 已有控件优先直接复用。
- 不为 ShotMill 重写一套已有基础组件。
- 如果出现通用 UI 需求，优先新增到 Terry React UI Library。
- 新增组件必须保持向后兼容。
- 不允许修改现有组件导出路径。
- 不允许移动现有公共组件目录导致 RulesMD Editor 失效。
- 不允许为了 ShotMill 私自改变旧组件 public props 语义。

### 3.2 什么进入共享 UI 库

适合进入 Terry React UI Library：

- Button
- Dialog
- Select / MultiSelect
- Dropdown / Popover
- Tooltip
- ProgressBar / ProgressRing
- Tabs
- Toast
- SegmentedControl
- EmptyState
- StatusPill
- 通用 Media Preview
- 通用 Overlay / Portal 基础设施
- 通用 Virtual List / Scroll Container（如需要）

### 3.3 什么只留在 ShotMill

包含业务语义的组件：

- TaskCard
- TaskComposer
- TaskChainView
- ContextLink
- AssetCard
- AssetPicker 的 ShotMill 业务层
- QueueMonitor
- GenerationResultCard
- ProviderSettings
- ProductionMonitor
- MobileMonitor

原则：

> **共享库负责积木，ShotMill 负责产品结构。**

---

## 4. 全局交互不变量（UI Invariants）

以下规则应当视为强约束，并尽量通过自动测试验证。

### UI-INV-001：Overlay 永远不能被业务容器裁切

任何：

- Dialog
- Dropdown
- Select Menu
- Context Menu
- Popover
- Tooltip
- Asset Picker Overlay
- Fullscreen Media Preview

不得被以下结构裁切：

- `overflow: hidden`
- 表格 / 列表容器
- Scroll Container
- transformed ancestor
- 局部 stacking context

全局浮层必须使用统一 Portal / Overlay Root。

### UI-INV-002：菜单必须自动适应可用空间

默认行为：

```text
优先向下展开
   ↓
下方空间不足
   ↓
自动向上展开
   ↓
上下都不足
   ↓
限制最大高度 + 菜单内部滚动
```

菜单不得因方向改变而出现选项被遮挡。

### UI-INV-003：后台刷新不得破坏用户输入

WebSocket / SSE 更新时：

- 不得重置当前输入框内容。
- 不得抢走焦点。
- 不得把用户正在编辑的 Prompt 替换成服务端旧值。
- 不得因为 Task 状态变化导致编辑器重新 mount。

### UI-INV-004：异步操作必须有完整状态

每个异步操作至少考虑：

```text
Idle
Loading
Success
Failure
Retryable Failure
Disabled / Unavailable
```

不得只实现“成功路径”。

### UI-INV-005：重要功能不能只藏在右键菜单里

右键可以作为快捷入口，但：

- 高频功能必须有显式按钮或可见入口。
- 用户不应依赖“知道这里可以右键”才能完成主流程。

### UI-INV-006：状态变化不应造成明显布局跳动

例如 Task 从 Ready → Running：

- 卡片宽高尽量保持稳定。
- 状态标签变化不能推挤主要内容大幅移动。
- 进度条出现时预留合理空间或使用稳定布局。

### UI-INV-007：危险操作与普通操作必须视觉分级

删除项目、删除结果、清空队列等不能与“保存”“生成”“通过”使用相同视觉权重。

### UI-INV-008：批量选择必须始终明确显示选择数量

例如：

```text
已选择 18 个任务
```

进入多选模式后，应出现稳定的批量操作区域。

### UI-INV-009：移动端不得出现页面级横向滚动

媒体内容允许自身缩放 / 横向展示，但页面根节点禁止因为某个组件超宽产生整体横向滚动。

### UI-INV-010：Empty / Loading / Error 不得混为一种状态

空数据、加载中、加载失败必须有不同表现和下一步操作。

### UI-INV-011：文本不可因容器过窄而破坏布局

长 Task 名、长模型名、长 Provider 名、文件名等：

- 可省略号。
- 必须有 Tooltip / 完整查看方式。
- 不允许把整个卡片或表格列撑爆。

### UI-INV-012：用户操作优先于后台自动行为

例如用户正在编辑 Task：

- 后台 Result 完成可以更新状态提示。
- 不能自动跳页。
- 不能自动关闭 Dialog。
- 不能自动切换当前 Task。

---

## 5. 单击、双击、右键与键盘规则

除非页面专门覆盖，否则采用以下统一语义。

### 5.1 单击

单击主要用于：

- 选择。
- 切换当前对象。
- 激活按钮 / 控件。

单击 Task Card 空白区域：

- 选中该 Task。
- 更新 Inspector / 详情区域。
- 不直接进入完整编辑页。

### 5.2 双击

双击对象型卡片默认表示：

- 进入该对象的主编辑 / 详情界面。

例如：

```text
双击 Task Card → Task Composer
双击 Asset Card → Asset Detail / Preview
双击 Result → 大预览
```

如果未来测试发现双击不适合某对象，可在该页面规范中覆盖。

### 5.3 右键

右键提供增强快捷操作：

- 复制。
- 重命名。
- 打开文件位置。
- 复制任务。
- 删除。
- 设为 Primary Result。

但不得承载唯一主路径。

### 5.4 Esc

统一优先级：

```text
关闭最上层临时 Overlay
  ↓
关闭 Popover / Menu
  ↓
关闭可取消 Dialog
  ↓
退出临时多选 / 临时模式
```

不得因按一次 Esc 同时关闭多层 UI。

### 5.5 Enter

- 单行输入：按具体表单语义提交或确认。
- Prompt / Script 多行编辑器：默认换行，不提交。
- Dialog 主按钮是否响应 Enter 必须明确，不默认猜测。

---

## 6. Navigation 与历史行为

### 6.1 首页

打开一个项目后默认进入：

> **任务生产区**

不进入传统 Dashboard。

一级导航：

```text
任务
资产
生产状态
结果
项目设置
```

### 6.2 页面切换原则

- 尽量保持用户之前的筛选、滚动位置、选中对象。
- 返回上一级时恢复之前上下文。
- 主导航切换不应清空用户没有明确要求清空的筛选条件。

### 6.3 深层跳转

从 Result → Task、Queue → Task、Context → Upstream Task 的跳转：

- 不应丢掉原页面上下文。
- 应提供清晰返回路径。
- 避免打开大量无意义新窗口。

---

## 7. Task Workspace

Task Workspace 是应用使用频率最高的页面。

设计目标：

> **大量任务仍然保持清楚、可扫视、可批量处理。**

V0.2 将该页面升级为 Storyboard-style Task Workspace。“Storyboard”描述画面化、按故事顺序排列的交互方式；其中每张卡片仍然是一个 `GenerationTask`，一张卡可以在 Task 内表达一个或多个镜头 / 视觉节拍。不得另画一套 Shot Cards 与 Task Bands 争夺主层级。

Scene Section 用于组织 Task Cards；单击卡片更新 Task Inspector，双击进入 Task Composer。卡片重排调整 Story Order，但不得静默改变 Task Context、Job 或 Result。

### 7.1 Task Card 内容优先级

建议视觉层级：

1. 参考画面 / 最新 Result Preview。
2. Task 编号。
3. 一行简短描述。
4. 状态。
5. 关键生成信息。
6. 资产摘要。
7. 次要信息。

不得把模型参数、技术字段塞满卡片。

### 7.2 Task Card 状态

至少支持：

```text
Draft
Prompt Generating
Prompt Ready
Ready
Queued
Running
Completed
Failed
Cancelled
Blocked
Context Stale
```

### 7.3 多选

- Ctrl / Cmd + Click：切换单个对象。
- Shift + Click：连续范围选择。
- 多选后出现固定 Batch Action Bar。
- 清楚显示数量。

批量操作包括：

- 生成 Prompt。
- 加入队列。
- 修改 Generation Profile。
- 设置公共参数。
- 删除。

### 7.4 新建任务节奏

高频入口应始终容易找到：

```text
+ 新建任务
+ 新建下一个任务
复制上一任务
```

创建下一任务时默认可继承：

- 项目默认 Generation Profile。
- 上一个 Task 的常用参数。
- 可选的角色 / 场景资产。
- Task Chain 关系。

继承发生时必须在 UI 中可见，不能“偷偷继承”。

---

## 8. Task Composer

Task Composer 是最核心的创作界面之一。

推荐三栏结构：

```text
┌──────────────┬────────────────────────┬──────────────┐
│ 剧本 / 设置   │       Prompt           │   项目资产    │
│              │                        │              │
│ 原始剧本      │ AI Prompt              │ Character    │
│ 创作意图      │ Final Prompt           │ Scene        │
│ 生成配置      │ Validator              │ Video        │
│ Context      │ Revision               │ Audio        │
└──────────────┴────────────────────────┴──────────────┘
```

### 8.1 原始剧本、AI Prompt、Final Prompt 必须视觉分离

用户必须一眼知道当前正在编辑哪一层。

不能把三者混成同一个文本框。

### 8.2 AI 改写不得覆盖人工修改

若 `Final Prompt` 已人工修改：

- 再次生成 AI Prompt 时保留 Final Prompt。
- 提供显式“用新的 AI Prompt 替换 Final Prompt”。
- 不允许后台自动覆盖。

### 8.3 Validator

Validation 结果尽量就地显示：

```text
✓ 引用有效
✓ 时长有效
! 缺少 Audio Reference
× 上游 Context 不可用
```

避免把普通可修复错误全都做成 Modal。

### 8.4 保存方式

Task Composer 推荐：

- 普通字段自动保存草稿。
- 明确显示保存状态：`已保存 / 保存中 / 保存失败`。
- Final Prompt 重要替换操作需显式确认。
- 退出页面不应该因为后台自动保存延迟造成内容丢失。

---

## 9. Asset Library / Asset Picker

### 9.1 Asset Library

主要服务于：

- 找到项目素材。
- 浏览。
- 分类。
- 重命名 / 标注。
- 查看被哪些 Task 使用。

### 9.2 Asset Picker 手感

打开时：

- 默认保留当前 Task 已选资产。
- 优先显示当前相关分类。
- 搜索框焦点行为保持一致。

多选模式：

```text
单击 → 选择 / 取消
Confirm → 一次性提交
Esc / Cancel → 丢弃本次未确认修改
```

避免“点一个资产立即修改 Task，再取消时无法恢复”的交互。

### 9.3 缩略图

- 项目封面、任务卡片与列表缩略图默认等比例居中铺满（cover），允许裁切，不得留下适配产生的黑边或白边，不得拉伸变形。完整图片查看和视频播放保留原始比例。

- 图片直接显示。
- 视频显示 Poster + 视频标识。
- 音频显示统一音频视觉。
- 加载失败显示明确 Placeholder。
- 不允许坏图标破坏卡片布局。

---

## 10. Task Chain / Context UI

Task Chain 是生成依赖关系，不做成剪辑时间线。

UI 应强调：

```text
Task A
  ↓ Context
Task B
```

而不是轨道和剪辑概念。

Context Link 最少能表达：

- Semantic Context。
- Generation Context 类型。
- 是否可用。
- 是否降级。
- 是否 Stale。

例如：

```text
Visual + Audio + Semantic
Frame Continue + Semantic
Semantic only
Context Stale
```

高级 Provider Context 细节默认折叠，不污染普通用户主界面。

---

## 11. Queue / Production Monitor

Production Monitor 的目标是：

> 用户点“批量生成”之后可以放心离开。

核心摘要优先：

```text
52 Tasks
37 Completed
2 Running
11 Queued
2 Failed
```

页面重点：

- 当前正在跑什么。
- 哪些失败。
- 哪些等待上游。
- 队列剩余多少。
- 是否 Provider 离线。

不需要把底层日志默认铺满页面。

错误详情采用：

```text
简洁错误摘要
+ [查看详细日志]
```

---

## 12. Result Review

Result Review 应接近“审核墙”，而不是文件管理器。

### 12.1 核心动作

每个结果主要动作：

```text
✓ 通过
重新生成
编辑 Task
设为 Primary（适用时）
```

### 12.2 批量审核

需要支持快速连续审核，不要求进入每个 Task。

通过后可：

- 降低视觉权重。
- 从“待审核”筛选中移出。
- 保留可撤销 / 再查看入口。

### 12.3 Result 历史

Task 的旧 Result 不覆盖。

用户应能明确知道：

- 当前 Primary。
- 最新版本。
- 哪些已通过。
- 哪些失败 / 废弃。

---

## 13. Provider / Settings 页面

Provider 配置是低频操作，不应占据日常主界面。

设置页应区分：

```text
Prompt Providers
Video Generation Providers
Generation Profiles
Project Defaults
Skills
Remote Monitor
```

敏感字段：

- API Key 默认遮蔽。
- 提供测试连接。
- 保存时明确反馈。

技术参数可以放高级折叠区。

---

## 14. Overlay / Dialog / Popover 规范

吸收 RulesMD Editor 的长期交互经验，ShotMill 从第一天建立统一 Overlay System。

### 14.1 Portal

所有高层浮动 UI 默认通过统一 Portal Root 渲染到应用根层或 `document.body`。

### 14.2 Z-index

不允许业务组件自行随意写极大 z-index。

定义统一层级，例如：

```text
Base
Sticky
Popover
Dropdown
ContextMenu
DialogBackdrop
Dialog
Toast
FullscreenPreview
```

具体数值由 UI Library 统一维护。

### 14.3 Dialog

Dialog 必须考虑：

- 小窗口。
- 内容超高。
- 内容超宽。
- 内部滚动。
- Esc。
- 外部点击。
- 异步提交。
- 错误状态。

危险操作确认 Dialog 尽量短，不做复杂表单。

---

## 15. 响应式与窗口尺寸

桌面重点测试：

```text
1920 × 1080
1600 × 900
1366 × 768
```

不要求把桌面复杂工作区强行压成移动版，而应在较小窗口：

- 折叠 Inspector。
- 降低并列列数。
- 保证核心操作可达。

手机 Remote Monitor 独立响应式设计。

推荐测试：

```text
390 × 844
430 × 932
```

---

## 16. Mobile Remote Monitor

手机端不是桌面端缩小版。

第一阶段只承担：

- 查看总体进度。
- 查看当前 Running。
- 查看 Failed。
- 播放最新 Result。
- 标记通过。
- 重新排队明显失败项。

### 16.1 手机信息优先级

```text
总体进度
当前任务
异常
最新结果
```

Provider 高级设置、Prompt 编辑、复杂 Asset Picker 不进入第一版手机界面。

### 16.2 触控

- 点击区域不得过小。
- 不依赖 Hover。
- 不依赖右键。
- 视频播放控件要适合触控。

---

## 17. Motion / Animation

动画目标是帮助理解状态，不是展示视觉特效。

建议：

- 页面切换轻微。
- Menu / Popover 快速出现。
- Hover 克制。
- Running 状态可有非常轻的动态反馈。
- 不做持续吸引注意力的大面积流光。
- Loading 动效必须避免造成页面跳动。

系统允许尊重 `prefers-reduced-motion`。

---

## 18. Toast 与通知

Toast 只用于：

- 保存成功等短暂反馈。
- 操作完成。
- 非阻断性错误。

不要 Toast 滥用。

以下情况优先就地显示：

- 表单字段错误。
- Validator 错误。
- 某个 Task 的错误。
- Provider 某项配置问题。

批量生成期间不要每完成一个 Task 就弹 Toast。

---

## 19. Loading 与 Skeleton

应区分：

- 页面首次加载。
- 局部内容更新。
- 用户主动提交。
- 后台实时状态更新。

后台实时更新时不要反复出现全局 Loading。

视频 Poster / Thumbnail 可使用固定比例 Skeleton，避免加载完成后布局跳动。

---

## 20. 错误信息

用户层错误应描述：

1. 发生了什么。
2. 当前 Task / Job 是否安全。
3. 用户下一步能做什么。

例如：

```text
ComfyUI 已断开
当前生成任务已标记为“中断”，未完成的下游任务不会继续提交。
[重新连接] [查看详情]
```

不要直接用巨大 traceback 作为默认错误 UI。

详细日志单独展开。

---

## 21. UI 测试与 Visual Regression

UI 完成不能只依赖人工肉眼。

### 21.1 Functional E2E

使用 Playwright 验证：

- 选择。
- 多选。
- 打开 / 关闭 Dialog。
- Dropdown 方向。
- Asset Picker Confirm / Cancel。
- Task Composer 输入不丢失。
- Queue 状态变化。
- Result Approve。
- Mobile Monitor 基本流程。

### 21.2 Visual Regression

`/dev/ui` 的稳定状态作为 Screenshot Baseline。

至少覆盖：

```text
1920x1080
1600x900
1366x768
390x844
430x932
```

视觉回归用于发现：

- Card 尺寸异常。
- Overlay 被截断。
- 状态变化导致布局偏移。
- Mobile Overflow。
- CSS 修改误伤其他组件。

### 21.3 不追求像素绝对静止

对视频、时间戳、动态进度等区域使用稳定 Mock 或屏蔽动态差异。

Visual Regression 目标是发现真正的布局和视觉退化，而不是制造大量无意义噪音。

---

## 22. UI Bug 修复规则

任何稳定可复现的 UI Bug，修复时尽量留下自动回归。

例如：

```text
Bug：Dropdown 在窗口底部向上展开时顶部选项被裁切

修复：
1. /dev/ui 增加 Bottom Edge Dropdown Case
2. Playwright 打开菜单
3. 验证所有菜单项位于 viewport 内
4. 加入截图 baseline
5. 修改 Overlay System
6. 回归通过
```

以后不会再依赖人工记忆“这个问题以前修过”。

---

## 23. UI 代码组织原则

避免重复 RulesMD Editor 后期出现的大型单文件不断膨胀问题。

ShotMill 从第一版开始优先：

```text
features/
  tasks/
  assets/
  queue/
  results/
  providers/
  remote-monitor/

components/
  business components

ui/
  ShotMill adapters around Terry UI Library
```

一个页面组件不应长期同时承担：

- 数据请求。
- 状态机。
- 巨大 JSX。
- Overlay 逻辑。
- 复杂表单。
- CSS 细节。

当组件已经出现明显多职责时及时拆分，而不是等几千行后再处理。

---

## 24. CSS 原则

- 共享视觉变量优先进入 Terry React UI Library。
- ShotMill 业务 CSS 不深入依赖共享组件的内部 DOM 结构。
- 避免大量 `!important` 补丁。
- 避免连续增加 `xxx-fix.css`、`xxx-polish.css` 作为长期结构。
- 如果同一种视觉问题在多个页面出现，应回到基础组件 / Design Token 修复。

### 24.1 Design Tokens

至少统一：

```text
spacing
radius
font size
line height
surface levels
border
shadow
status colors
overlay levels
transition duration
```

不在业务组件中散落大量近似数值。

---

## 25. Codex UI 开发要求

未来根目录 `AGENTS.md` 应加入类似规则：

```text
UI changes must follow docs/UI_UX_SPEC.md.

Before connecting a new major UI feature to the real backend:
1. Add it to /dev/ui with representative states.
2. Implement the intended interaction using mock data.
3. Add targeted Playwright interaction tests.
4. Add or update visual-regression coverage when layout is affected.
5. Reuse Terry React UI Library components when available.
6. Do not introduce a second local implementation of an existing shared primitive.
```

### 25.1 Token 成本控制

Codex 修改 UI 时：

- 先定位 owning feature。
- 不扫描无关后端目录。
- 优先运行相关 UI test，而不是每次跑全套。
- 通过 `/dev/ui` 直接复现视觉状态，不构造真实业务数据。
- 只有目标完成前再运行 full verification。

这既提升速度，也减少重复上下文读取和 Token 浪费。

---

## 26. UI 阶段验收方式

ShotMill 的 UI 开发应分为三个验收层：

### A. 手感验收

由用户在 `/dev/ui` 和 Mock 主页面中反复体验：

- 是否顺手。
- 信息密度是否合适。
- 哪些按钮位置不自然。
- 多选是否舒服。
- Prompt 编辑是否顺畅。
- Asset Picker 是否高效。
- Result Review 是否能快速扫完。

这一阶段不依赖真实后端。

### B. 自动交互验收

Codex / Playwright 保证：

- 已确认的行为不回退。
- Overlay 不被裁切。
- 输入内容不丢失。
- 状态变化正确。

### C. 后端集成验收

真实 API 接入后只验证：

> Mock 状态是否被真实状态正确替换。

不应在这一阶段重新设计基础 UI 手感。

---

## 27. 第一阶段 UI 开发优先级

建议 UI 第一轮按以下顺序打磨：

```text
1. App Shell / Navigation
2. Task Workspace
3. Task Card 全状态
4. Task Composer
5. Asset Picker
6. Overlay / Dropdown / Dialog 基础设施
7. Task Chain / Context
8. Queue / Production Monitor
9. Result Review
10. Provider Settings
11. Mobile Remote Monitor
```

其中前 6 项应在大量后端业务接入前尽量稳定。

---

## 28. 从 RulesMD Editor 吸收的原则

RulesMD Editor 经过长期反复打磨后已经证明：大量真实 UI 问题往往来自非常细的交互边界，例如菜单展开方向、弹窗层级、导航历史、筛选状态、组件尺寸、编辑状态保留等。

ShotMill 不复制 RulesMD Editor 的业务 UI，但吸收其开发经验：

- Overlay / Dialog 从第一天统一。
- 高频操作不能依赖隐藏入口。
- 导航历史和用户当前上下文要稳定。
- 菜单必须考虑窗口边缘。
- 真实数据接入前先用 Mock 把交互做顺。
- 已修过的 UI Bug 尽量转为自动回归。
- 通用修复优先沉淀到 Terry React UI Library，而不是在每个项目重复打补丁。

---

## 29. 核心 UI 原则总结

当前可执行质量底线和真实体验验收记录见 [UI/UX 验收底线](./UX_ACCEPTANCE_BASELINE.md)。可访问性标准与产品风格必须区分，未完成核验的条目不得宣称合规。

1. **UI 先于真实后端打磨。**
2. **`/dev/ui` 是长期保留的交互实验场。**
3. **用户主要负责判断“手感”，Codex 负责让行为稳定可回归。**
4. **共享 UI 由 Terry React UI Library 统一。**
5. **ShotMill 不重复实现已有基础控件。**
6. **卡片服务对象，列表 / 表格服务高密度信息。**
7. **媒体内容优先，装饰退后。**
8. **低饱和、中性、克制，状态色才高亮。**
9. **重要操作可见，右键只是增强。**
10. **Overlay / Dropdown 永不被业务容器裁切。**
11. **后台状态更新永不破坏用户当前输入和焦点。**
12. **所有重要 UI 状态都必须在开发模式中可模拟。**
13. **UI 功能测试与视觉回归同时存在。**
14. **UI Bug 修复尽量留下永久回归测试。**
15. **真实后端接入阶段不再重新发明基础交互。**

最终希望达到的开发分工是：

```text
用户
负责：视觉判断、操作手感、创作流程体验

/dev/ui
负责：快速暴露和调整所有可见状态

Codex
负责：实现、自动测试、回归、修复、真实后端集成

TEST_STRATEGY + UI_UX_SPEC
负责：让已经确认的体验长期稳定
```

这套机制的目标不是完全消除 UI 调整，而是把 UI 调整从“应用做完以后几十个问题同时爆发”，变成“在专门的可视化实验场中逐步、集中、可回归地打磨”。
