# ShotMill 文档索引

ShotMill 的开发文档按职责拆分，避免单个文档无限膨胀。开发者 / Codex 应按任务读取必要文档。

## 当前开发任务

2026-09-20：指定工作流的“异星边境”8 项批量生产已实跑通过，详细进展见 [开发记录](./DEVELOPMENT_LOG.md) 和 [验收记录](./UX_ACCEPTANCE_BASELINE.md)。这不代表 V0.4 路线图及所有 UI/UX 待办已经完成。ComfyUI 节点包安装与升级说明见 [Bridge 文档](../integrations/comfyui_shotmill/README.md)。

- [UI/UX 验收底线与实测记录](./UX_ACCEPTANCE_BASELINE.md)
  行业规范依据、可测量的交互质量要求与真实用户流程缺陷清单。所有 UI 优化同时参考，不能仅以截图作为完成依据。

- [V0.4 Batch Production Pipeline 开发任务](./V0.4_BATCH_PRODUCTION_PIPELINE.md)  
  **当前主执行清单。** 在 V0.3 已完成的后端基础上，实现批量 AI Prompt Enhancement、Prompt Enhancement Queue、人工 Prompt 审核、批量 Video Generation、双 Queue Runtime 与对应测试。默认 Prompt AI Profile 为 Qwen3.8，但 Core 保持 Provider / Model 无关。

- [V0.9 Batch Review Workflow UI 规范](./UI_V0.9_BATCH_REVIEW_WORKFLOW.md)  
  **当前 UI 增量规范。** 定义工作台批量 AI 增强、Task 状态、多选批量操作、运行中心、连续审核、上一个 / 下一个、确认并下一个，以及批量视频生成前的审核 Gate。

- [ShotMill UI 开发规则](./UI_DEVELOPMENT_RULES.md)  
  **所有 UI / CSS / Overlay / Dialog / UI Library 集成修改的强制实现红线。** 定义组件边界、CSS 所有权、弹性布局、滚动条原则、信息密度、标签语义、主题颜色、Portal、垂直居中、UI Library Showcase、调试顺序与提交前检查。该文档吸收 Rulesmd Editor 已验证的 UI 开发经验，目标是减少 ShotMill 后续重复打磨与 fix CSS 堆叠。

## 当前必须优先阅读

- [AI 提示词增强专项架构](./AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md)  
  **AI Prompt Enhancement 的长期最高优先级架构文档。** 定义真实多模态输入、可选项目背景、可选上一任务摘要、H3 / Seedance 独立 Skill、Provider 媒体适配、revision 与 Capability。凡涉及 AI 提示词增强实现，优先读此文档。

- [V0.8 AI 提示词增强与历史版本 UI 规范](./UI_V0.8_AI_PROMPT_ENHANCEMENT.md)  
  定义 AI 增强历史下拉、空状态、可重复增强、Prompt Source 和用户 / AI 版本选择。V0.9 在此基础上增加批量增强与连续审核，不替换单任务增强行为。

- [V0.8 后端适配：AI 提示词增强与历史版本](./V0.8_BACKEND_AI_PROMPT_ENHANCEMENT.md)  
  **V0.8 版本增量。** 说明历史版本和现有前端过渡字段。长期实现以 AI 提示词增强专项架构为准。

- [V0.6 项目配置与 H3 提示词编辑规范](./UI_V0.6_PROJECT_CONFIG_H3_EDITOR.md)  
  **当前涉及项目工作台顶部、项目配置、结果播放和 H3 提示词双模式的基础文档。** 定义返回首页、项目配置、卡片/列表共用工具栏、Result 播放，以及用户/AI 提示词各自的可视化/文本模式。

- [V0.6 后端适配增量](./V0.6_BACKEND_DELTA.md)  
  **V0.5 Frontend Adapter 的增量。** 定义项目简介、AI 项目背景开关、项目资产 CRUD、Task Prompt Source、H3 编辑器偏好和 Result 播放数据。

- [V0.5 Terry导演工作台 UI 基线](./UI_V0.5_PROJECT_WORKSPACE.md)  
  定义项目首页、项目工作台、列表 / 卡片双视图、右侧只读栏、底部状态栏和任务编辑弹窗的总体结构。未被后续版本覆盖的规则继续有效。

- [V0.5 任务编辑窗细化规范](./UI_V0.5_TASK_EDITOR_REFINEMENT.md)  
  定义任务标题区、紧凑生成参数、片段承接区间、固定少量候选项使用分段控件，以及下拉菜单宽度规则。

- [V0.5 后端适配新前端方案](./V0.5_BACKEND_FRONTEND_ADAPTER.md)  
  后端 Frontend Adapter 基线。ProjectSummary、ProjectWorkspaceView、TaskSummary、TaskEditorView、Runtime、推荐 API、SSE 和 Gateway 继续有效；V0.4 在这些 Read Model / Gateway 边界上增加 Batch / Review 状态。

- [Director Mode UI 开发规范](./UI_DIRECTOR_MODE_GUIDE.md)  
  保留“查看与编辑分离、右侧只读、任务编辑使用悬浮窗、防参数墙、全中文”等通用规则。

## 已完成基础版本

- [V0.3 Backend Foundation 开发任务](./V0.3_BACKEND_FOUNDATION_DEVELOPMENT_TASKS.md)  
  **已完成后端基础与首个 ComfyUI 实机闭环。** B0-B7 已落地：SQLite / Repository、Project / Asset / Task、Frontend Adapter、AI Prompt Enhancement、Job / Result、ComfyUI Provider、Runtime Events 与真实 Frontend Gateway。V0.4 必须建立在这些边界上，不得另起第二套基础设施。

## 领域与架构文档

- [Storyboard-style Task Workspace 数据模型](./STORYBOARD_TASK_MODEL.md)  
  核心领域模型。`GenerationTask`、Story Order、Context、Job、Result 等内部关系仍然有效，即使当前 UI 不直接展示这些概念。

- [产品与架构规划](./ShotMill_产品与架构规划.md)  
  产品边界、Provider 架构、Task / Job / Result、Context、Queue、Remote Monitor、整体技术方向。

- [UI / UX 开发规范](./UI_UX_SPEC.md)  
  通用视觉、Overlay、可访问性、开发模式与视觉回归基础协议。产品体验目标看此文档；实现红线看 `UI_DEVELOPMENT_RULES.md`。

- [测试策略](./TEST_STRATEGY.md)  
  Unit / Integration / Contract / E2E / Hardware Smoke、Fake Provider、故障注入和回归策略。

## 历史开发任务

- [V0.2 Storyboard-style Task Workspace 开发任务](./V0.2_STORYBOARD_DEVELOPMENT_TASKS.md)  
  已完成能力与领域回归基线。旧三栏 / Storyboard 默认界面不得覆盖当前 UI 决策。

- [V0.1 第一版开发任务](./V0.1_DEVELOPMENT_TASKS.md)  
  第一版基础工程与总体 Phase，仅保留未被后续版本覆盖的内容。

- [开发记录](./DEVELOPMENT_LOG.md)  
  已实际完成的功能、验证结果和历史记录。规划中的 V0.4 能力不得提前写成“已完成”。

---

# 当前产品心智

默认产品结构固定为：

```text
项目首页
  ↓ 选择 / 新建项目
项目工作台
  ├─ 返回首页
  ├─ 项目配置
  ├─ 列表模式
  ├─ 卡片模式
  ├─ 主内容区新建任务卡 / 创建行
  ├─ 批量操作 contextual bar
  ├─ 右侧只读信息 / Result 预览
  └─ 底部 Prompt / Video 运行摘要
       ↓ 双击 / 右键 / 新建任务
任务编辑弹窗
       ├─ 上一个 / 下一个任务
       ├─ 用户 / AI增强提示词来源
       ├─ 可视化 / 文本显示模式
       ├─ AI增强历史 / 可重复增强
       └─ 确认并下一个
```

不再使用 `故事板 / 生成 / 素材` 作为三个默认一级页面。

V0.4 的生产心智固定为：

```text
AI 批量准备 Prompt
        ↓
人集中逐项审核
        ↓
GPU 批量生成视频
```

现有单任务 AI 增强与单任务生成能力继续存在，批量流程只是在其上增加正式调度与审核 Gate。

底层领域关系仍然满足：

```text
GenerationTask 可包含 1..N Visual Beats
Story Order 与 Generation Context 独立
Task 是可变生产意图
Prompt Enhancement Job 是不可变增强输入快照
Video Job 是不可变生成执行快照
Result 属于 Job / Task 历史
Prompt Queue 与 Video Queue 独立
```

这些内部关系不能直接决定默认 UI 信息架构。

---

# 当前实施顺序

```text
V0.3 Backend Foundation（已完成）
   ↓
V0.4 Batch Production Pipeline
   ↓
C0 Prompt Review Foundation
   ↓
C1 Prompt Batch Persistence
   ↓
C2 Prompt Queue Scheduler / Qwen3.8 default profile
   ↓
C3 Batch Review UI
   ↓
C4 Batch Video Generation
   ↓
C5 Runtime / Regression
```

V0.4 的关键原则：

```text
单任务增强继续存在
批量增强不复制 Prompt Enhancement 逻辑
Prompt Enhancement Queue 由后端持久化 / 调度
增强完成 != 可以直接批量生成
人工确认当前有效 Prompt 后才进入默认批量生成 Gate
Prompt Queue 与 Video Queue 可以同时运行
```

AI 提示词增强实现优先遵守：

```text
AI_PROMPT_ENHANCEMENT_ARCHITECTURE
   ↓
V0.4_BATCH_PRODUCTION_PIPELINE
   ↓
V0.8_BACKEND_AI_PROMPT_ENHANCEMENT（版本迁移）
   ↓
V0.6_BACKEND_DELTA
   ↓
V0.5_BACKEND_FRONTEND_ADAPTER
```

UI 实现优先遵守：

```text
UI_DEVELOPMENT_RULES               # 实现红线 / CSS / 组件边界 / Overlay / 弹性布局
   +
UI_UX_SPEC                         # 通用体验与交互原则
   ↓
UI_V0.9_BATCH_REVIEW_WORKFLOW      # 当前版本具体批量 UI
   ↓
UI_V0.8_AI_PROMPT_ENHANCEMENT
   ↓
UI_V0.6_PROJECT_CONFIG_H3_EDITOR
   ↓
UI_V0.5_PROJECT_WORKSPACE / TASK_EDITOR_REFINEMENT
   ↓
UI_DIRECTOR_MODE_GUIDE
```

---

# 文档冲突优先级

发生冲突时：

1. 明确的新需求 / 最新决策；
2. **`V0.4_BATCH_PRODUCTION_PIPELINE.md`：当前批量生产、Prompt Review、双 Queue 和 Batch Generation 执行顺序、Gate 与 Freeze 标准；**
3. **`UI_DEVELOPMENT_RULES.md`：所有 UI 实现、CSS 所有权、组件边界、Overlay、主题、弹性布局、信息密度与调试红线；**
4. **`UI_V0.9_BATCH_REVIEW_WORKFLOW.md`：当前工作台批量增强、连续审核、批量生成与运行中心 UI；**
5. **`AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md`：AI 提示词增强输入、媒体、上下文、Skill、Provider 与 revision 长期架构；**
6. `V0.3_BACKEND_FOUNDATION_DEVELOPMENT_TASKS.md`：已完成的后端基础边界与不可变 Job / Result 基线；
7. `UI_V0.8_AI_PROMPT_ENHANCEMENT.md`：单任务 AI 增强 UI、历史、Prompt Source；
8. `UI_V0.6_PROJECT_CONFIG_H3_EDITOR.md`：项目工作台顶部、项目配置、H3 Prompt 与 Result；
9. `UI_V0.5_PROJECT_WORKSPACE.md`：总体页面结构与交互；
10. `UI_V0.5_TASK_EDITOR_REFINEMENT.md`：任务配置、Context、控件细化；
11. `V0.8_BACKEND_AI_PROMPT_ENHANCEMENT.md` + `V0.6_BACKEND_DELTA.md` + `V0.5_BACKEND_FRONTEND_ADAPTER.md`：版本适配和前后端边界；
12. `UI_DIRECTOR_MODE_GUIDE.md`：查看/编辑分离、防参数墙、用户术语等未冲突规则；
13. `STORYBOARD_TASK_MODEL.md`：领域关系；
14. `UI_UX_SPEC.md`：通用 UI 行为与体验；
15. `TEST_STRATEGY.md`：测试与验收；
16. `ShotMill_产品与架构规划.md`：其他核心架构；
17. V0.2 / V0.1：历史能力基线。

根目录 `AGENTS.md` 保持为开发导航与不可违反规则汇总。
