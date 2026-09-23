# ShotMill UI 开发规则

> 状态：强制开发规范 / UI 实现红线  
> 最后更新：2026-09-14  
> 适用范围：`frontend/`、Tauri Desktop UI、Mobile Remote Monitor、`/dev/ui`、所有 ShotMill Overlay / Dialog / Popover  
> 上位体验规范：`UI_UX_SPEC.md`  
> 当前增量规范：`UI_V0.9_BATCH_REVIEW_WORKFLOW.md`  
> 默认共享 UI：`Terry_React_UI_Library`

本文负责回答 **“ShotMill 的 UI 代码应该怎么写、哪些写法禁止、出现视觉问题时按什么顺序排查”**。

`UI_UX_SPEC.md` 继续定义产品体验与交互目标；本文定义实现红线。两者都必须遵守。若某个版本 UI 文档与本文冲突，最新明确产品决策可以覆盖具体布局，但不得绕过组件边界、CSS 所有权、Overlay、主题和调试红线。

本文吸收 Rulesmd Editor 已经经过真实项目验证的 UI 经验，并结合 ShotMill 近期实际发生的问题重新整理。目标是减少“截图发现问题 → 增加一层 fix CSS → 另一处又被破坏 → 再补一层”的循环。

---

## 1. 核心结论

ShotMill UI 默认遵循以下顺序：

```text
语义正确
→ 组件边界正确
→ 布局所有权正确
→ 弹性尺寸正确
→ 主题与层级正确
→ 最后才做视觉微调
```

禁止反过来先用像素补偿把截图“顶到差不多”。

任何 UI 问题如果连续两轮修改仍然只是“稍微好一点”，必须停止补偿，排查：

```text
是不是修错责任层？
是不是业务 CSS 污染了共享组件？
是不是同一区域有多个 CSS 所有者？
是不是实际运行的 UI Library 版本不是刚修改的版本？
是不是 Overlay / stacking context / overflow 根因？
是不是容器本身的尺寸契约错误？
```

---

# 2. UI 所有权分层

## 2.1 Terry React UI Library 拥有

所有可跨项目复用的基础组件及其内部实现，包括但不限于：

- `Button`
- `Dialog`
- `Select / MultiSelect`
- `TextField`
- `Checkbox / BoolSwitch`
- `Slider`
- `Tooltip / Popover`
- `SegmentedControl`
- `SlidingTabs`
- `StatusPill`
- 通用 Progress / Empty State / Overlay primitive

UI Library 对这些组件拥有：

- 内部 DOM；
- 高度、padding、margin、line-height；
- Track / Knob / Thumb / Indicator；
- 图标与文字内部对齐；
- hover / active / focus / disabled；
- dark / light 主题；
- 动画；
- 组件内部圆角和边框几何。

**ShotMill 业务 CSS 不得重新实现上述内部细节。**

如果共享组件不够用：

1. 先检查公开 props 是否已有能力；
2. 缺少通用能力时回 `Terry_React_UI_Library` 增加正式 API；
3. 在 UI Library Showcase 中同时展示新能力；
4. 再升级 ShotMill 依赖；
5. 禁止先在 ShotMill 写一套私有同类组件。

## 2.2 ShotMill 拥有

ShotMill 只拥有产品结构和业务语义，例如：

- Project Workspace 布局；
- Task Card / Task Row；
- H3 Prompt Editor；
- Asset Manager 的业务结构；
- Prompt Review；
- Batch Bar；
- Queue / Runtime Center；
- Result Preview；
- 项目配置内容；
- 业务状态与业务文案。

原则：

> **UI Library 负责积木，ShotMill 负责产品结构。**

## 2.3 新公共组件必须进入 Showcase

UI Library 新增或改变任何公开组件时，同一个开发周期必须：

- 加入 UI Library Showcase；
- 展示默认态、选中态、禁用态；
- 能验证 dark / light；
- 能验证实际交互，而不是只渲染静态截图。

没有进入 Showcase 的公共组件视为未完成。

---

# 3. 共享组件集成红线

## 3.1 禁止宽泛 descendant 标签选择器

业务 CSS 禁止：

```css
.task-panel span { ... }
.dialog button { ... }
.settings input { ... }
.asset-row div { ... }
.panel svg { ... }
```

原因：共享组件内部同样包含 `span / button / input / div / svg`，这种规则会穿透组件边界。

必须使用业务语义类，例如：

```css
.task-review-copy { ... }
.task-review-actions { ... }
.project-config-description { ... }
```

如果暂时无法新增语义类，至少使用明确的 direct child，不得使用宽泛后代选择器。

## 3.2 ShotMill 业务 CSS 禁止修改 `.tc-*` 内部结构

默认规则：

> **业务 CSS 不出现针对 `.tc-*` 内部节点的样式。**

ShotMill 可以控制共享组件的业务宿主：

```text
宽度槽位
所在 Grid / Flex 区域
外部 gap
业务层级
是否 fluid / compact 等公开 prop
```

但不能进入：

```text
.tc-segmented-item
.tc-sliding-tab
.tc-select-current
.tc-select-item
.tc-bool knob / track
.tc-range thumb
```

修改其 padding、字体、内部圆角、颜色、transform 等。

如果组件在 ShotMill 中看起来不正确：

```text
Showcase 也不正确 -> UI Library 修
Showcase 正确 -> 查 ShotMill 宿主 / CSS 污染 / 版本 / 级联
```

## 3.3 一个控件只能有一个尺寸所有者

禁止同时出现：

```text
组件默认尺寸
+ React prop 尺寸
+ ShotMill CSS !important 再覆盖
```

优先级固定为：

```text
组件默认
→ 明确公开 prop
→ 业务宿主分配空间
```

禁止第四层“再补 CSS”。

---

# 4. CSS 所有权与级联

## 4.1 一个区域只能有一个主要 CSS 所有者

同一块 UI 不得长期由多个 `*-fix.css / *-polish.css / *-final.css` 共同维护。

近期 ShotMill 已经出现多层 V0.x CSS 覆盖同一区域的问题。后续新增功能必须优先：

- 找到当前 owning stylesheet；
- 在拥有者中修改；
- 废弃旧规则时直接删除旧规则；
- 不通过“再加载一个更晚的 fix 文件”长期覆盖。

允许临时迁移层，但迁移完成后必须合并回明确所有者。

## 4.2 禁止依赖文件名猜级联

`final`、`polish`、`fix` 只是文件名，不代表浏览器优先级。

判断实际结果必须依据：

```text
真实 import 顺序
selector specificity
CSS inheritance
stacking context
computed style
```

## 4.3 全局 CSS 只保留一条加载链

ShotMill 的全局样式必须只通过模块 import 进入。

禁止同时在：

```text
index.html <link>
main.tsx import
```

加载 `/src/*.css` 形成第二条级联链。

## 4.4 禁止 `!important` 作为常规修复方式

`!important` 只能用于已证明的浏览器/第三方兼容边界，不用于普通布局和共享控件覆盖。

如果必须通过提高 specificity 或 `!important` 才能“压住另一层”，优先判断是否存在重复所有权。

---

# 5. 禁止像素补偿式修复

未经根因证明，禁止使用以下方式修共享组件或未知错位：

```css
top: -2px;
left: 1px;
margin-top: -3px;
transform: translateY(-1px);
```

尤其是“垂直居中差 1～2px”这种问题，第一检查项应是：

- 父级 `align-items`；
- 控件 `height / line-height`；
- 业务 CSS 是否命中内部 span/svg；
- 组件真实运行版本；
- 是否存在两套样式同时生效。

**容器中同一行的文字、图标、按钮、标签默认必须垂直居中。** 这是基本验收项，不应等用户截图指出。

---

# 6. 弹性布局是默认布局模型

这是 ShotMill 的全局 UI 原则。

## 6.1 优先使用

```text
Flex
Grid
minmax()
clamp()
min-width: 0
min-height: 0
fr
合理的 intrinsic sizing
```

窗口变宽 / 变窄时，先重新分配已有空间。

## 6.2 弹性容器不等于弹性控件

可变剩余空间默认由：

```text
gap
spacer
1fr 内容区
真正的编辑区 / 预览区
```

吸收。

按钮、标签组、Select、搜索框、导航项等操作控件，不得仅因为父容器变宽就无意义拉长。

推荐：

```text
[固定操作组] ← 弹性空白 → [固定操作组]
```

而不是：

```text
[按钮][被强行拉长的 Select =================][按钮]
```

只有语义本身就是内容区的对象，例如 Prompt Editor、资产预览、任务列表、正文面板，才主动吃满剩余空间。

## 6.3 滚动条不是布局解决方案

除非需求明确说明某区域应该滚动，否则不得新增滚动条。

允许滚动的典型区域：

- 超长 Task / Asset 列表；
- 左侧长参数栏；
- Prompt 文本本身；
- 长日志 / 历史列表。

不应滚动：

- Dialog 外框本身；
- 页面根容器；
- 因为布局算错而溢出的主工作区；
- 本可以通过弹性分配解决的普通详情区。

窗口变窄时：

```text
先压缩弹性空白
→ 调整 Grid/Flex 比例
→ 必要时收起次要区
→ 最后才允许业务明确的局部滚动
```

---

# 7. 信息密度规则

ShotMill 默认采用 **专业桌面创作工具的紧凑密度**。

提高密度优先收紧：

- 外框留白；
- panel padding；
- section gap；
- 行高；
- Task / Asset / Result 条目高度；
- 工具栏高度；
- 控件间距。

不得优先通过缩小正文字号获得空间。

内容少时，窗口本身也应缩到与内容量匹配，不为了“高级感”制造大片空白。

同屏应优先看到更多：

```text
Task
Asset
Result
Queue item
```

媒体预览可以保持足够视觉面积，但参数、元数据和工具栏必须紧凑。

---

# 8. 标签 / Tab 语义

ShotMill 当前只使用两类共享标签组件。

## 8.1 `SlidingTabs`：参数密集区域

用于：

- 分辨率；
- 质量；
- 生成模式；
- 上下文承接；
- 其他固定少量参数枚举。

视觉：

- 无圆角外框；
- 同组等宽；
- 底部存在暗轨；
- 当前项下面 Accent 指示条滑动；
- 当前文字 / 图标同步变 Accent；
- 紧凑字号。

## 8.2 `SegmentedControl`：高层模式切换

用于：

- 用户 / AI 增强；
- 可视化 / 文本；
- 其他明显改变工作模式或视图模式的切换。

视觉：

- 同组等宽；
- 两端完整半圆胶囊；
- 选中块整体轻微提亮；
- 文字 / 图标 Accent；
- 不使用底部亮条。

禁止出现第三套“像胶囊又像简易 Tab”的混合控件。

---

# 9. Overlay / Dialog / Popover 红线

## 9.1 所有高层浮层统一走 Overlay / Portal

Dialog、Dropdown、Context Menu、Popover、Tooltip、`@` Asset Menu、Fullscreen Preview 等不得直接受业务容器的 `overflow` / transform / stacking context 控制。

统一使用 ShotMill Overlay 基础设施 / UI Library Portal。

## 9.2 菜单自动选择展开方向

默认：

```text
向下
→ 下方不足则向上
→ 上下都不足则限制菜单高度并只让菜单内部滚动
```

菜单不得被 Dialog、表格、工作区边缘裁切。

## 9.3 禁止 z-index 军备竞赛

出现遮挡时禁止直接写：

```css
z-index: 99999;
```

先检查：

- 是否经过统一 Portal；
- 哪个 ancestor 创建 stacking context；
- overflow 是否错误；
- sticky 区域是否在菜单打开时需要业务层级协调。

## 9.4 Dialog 外框尺寸稳定

用户 / AI、可视化 / 文本、上下文模式、AI Revision 等内部切换只替换内容，不得让整个 Dialog 忽大忽小。

Task Editor 尤其必须保持稳定外框。

---

# 10. 主题颜色所有权

ShotMill 不允许每个页面维护自己的“深蓝 / 灰 / 金色”色板。

长期主题输入统一收敛到 Terry UI Library 五个公共通道：

```text
Base
Accent
Effect
Text
Text Bright
```

ShotMill 的 `--sm-*` surface / border / muted / status 等变量应作为这些源色的**语义派生层**，而不是形成第二套独立色板。

规则：

- Base 负责背景和中性 surface 层级；
- Accent 负责选中 / 当前 / 主交互；
- Effect 用于有限 focus / edge / glow；
- Text 负责正文；
- Text Bright 只用于真正高亮内容；
- success / warning / danger 属于少量语义状态色，不得扩散成大面积面板背景。

禁止业务组件直接写大量独立 hex/rgb 配色。

颜色需要变化时优先从主题 token 派生：

```css
color-mix(...)
```

而不是新增一个页面专用色板。

Light / Dark 只改变颜色，不改变同一共享控件的几何、尺寸、对齐或动效语义。

---

# 11. 说明性文本红线

未经明确需求，不得主动增加教学性文字。

禁止为了“更友好”自行加入：

- `title` 教学提示；
- Tooltip 操作教程；
- “点击这里……”；
- “右键可以……”；
- “你可以通过……”；
- 大段常驻说明；
- 界面结构已经表达清楚后重复解释同一功能。

默认原则：

> **功能存在，不等于需要文字解释。**

例外：

- 明确错误原因；
- 用户需要做决定的确认信息；
- 空状态确实缺少下一步；
- 安全 / 数据丢失风险；
- 用户明确要求的说明。

文本必须短、直接、用户语言优先，避免 Provider / Job / Snapshot / Capability 等工程术语进入普通界面。

---

# 12. 状态来源唯一

UI 状态必须由 React state / props / Frontend Read Model 驱动。

禁止通过：

- DOM 查询；
- 复制 DOM；
- MutationObserver；
- 从元素 class 反推业务状态；

来同步业务逻辑。

同一 Task 在列表、卡片、右侧详情、Task Editor 中的：

```text
名称
状态
Prompt Review
运行状态
资产
Result
```

必须来自同一 Read Model / 正式数据源。

V0.4 批量流程尤其禁止前端根据 Revision / Job 数组自己猜 `promptReviewStatus` 或 eligibility；以后端 Frontend Adapter / Read Model 为准。

---

# 13. 输入控件语义与延迟

控件的视觉范围和业务验证边界必须分离。

例如 Slider：

- Track range 是编辑便利，不等于合法值边界；
- 不应因为 thumb 到达端点就偷偷重写真实业务值；
- 精度不得因为 UI 控件步长而无意丢失。

高频输入：

- 用户可见状态必须即时更新；
- 不允许为了后端 debounce 让控件明显滞后；
- 持久化可以 coalesce，但旧响应不得覆盖较新的本地输入；
- SSE / Runtime 更新不得抢走焦点或覆盖正在编辑的 Prompt。

---

# 14. 容器对齐默认规则

如无明确设计理由：

- 同一横行的独立控件默认垂直居中；
- 图标与文字默认在自身控件内居中；
- 操作区默认与相邻标题 / 控件共享中心线；
- 同类控件高度一致；
- 两列布局右列控件也必须在自己的轨道中正确居中。

允许非居中的场景必须有明确语义：

- 正文顶部对齐；
- 表格基线；
- 多行说明；
- 长表单纵向起点。

“看起来差不多”不是验收标准。

---

# 15. 当前 ShotMill 专属 UI 决策

以下为当前明确决策，不能因后续开发方便而恢复旧方案：

- 默认一级结构：**项目首页 → 项目工作台 → Task Editor Overlay**；
- 不恢复“故事板 / 生成 / 素材”三个一级页面；
- 列表 / 卡片只是同一 Task 集合的两种视图；
- 两种视图都用主内容区内的“新建任务卡 / 创建行”，不恢复顶部巨大新建工具栏；
- 右侧详情只读；
- Project Config 管项目级标题、简介、AI 背景开关、资产；
- Task Editor：左侧紧凑参数，右侧 Prompt，底部动作；
- 左侧参数区可作为明确局部滚动区，右侧 Prompt 主区优先弹性适配；
- Task Editor 内部模式切换不得改变外框尺寸；
- Prompt Source：用户 / AI；显示模式：可视化 / 文本；两者语义独立；
- AI Prompt Revision 只在 AI Source 下显示；
- 当前 Source 决定真正用于生成的 Prompt；
- 不恢复“采用增强结果”按钮；
- 批量生产主路径：**批量 AI 增强 → 人工逐项审核 → 批量视频生成**；
- 批量 UI 不堆工程 Badge，不在每张卡堆按钮矩阵；
- Prompt / Video 两类队列可以统一展示，但 UI 不暴露内部 Job ID / Snapshot 等实现字段。

---

# 16. UI Library 版本与调试顺序

ShotMill 使用 Git SHA 锁定 UI Library。

排查共享组件问题前必须先确认：

1. `package.json / lockfile` 指向预期 SHA；
2. 启动脚本确实刷新了 Git dependency；
3. `node_modules` 中安装的是最新 build 产物；
4. Showcase 中该组件行为正确；
5. 再检查 ShotMill CSS。

禁止出现：

> UI Library 仓库已经修好，但 ShotMill 实际仍运行旧缓存，然后继续根据旧截图修改 CSS。

---

# 17. UI Bug 固定排查顺序

遇到视觉问题固定按以下流程：

```text
1. 确认需求语义
2. 确认 owning component / owning stylesheet
3. 共享组件？先看 Showcase
4. 确认实际 UI Library SHA
5. 看 Computed Style，而不是只读源码
6. 检查父容器是否有宽泛 selector 污染
7. 检查真实 CSS import 顺序
8. 检查 overflow / stacking context / Portal
9. 检查 Flex/Grid 尺寸契约
10. 最后才做视觉数值微调
```

如果步骤 1～9 没完成，不得开始写负 margin / translate 补偿。

---

# 18. UI 开发前固定检查

开始一个新的 UI 功能前：

- 先读 `UI_UX_SPEC.md`；
- 再读本文；
- 当前批量流程读 `UI_V0.9_BATCH_REVIEW_WORKFLOW.md`；
- 确认 UI Library 是否已有需要的组件；
- 如果缺的是通用控件，先做 UI Library；
- 新公共组件同步进入 Showcase；
- 先在 Mock / 假 API 场景完成布局和交互；
- 再连接真实 Read Model / API。

---

# 19. UI 提交前验收清单

UI 相关提交至少确认：

- [ ] 使用的是正确责任层；
- [ ] 没有宽泛 `span/button/input/div/svg` descendant selector；
- [ ] 没有在 ShotMill CSS 修改 UI Library 内部几何；
- [ ] 没有为已有共享控件重新造 ShotMill 私有版；
- [ ] 新共享组件已经进入 UI Library Showcase；
- [ ] 同一区域没有多份 CSS 相互覆盖；
- [ ] 没有用负 margin / top / translate 掩盖未知根因；
- [ ] 同一行控件做了真实垂直居中；
- [ ] 使用 Flex/Grid 弹性布局，而不是靠滚动条消化溢出；
- [ ] 操作控件没有为了填满空间被无意义拉长；
- [ ] Dialog 模式切换不会改变外框尺寸；
- [ ] Popup 在窗口上下边缘都不会被裁切；
- [ ] Overlay 使用统一 Portal；
- [ ] 主题没有新增页面级独立色板；
- [ ] 没有未经需求主动增加说明性文案；
- [ ] SSE / Runtime 更新不会覆盖当前输入或抢焦点；
- [ ] 小窗口 / 常见桌面分辨率检查通过；
- [ ] Light / Dark（启用后）都检查；
- [ ] 对稳定可复现 Bug 增加了对应回归测试或 Mock 场景。

---

# 20. 后续自动化红线

应逐步把以下规则加入 ShotMill 前端静态检查 / CI，而不是永远只靠人工记忆：

- 禁止业务 CSS 宽泛 descendant 标签 selector；
- 禁止业务 CSS 越界修改 `.tc-*` 内部实现；
- 检查全局 CSS 单一加载链；
- 检查重复 CSS owner / 重复 import；
- 检查新公共 UI 组件是否在 Showcase 注册；
- 检查新增 Dialog / Overlay 是否经过统一 Portal；
- 检查危险的超大 z-index；
- 检查业务 CSS 新增大量硬编码颜色；
- 检查未经允许的说明性 Tooltip / `title` 文案。

检查器只能验证架构不变量，不能复制另一份完整 CSS manifest 或组件名单成为第二 source of truth。

---

# 21. Rulesmd Editor 经验来源

本文不是凭空增加规则，而是吸收以下已经在 Rulesmd Editor 中通过实际故障和修复验证的文档经验：

- `UI_DESIGN_PRINCIPLES.md`：默认居中、同类控件一致、菜单方向、信息密度、状态来源；
- `UI_DEVELOPMENT_RULES.md`：组件边界、CSS 所有权、禁止像素补偿、弹性空白、UI Library 版本验证；
- `UI_COMPONENT_INTEGRATION_PITFALLS.md`：共享组件被业务 CSS 污染的真实案例；
- `UI_CSS_CASCADE_REDLINE.md`：单一 CSS 加载链、真实级联、stacking context、single source of truth；
- `UI_SUBWINDOW_RULES.md`：统一 Dialog / Portal / z-index；
- `UI_WORKSPACE_GUIDELINES.md`：高密度桌面布局、控件一致性、主题、菜单和工作区长期规则；
- `THEME_COLOR_CONTRACT.md`：五个源颜色与语义派生；
- `EDITOR_CONTROL_SEMANTICS.md`：控件视觉范围与真实业务语义分离、输入延迟；
- `UX_TEXT_RED_LINES.md`：未经需求不得主动增加教学性说明文本。

这些原则已经被证明能直接减少 UI 返工，ShotMill 后续新 UI 默认继承，不再等相同问题第二次发生后才补规则。

## 2026-09-22 · 用户确认的新风格开发方式
本项目先独立打磨新 UI 风格，允许将下拉菜单等控件从旧 UI 库解耦。下拉组件统一由 frontend/src/ui/Select.tsx 与 Select.css 所有，旧 PortalSelect 仅兼容入口。待用户明确要求同步时，再将完成的样式作为新的风格类加入 UI 库，保留原风格。该最新决策覆盖旧规则中必须立即在共享库修改的要求。
