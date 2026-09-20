# ShotMill 开发导航

ShotMill 是面向 AI 视频生产流程的素材生成平台，不是剪辑器或 ComfyUI 外壳。Core 仍以 Generation Task、Job、Result、Asset、Context 等领域对象组织能力，但当前默认产品 UI 已收敛为“项目首页 → 项目工作台 → 任务编辑弹窗”。

## 当前优先文档

- **当前主开发任务：`docs/V0.4_BATCH_PRODUCTION_PIPELINE.md`**
- **当前批量审核 UI：`docs/UI_V0.9_BATCH_REVIEW_WORKFLOW.md`**
- **UI 实现红线：`docs/UI_DEVELOPMENT_RULES.md`**
- 已完成后端基础：`docs/V0.3_BACKEND_FOUNDATION_DEVELOPMENT_TASKS.md`
- **AI 提示词增强专项架构：`docs/AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md`**
- AI 增强 UI 基线：`docs/UI_V0.8_AI_PROMPT_ENHANCEMENT.md`
- AI 增强 V0.8 后端迁移：`docs/V0.8_BACKEND_AI_PROMPT_ENHANCEMENT.md`
- 项目配置 / H3 Prompt 基线：`docs/UI_V0.6_PROJECT_CONFIG_H3_EDITOR.md`
- V0.6 后端增量：`docs/V0.6_BACKEND_DELTA.md`
- 当前产品 UI 基线：`docs/UI_V0.5_PROJECT_WORKSPACE.md`
- 任务编辑与 Context / Select 细化：`docs/UI_V0.5_TASK_EDITOR_REFINEMENT.md`
- V0.5 后端适配基线：`docs/V0.5_BACKEND_FRONTEND_ADAPTER.md`
- 查看/编辑分离、防参数墙：`docs/UI_DIRECTOR_MODE_GUIDE.md`
- Storyboard / Task 核心领域模型：`docs/STORYBOARD_TASK_MODEL.md`
- 产品边界与核心架构：`docs/ShotMill_产品与架构规划.md`
- 通用 UI / UX：`docs/UI_UX_SPEC.md`
- 测试与故障注入：`docs/TEST_STRATEGY.md`
- 文档索引与冲突优先级：`docs/README.md`

当前开发必须先读 V0.4。**任何 UI / CSS / Overlay / Dialog / UI Library 集成修改都必须先读 `docs/UI_DEVELOPMENT_RULES.md` 与 `docs/UI_UX_SPEC.md`。** 涉及批量 Prompt Enhancement、人工 Prompt 审核、批量 Video Generation、双 Queue Runtime 或 Qwen3.8 默认 Prompt AI Profile 时，还必须读 `UI_V0.9_BATCH_REVIEW_WORKFLOW.md` 与 `AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md`。旧文档里的“故事板 / 生成 / 素材”三个一级页面已被当前 UI 覆盖，不得恢复。

## 目录职责

- `frontend/`：React、TypeScript、Vite、Tauri 壳与 `/dev/ui`。
- `backend/shotmill/`：FastAPI 模块化单体后端，按 V0.3 建立 API / Domain / Application / Frontend Adapter / Provider / Persistence，并在 V0.4 上增加批量生产能力。
- `scripts/`：统一开发与验收入口。
- `tests/`：Python unit、integration、contract、E2E fixtures 与场景。
- `docs/`：产品、交互、架构和测试协议。

## 不可违反的领域边界

- ShotMill Core 不得绑定 H3、Qwen、ComfyUI 或具体厂商。
- Prompt AI Provider 与 Video Generation Provider 必须独立。
- Provider 行为由 Capability 驱动；专属字段只存在于 Adapter、Profile、Skill、Validator 或 Provider Parameter Schema。
- Task 可以在内部描述一个或多个 `TaskVisualBeat`；Beat 不拥有独立 Queue、Job 或 Result 生命周期。
- Story Order、Task Content、Generation Context 必须保持独立。
- Result 属于 Job / Task；重新生成不得覆盖历史 Result。
- Task 是可变生产意图；Job 是不可变执行快照。
- Task 展示编号不是稳定 ID；关系必须使用稳定内部 ID。
- 剧本原文、AI Prompt 与人工 Final Prompt 必须分离。
- 项目业务引用使用 project-relative path 和 `asset_id`，不得传播绝对资产路径。
- Primary Result 变化必须正确传播 Context Stale。
- H3 当前时长 / 多镜头等限制必须由 Profile / Capability 表达，不得写死在 Core。

## V0.4 批量生产不变量

- V0.4 主生产路径固定为 **批量 AI 增强 → 人工逐任务审核 → 批量视频生成**。
- 现有单任务“增强”行为必须完整保留；批量增强与单任务增强调用同一 Prompt Enhancement Application / Skill / Provider 能力。
- Qwen3.8 是默认 Prompt AI Provider Profile，不得进入 Task Domain 或 Core 条件分支。
- Prompt Enhancement Batch / Job 必须由后端持久化和调度，React 不得通过 `for` 循环充当真实队列。
- Prompt Enhancement Job 提交时冻结输入 / context / provider profile 快照；排队后修改 Task 不得静默改变已有 Job。
- 默认本地 Prompt AI 并发为 1，但并发度属于配置，不写死到 Domain。
- Prompt Enhancement Queue 与 Video Generation Queue 必须独立；两类后台工作可以同时运行。
- AI 增强完成后默认进入人工 `pending_review`，不得自动视为可批量生成。
- Prompt 审核针对当前真正会用于生成的 Prompt Source + 内容；确认必须保存稳定 hash / source / 时间。
- 编辑当前有效 Prompt、切换 Prompt Source、切换 AI Revision 或再次增强后，已有审核必须自动失效。
- 仅切换可视化 / 文本模式不得使审核失效。
- 批量视频生成默认只接受 **已审核 + 当前 Prompt hash 未变化 + generation validation 通过 + 无 active video job** 的 Task。
- 未审核 Task 默认跳过，不提供显眼的“忽略审核全部生成”主路径。
- Batch 只是汇总 / 调度边界，现有 immutable Video Job / Result 模型不得被复制或改写。
- 单项 Prompt / Video Job 失败不得阻断整批后续合法任务。
- Runtime Read Model 可以统一聚合两类 Queue，但内部领域对象不能强行合并成一个笼统 QueueItem。

## V0.3 后端基础不变量

- 当前后端以**模块化单体**为目标，不引入微服务、Redis、Celery、Kafka、CQRS/Event Sourcing 等额外基础设施。
- 第一阶段持久化使用 `SQLite + SQLAlchemy 2.x + Alembic`。
- `app.py` 只负责应用组装；业务逻辑不得继续堆入 route handler。
- Application 层依赖 Repository 边界，不在业务代码中散落 SQL。
- Project / Asset / Task 是正式 Source of Truth。
- Asset 必须区分用户可改的 `name` 与只读 `original_filename`。
- Frontend Adapter / Read Model 是 React 与 Core 的正式边界；UI 不直接消费数据库 model 或完整 `GenerationTask`。
- 首页消费 `ProjectSummary`，项目页消费 `ProjectWorkspaceView / TaskSummary`，编辑窗消费 `TaskEditorView`。
- Job / Result 保持不可变历史模型。
- Provider 执行层可以未来拆远程服务，但 Domain 不因部署方式变化而拆散。

## 当前 UI 不变量

- **所有界面必须优先使用弹性布局（Flex / Grid / minmax / clamp 等）。窗口尺寸变化时，先让现有区域自适应收缩、扩展或重新分配空间，不得用新增滚动条代替布局适配。**
- **除非需求明确指定某区域需要滚动，否则不得新增滚动条。允许滚动的区域必须有明确业务理由，例如左侧长参数列表、超长文本编辑内容或长资产列表；不得让 Dialog、页面根容器或主内容区通过整体滚动掩盖布局溢出问题。**
- **全局默认采用“专业桌面工具的紧凑信息密度”。提高密度优先收紧窗口/面板留白、padding、gap、行高、卡片高度和控件高度，不通过缩小正文字号、大量压缩可读性来换取空间。**
- **窗口尺寸必须与实际内容量匹配。内容较少时不得为了“高级感”制造大面积空白；对象列表（Task / Asset / Result 等）应优先使用紧凑行高和稳定间距，让同屏可见项更多。媒体预览可以保留视觉面积，但参数、元数据和工具栏应保持紧凑。**
- **Dialog / Overlay 的外框尺寸必须稳定。用户/AI、可视化/文本、上下文承接模式等内部标签切换只能替换或重排既定内容区，不得导致整个窗口忽大忽小。**
- **可跨项目复用的基础控件必须优先进入 `Terry_React_UI_Library`，ShotMill 不得为 Button、Select、SegmentedControl、SlidingTabs、Checkbox、Switch、Slider、TextField、Tooltip 等再维护一套平行实现。只有 Task Card、H3 Prompt Editor、Result Preview、运行中心等业务专属组件留在 ShotMill。UI 库新增公开组件必须同步挂到 UI Showcase。**
- **共享组件的内部 DOM / 几何 / padding / line-height / Track / Knob / Indicator 归 UI Library 所有；ShotMill 业务 CSS 不得通过 `.tc-*` 内部选择器、宽泛 descendant selector、`!important` 或负 margin/translate 二次修共享组件。组件异常先看 Showcase、实际依赖 SHA、Computed Style 和 CSS 所有权。**
- **同一行中的文字、图标、按钮、Select、标签组默认必须真实垂直居中；不得依赖肉眼近似或后续像素补偿。**
- **标签控件分为两类且语义固定：`SegmentedControl` 用于用户/AI、可视化/文本等高层模式或视图切换，组内等宽、两端完整半圆，选中项整块轻微提亮且文字/图标变 Accent，不使用底部亮条；`SlidingTabs` 用于分辨率、质量、生成模式、上下文承接等参数密集区域，无圆角外框，底部保留暗轨道，Accent 指示条滑动到当前项，当前文字/图标同步变 Accent。不得在参数密集区滥用胶囊标签。**
- 默认一级结构只有 **项目首页** 与 **项目工作台**；任务编辑使用 Overlay。
- 首页只负责打开 / 新建项目，不展示任务内部参数。
- 项目页左上是 **返回首页**，必须有房子图标，不再用产品标题伪装导航。
- 项目页顶部中间显示当前项目；右侧必须有 **项目配置** 与表格 / 卡片切换。
- **列表与卡片是同一任务集合的两种视图。** 切换不得改变任务数据和选中任务。
- **列表和卡片都在主内容区保留“新建任务卡”入口；列表使用接近普通任务行的创建行，卡片模式使用创建卡。不得恢复旧顶部“新建任务 / N 个任务”工具栏。**
- 单击任务只选择并更新右侧只读栏。
- 双击任务或右键“编辑任务”打开同一套任务编辑弹窗。
- 右侧栏永远只读，不得出现 input / textarea / Select / 保存 / 添加素材等编辑控件。
- 有 Result 时右侧缩略图允许点击打开独立播放弹窗；播放器不得常驻右栏。
- 底部左侧是应用设置入口，右侧显示当前 Prompt / Video 运行摘要。
- 项目配置负责项目标题、简介、AI 项目背景开关与项目资产管理；不得把这些塞进任务编辑器。
- 不再恢复“故事板 / 生成 / 素材”三个一级导航。
- 任务编辑弹窗保持“左侧少量配置 + 右侧大提示词区 + 底部取消/保存”。
- V0.9 在任务标题区增加上一个 / 下一个任务导航，并增加“确认并下一个”的连续审核动作；Overlay 本身不要反复关闭重开。
- 用户提示词与 AI 增强提示词都必须支持 **可视化 / 文本** 两种模式。
- 用户 / AI 标签决定真正使用哪份提示词；可视化 / 文本只决定同一份 H3 字符串的编辑表现。
- **AI 增强历史下拉只在 AI 标签出现。** 每次点击“增强”创建新版本，不覆盖旧版本。
- AI 增强页没有结果时必须显示明确空状态，不允许留下无提示的大面积空白。
- 不得恢复“采用增强结果”按钮；当前 AI 历史版本就是 AI Prompt Source。
- 底部按钮附近继续显示“已使用 AI 增强提示词 / 已使用用户提示词”，不要移回 Prompt 内容区域。
- H3 可视化模式参考 `ComfyUI-TerryXu-nodes` 的 H3 Prompt Editor：标签、素材引用、Shot、对白、时间、运镜等以用户可读组件显示，但序列化仍保持标准 H3 文本。
- V0.9 的 Task Card / Table 只展示用户真正需要的 `AI 未增强 / 增强中 / 待检查 / 已检查 / 生成中 / 已生成 / 失败` 等轻量状态，不堆 Job / Batch / Snapshot 工程字段。
- 批量操作主要位于工作台批量操作区 / 多选 contextual bar，不给每张卡堆按钮矩阵。
- Profile、Visual Beat、ContextLink、Job、Capability、Validation 等工程概念不得进入默认产品 UI。
- 不得通过缩小字号、大量 Badge / Pill、密集 key-value 来容纳更多参数。
- 用户可见文案默认中文，产品名 / 模型名 / 外部协议标签除外。

## AI 提示词增强不变量

- AI Prompt Enhancement 的核心输入是 **用户描述 + 当前任务真正引用的图片 / 视频媒体**。
- `assetId / 资产名 / <Picture 1>` 等元数据不能代替真实媒体本体。
- 前端只传稳定 `assetId + role + context options`；绝对路径、base64、上传、`image_url / video_url`、视频抽帧属于后端 Prompt AI Provider Adapter。
- 项目背景是可选上下文，受项目开关控制。
- **上一任务摘要也是可选上下文，不得默认强制发送。** `includePreviousTaskSummary=false` 时增强请求不得携带摘要正文。
- 即使启用上一任务摘要，也不得默认发送上一任务完整 `userPrompt / aiPrompt / finalPrompt`。
- Prompt Enhancement Context 与 Video Generation Context 必须独立。
- MiniMax H3 与 Seedance 2.0 必须使用不同 Prompt Skill；可以共用底层 Prompt AI Provider，但不能共用一套混杂的 System Prompt。
- Prompt AI Provider 的图片、原生视频、视频抽帧、音频理解等能力必须由 Capability 表达。
- 音频 Provider 不支持真实理解时，不得声称已听取或分析音频。
- 每次增强产生独立 `AiPromptRevision`；失败请求不产生伪历史。
- 只发送当前任务真正选中的媒体和用户明确启用的可选上下文，不因资产存在于项目库就自动上传给 AI。

## 后端接入不变量

- React 页面不得直接围绕 Core 对象或数据库表拼 UI；使用 Frontend Adapter / Read Model。
- Project status、Task status、resultCount、preview fallback、Prompt review / batch eligibility 等聚合逻辑放在后端 Adapter，不让前端理解 Job / Result / Context 细节。
- 项目简介不得直接拼进用户 Prompt。
- H3 可视化 HTML / Chip DOM 不得入库，后端只存标准 H3 文本。
- Prompt Source 必须明确保存为 user / ai；两份 Prompt 独立保存。
- `userViewMode / aiViewMode` 是 UI 偏好，不属于真实 Video Provider 参数；真实后端接入时应从 generationParams 中拆出。
- 新建任务应在用户点击“保存”时才真正落库；打开空白编辑窗不产生数据库垃圾记录。
- Core 的 Scene / TaskPlacement 不因当前 UI 隐藏 Scene 而删除；Adapter 负责压平成任务顺序。
- 实时状态优先使用项目级 SSE，轮询可作为 fallback。
- 所有页面调用后端优先经过 `ProjectGateway` / 正式 Gateway，禁止重新让组件散落 `fetch()`。

## 开发与验收

- 当前开发必须先阅读 `V0.4_BATCH_PRODUCTION_PIPELINE.md`。
- **任何 UI 修改必须阅读 `UI_DEVELOPMENT_RULES.md` 与 `UI_UX_SPEC.md`；不得通过新增 fix CSS、越界修改共享控件、额外滚动条或像素补偿绕过其中红线。**
- V0.4 UI 修改必须阅读 `UI_V0.9_BATCH_REVIEW_WORKFLOW.md`，并继承 V0.8 / V0.6 / V0.5 UI 文档和 `UI_DIRECTOR_MODE_GUIDE.md` 未被覆盖的规则。
- AI 提示词增强实现必须先阅读 `AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md`。
- 后端基础边界仍以 `V0.3_BACKEND_FOUNDATION_DEVELOPMENT_TASKS.md` 为已完成基线。
- 后端接 UI 必须阅读 `V0.5_BACKEND_FRONTEND_ADAPTER.md`、`V0.6_BACKEND_DELTA.md` 与相关版本增量。
- Storyboard / Task 领域变更必须阅读 `STORYBOARD_TASK_MODEL.md`。
- 测试修改必须阅读 `TEST_STRATEGY.md`。
- 修改业务逻辑必须增加测试；修复 Bug 必须先增加可复现回归测试。
- Provider 变更必须运行 Contract Tests；UI 行为变化必须运行相关 Vitest / Playwright。
- 批量队列修改必须覆盖部分失败、取消、重试、active duplicate、重启恢复与输入快照不可变。
- Prompt Review 修改必须覆盖 Source / Revision / Prompt 内容变化后的审核失效矩阵。
- 开发中优先 targeted tests，完成前运行对应 `python scripts/verify.py --area <area>`。
- 发布与高风险跨域变更运行 `python scripts/verify.py --full`。
- 禁止删除、跳过或弱化有效测试来规避失败。
- 无法执行的验收必须明确报告原因和未验证风险。

## Windows 本地规则

- 本地命令使用 PowerShell 7，并在中文或文本读写前设置 UTF-8。
- 文本文件读写显式使用 UTF-8。
- 通过 `python -c` 传递含 SQL 或嵌套引号的脚本时，先用 PowerShell 单引号 here-string 保存到变量，再将变量作为参数；不要用反斜杠转义双引号，PowerShell 不采用该转义规则。
- 当前 ComfyUI 开发环境：`G:\AIGC\ComfyUI_Codex`。它是 Video Generation Provider 的执行端，不是 Core 依赖。
