# ShotMill 开发导航

ShotMill 是面向 AI 视频生产流程的素材生成平台，不是剪辑器或 ComfyUI 外壳。Core 仍以 Generation Task、Job、Result、Asset、Context 等领域对象组织能力；当前产品 UI 是“项目首页 → 项目时间线列表 → 导演时间线”，同一工作台可浏览生成结果。

## 默认开发策略（2026-10-11）

- **一次完成一个可检查的小交付：明确目标 → 完整实现 → 最小相关验证 → 交付即停。** 小交付是实施与验证节奏，不是限制后端只能打补丁。开始前简短说明目标和通过条件，不把相邻功能、历史欠账或假设风险自动加入本轮。
- **前端体验保持稳定，后端简化优先。** 用户已反复打磨的布局、视觉、交互和编辑体验是应保留的成果，不为内部架构整理主动改 UI、CSS 或重写前端。必要接入只做最小 Gateway／类型适配，后端优先保持现有 API 与 Read Model 契约。
- **后端必要时允许大改，包括重划职责、合并流程和重写相关模块。** 目标是业务流程直白、数据职责明确、重复路径与旧实现退出；不把“最小改动”变成保留坏结构，也不把“大改”变成增加更多层、接口、框架或长期并行实现。按可验证的业务闭环分步落地。
- **按个人使用、可信局域网设计。** 优先简单直接的实现；没有实际需求或已复现问题，不新增防攻击机制、权限体系、通用框架、多层兜底、备用实现、配置开关或兼容旧方案的分支。
- **当前交付为 Windows 绿色包：解压直接运行完整 ShotMill，没有安装器。** 不建设通用旧数据迁移工程或自动垃圾回收；项目 ZIP 导入／导出和客户端断线／退出后的状态与结果恢复继续保留。不得把 AI 的实现推演或测试建议升级为用户需求。
- **现有项目全部是测试项目，不要求兼容旧数据库或旧工程格式。** 只将最近更新的一个测试项目一次性转换为新格式工程，保留其内容与所需文件引用，其余旧项目不迁移。不因此保留旧运行路径、双写或兼容层；转换可用一次性脚本，不扩建迁移系统。旧测试数据不约束新架构，原始素材仍不得误删。
- **用户数据分为项目与应用设置。项目保存为用户选择位置的普通工程文件，不为项目建立数据库，也不由全局数据库保存另一份项目真相。** 应用设置独立保存，不随项目归档。导入本机已有素材只记录原文件引用，不复制到项目目录或全局文件库；多个项目直接引用同一个原文件。移除项目引用不得删除用户原始素材。项目 ZIP 收集所依赖的文件（含项目目录外素材与结果）后归档，防止换位置或换电脑时缺文件，不是唯一的项目保存方式。
- **写文件只发生在确实产生或收到文件内容时。** 生成结果保存到项目输出目录，ZIP 解包保存包内文件；没有可直接引用的本地路径、确需上传的文件才保存收到的内容。桌面选择本地素材不得先上传再复制。已有 `FileLibrary`／全局去重实现是历史基础，不是新架构必经层；保留清晰的文件读写与引用职责，不继续维护强制复制入库或项目文件与数据库双向同步。
- **生成中的任务因服务器退出而中断，标为失败，由用户手动重跑。** 原因显示服务器退出，已知是手动关闭或崩溃时据实说明，无法区分则说明具体原因未知；不自动续算或重新提交，不建设崩溃诊断体系。单纯客户端退出或网络断开不能当作服务器退出；服务器已完成并保存的结果在重启后仍可取回。
- **尚未提交给服务器的后续视频任务，在服务器未响应时挂起，显示原因“服务器未响应”，用户可重试提交。** 保留任务及排队输入，不标为生成失败、不清空排队；等待用户重试，不自动重新提交。重试仍未响应则保持挂起并说明原因，复用现有提交能力，不另建通用重试框架。
- 保留直接关系到用户数据和正常使用的保护：不误删共享文件、不覆盖历史结果、不重复提交生成、失败不丢编辑内容。缺文件、断线等常见错误给出清楚反馈；无法确认文件引用时保留文件即可，不因此扩建恢复系统。已有有效保护不为“精简”而随手删除。
- **测试按文件／用例选择，局部通过即停。** 不把“最终版”“发布前”“高风险”当成自动扩大测试范围的理由。具体规则见下方“开发与验收”。
- 已完成项沿用已有证据，只重测本次改变的行为。未验收只补缺失证据，不从头重建整套验收；存储自动清理、长期压力测试等独立事项不得绑架可用功能交付。
- **省 token：先读当前计划和目标模块，用 `rg` 定位后只读相关章节／函数／失败日志。** 已读且未变的规范不重复全文读取；不默认扫描全仓、翻长历史、输出整份日志。小任务直接完成，只有可独立并行且能节省时间的子任务才分工，不重复调查同一范围。
- 文档只更新当前计划的状态、日期和简短证据；规则改变才改规则文档，不为普通修复新建计划、长报告或平行清单。
- 一个小交付超过约 30 分钟仍没有可检查的结果时，主动说明具体卡点并收窄切分；这是进度检查点，不是停止已授权工作的审批点，也不以时间盒为由省略必要验证。

## 当前优先文档

- **当前唯一开发任务与状态：`docs/CURRENT_DEVELOPMENT_PLAN.md`**
- 历史验收依据（含 P0）：`docs/ACCEPTANCE_EVIDENCE.md`（只查相关记录，不将旧存储实现作为新架构约束）
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

当前开发先读 `docs/CURRENT_DEVELOPMENT_PLAN.md` 的目标项，再按任务查领域规范；只有核对历史验收时才读 `docs/ACCEPTANCE_EVIDENCE.md` 的对应条目。下列领域规则继续有效，文档列表是导航，不是每轮全文必读清单。**任何 UI / CSS / Overlay / Dialog / UI Library 集成修改都必须先读 `docs/UI_DEVELOPMENT_RULES.md` 与 `docs/UI_UX_SPEC.md` 的相关规则。** 涉及 Prompt Enhancement 时还须读 `AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md` 的对应章节。旧文档里的“故事板 / 生成 / 素材”三个一级页面已被当前 UI 覆盖，不得恢复。

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
- 项目业务关系使用稳定 `asset_id`；工程文件保存原文件定位信息，相对路径优先，跨目录／跨盘引用可按需记录绝对路径。路径由文件访问层解析，不将本机路径当作业务 ID 或直接传给远端 Provider。
- Primary Result 变化必须正确传播 Context Stale。
- H3 当前时长 / 多镜头等限制必须由 Profile / Capability 表达，不得写死在 Core。

## V0.4 批量生产不变量

- 用户界面与 Agent、单任务与批量生成统一支持直接使用当前提示词；AI 增强和提示词审核均为可选操作。
- 现有单任务“增强”行为必须完整保留；批量增强与单任务增强调用同一 Prompt Enhancement Application / Skill / Provider 能力。
- Qwen3.8 是默认 Prompt AI Provider Profile，不得进入 Task Domain 或 Core 条件分支。
- Prompt Enhancement Batch / Job 必须由后端持久化和调度，React 不得通过 `for` 循环充当真实队列。
- Prompt Enhancement Job 提交时冻结输入 / context / provider profile 快照；排队后修改 Task 不得静默改变已有 Job。
- 默认本地 Prompt AI 并发为 1，但并发度属于配置，不写死到 Domain。
- Prompt Enhancement Queue 与 Video Generation Queue 必须独立；两类后台工作可以同时运行。
- AI 增强完成后保留 `pending_review` 状态，不伪造审核；此状态不阻断生成。
- Prompt 审核针对当前真正会用于生成的 Prompt Source + 内容；确认必须保存稳定 hash / source / 时间。
- 编辑当前有效 Prompt、切换 Prompt Source、切换 AI Revision 或再次增强后，已有审核必须自动失效。
- 仅切换可视化 / 文本模式不得使审核失效。
- 批量视频生成接受 **有效当前 Prompt + generation validation 通过 + 无 active video job** 的 Task；审核是否完成或过期不构成门禁。
- 未增强、未审核 Task 可直接生成，不需要“强制跳过”开关或额外确认。
- Batch 只是汇总 / 调度边界，现有 immutable Video Job / Result 模型不得被复制或改写。
- 单项 Prompt / Video Job 失败不得阻断整批后续合法任务。
- Runtime Read Model 可以统一聚合两类 Queue，但内部领域对象不能强行合并成一个笼统 QueueItem。

## V0.3 后端基础不变量

- 当前后端以**模块化单体**为目标，不引入微服务、Redis、Celery、Kafka、CQRS/Event Sourcing 等额外基础设施。
- 已完成的第一阶段使用 `SQLite + SQLAlchemy 2.x + Alembic`；这属于历史实现基线。最新项目保存要求以普通工程文件为准，不得据此为每个项目建库或保留全局项目数据库作为另一份真相；已有数据库是否仍承担必要的应用运行记录，按实际需要收敛。
- `app.py` 只负责应用组装；业务逻辑不得继续堆入 route handler。
- Application 层依赖 Repository 边界，不在业务代码中散落 SQL。
- Project / Asset / Task 是正式 Source of Truth。
- Asset 必须区分用户可改的 `name` 与只读 `original_filename`。
- Frontend Adapter / Read Model 是 React 与 Core 的正式边界；UI 不直接消费数据库 model 或完整 `GenerationTask`。
- 首页消费 `ProjectSummary`，项目页消费 `ProjectWorkspaceView / TaskSummary`，编辑窗消费 `TaskEditorView`。
- Job / Result 保持不可变历史模型。
- Provider 执行层可以未来拆远程服务，但 Domain 不因部署方式变化而拆散。

## 当前 UI 不变量

- **项目封面、任务卡片、列表等缩略图统一等比例居中铺满（cover），允许裁切边缘，不得因 contain 适配留下黑边或白边，也不得拉伸变形。完整图片查看与视频播放器按原始比例展示。**

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
- 项目页顶部中间显示当前项目；保留 **项目配置**。打开一条时间线后，顶栏提供导入／导出，标题行居中显示该时间线总时长。项目记录上次打开的时间线与总览／结果浏览状态。
- **项目 → 时间线 → 片段（Task）** 是当前层级；现有 Scene / TaskPlacement 承载时间线归属，一条时间线含多个 Task，可建立多条。导演时间线一个片段对应一个稳定 Task ID；不另建 Clip 真相、任务副本或队列。
- 原任务列表布局用于显示多条时间线；卡片布局用于逐项浏览历史生成结果。两者不再把任务集合当作两个视图，也不再提供“导演时间线／任务视图”切换。时间线列表直接新建时间线，片段在 TerryDirector 内原位新建和编辑，不弹出任务编辑窗。
- 时间线标题、居中的总时长与新建片段／全局提示词／一键增强／生成前自动增强操作在宽桌面窗口保持同一行；内嵌 TerryDirector 不再为这些操作占用独立顶部行。
- 导演时间线保留 TerryDirector 的完整编排、内联提示词编辑及资产池；资产池属于项目，供各条时间线共用。时间位置、故事顺序与生成承接关系保持独立，拖动不得静默改写承接来源、已有执行快照或历史结果。
- 旧任务／项目归档、结果归档与回收站功能退出运行路径。任务直接删除前确认；从最近打开列表移除项目时保留普通工程文件和媒体文件。项目 ZIP 导入／导出仍保留。
- 生成结果卡片打开独立播放器；播放器不得常驻工作台。
- 底部左侧是应用设置入口，右侧显示当前 Prompt / Video 运行摘要。
- 项目配置负责项目标题、简介与 AI 项目背景开关；项目资产在导演时间线的资产池管理。
- 不再恢复“故事板 / 生成 / 素材”三个一级导航。
- 旧任务编辑弹窗不作为导演时间线的编辑路径；若在其他入口保留，维持原有布局与提示词历史行为。
- 任务标题区保留上一个 / 下一个任务导航；2026-09-22 用户要求移除编辑窗“确认并下一个 / 确认提示词”，底部保留取消、保存；Overlay 不反复关闭重开。
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
- Core 的 Scene / TaskPlacement 是时间线分组与 Task 归属的工程真相；Frontend Adapter 向工作台提供时间线及其任务 ID 顺序。
- 实时状态优先使用项目级 SSE，轮询可作为 fallback。
- 所有页面调用后端优先经过 `ProjectGateway` / 正式 Gateway，禁止重新让组件散落 `fetch()`。

## 开发与验收

- 按上方导航读取涉及领域的相关规则；测试选法与可用入口见 `docs/TEST_STRATEGY.md`，不把历史场景目录当作本次新增需求。
- **文档／注释只查差异与链接；纯文案／颜色／间距等视觉调整做对应界面检查。** 此类低影响改动不新增形式化测试，不连带启动后端、全部浏览器用例或打包。
- 业务逻辑变更补充或更新能证明需求的最小测试。业务 Bug 先用最小回归复现；已有失败用例可直接复用，不重复造测试。纯视觉问题可用对应页面或 Mock 场景复现和验收。
- UI 交互改动选对应 Vitest；只有涉及浏览器布局、焦点、跨层流程等才增加对应页面／用例的 Playwright。Provider 改动运行受影响 Provider 的 Contract Tests，不连带全部 Provider 和真实模型。
- 队列与 Prompt Review 按受影响行为选择已有矩阵用例；公共状态机或共享审核判定改变时才覆盖该模块相关完整矩阵。文件迁移／删除验证本次路径的引用保留和失败不丢数据，不自动扩展为全应用故障注入。
- **优先单用例 → 单文件 → 直接相关模块，只有具体失败或明确调用影响才扩大。** 无新修改或新证据，不重复跑已通过的同一组测试；typecheck、lint、构建、模型冒烟按改动需要选用，不叠成默认套餐。
- `python scripts/verify.py` 无参数会同时运行后端和前端大范围验证；`--area backend/frontend` 也不是单项测试入口。日常不用它们代替定向测试，区域验证仅在确实影响整个区域时使用，不把多次区域测试拼成等价全量。
- **不得自行运行 `python scripts/verify.py --full` 或其他等价全量验证**，发布与高风险跨域变更也不构成自动授权。局部验证发现本次改动范围之外的 Bug 时，先自行做一轮针对性排查、修复，并用相关局部测试确认；修好即止，不申请全量验证。
- 只有上述范围外 Bug 经一轮针对性修复仍未解决，且评估确实需要全量验证来定位或排除影响时，才向用户说明发现、已尝试的修复、拟运行范围与预计耗时，并取得明确授权后运行。不得因少见的范围外问题自动扩张为长时间、反复的全量测试。未获授权时记录已通过的局部验证及未验证风险，不把任务假称为全量通过。
- 禁止删除、跳过或弱化有效测试来规避失败。
- 完成条件：本次需求可用、相关最小验证通过、无已知由本次改动造成的阻塞问题。报告改了什么、验证了什么和具体未验收项即可；不把“未跑全量”本身当成未完成。

## Bridge 源码归属

- Bridge 的唯一开发仓库为 `G:/AIGC/ComfyUI-TerryFlowBridge`，远端为 `https://github.com/terry-xu-2077/ComfyUI-TerryFlowBridge.git`。
- `integrations/comfyui_shotmill/` 是离线合同测试使用的固定版本快照，不在此维护独立改动。先在独立仓库修改、测试并提交，再整体同步快照和 `integrations/terryflow-bridge.lock.json`。
- 依赖升级按 `integrations/README.md` 执行；运行快照完整性、受影响 Provider 合同及后端相关用例，不默认启动全部后端验收。不得仅修改摘要掩盖未经验证的源码变更。
- 本地提交、远端发布、运行部署与真实 ComfyUI/LAN 验收是不同状态，不得互相替代。

## Windows 本地规则

- 本地命令使用 PowerShell 7，并在中文或文本读写前设置 UTF-8。
- 生成 Git 补丁不要使用 PowerShell 文本管道交给 Set-Content；该路径可能把 LF 改成 CRLF，破坏无末尾换行文件的补丁。已验证的方式是 Python subprocess 捕获 git diff 的 stdout 字节，按 UTF-8 解码后以 encoding='utf-8'、newline='\n' 写入，并实际运行 git apply --check 验证。
- 文本文件读写显式使用 UTF-8。
- 通过 `python -c` 传递含 SQL 或嵌套引号的脚本时，先用 PowerShell 单引号 here-string 保存到变量，再将变量作为参数；不要用反斜杠转义双引号，PowerShell 不采用该转义规则。
- 当前 ComfyUI 开发环境：`G:\AIGC\ComfyUI_Codex`。它是 Video Generation Provider 的执行端，不是 Core 依赖。
