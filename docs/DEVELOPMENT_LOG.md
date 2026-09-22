# ShotMill 开发记录

本文件记录已经实际完成并通过验证的开发内容。当前以批量生产流程为主线，执行清单见 [V0.4 Batch Production Pipeline](./V0.4_BATCH_PRODUCTION_PIPELINE.md)；V0.3 保留为已完成的后端基础。

## 2026-09-22 · 当前体验版本与批量承接修复

- 整合项目文件夹、品牌 SVG、任务列表与卡片、标签、右侧预览、任务编辑、播放器和全局运行中心的交互打磨。
- 提示词增强和审核均为可选步骤；增强系统提示词加入电影分镜与世界观约束。
- 批量尾帧承接绑定同批上一 Job，等待结果后一次性保存执行上下文；支持调序、挂起/恢复、失败提醒及重启恢复，保留提交快照。
- 当前 UI 依赖固定为 shotmill.11；包含数据库 0003–0005 迁移和前端接口契约。
- 后端、前端、Provider、Scheduler 检查通过；上下文专项 8 项通过。界面用例经分轮复测 70/71 通过，剩余既有文件夹对比度问题未降低标准或改动用户确认配色。
- 当前电影项目 26 个任务仅完成提交前检查，未启动视频生成。详情见 [批量承接修复记录](./BATCH_CONTINUATION_EXECUTION.md)。


## 2026-09-21 · 文件夹材质与回弹微调

- 按用户连续反馈，最终回弹曲线调整为 cubic-bezier(.2,1.5,.32,1)，普通模式 400ms、当前减少动态效果模式 340ms；停靠位置与行程不变。
- 前面板渐变不透明度从 94%–85% 降至 82%–74%，背景模糊从 18px 降至 10px，饱和度保留比例由 .65 提至 .8。文字层级保留并略微加深，以保证深色封面透出时的可读性。
- 用户当前浏览器已确认新材质与动画参数生效。

## 2026-09-21 · 文件夹轻微回弹

- 用户继续要求弹性感：卡片平移改为轻微过冲后回落的缓动曲线 cubic-bezier(.22,1.28,.36,1)，保持刚确认的收拢位置和短行程。
- 普通模式 560ms，当前用户浏览器减少动态效果模式保留 460ms 的局部回弹；实机已读取到新时长与曲线。文件夹动效浏览器回归通过。

## 2026-09-21 · 文件夹动效实机修正

- 直接检查用户正在体验的内嵌浏览器：prefers-reduced-motion 为 true，实际 transition-duration 仅 0.00001s，解释了此前独立浏览器有动画、用户页面却瞬间弹出的差异。清除 app.css 重复的全局减少动效规则，将策略收敛到 tokens.css。
- 用户明确要求保留文件夹弹出动画，因此该局部在减少动态效果模式下仍保留 320ms 短缓动；普通模式为 480ms。不改变系统/浏览器偏好，其他控件继续遵循减少动态效果。
- 内卡默认顶部从容器 28% 调至 40%，高度从 70% 调至 58%；位移从容器约 28% 减至 13.92%，弹出终点约为 26.08%，覆盖之前“顶到容器顶部”的要求。默认更收拢、弹出更克制。
- 用户当前页面已实测生效为 0.32s。六项浏览器回归通过，包括减少动态效果下真实 CSS Transition 存在、时长、位移、回落及相邻布局不变；前端分区检查通过。

## 2026-09-21 · 用户体验反馈：菜单、滑块与拟物文件夹

- 回归先复现：档位菜单在参数栏内被压至 45px，超长项目简介把 384px 卡片内容撑至 5102px。共享 Select 改为挂在当前 Modal 的 Portal，按窗口空间选择上下展开，长菜单项换行；触发器保留省略，不侵占总秒数区域。秒数接入共享 Slider，保留键盘与数值输入、保存和生成只读行为。
- 文件夹按新参考改为干净的蓝色磨砂材质，无封面采用灰白纸页；标题、简介、统计有独立文字层级，超长标题/简介末端省略。前面板使用半透明背景与圆弧转折，项目及任务状态使用轻量纸贴质感。
- 后续补充：外层为正方形，为动画留空；文件夹本体仍为扁宽，背景层略窄。内卡增加高光描边，悬停或键盘聚焦时平移上滑，顶部到容器边界，移开柔和回落，邻居和内容布局不移动。新建入口仍为紧凑扁宽形态。
- 文件夹采用 480ms 缓动平移；菜单、弹窗、参数展开、视图切换复用柔和减速节奏，系统减少动态效果仍有效。没有通过缩小字号或新增横向滚动解决布局。
- 最终前端类型/单元/构建三阶段通过，17 项相关浏览器回归通过，覆盖 1366/960/390 宽度、两种主题、长名称、真实鼠标悬停/回落、减少动态效果、保存、播放与只读状态。共享 Showcase 四组主题/尺寸下的窄栏、搜索、禁用及滑块键盘操作通过。
- 半透明面板对比度按黑/白背景极值合成测量，避免假设封面总是浅色；沿用文字 4.5 阈值。真实项目首页、播放器和编辑器复核正常，6 个已有项目保留、Bridge 已连接，未提交生成或修改生产任务。
- 共享库固定为 0.2.1-shotmill.8：补丁重建核对 21 个源码文件，84 个安装文件与归档逐字节一致；未推送上游。证据 `.artifacts/experience-layout/`。本轮不继续切镜检测及原整体计划的其他待办。

## 2026-09-21 · 主题对比度收尾与用户体验交接

- 修复主要按钮、选中标签、亮色普通按钮、引用菜单辅助文字与图标，以及橙色文件夹背景上的状态/简介/统计文字对比度。共享控件修改在 UI Library 源码完成，业务文件夹样式留在应用所属文件。
- 两种主题的应用 42 个测量样本及共享 Showcase 24 个样本通过；普通文字阈值 4.5，引用图标阈值 3。测量解析实际 CSS 颜色、透明背景和线性渐变端点，不等同于逐像素、屏幕阅读器或全部 WCAG 验收。亮暗文件夹与菜单截图已检查。
- 共享依赖固定为 0.2.1-shotmill.7，源码补丁可从指定基线重建；17 个源码文件及 84 个安装文件比对通过，尚未推送上游。
- 本轮全量八阶段通过，浏览器 55/55。最后补充文件夹颜色修复后，前端类型检查、单元测试、构建三阶段，以及主题/项目封面两项浏览器回归再次通过；没有将此前全量运行冒充最后 CSS 修改后的全量重跑。
- 交接前发现前端 1420 未运行，已启动连接真实后端的前端服务。真实浏览器确认首页 6 个项目、Bridge 已连接、上下文测试项目视频自动播放且无解码错误、任务编辑窗正常，无页面脚本错误。服务保留运行，未提交生成或修改生产任务。
- 用户要求先体验再决定后续。当前正在修的颜色问题已收尾；暂停新增开发。待办保留：切镜检测、H3 内部裁帧/严格连续性、队列验收矩阵最终归档及版本文档总收尾。既有回归和实测记录保留，不宣称整体路线图全部完成。
- 证据：`.artifacts/theme-contrast/`，包括 app-measurements.json、showcase/measurements.json、dependency-proof.json、live-check.json 与实际界面截图。

## 2026-09-21 · 引用菜单键盘与长内容布局

- 修复文本/可视化 @ 菜单按 Esc 后重新弹出的问题，验证方向键选择、Enter/Tab 插入及逐层关闭后焦点返回。
- 修复超长任务标题把关闭按钮挤出弹窗的问题；业务标题区弹性收缩，长提示词仍只在编辑区滚动，原字号和窗口外框保持。
- 前端分区三阶段、相关浏览器 14 项及移动/只读补充 3 项通过。亮暗两套主题、960×540 CSS 布局和设备像素比 2 的长内容截图已检查；未把仿真布局等同于实际系统缩放或读屏验收。
- 共享依赖复核 84 个安装文件、16 个源码文件与归档/重建源码一致，源码及 Showcase 的固定版本验收项完成。整体对比度等剩余项见完善清单，证据 `.artifacts/final-ui-audit/`。

## 2026-09-21 · 连续查看与审核重试

- 切换任务保持原编辑窗口，未保存内容支持保存后切换、放弃或继续编辑；只切换显示模式不额外确认。增加 Alt+左右切换、Ctrl+Enter 保存，沿用生成只读和审核规则。
- 修复保存成功后审核失败导致重试版本冲突的问题；核对服务端内容一致后更新版本，失败时保留草稿，确认成功才切换下一任务。
- 前端分区三阶段及相关浏览器 11 项通过，覆盖保存失败重试、放弃修改、窗口不重开、审核失败恢复和生成只读；确认窗截图已检查。证据 `.artifacts/task-navigation/`。

## 2026-09-21 · 取消待执行视频

- 运行中心增加取消排队视频入口，只处理明确列出的 queued Job；已经运行的任务继续完成，新提交任务和历史结果不受影响。取消后任务恢复可编辑，取消历史在刷新及重启后保留。
- 后端先校验整个 ID 集合的项目归属，再在同一事务取消；保留快照、主结果、审核和内容，避免与另一个活动视频/增强任务状态冲突。前端复用运行中心的等待、失败重试和实时刷新。
- 新增接口隔离、重复请求、运行中竞态、结果保留、重启和端到端回归。全量八阶段、50 项桌面/移动浏览器、109 项契约通过。后端空闲更新后，6 个项目、15 个任务与运行历史指纹一致，证据 `.artifacts/video-queue-cancel/`。

## 2026-09-21 · 生成任务只读查看

- 排队和生成中的任务复用现有窗口，只读查看提示词、参数及输入资产，保留文本复制和可视化/文本切换；收起保存、审核、增强操作，右键入口改为“查看任务”。完成生成后同窗恢复编辑。
- 前端分区三阶段通过；队列浏览器 2 项、提示词显示偏好/亮暗回归 4 项及后端只读回归 2 项通过。现有后端禁止活动视频任务内容修改的规则保留，显示偏好仍可独立保存。

## 2026-09-21 · 视频队列重启恢复与运行状态隔离

- 视频队列启动恢复持久化待执行任务；同一 Job 的并发/终态重复投递不再次执行。恢复原 running Job 通过 Provider 能力读取既有任务和输出，无法恢复时明确失败，不自动重提生成。
- 修复同一任务的提示词增强开始、成功或失败覆盖活动视频状态的问题；增强与视频仍可独立执行，排队输入保持原快照。
- 增加 20 条视频恢复、部分失败继续、历史保留重试、重复投递、双队列并发和恢复协议回归。完整契约及队列测试 122 项通过；真实 Bridge 回收的既有成片哈希一致，状态与队列不变，未重新运行模型。
- 全量验证八阶段通过，浏览器 48/48。空闲更新本地后端后，6 个项目、15 个任务及运行历史核对一致。证据 `.artifacts/queue-recovery/`；视频待执行项取消入口等未完成项继续列于完善清单。

## 2026-09-21 · 批量增强提交预览

- 增加只读增强资格接口，与实际提交共用空提示词和活动增强判断，按任务顺序返回可增强项及跳过原因。预览不会创建 Job、Batch、Revision 或调用 Provider。
- 确认窗显示选中数、可增强数及跳过原因，检查失败阻止提交并支持重试；上下文选项保持。提交前再次核对，任务集合变化要求重新确认，只提交已确认的合法项，保留服务端最终防重复检查。
- 收紧确认窗宽度，亮暗 960×540 截图已检查。新增后端只读/隔离/排序/重复/排队与运行状态回归，浏览器覆盖过滤提交、状态变化、失败重试和上下文选择保留。
- 全量验证七阶段通过，桌面/移动浏览器 48/48、完整接口契约 101/101。空闲重启本地后端后，6 个项目、15 个任务的编辑器数据及运行历史指纹一致；全部项目的只读预览可用。证据 `.artifacts/prompt-batch-preview/`。

## 2026-09-21 · 提示词配色与每任务显示偏好

- 用户追加暗色复查后，扩展用户/AI 两套可视化的文字对比度、1366/960 宽度编辑与选中检查。检查发现并修复对白内部焦点转移重绘，以及离开编辑区后再修改语言回调失效；增加语言控件键盘焦点提示，配色本身无需再次调整。
- 修正亮色可视化标签沿用暗色浅色文字的问题，使用随 Accent 变化的亮暗语义色；对白增加明显底色与侧边线，保持亮暗主题可读。
- 可视化 / 文本切换后立即按任务记忆，用户和 AI 提示词分别记录。独立偏好接口只更新显示字段，取消仍丢弃内容草稿，来源选择和审核语义保持原样。快速写入顺序执行，失败可重试，新任务在保存前不落库。
- 后端分区、前端分区、101 项接口契约及 44 项桌面/移动浏览器回归全部通过，亮暗截图已检查。本地后端在队列空闲时重启并验证新接口，项目和任务数据保留。详情见完善清单。

## 2026-09-21 · 悬浮承接时间轴

- 根据用户补充，承接区间改为点击摘要展开的悬浮时间轴，参数区不再承载完整轨道，也不会因展开而变高。
- 片段块支持整体拖动、边缘修剪、边界夹取和键盘微调，实时显示起止时间与时长。完成、外部点击或 Esc 收起，任务保存后持久化区间。
- 共享库 0.2.1-shotmill.5 增加 timeline 形式并进入实际 Showcase；源码补丁可重建，安装内容与本地归档逐文件一致。上下文浏览器 4 项、相关组件 27 项通过；最终前端分区三阶段与桌面/移动浏览器 41/41 均通过，细节见完善清单。

## 2026-09-21 · 模态焦点与菜单键盘交互

- 共享库 Modal 使用原生模态隔离背景，处理初始焦点、Tab 边界与返回；ShotMill 保留业务弹窗外观并复用共享行为，弹窗内 Portal 挂入对应模态层。
- 工作流下拉菜单优先消费 Esc，避免连带关闭编辑窗；方向键、Home/End、回车和搜索菜单焦点已在真实浏览器验证。
- 新增 5 个浏览器回归涵盖嵌套大图、播放器自动播放、焦点返回和小窗口亮暗布局；共享库实际 Showcase 的四组主题/尺寸组合通过，减少动效通过。前端分区三阶段通过。
- 本地固定依赖升级至 0.2.1-shotmill.4，源码补丁可重建，安装内容与归档逐文件核对。未推送上游。完整浏览器回归发现滑块测试在展开动画期间读取坐标，补齐稳定测量后 40/40 通过；通知叠放、旧全屏预览和对比度仍待收尾。
## 2026-09-21 · 原生节点生成前校验

- Bridge 0.3.1 在只读预检中复用执行的图编译、输入绑定和 ComfyUI 校验。缺失节点/模型、必填连接、类型错误、数值越界、循环以及非法动态选项在创建 Job 前反馈。常见错误使用中文并保留节点位置与选项名称。
- 仅延期检查已选媒体上传后的远端文件存在性，工作流自己的未替换文件继续验证。全流程没有上传素材、排队或修改全局节点校验器；执行时再做包含真实上传文件的完整检查。媒体解码和模型推理仍可能在运行中失败。
- 本机 14 个正常/故障场景通过，包含两份实际 H3 画布，素材文件、队列和任务索引在只读检查前后一致。26 条 Bridge 状态与 6 个项目历史保留。另用原生节点通过正式 Provider 预检并输出 25 帧视频，解码通过。证据在 `.artifacts/preflight-live/`。
- 后端分区、Provider 分区与完整契约 101 项通过。最终 `scripts/verify.py --full` 七阶段全部通过，浏览器 35/35。真实测试暴露并修复动态选项漏检和通配端口误判，两者均有回归；本机 Bridge 已更新，应用显示已连接，结束时队列为空。

## 2026-09-21 · 排队任务冻结工作流内容

- 视频任务保存工作流原始内容、编译图、输入端口与 SHA-256，和已冻结的地址、档位数值绑定一起持久化。执行不再读取后来修改的文件；缺失、损坏或旧版不完整快照明确拒绝，要求重新提交。
- Bridge 0.3.0 的快照读取不上传媒体或排队；画布编译错误提前反馈，目录与快照之间变更端口也会重新校验。原生节点、模型选项及完整运行时输入的只读预检仍待补齐，没有将完整生成校验标成完成。
- 空闲升级本机 Bridge 和后端，备份并核对 24 条 Bridge 状态和 6 个项目的历史。临时工作流捕获两版后删除文件，重建 Provider 后分别输出橙色 25 帧与蓝色 49 帧视频，均为 24 fps，完整解码与颜色核验通过。所有原工作流文件哈希保持不变，测试未运行生成模型。
- 两份真实 H3 画布可只读捕获和编译；安装的 Bridge 与源码哈希相同。证据、备份及临时视频位于 `.artifacts/workflow-snapshot-live/`。补齐此前实际视频时长字段的 OpenAPI 快照，最终后端分区两阶段、Provider 分区及完整契约 92/92 均通过。本增量未修改 UI，未重复运行浏览器验收。

## 2026-09-21 · 上下文媒体与第一场真实对照

- 补齐新建任务草稿的时间轴：结果摘要携带成片实测时长，首次打开即可选择上一成片末尾 1 秒；保留任务计划时长，兼容旧结果且不改写历史。上下文浏览器 3 项、后端与前端分区验证通过。

- 补齐上下文从关系到真实媒体的缺口：最后一帧、明确视频区间、实际时长校验、不可变来源与文件哈希，以及过期/缺失/跨项目/不承接隔离。
- 使用《异星边境》第一场创建两个任务，第二任务同提示词、同种子分别测试尾帧与 7–8 秒片段；共三条 8 秒成片保留，输入上传逐字节校验，尾帧逐像素校验。
- 原工作流和默认档位保留，新增视频入口的独立测试工作流。Bridge 0.2.2 修复原生视频解码链引用与输入预览误列为输出；片段版已生成成片从原执行记录恢复，未再次运行 GPU。
- 全量七阶段、上下文浏览器用例、媒体与集成回归通过。H3 内部将 24 帧裁至前 22 帧以及非严格首帧连续性仍有明确限制。结果、耗时和证据见 [实测记录](./CONTEXT_ACCEPTANCE_2026-09-21.md)。

## 2026-09-21 · 生产状态与常用操作完善（进行中）

- Bridge 显示通信状态并支持重试，区分未安装、断开和服务异常。工作流设置支持选文件、名称与简介后保存档位。
- 项目文件夹使用横向比例与橙色渐变，展示简介和完成数量；默认封面跟随第一个任务，项目配置支持选资产、视频截帧和恢复自动封面。
- 已生成任务使用视频截图；列表、卡片和详情可点击直接打开并自动播放。资产图片点击放大，再点大图关闭。
- 单项和批量增强保留尝试耗时、失败原因和不可变配置快照；运行中心支持取消未开始项、重试失败项和刷新后查看历史。任务列表、卡片和详情展示独立的增强、视频及排队耗时。
- 增加可见任务复选框、全选、全项目/选中范围增强入口；显示实际增强模型。窄窗口顶栏按两行排列，避免项目名与通信状态重叠。
- Prompt 审核失效矩阵 18 项通过；来源切换、有效内容变化、再次增强及 AI 历史切换会撤销审核；仅显示模式、任务标题或未使用提示词变化不会撤销审核。用户/AI 两种来源均覆盖。
- 本轮完整需求与逐项证据见 [完善清单](./V0.4_COMPLETION_TRACKER.md)。完整生成前校验、共享浮层焦点与可访问性收尾、真实模型增量冒烟仍未完成；数值端口进度见下节。
- 本增量最终 `scripts/verify.py --full` 七阶段全部通过，桌面/移动 E2E 32 项通过，另外 74 项完整接口契约通过。真实 Bridge 只读健康与目录检查正常，本轮没有提交真实 GPU 生成。

### 生成预检后续增量

- 生成前采用正式执行输入与 Provider 校验，提前拒绝无效工作流、错误媒体槽位、缺失文件及超出能力的时长；确认窗显示原因。
- 提交前重新核对任务版本、审核和活动视频 Job，防止检查期间编辑或增强改变显示状态后误提交。
- 视频 Job 保存检查时的 ComfyUI 地址和工作流选择，后续设置变化不会改写已排队任务。九项新增集成回归通过；远端工作流文件内容版本、数值端口及编译级预检仍待完成。
- 此增量全量验证七阶段通过，E2E 32/32，另外完整契约 74/74 通过；本轮仍未进行真实 GPU 生成。

### 数值档位与 Bridge 0.2.0

- 档位保存数值输入来源与秒数/帧数规则，任务编辑器显示生效值；配置进入视频任务快照，Provider 与 Bridge 共同验证端口与类型。没有时长绑定的工作流明确显示使用工作流默认值。
- API 工作流从数值节点确定类型，不再从 `frames` 等名称误判媒体；同源多输入连接完整保留。新增回归先复现失败，修复后 Bridge 合同 29 项及 Provider 分区通过。数值主增量的全量验证七阶段、E2E 32 项通过。
- 本机 Bridge 备份并空闲升级至 0.2.0，17 项历史状态在重启前后完全一致。正式 Provider 驱动原生视频节点，2/3 秒按 24 fps、4n+1 输出 49/73 帧，MP4 解码通过；独立临时工作流已移除。该验收不替代真实模型生成，现有生产工作流和默认设置未修改。详见完善清单的证据目录。

### 上下文区间滑块

- 浏览器先复现双端刻度不同导致选区与手柄错位、拖动不命中。增加共享 `RangeSlider` 和亮暗 Showcase，固定依赖至 `0.2.1-shotmill.2`，移除业务私有轨道与手柄样式。
- 双端使用统一时间轴；控件本地实时更新并限频通知父级，释放立即提交。重叠端点可独立拖动，键盘可调整，保存/刷新重开保留区间，上一任务不足 1 秒和小数区间不再取整丢失。
- 20 项编辑器测试通过，Showcase 亮暗/200% 缩放/禁用态通过；全量验收七阶段通过，浏览器 33/33。
- 上下文整体仍未完成：执行请求尚未把已保存承接关系解析为片段/尾帧媒体，继续作为优先修复与验收项。

## 2026-09-20 · Bridge 批量实跑与界面更新

- 接入应用设置、本地 `llama_cpp_instruct_adv` / API 推理切换、通用系统提示词预设、ComfyUI 通信与生成工作流配置。
- 视频主路径改为 ShotMill 后端 → Bridge API → ComfyUI。Bridge 读取普通工作流、定位输入输出标记、注入资产并包装原生保存节点，结果按任务目录隔离；不要求用户导出 API 工作流。
- Bridge In 支持多路对应输出与总线，输入槽位按最终接入点标识；H3 在执行副本中处理空槽位导致的连续引用编号变化。完整节点包（Python 入口和浏览器扩展）收录到 integrations。
- 批量增强后台入队，审核确认当前提示词后才能批量生成；修复 AI 历史版本恢复、SSE 重连及排队/运行状态区分。
- 更新亮暗主题、电影文件夹首页、胶囊操作按钮、单图标视图切换、弹窗与展开动效、资产槽位缩略图、紧凑工作流参数区和结果播放器。移除已被项目配置样式替代的旧补偿样式。
- “异星边境”8 项任务均使用 `异星边境_稳定720P.json` 完成增强、审核和生成；每项独立保存 Result。所有视频完整解码并播放到结尾；Bridge 重启后的下载与应用副本 SHA256 一致。
- 工作流默认输出实际为 864×480、24fps、8 秒，未修改默认生成参数。界面区分目标参数与媒体实际规格；不能据此声称任意工作流已接通时长控制。
- 通过 `python scripts/verify.py --full` 七阶段验证，含 Provider 契约及 28 项桌面/移动端 E2E。实跑证据、部署备份和未完成交互项详见 [验收记录](./UX_ACCEPTANCE_BASELINE.md)。
- 提交整理：删除一次性截图脚本、重复下载样本、临时源码副本和缓存；项目数据、生成结果、部署备份及验收证据仅在本地保留并被 Git 忽略。组件库源码补丁属于固定依赖包的重建材料，不是运行时临时补丁，尚未合入上游组件库。

## 2026-09-14 · 同一 UI 的真实数据 / 假 API 双模式

- 修复假数据启动器在 `1420` 被无窗口残留服务占用时只能报错的问题；启动器记录自己创建的进程 ID 与启动时间，下次运行可精确清理异常退出残留。对旧版本留下的服务再用页面内容、进程类型和当前项目路径三重确认；身份不明的占用者不会被结束，而是安全顺延端口并打开最终地址。
- 前端继续只使用 `HttpProjectGateway` 与 `/api/v1`；没有修改当前冻结 UI，也没有在组件内增加第二套 Mock 数据分支。
- 新增后端拥有的独立假 API，复用正式 FastAPI Route、Pydantic Schema、Frontend Adapter、SQLite 与业务 Service，预置项目、任务、可显示图片资产和 AI Prompt Revision。
- 假 Prompt Provider 输出确定性结果，不访问网络或消耗额度；假数据保存、编辑与新建在当前会话内真实生效。
- 新增 `启动 ShotMill（假数据）.bat`：使用系统默认 PowerShell，启动 `8766` 假 API 与 `1420` 浏览器 UI；退出时停止两项服务并清理临时数据库。
- 真实数据继续使用 `启动 ShotMill（前端+后端）.bat`，两种模式不允许同时抢占前端端口。
- 新增后端生成的 `contracts/openapi.json`、契约说明和快照测试；另有测试逐项比较假 API 与真实 API 的 OpenAPI paths / schemas，避免接口漂移。

## 2026-09-14 · MiniMax H3 / ComfyUI 真实生成闭环

- 从 `G:\AIGC\ComfyUI_Codex` 的稳定 MiniMax H3 参考工作流捕获真实 API prompt，并固化为 ShotMill Provider Profile 模板。
- 模板只保存 ComfyUI API 节点图，不把 H3 专属节点写入 Core；Final Prompt、seed、Task 时长、Job 输出前缀和最多五个 `<Picture N>` 参考槽由 Adapter 注入。
- ComfyUI Adapter 会先通过本地 `/upload/image` 将 Task 真正绑定的媒体放入 `input/shotmill`，工作流只接收 ComfyUI 可解析的相对文件名，不再错误传播 ShotMill 资产绝对路径。
- 未绑定的可选参考槽会连同 LoadImage 节点和悬空连接一起裁剪，因此同一模板可执行纯文本或 1–5 图参考任务。
- 新增完整 Provider Contract Test，覆盖媒体上传、模板渲染、任务提交、history 轮询、`/view` 下载与视频响应。
- 开发启动器会在用户没有显式覆盖环境变量时自动发现仓库内 H3 模板和同级 `ComfyUI_Codex`；不改变现有产品 UI。
- 增加可重复运行的 `scripts/smoke_comfyui.py`，真实 GPU 验收输出放在已忽略的 `.artifacts/`。

### 实机验收

- 本机 ComfyUI 0.35.0 / RTX 3090 接受并完成真实 MiniMax H3 任务。
- 先完成 Provider 直连 smoke，再完成 ShotMill API → Project → Task → 不可变 Job → Generation Queue → ComfyUI → Result → Primary Result 的全链路 smoke。
- 全链路 Job 状态为 `completed`，保存真实 ComfyUI `provider_job_id`；Result 已落库，Task 状态为 `completed`、进度为 100%，Primary Result 指向新结果。
- 项目输出视频已下载到 project-relative output；ffprobe 验证为 H.264/AAC、1280×736、24fps、1.625 秒。

### 后续重点

- 真实 Prompt AI 服务仍需按最终 Provider 配置做一次网络 smoke；当前没有配置外部 Prompt AI endpoint，因此日常回归继续使用确定性 Fake Provider。

## 2026-09-14 · Prompt AI Provider 契约补齐

- OpenAI-compatible Prompt Adapter 支持注入测试传输层，并继续由 Capability 明确声明图片、原生视频、抽帧与音频理解边界。
- Contract Test 验证 system context、文本、真实图片 base64、可选原生视频、鉴权头、401 / 429 / 503、超时、非法 JSON、非法结构与空响应。
- 不支持的视频 / 音频路径返回稳定业务错误，不会声称已经理解媒体；HTTP 与超时统一归一化为 Provider 不可用。
- Prompt / Video Provider 合同测试合计 14 条通过。
- 修复统一验收器把“不存在匹配测试”误报为失败的问题；Scheduler 等可选阶段只有发现对应测试后才加入执行，并有单元回归测试保护。
- 最终 `python scripts/verify.py --full` 共 7 个实际阶段全部通过：后端 lint、后端测试、前端类型检查、前端测试、生产构建、Provider Contract 与桌面 / 手机 E2E。

## 2026-09-14 · 新建任务无残留 AI 增强

- 新建任务首次保存前改走项目级 `prompt-enhancement-previews`：后端校验项目与资产归属、解析真实媒体、应用同一 Prompt Skill，并可按稳定 `previousTaskId` 读取上一任务摘要。
- 草稿增强不创建 Task、不写入 `AiPromptRevision`；用户保存时才把当前 AI Prompt 落入 Task，取消编辑不会留下数据库垃圾记录。
- 已保存 Task 仍走正式增强接口并为每次增强创建独立 Revision；编辑器中新选择但尚未保存绑定的项目资产也可作为真实媒体参与增强，保存时再写入 Task Asset Binding。
- 前端只增加网关分流和编辑状态传递，没有改变当前冻结 UI 的布局、控件或文案。
- 新增后端集成测试与前端网关测试，覆盖真实媒体、上一任务摘要、跨项目资产拒绝、无 Task / Revision 残留及草稿路由分流。

## 2026-09-14 · 冻结 UI 的新版 E2E 主路径

- 移除重构前“故事板 / 生成 / 素材”复杂界面的失效断言，按当前冻结 UI 重建“项目首页 → 项目工作台 → 任务编辑 Overlay”主路径。
- E2E 入口会自动启动隔离的 ShotMill 后端、确定性 Prompt Fake Provider、临时 SQLite 数据库和独立 Vite 端口，不依赖用户开发数据或真实 GPU。
- 桌面覆盖项目创建与返回、Task 首次保存、同一 Task 的列表 / 卡片视图、双击与右键编辑、只读详情栏、项目配置、H3 `@` 资产引用和草稿 AI 增强取消无残留。
- 手机端保留当前工作区可打开且无页面级横向溢出的 viewport smoke；不把桌面悬浮交互强套到手机断言。
- `python scripts/verify.py --area e2e` 验证 12 条 Playwright 用例全部通过。

## 2026-09-13 · 真实 Frontend Gateway 与运行状态接入

- 当前简化 UI 已从运行时 Mock 数据切换到 `ProjectGateway`；默认使用 HTTP Gateway，测试使用同契约的内存 Gateway。
- 项目列表、项目创建/重命名、项目设置、工作区摘要、任务创建/读取/保存、资产导入/编辑/删除、Prompt Revision 与 AI Prompt Enhancement 已接入 `/api/v1`。
- 修复 Vite 将 `/api/v1` 错误改写成 `/v1` 的代理问题，并增加 `/media` 代理；项目资产继续只向前端暴露 `asset_id` 与 project-relative path。
- 任务编辑器保持当前布局与通俗措辞；现有任务按需加载完整编辑数据，首页和列表只读取轻量 Read Model。
- `@` 菜单现在读取项目资产，新任务也可插入 H3 风格引用；保存时仅把提示词实际引用的资产写成 Task Asset Binding。
- 修复后端 `originalFileName` 到前端只读原始文件名的映射，并修复资产标签连续输入逗号时丢字符的问题。
- AI 增强请求已改为正式后端契约，不再在开发环境静默伪造成功结果；增强后同步最新任务 revision，避免随后保存产生伪冲突。
- 项目级 SSE 已接入 Gateway；后台运行、进度、结果与项目摘要事件会刷新当前工作区，无需改变现有 UI 结构。
- 后端 API 依赖声明统一为现代 FastAPI `Annotated` 写法，恢复全仓后端规范检查。
- 当前产品 UI 作为冻结层：除真实后端引入的加载、错误与状态同步外，不主动调整布局或重新引入复杂控件。

### 当前验证

- 后端 lint、unit/integration tests 通过。
- Prompt / Video Provider contract tests 通过。
- 前端类型检查、Vitest 与生产构建通过。

### 当日仍未关闭（后续状态见 2026-09-14）

- 当日尚未配置真实 ComfyUI API workflow；该项已于 2026-09-14 完成实机闭环。
- 新建任务的无残留草稿增强协议已于 2026-09-14 完成。
- 冻结 UI 的新版 Playwright 主路径已于 2026-09-14 重建并通过。

## 2026-09-13 · Windows 启动器端口复用修复

- 修复 `1420` 已由 ShotMill Vite 占用时，Tauri 再次执行 `beforeDevCommand` 并以红字退出的问题。
- 启动器现在会主动识别 `http://127.0.0.1:1420/dev/ui`：确认是 ShotMill 时复用现有前端，并通过独立 Tauri 覆盖配置禁用重复的 `pnpm dev`。
- 若端口属于其他应用，启动器只报告占用者并退出，不会误杀其他进程。
- 新增空闲端口、ShotMill 占用、其他应用占用与 Tauri 复用配置回归测试；实际启动验证只出现 `Running DevCommand`，没有再次出现 `Running BeforeDevCommand`，桌面窗口成功打开。

## 2026-09-12 · V0.2 产品基线纠偏与 Task-first Gate S0–S12 / V0.2 Freeze

### 已完成

- 根据最新产品决策修订 `V0.2_STORYBOARD_DEVELOPMENT_TASKS.md`、`STORYBOARD_TASK_MODEL.md`、文档索引、UI 规范与项目开发边界。
- 明确 Storyboard 是分镜式 Task 交互，不是独立分镜制作工具；`1 Storyboard Card = 1 GenerationTask`。
- 明确 Task 不硬绑定为一个 Shot；一个 Task 可在内部包含 1..N 个 `TaskVisualBeat`，Beat 没有独立 Queue / Job / Result 生命周期。
- 移除 V0.2 对一级 `StoryboardShot`、`TaskShotBinding`、Shot Card、Task Band 与必选 `ResultShotSpan` 的错误要求。
- 前端 Domain `GenerationTask`、`TaskStoryboardPlacement`、`TaskVisualBeat`、`GenerationContextLink`、不可变 `Job` 与 `Result` Contract 已按 Task-first 模型落地。
- Story Order 与 Generation Context 独立存储；Job 保存完整 Task 内容、Prompt、Assets、Profile、Params 与 Context 快照。
- `/dev/ui` 默认进入“分镜式任务工作台”，中央直接显示 Task Cards；Scene Navigator 与 Inspector 均可折叠。
- Task Card 明确标识单镜头 / 多镜头 Task；单击更新 Task Inspector，双击进入现有 Task Composer。
- 增加空 Scene、6 Tasks 和 36 Tasks 三种 Mock 场景；36 Tasks 中混合单镜头与三视觉节拍 Task。
- 抽出独立 `StoryboardTaskCard`；固定代表帧、状态、进度占位、时长、资产、Profile 与多镜头标识的信息层级，状态切换不改变卡片结构。
- 默认 Storyboard Task Board 已支持单选、Ctrl/Cmd 多选、Shift 连选与 Batch Inspector。
- 支持新建空白 Task、“新建下一个”并仅继承 Generation Profile，以及复制 Task 内容。
- 复制时明确清空 Job、Result、Context 与执行状态；已有 Job / Result 历史的 Task 禁止直接删除，无历史 Task 删除前必须确认。
- 支持 Scene 内排序与跨 Scene 拖动 Task Card；移动只改写 `TaskStoryboardPlacement`，Task ID、Task 内容、Job 与 Result 均保持不变。
- 拖动触及已有 Generation Context 时不重连依赖，只将原 Context Link 标记为待复核，并在 Task Inspector 显示明确警告。
- Storyboard Task Card 支持 Ctrl/Cmd+C、Ctrl/Cmd+V、Ctrl/Cmd+D、Delete、Enter、Escape 与方向键操作。
- Scene Overview 支持快速编辑名称、摘要、地点、时间与备注，并保持状态汇总同步。
- Task Inspector 支持快速编辑 Task Name、Summary、Script Source、User Intent、计划时长与 Generation Profile，同时显示 Storyboard Frame、Visual Beats、前后邻接、Prompt / Queue 状态、Context 与 Primary Result。
- Generation Profile 由 Capability 驱动；多镜头 Task 选用不支持多镜头的 Profile 或超出时长上限时显示明确警告。
- Batch Inspector 已提供跨 Scene 移动、批量 Profile、批量资产绑定、仅将 Ready Task 入队、复制与安全删除。
- `/dev/ui` 场景控制器默认收起，避免遮挡右侧 Inspector；需要切换 Mock 密度或浮层场景时仍可随时展开。
- 新增 Script → Task Cards 工作流，支持粘贴大段剧本、从选中文本创建 Proposal 与生成确定性的 Mock AI Proposal。
- Proposal 可在创建正式 Task 前修改标题、剧本边界、User Intent、计划时长、目标 Scene 和 Task 内部 Visual Beats。
- Proposal 支持排序、删除、合并与拆分；逐条接受或“接受全部”均为显式动作，未接受时不会产生正式 GenerationTask。
- 从 Proposal 创建的正式 Task 保持 `Card = Task`，每个 Proposal 内可继续包含多个镜头式 Visual Beats。
- 新增 Asset Library，支持 Image / Video / Audio 与 Character / Scene / Prop / Reference 分类、名称和 Tags 搜索、详情预览。
- Task Asset Picker 支持预览与多选；只有“确认绑定”才更新 Task，取消不会泄漏临时选择。
- 资产业务引用统一使用 `asset_id` 与 project-relative path；新增解析函数生成包含媒体类型、相对路径与 checksum 的不可变资产快照。
- Storyboard Task 的真实资产绑定已传入 Prompt Composer，Final Prompt `@` 菜单会基于当前 Task 资产筛选并插入 `<Subject/Picture/Video/Audio N>` 引用，同时展示素材来源路径。
- Task Composer 已升级为直接编辑当前 GenerationTask；单镜头或多镜头描述统一保存在 Task 内部 `TaskVisualBeat`，不会生成独立 Storyboard Card。
- Visual Beat Strip 支持选择、修改、新增、排序和删除；Generation Profile Capability 会就地提示多镜头与最大时长不兼容。
- 新增 Provider-neutral `PromptRequest` Contract，一次性快照 Task 内容、Visual Beats、解析后的资产、前序生成 Context、后续 Story Context 与目标 Generation Profile。
- AI Prompt Revision 与人工 Final Prompt 保持独立；重新生成 AI Prompt 不覆盖人工内容，显式确认后才允许替换 Final Prompt。
- 新增完整 Ready Validation，检查 Final Prompt、资产引用、Profile Capability、计划时长、Visual Beat timing、Generation Context 与 Provider 在线状态。
- Ready Task 加入队列时会追加不可变 Job 快照，保存当时的 Task 内容、Final Prompt、Assets、Profile、Params 与 Context；已有 Job / Result 历史不被改写。
- Task 内容、Profile 或资产变化会将相关 Context Link 标记为 Stale；上游 Primary Result 变化同样传播 Context Stale。
- Inspector 已将 Task 内部 Visual Beats、Story Order 邻接与 Task 间 Generation Context 分区显示，并提供更新 Context、保留现有 Result、重编 AI Prompt、从当前 Task 向后重新生成等显式操作。
- Provider 离线状态已接入 Ready 与 Queue 流程；离线时显示可操作阻塞原因，单任务和批量入队均不会静默执行。
- 新增 Result Review 工作区，按完整 Generation Task 审核 Result，支持 Pending / Approved / Rejected 筛选、预览、通过、拒绝、批量通过、重新生成、编辑 Task 与历史查看。
- Result 保持归属 Job / Task；多镜头 Task 的 Result 只显示为一份完整结果，不按 Visual Beat 伪造多个 Shot Result。
- Set Primary 保留旧 Result 与不可变 Job 历史，并将引用旧 Primary 的下游 Generation Context 明确标记为 Stale；返回编辑会按稳定 Task ID 选中原卡片。
- 新增 Story Reel，严格按 `TaskStoryboardPlacement` 的 Story Order 预览；素材优先级为 Primary Task Result → Task Storyboard Frame → Placeholder。
- Story Reel 仅提供 Play / Pause、Previous / Next Task、Jump to Task、Current Task 与 Planned Duration；多镜头 Task Result 作为一个完整 Reel 项播放，未引入时间线、多轨、Trim、转场或关键帧控件。
- 新增 `StoryboardRepository` 契约与 `MockStoryboardRepository`，覆盖 Scene、Task Placement、Task、Visual Beats、Assets、Prompt、Context、Job、Result 与 Primary Result 的完整 Mock Repository API。
- Repository 所有读写边界使用防御性副本；Task 后续编辑不会污染已提交 Job 的内容、Prompt、资产、Profile、参数或 Context 快照。
- Repository 的 Story Order 操作只改变 Placement；已有 Task、Job、Result 与 Context 端点不被重写，受影响的 Context Link 以明确 Stale 列表进入复核。
- 高密度 Mock 增加极长标题，并与空 Scene、36 Tasks、单/多镜头 Task、Ready、Running、Failed、Context Stale 一同进入桌面端和移动端回归。

### Gate S0–S12 / V0.2 Freeze 验证

- 83 个 Vitest 测试全部通过，无未处理异步异常，其中 7 个专门验证 Mock Repository Contract。
- 66 个桌面端 / 移动端 Playwright 测试通过；桌面专属的密度与 HTML Drag 用例共 2 个在移动端按预期跳过。
- 浏览器密度用例验证 36 Task Cards，并覆盖 1366×768、1600×900、1920×1080 三档目标视口与页面级无横向溢出。
- 人工检查 1440×900 与 390×844；Ready、Queue、Prompt / Job、Story Order、Generation Context、Result Review 与 Story Reel 信息层级清楚，移动端无页面级横向溢出。
- 使用项目 `.venv` 运行 `scripts/verify.py --full`，后端 lint、后端测试、前端类型检查、83 个前端测试、生产构建、66 个桌面/移动 E2E 共 6 阶段全部通过。
- 当前 V0.2 未变更真实 Video Generation Provider；因此没有触发 ComfyUI / GPU Hardware Smoke，真实生成链路仍属于后续 Provider 接入阶段。

### 下一目标

- V0.2 Storyboard-style Task Workspace 已冻结；下一阶段应在保持 Task-first Contract 的前提下，将 Mock Repository 替换为真实 Core / SQLite 持久化，再接入独立的 Prompt Provider 与 ComfyUI Video Generation Provider。

## 2026-09-12 · Phase 0 完成，Phase 1 Task Composer 可交互原型

### 当前状态

项目已完成基础工程建设，并进入 Phase 1 UI 可交互原型阶段。任务工作区和 Prompt 编辑主链路已经可以在 `/dev/ui` 中运行；当前业务数据仍为本地 Mock，尚未接入真实数据库、Provider 或 ComfyUI 执行链路。

### 已完成

#### 工程与运行基础

- 建立 React、TypeScript、Vite 前端工程。
- 建立 Tauri 2 桌面应用骨架。
- 建立 FastAPI 后端骨架和健康检查。
- 接入并锁定 Terry React UI Library 版本。
- 建立 Windows PowerShell 7、Python、前端、浏览器端和 Tauri 验收流程。
- 参考 Rulesmd_editor 新增根目录 `启动项目.bat`，通过系统默认 PowerShell 调用 `scripts/start-dev.ps1`。
- 启动脚本会检查 Node.js、pnpm、Rust/Cargo、前端依赖指纹和 Tauri 工程，然后直接打开 Tauri 桌面开发窗口。
- `Start-UI.bat` 与 `启动 ShotMill UI.bat` 保留为同一桌面启动流程的兼容别名；`Start-UI.ps1` 保留为浏览器调试入口。

#### App Shell 与任务工作区

- 完成左侧主导航、项目顶部栏、任务卡片列表和状态展示。
- 完成任务搜索和状态筛选。
- 完成 Ctrl 多选、Shift 连续多选和批量操作栏。
- 完成任务复制与连续创建入口。
- 完成桌面端和移动端响应式布局。

#### 统一 Overlay 系统

- 完成 Dialog、Select、Popover、Tooltip、Context Menu、Toast 和 Fullscreen Preview。
- Overlay 统一挂载到 Portal 根节点，避免被滚动容器或变换节点裁切。
- 支持视口边缘避让、嵌套关闭顺序和 Escape 操作。

#### Task Composer Mock

- 完成“剧本 / 设置、Prompt、项目资产”三栏编辑界面。
- 包含 Script Source、User Intent、Generation Profile、Previous / Next Context、AI Prompt、Final Prompt、Prompt Revision、Validator、任务资产、保存状态和后台进度 Mock。
- AI Prompt 重新生成不会覆盖人工编辑的 Final Prompt。
- 用 AI Prompt 替换 Final Prompt 前必须显式确认。
- 后台状态刷新不会抢走编辑焦点，也不会重挂载编辑器节点。

#### Final Prompt `@` 资产菜单

- 参考 ComfyUI-TerryXu-nodes 的 H3 提示词编辑器实现 `@` 触发菜单。
- 菜单读取当前任务资产，并按名称、类型和引用名实时过滤。
- 菜单定位到编辑光标附近，并在桌面端和移动端自动避让视口边缘。
- 支持鼠标选择、方向键、Enter、Tab 和 Escape。
- 当前插入 H3 风格引用：`<Subject 1>`、`<Picture 1>`、`<Video 1>`、`<Audio 1>`。

### 验证结果

- 16 个组件与单元测试通过。
- 32 个桌面端和移动端 Playwright 测试通过。
- `scripts/verify.py --full` 六阶段验证全部通过。
- TypeScript 类型检查和前端生产构建通过。
- Tauri Debug 桌面应用构建通过。

### 当前边界

- Asset Library / Asset Picker 仍需实现完整的分类、搜索、多选、预览、确认和取消流程。
- 任务链目前只显示上下文摘要，尚未形成完整交互。
- Project、Scene、Task、Prompt Revision、Job、Result 等数据仍未接入持久化模型。
- `G:\AIGC\ComfyUI_Codex` 尚未接入工作流发现、参数映射、提交、进度监听和结果回收。
- 真实生成 Provider、失败重试、取消任务、历史结果和导出仍待开发。

### 下一步建议

1. 完成 T1.6 Asset Library / Asset Picker Mock。
2. 完成 T1.7 Task Chain / Context Mock。
3. 固化上述 UI 的交互与视觉回归测试。
4. 进入 Phase 2 数据模型、持久化和 ComfyUI 执行链路。

## 2026-09-22 · 全局底栏与分层运行中心

- 底栏移到 App 外层，首页与项目页共用设置、全局运行摘要和运行中心；内容区自适应剩余高度。
- 新增 `/api/v1/projects/runtime`，在后端查询层汇总各项目增强与视频记录，复用原有运行 Read Model，不加载媒体预览。
- 运行中心为“项目 → 提示词增强 / 视频生成 → 任务状态”三级折叠，保留耗时、错误、取消待执行项和重试失败增强。操作携带所属项目 ID。
- 全局记录每 5 秒更新，项目切换与操作后立即更新；折叠状态不因刷新重置，读取失败显示重连状态。
- 前后端 verify、跨项目 API 集成测试、全局底栏与三级折叠 Playwright 均通过；本地服务已更新并检查实际 6 个项目记录。

## 2026-09-22 · 运行中心队列操作与层级缩进

- 项目内按提示词增强 / 视频生成分组，任务行提供上移、下移、挂起、恢复、移除。正在执行的任务不接受这些操作。
- 排序改变同项目同类型待执行任务在真实队列中的次序；暂停与顺序通过独立 runtime_controls 表保存，不改写 Job 输入快照。新调度器启动后沿用保存的次序和暂停状态。
- 移除待执行项将其取消；移除历史项仅隐藏运行中心记录，Job、Result 与 AI Revision 均保留。恢复重新唤醒队列，重复投递由既有执行状态保护。
- 分类层、任务层各增加到 28px 缩进，项目块间距增至 18px。
- 双队列集成测试覆盖顺序、挂起、恢复、重建调度器、跨项目拒绝、运行中拒绝、取消与快照保留；前后端 verify 和运行中心 Playwright 两项通过。
- 本地数据库升级前已备份至 .artifacts/runtime-controls-before.sqlite，服务已更新，原有 6 个项目记录可读取。
