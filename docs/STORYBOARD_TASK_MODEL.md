# ShotMill Storyboard-style Task Workspace 数据模型

> 状态：架构基线  
> 最后更新：2026-09-12  
> 决策来源：Storyboard 在 ShotMill 中是一种分镜式交互方式，不是独立分镜制作工具。

本文用于约束 V0.2 的 Task、Job、Result、Context 与 Storyboard-style UI；与用户最新决定及[当前开发计划](./CURRENT_DEVELOPMENT_PLAN.md)冲突时，以后者为准。

**2026-10-11 补充：** 用户要求增加 TerryDirector 风格的导演时间线，一个片段就是一个 Task，与列表／卡片共用任务和编辑器。允许任务时间编排，不新增独立 Clip 内容、队列或工程存储，不将 Task 内部 Beat 拆成任务。时间位置、故事顺序与生成承接关系保持独立；调整计划时长不裁剪历史 Result。下文 V0.2 的“不提供 NLE 时间线能力”是历史范围，不禁止这次导演时间线需求，也不意味着要开发完整剪辑器。

---

## 1. 核心结论

**Storyboard 中每一张可操作卡片都是一个 `GenerationTask`。**

这里的 Storyboard 指按故事顺序排列画面化 Task 卡片的交互方式，不表示系统必须建立一套独立的 Shot 实体、Shot Card 和 Task Band。

一张 Task Card 可以表达：

- 单一镜头意图；
- 同一段生成视频里的多个镜头 / 多个视觉节拍；
- 一个长镜头或 continuation 任务；
- 尚未完成拆镜描述的草稿任务。

因此严禁重新引入以下假设：

```text
1 Storyboard Card = 1 Shot = 1 Generation Task
```

正确表达是：

```text
1 Storyboard Card = 1 Generation Task
1 Generation Task = 1..N 个可选的视觉节拍描述
1 Generation Task submission = 1 immutable Job
1 Job = 0..N immutable Results
```

视觉节拍只是 Task 内部用于组织 Prompt 的描述，不是 V0.2 必须独立持久化、独立排队或独立显示为卡片的生产对象。

---

## 2. 三种关系必须独立

### 2.1 Story Order

表示 Task Card 在 Scene 中的叙事顺序：

```text
Task A → Task B → Task C
```

通过 `TaskStoryboardPlacement` 表达，不使用 Context Link 充当排序关系。

### 2.2 Task Content

表示一次 Provider 调用要生成的完整内容。Task 内部可以有一个或多个 `TaskVisualBeat`：

```text
Task A
├─ Beat 1 · 0-4s · 远景建立雨夜码头
├─ Beat 2 · 4-9s · 中近景人物停在门前
└─ Beat 3 · 9-15s · 特写推门
```

`TaskVisualBeat` 不拥有 Queue / Running / Result 等独立生命周期。

### 2.3 Generation Context

表示 Task 之间的生成依赖与续接关系：

```text
Task A ── Visual / Audio / Latent / Semantic ──> Task B
```

移动 Task Card 只改变 Story Order，不得静默改写 Generation Context。

---

## 3. 推荐领域对象

### 3.1 Scene

```text
Scene
├─ id
├─ number                 # 展示编号，可重算
├─ title
├─ summary
├─ order_key
├─ location
├─ time_of_day
└─ notes
```

Scene 是 Storyboard-style 工作台面的分区，可为空、折叠、排序。

### 3.2 TaskStoryboardPlacement

```text
TaskStoryboardPlacement
├─ task_id
├─ scene_id
└─ order_key
```

它只表达当前工作区中的位置。Task ID 稳定，展示编号可根据位置重算。

### 3.3 TaskVisualBeat

```text
TaskVisualBeat
├─ id
├─ label
├─ description
├─ planned_start?
├─ planned_end?
├─ shot_size?
├─ camera_movement?
└─ notes?
```

它是 Task 内可选的 Prompt 结构化信息：

- 单镜头 Task 可以不创建或只创建一个 Beat；
- 多镜头 Task 可以创建多个 Beat；
- Beat 不出现在一级导航、任务队列或独立卡片列表中；
- Beat 不保存唯一 `task_id`，因为它直接隶属于当前 Task 内容；
- V0.2 不提供完整分镜工具级的 Shot 管理能力。

### 3.4 GenerationTask

```text
GenerationTask
├─ id
├─ number
├─ title
├─ summary
├─ script_source
├─ user_intent
├─ storyboard_frame
├─ visual_beats[]
├─ asset_bindings[]
├─ generation_profile_id
├─ ai_prompt
├─ final_prompt
├─ prompt_revisions[]
├─ generation_params
├─ context_link_ids[]
├─ state
├─ job_ids[]
└─ primary_result_id?
```

GenerationTask 同时是：

- Storyboard 中的可视卡片对象；
- Task Composer 的编辑对象；
- Ready / Queue / Running / Failed 的状态载体；
- Provider 提交前的可变生产意图。

### 3.5 StoryboardFrame

```text
StoryboardFrame
├─ source_type            # placeholder / imported-image / asset / video-frame / result-frame
├─ source_id?
├─ preview_url?
├─ frame_time?
└─ updated_at
```

它是 Task Card 的封面或代表帧，不意味着这张卡只生成一个镜头。

### 3.6 GenerationContextLink

```text
GenerationContextLink
├─ id
├─ source_task_id
├─ target_task_id
├─ kind                   # semantic / visual / audio / latent / native / fallback
├─ source_result_id?
└─ stale
```

Context 默认定义在 Task 边界。

### 3.7 Job

Job 是 Task 每次提交时形成的不可变执行快照，至少保存：

```text
Job
├─ id
├─ task_id
├─ task_content_snapshot
├─ final_prompt_snapshot
├─ assets_snapshot
├─ generation_profile_snapshot
├─ params_snapshot
├─ context_snapshot
└─ created_at
```

Task 后续修改、重排或增加视觉节拍，不得改变历史 Job。

### 3.8 Result

```text
Result
├─ id
├─ job_id
├─ video_url
├─ preview_url?
├─ metadata
└─ review_state
```

Result 属于 Job。一个多镜头 Task 的 Result 仍是一份完整生成结果，不需要为了迎合卡片布局被复制成多个 Shot Result。

如果未来需要镜头级回看，可以在 Result metadata 中增加可选时间提示；它不构成 V0.2 Storyboard Card 的身份基础。

---

## 4. 状态归属

以下状态全部属于 GenerationTask：

```text
Draft
Prompt Generating
Prompt Ready
Ready
Queued
Running
Completed
Failed
Blocked
Context Stale
```

`TaskVisualBeat` 不拥有独立运行状态。

`Job` 与 `Result` 是历史记录，不复用 Task 的可变状态字段。

---

## 5. Capability Driven

Ready Validation、时长警告与多镜头能力由 Generation Profile Capability 决定，例如：

```text
multi_shot_prompt = true
max_duration_seconds = 15
continuation = true | false
```

Core 不得写死 H3 或 15 秒。H3 专属语法只存在于 Prompt Skill、Adapter、Profile 或 Validator。

---

## 6. Storyboard UI 表达

视觉主对象是 Task Card：

```text
┌────────────────────────────┐
│      Storyboard Frame      │
├────────────────────────────┤
│ Task A · READY · 15s       │
│ 抵达仓库并推门             │
│ 3 个视觉节拍 · 3 项资产    │
└────────────────────────────┘
```

不得再同时绘制一套 Shot Cards 与 Task Bands。用户应能一眼看出：

1. 每张卡就是一次生成任务；
2. Task 可能包含多个镜头描述；
3. Task 的计划时长、Profile 与运行状态；
4. Task 与前后 Task 的 Context 关系；
5. 卡片顺序与生成依赖是两回事。

交互语义：

- 单击 Task Card：选中并更新 Task Inspector；
- 双击 Task Card：进入 Task Composer；
- Ctrl/Cmd、Shift：多选 Task；
- 拖动 Task Card：调整当前 Story Order / Scene placement；
- 移动卡片不得改写 Job、Result 或 Context Link。

---

## 7. Story Reel

Story Reel 按 `TaskStoryboardPlacement` 的 Story Order 播放每个 Task 的 Primary Result；没有结果时使用 Task 的 Storyboard Frame 或 Placeholder。

V0.2 只提供播放、暂停、Previous / Next Task、Jump to Task 与当前 Task 高亮，不提供 NLE 时间线能力。

---

## 8. 迁移规则

早期代码中的 `ShotTask` 若本质上是一次生成生产单，应迁移为 `GenerationTask`，而不是拆成 `StoryboardShot + GenerationTask` 两套强制对象。

旧设计中的以下结构不再是 V0.2 必需 Contract：

- 一级 `StoryboardShot` 集合；
- `TaskShotBinding`；
- 独立 Shot Card；
- Generation Task Band；
- 必选 `ResultShotSpan`。

未来若产品确实需要专业 Shot 管理，可另立版本和迁移方案，不能反向改变 V0.2 中“一张卡就是一个 Task”的交互身份。

---

## 9. 不可违反的规则

1. **1 Storyboard Card = 1 GenerationTask。**
2. **Task 不硬绑定为一个 Shot；可描述一个或多个镜头 / 视觉节拍。**
3. **Storyboard 是交互方式，不是独立分镜制作工具。**
4. **Story Order != Generation Context。**
5. **Task 是可变意图；Job 是不可变执行快照；Result 是不可变输出记录。**
6. **Ready / Queue / Running 等执行状态属于 Task。**
7. **Result 属于 Job，不因多镜头 Prompt 被伪造为多个结果。**
8. **AI Prompt 不得自动覆盖人工 Final Prompt。**
9. **H3 能力通过 Profile / Capability 表达，不写死 Core。**
10. **Storyboard-style 工作区不是 NLE。**
