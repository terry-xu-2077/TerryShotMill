# ShotMill 文档索引

## 当前入口与冲突优先级

1. 用户的最新明确决定与项目根目录 [AGENTS.md](../AGENTS.md)。
2. [当前开发任务计划](./CURRENT_DEVELOPMENT_PLAN.md)：**唯一任务状态表**，采用🟢已完成、🟡未验收、🔵进行中、⚪未进行四态。
3. [已完成能力的验收依据](./ACCEPTANCE_EVIDENCE.md)：只记录已发生的验证及边界，不发布待办。
4. 对应领域／UI／测试规范；有冲突时不得从旧版本号推断其优先级。

提示词增强与审核均可选，不是生成门禁；任务编辑器没有“确认并下一个”。ShotMill 专注视频生产，笔记本使用解压即用的 Windows 绿色包运行完整前后端，没有安装器。用户选择位置保存／打开普通工程文件，不为项目建数据库；应用设置独立保存。本地素材导入只引用原文件，不复制到项目目录或全局库，多项目可引用同一文件。ZIP 收齐项目依赖（包含项目目录外素材和结果）后完整归档，避免搬走后缺文件；ZIP 不是日常保存方式。当前全局数据库存项目、素材复制入库的实现尚未满足这一边界，优先任务见 B0；P0 记录保留为历史成果，不强制新架构沿用文件库。现有项目全部为测试项目，无需旧格式兼容；只将最近更新的一个项目一次性转成新格式工程，其余不迁移。不建立通用迁移系统或自动清理工程。

客户端断线／退出后的状态与结果恢复保留；生成中的任务因服务器退出而中断则标为失败、说明已知退出原因，由用户手动重跑。尚未提交的后续视频任务在服务器未响应时挂起，显示“服务器未响应”，保留排队输入，由用户重试提交。不自动续算或重新提交；已完成并保存的结果在服务器重启后仍可取回。旧版强制审核流程、日常跨项目物理副本与前端独立热更新方案均已废止。历史长篇计划已从工作树移除，仍可从 Git 历史查阅，不作为当前开发指令。

日常执行以 [AGENTS.md 的默认开发策略](../AGENTS.md) 为准：一个小交付、最小相关测试、通过即停；未经用户明确授权不运行全量验证。历史验收记录不自动形成今天的重测任务，目录中的异常场景不自动形成新增开发需求。

当前计划按目标架构安排为 **B0 工程文件与素材引用 → B5 导演时间线 → B2 ZIP 归档 → B4 视频任务状态 → B3 一次真实视频 → B1 绿色包交付**。保留原编号，B5 为用户新增需求：参考 TerryDirector，一个片段就是一个任务卡，与列表／卡片共用任务和编辑器。其他可复用能力是候选，不自动追加任务。P0 详细记录已移到验收依据。下一项仅实施 B0 的工程保存／打开，不提前组装整包或重跑历史验收。

## 开发时按领域阅读

先定位本次改动涉及的章节，已读且未变的内容不重复全文读取；下表不是每轮全部必读清单。

| 工作 | 按需查阅的领域文档 |
| --- | --- |
| UI、CSS、弹窗或共享控件 | [UI 开发规则](./UI_DEVELOPMENT_RULES.md)、[UI/UX 规范](./UI_UX_SPEC.md) |
| AI 提示词增强 | [AI 提示词增强架构](./AI_PROMPT_ENHANCEMENT_ARCHITECTURE.md)、[V0.8 UI 基线](./UI_V0.8_AI_PROMPT_ENHANCEMENT.md) |
| 项目工作台与任务编辑器 | [V0.5 项目工作台](./UI_V0.5_PROJECT_WORKSPACE.md)、[任务编辑细化](./UI_V0.5_TASK_EDITOR_REFINEMENT.md)、[V0.6 项目配置与 H3](./UI_V0.6_PROJECT_CONFIG_H3_EDITOR.md) |
| 后端／前端适配 | [V0.3 后端基础](./V0.3_BACKEND_FOUNDATION_DEVELOPMENT_TASKS.md)、[V0.5 适配](./V0.5_BACKEND_FRONTEND_ADAPTER.md)、[V0.6 增量](./V0.6_BACKEND_DELTA.md)、[V0.8 增量](./V0.8_BACKEND_AI_PROMPT_ENHANCEMENT.md) |
| Storyboard／Task／Context | [核心领域模型](./STORYBOARD_TASK_MODEL.md)、[产品架构](./ShotMill_产品与架构规划.md) |
| 测试与验收 | [测试策略](./TEST_STRATEGY.md)、[UX 验收基线](./UX_ACCEPTANCE_BASELINE.md) |
| Bridge 固定快照 | [集成说明](../integrations/README.md)、[结果保留策略](./BRIDGE_RESULT_RETENTION.md) |
| Windows 绿色包 | [打包说明](../packaging/README.md) |

## 历史背景，不作为当前任务清单

- [开发日志](./DEVELOPMENT_LOG.md)：逐次实现和测试记录；其中早期“下一步”只反映当时状态。
- [V0.1 任务](./V0.1_DEVELOPMENT_TASKS.md)、[V0.2 任务](./V0.2_STORYBOARD_DEVELOPMENT_TASKS.md)：版本历史，不恢复旧三栏主界面。
- [查看与编辑分离指南](./UI_DIRECTOR_MODE_GUIDE.md)：未与当前决策冲突的原则仍适用。
- [Agent 接入计划](./AGENT_ACCESS_PLAN.md)：独立未来方向；状态以当前任务计划为准。

修改进度时只更新 [当前开发任务计划](./CURRENT_DEVELOPMENT_PLAN.md)，写明日期、证据、剩余验收。不要在其他文档重建平行勾选清单。
