# ShotMill 测试策略

> 状态：持续实施
>
> 最后更新：2026-10-11

本文件定义 ShotMill 的自动测试、回归测试、故障注入和 Codex 验收原则。

当前默认采用快速局部验证：先选能证明本次行为的单用例或单文件，必要时再扩大到直接受影响的模块；通过即停，不重复跑同一套检查。只验证真实需求与相关失败路径，不因假设风险增加防御框架或产品复杂度。纯文档不运行应用测试。未经用户明确授权，不得运行全量或等价全量验证；发布和高风险标签也不构成授权。

目标不是追求形式上的测试覆盖率，而是让以下行为能够被机器持续验证：

- 批量任务可稳定运行
- Provider 可替换
- Scheduler 可恢复
- Task Chain / Context 不因异常进入错误状态
- Bug 修复后不再复发
- Codex 能在最少人工干预下完成“实现 → 测试 → 修复 → 验收”闭环

---

## 1. 总体测试金字塔

```text
                 Hardware Smoke
                      ▲
                    E2E
                      ▲
           Integration / Contract
                      ▲
                 Unit Tests
```

常规开发以 Unit + Integration + Contract 为主。

真实 GPU / ComfyUI / 视频模型只在必要时做 Hardware Smoke，不应成为日常回归测试的依赖。

---

## 2. Unit Tests

后端：`pytest`  
前端：`Vitest + React Testing Library`

重点覆盖：

- Task 状态转换
- Task 复制 / 插入 / 继承参数
- Asset 项目隔离和路径处理
- Prompt Revision
- Validator
- ContextLink
- Context Stale
- Primary Result
- Queue 优先级
- Scheduler DAG 计算
- Provider Capability 匹配
- Generation Profile 参数校验
- 数据库 CRUD / migration

Unit Tests 应快速、确定、无网络、无真实模型依赖。

---

## 3. Integration Tests

验证跨模块行为：

```text
Task
→ Ready Validation
→ Queue
→ Scheduler
→ Provider
→ Job
→ Result
→ Context / Downstream Task
```

重点验证：

- 多任务批量执行
- Task Chain 依赖
- 上游失败 / 下游阻塞
- Retry
- Cancel
- Pause / Resume
- App 重启恢复
- Provider 重连
- Result 回收
- Primary Result 替换
- Context Stale

Integration Tests 默认使用 Fake Provider，不依赖真实 GPU。

---

## 4. Provider Contract Tests

所有 Prompt Provider 和 Video Generation Provider 必须通过统一契约测试。

### Prompt Provider Contract

至少验证：

- capability declaration
- text input
- multimodal input（按 capability）
- system context
- structured output（若支持）
- timeout
- authentication error normalization
- invalid response handling
- cancellation（若支持）

### Video Generation Provider Contract

至少验证：

- capability declaration
- validate task
- submit job
- status / progress
- cancel
- collect result
- timeout
- provider unavailable
- duplicate completion event
- unknown remote job id
- context export / continuation（按 capability）

新增 Provider 时，不允许只做人工验证。

---

## 5. Fake Provider

测试基础设施必须包含：

```text
FakePromptProvider
FakeVideoProvider
```

Fake Video Provider 可配置：

- immediate_success
- delayed_success
- fail_at_progress
- fail_once_then_success
- disconnect
- timeout
- cancel_success
- cancel_race_with_complete
- duplicate_complete_event
- unknown_job
- no_context_support
- last_frame_only
- latent_context_supported
- audio_context_supported

Fake Provider 应输出可预测结果，便于断言 Scheduler / Job / Result 状态。

### UI 的真实数据 / 假数据模式

前端只维护一套 `HttpProjectGateway`，两种模式都请求同一组 `/api/v1` 契约：

- 真实模式连接正式后端、持久化数据与按配置启用的真实 Provider。
- 假数据模式连接后端拥有的独立假 API；假 API 复用正式 Route、Schema、Frontend Adapter、SQLite 与业务 Service，仅替换临时数据和外部 Provider。
- 假数据模式不得在 React 组件内注入第二套字段或绕开 HTTP Gateway。
- 假 API 与真实 API 的 OpenAPI paths / schemas 必须有 Contract Test 保证一致。
- 仓库内 `contracts/openapi.json` 必须由后端脚本生成，并通过快照测试防止过期。

内存 Mock Gateway 可继续用于快速单元测试，但不能代替 HTTP 假 API 的联调与契约验证。

---

## 6. Failure Injection

按本次改动涉及的行为选择正常与异常路径。以下是可复用的领域场景目录，不是每次开发必跑的清单；保留有效业务回归和数据安全测试，不为无关假设新增机制。

第一批场景：

```text
FS-001 Provider 在 60% 断线
FS-002 ShotMill 在 Running Job 中退出并重启
FS-003 Provider 重启后远端 Job 仍存在
FS-004 Provider 重启后远端 Job 丢失
FS-005 Result 已生成但回调丢失
FS-006 duplicate completed event
FS-007 cancel 与 completed 同时发生
FS-008 Asset 文件被移动 / 删除
FS-009 上游 Task 失败，下游等待
FS-010 上游 Primary Result 替换，产生 Context Stale
FS-011 数据库 migration 失败
FS-012 输出文件写入失败
FS-013 磁盘空间不足
FS-014 Provider 返回非法 payload
FS-015 API timeout / rate limit
```

生产业务 Bug 应有可复现的回归覆盖；已有场景能准确覆盖时直接复用，无需为同一行为重复编号或造测试。

---

## 7. E2E

使用 Playwright。

默认启动：

```text
ShotMill Backend
+ Desktop React
+ Mobile React
+ Fake Providers
```

当前 V0.8 冻结 UI 的核心桌面 E2E：

```text
创建项目
→ 打开项目工作台
→ 创建 / 编辑 Task
→ 在列表与卡片视图间保持同一 Task
→ 使用 H3 @ 资产引用
→ 草稿 AI 增强
→ 保存或取消
→ 验证只读任务详情与项目配置 Overlay
```

Queue、Context、Result / Primary Result 等后端行为现阶段由 Integration / Contract Test 覆盖；对应产品 UI 明确恢复后，再把它们加入 E2E，不得为了旧测试恢复已删除的复杂界面。

当前手机 E2E：

```text
打开项目首页
→ 打开项目工作台
→ 验证关键入口可见
→ 验证无页面级横向溢出
```

Remote Monitor 尚未进入当前产品 UI，在其正式开发前不保留虚假 E2E。移动端优先使用 Playwright viewport 自动回归，真实手机只做阶段性体验测试。

---

## 8. Hardware Smoke

真实模型测试不进入每次开发循环。

只有改动必须依赖真实模型才能确认，或用户明确要求时，才执行受影响 Provider 的最小 Hardware Smoke。发布或 Adapter 重大修改不自动要求遍历所有模型；以下项目按本次变化选用：

### ComfyUI / 当前视频模型

- 生成一个独立 Task
- 生成一条两段连续 Task Chain
- 验证视频文件存在
- 验证可解码
- 验证基本时长 / 分辨率
- 验证 Job / Result 元数据
- 验证 Context Cache（若 Provider 支持）

### Prompt Provider

- 本地 VLM Smoke
- 一个 OpenAI-compatible API Smoke
- 多模态输入 Smoke

生成质量和美术判断仍由人工完成。

---

## 9. Regression Test First

业务 Bug 修复默认流程：

```text
1. 选择可复现 Bug 的最小自动测试；已有失败测试可复用
2. 确认测试失败
3. 修代码
4. 确认该测试通过
5. 仅在当前测试不能覆盖影响时，补跑直接相关的检查
6. 保留测试永久参与回归
```

纯视觉、样式或文案问题可用最小复现和目测验证，不必为了形式新增自动化测试；若改变交互或业务行为，再选用相应自动化回归。

禁止：

- 删除有效测试来通过验收
- 弱化断言掩盖 Bug
- 将真实错误改为静默忽略
- 用 sleep / 超长 timeout 掩盖 race condition

---

## 10. 验收命令

优先使用已有的单文件／单用例入口，路径替换为本次对应的测试：

```text
python -m pytest -q tests/unit/test_verify_script.py
python -m pytest -q tests/contract/test_bridge_negotiation_provider.py -k 关键词
npm --prefix frontend run test -- run src/gateways/projectTransferGateway.test.ts
python scripts/run_e2e.py e2e/task-navigation.spec.ts -g "用例关键词"
npm --prefix frontend run typecheck
```

Pytest 可用 `文件路径::用例名` 精确选择用例；类型检查仅在涉及 TypeScript 类型时按需运行。以上命令是可选入口，不是一套必须依次执行的验收套餐。

`python scripts/verify.py` 无参数会运行后端与前端广泛验证；`--area backend` 包含全部 unit / integration 和广泛 lint，`--area frontend`／`ui` 包含全部 Vitest、typecheck 与 build，`--area e2e` 运行整个桌面与移动端 E2E。它们不是日常小改动的默认入口。`--area providers`／`scheduler` 也只在需要对应区域检查时使用。

未经用户明确授权，不得运行 `--full` 或分批拼成等价全量验证。发现本次范围外的 Bug，先做一轮针对性排查、修复和局部确认；若仍未解决且确需全量定位，才说明发现、已尝试的修复、拟运行范围和预计耗时并申请授权。未获授权时报告已通过项与未验证边界，不假称全量通过。

---

## 11. Codex 开发规则

日常开发遵循以下原则；与旧文档冲突时，以用户最新决定和根目录 `AGENTS.md` 为准：

1. 使用完成任务所需的最小仓库上下文。
2. 已知所属模块时不要扫描无关目录。
3. 按实际涉及的边界读取对应文档章节和测试，不整套重读历史规范。
4. 业务逻辑变化须有对应自动测试；已有覆盖足够时复用，不写镜像实现的重复测试。
5. 业务 Bug 先确认最小回归失败再修复；纯视觉／文案按第 9 节处理。
6. Provider 契约变化运行受影响的 Contract Tests。
7. UI 交互变化选择相关 Vitest；需要浏览器才能验证时补对应 Playwright 用例。
8. 单用例／单文件优先，仅有具体证据时扩大验证范围。
9. 相关验收通过即停，不为“收尾”再跑区域套餐或重复验证。
10. 不得通过删除或弱化测试规避失败。
11. 无法执行的测试必须在最终报告中明确说明。

---

## 12. Token / AI 开发成本控制

测试体系本身也是 Token 优化基础设施。

原则：

- 用确定性的测试结果代替 AI 反复推演。
- 用 Fake Provider 代替每次分析 ComfyUI / GPU 长日志。
- 用 Contract Tests 快速确定 Provider 行为是否合格。
- 日志采用结构化错误码，原始长日志按需读取。
- 模块职责保持小而清晰。
- `AGENTS.md` 作为导航，不重复整个项目文档。
- 架构文档按主题拆分，Codex 按需读取。
- 开发期间不无脑执行 Full Suite。
- 用户 Prompt 只描述目标和体验，不重复项目背景。

示例目标：

```text
修复 Scheduler 在应用重启后 Running Job 不恢复的问题。
先增加回归测试，遵循现有 Scheduler 状态机，完成相关验收。
```

而不是在每次目标里重新解释整个 ShotMill 架构。

---

## 13. Definition of Done

一个 Codex 目标默认只有在以下条件满足后才算完成：

- 行为符合需求
- 架构边界未被破坏
- 变化的业务逻辑有相关自动测试，业务 Bug 有最小回归覆盖
- 本次直接相关的局部验证通过；纯视觉／文案完成最小复现和目测
- Contract、E2E、typecheck、lint、migration 等仅按实际涉及的层和风险选用，不要求全套餐
- 未执行项和残余风险被明确报告

最终目标是：

> 将“重复测试、复现异常、验证修复”尽可能交给机器，把人工时间集中在产品行为、交互体验和生成质量判断上。
