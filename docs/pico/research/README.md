# 调研索引

专题文件记录结论、官方文档或源码链接、查验日期，以及待验证问题。测量数据应链接到真机记录，不混入未经实验的性能排名。

优先专题：安卓 Wine/Proton 与纯 ARM64 模块、真实 Steam 服务、Native OpenXR 图像与输入桥、坐标和帧时序、音频延迟、缓存与构建隔离，以及 Spatial 外部双眼画面。

已确认的架构事实：ARM64 Player 替换后仍为 Windows 应用；Proton 包含图形 API 转换组件；Steam 桥仍依赖真实客户端服务。上游源码关系见 [ARCHITECTURE.md](../../ARCHITECTURE.md)。

Pico CLI 的项目/设备工具和其 Agent 工作流要分开评估：有工作流可以调用 Gradle 构建，不代表具备独立编译器，也不代表自动支持跨 WSL 构建。缓存方案见 [构建说明](../build/README.md)。

## Native OpenXR 知识入口

2026-10-07 整理了项目 skill：[pico-native-openxr](../../../.agents/skills/pico-native-openxr/SKILL.md)。官方网页及已检查 LLM 文本入口见 [来源说明](../../../.agents/skills/pico-native-openxr/references/sources.md)；Android 接入、渲染/坐标/输入、扩展性能和 BS for Pico 桥接分别放在其 references 中，避免在这里重复维护。

这些内容是开发资料与工程建议，尚未证明本 Fork 已在 Space Pro 上运行。实现、官方文档或真机结果变化时，同步更新 skill、项目入口与对应记录。
