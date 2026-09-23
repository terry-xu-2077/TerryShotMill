# ShotMill 本地基础组件

这里是项目自有的按钮、复选框、标签、文本框、重置按钮和 Modal 基础实现，不依赖外部 UI 包。
从此前使用的基础实现迁入，以保持当前交互和外观；后续直接修改这里。

- 组件：同名 TSX。
- 样式入口：style.css；具体控件样式在 styles/。
- 主题基础：styles/theme.css、theme-system.css 及 palette-derivation.css。
- 业务主题映射：../../styles/tokens.css。
- 已重新设计的 Select、Slider、RangeSlider、BoolSwitch 位于上一级 ui/。

现有 tc- 类名和 --tc- 变量作为兼容命名保留，定义和实现均在本地，不代表仍依赖旧库。不要从旧库升级覆盖这些文件。后续同步新风格到 UI 库须另行执行。
