# 调研索引

专题文件记录结论、官方文档或源码链接、查验日期，以及待验证问题。测量数据应链接到真机记录，不混入未经实验的性能排名。

优先专题：安卓 Wine/Proton 与纯 ARM64 模块、真实 Steam 服务、Native OpenXR 图像与输入桥、坐标和帧时序、音频延迟、缓存与构建隔离，以及 Spatial 外部双眼画面。

已确认的架构事实：ARM64 Player 替换后仍为 Windows 应用；Proton 包含图形 API 转换组件；Steam 桥仍依赖真实客户端服务。上游源码关系见 [ARCHITECTURE.md](../../ARCHITECTURE.md)。

Pico CLI 的项目/设备工具和其 Agent 工作流要分开评估：有工作流可以调用 Gradle 构建，不代表具备独立编译器，也不代表自动支持跨 WSL 构建。缓存方案见 [构建说明](../build/README.md)。
