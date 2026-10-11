# 调研索引

本目录收录专题调研与候选线索；维护要求见 [本目录约定](AGENTS.md)。

优先专题：安卓 Wine/Proton 与纯 ARM64 模块、真实 Steam 服务、Native OpenXR 图像与输入桥、坐标和帧时序、音频延迟、缓存与构建隔离，以及 Spatial 外部双眼画面。

已确认的架构事实：ARM64 Player 替换后仍为 Windows 应用；Proton 包含图形 API 转换组件；Steam 桥仍依赖真实客户端服务。上游源码关系见 [ARCHITECTURE.md](../upstream/ARCHITECTURE.md)。

Pico CLI 的项目/设备工具和其 Agent 工作流要分开评估：有工作流可以调用 Gradle 构建，不代表具备独立编译器，也不代表自动支持跨 WSL 构建。缓存方案见 [构建说明](../build/README.md)。

## D1 专题

- [Bionic Wine 运行链与 Android 产品宿主（D1）](2026-10-11-d1-bionic-wine-runtime.md)：Wine 嵌入边界的源码事实（JNI 初始化路径、TEB／TLS 与 Android x18、ART 信号链、退出与服务、窗口／WSI、纯 ARM64 与上游 ARM64EC 构建、音频与许可）及本轮对官方 Unity 输入与官方 OpenXR 插件的只读验证证据（PE、版本、摘要与字节对比）；窗口／音频复用边界待用户决定。机器路径与大型原始输出只留在本机忽略目录。

## Native OpenXR 知识入口

2026-10-07 整理了项目 skill：[pico-native-openxr](../../.agents/skills/pico-native-openxr/SKILL.md)。官方网页及已检查 LLM 文本入口见 [来源说明](../../.agents/skills/pico-native-openxr/references/sources.md)；Android 接入、渲染/坐标/输入、扩展性能和 BS for Pico 桥接分别放在其 references 中。

这些内容是开发资料与工程建议，尚未证明本 Fork 已在 Space Pro 上运行。

## GameNative 实现参考

2026-10-11 已读取 GameNative 固定提交 `1fbd2221da0ec90c4bcddf607c24fa338e4abe2a` 的公开源码；忽略的 `private/GameNative/` 留作本地参考，不作为已部署运行时或可再分发组件。

已用于设计的资料包括 Bionic Wine／Proton 构建、实际子进程启动、Steam 登录与独立服务，以及真正的 Windows OpenXR 双眼／动作桥。现有 XR Windows runtime 为 x86／x64，Android 侧是跨进程 GLES 提交；纯 ARM64／Vulkan 接入需要实际开发。部分启动、Steam bootstrap 与 GPU 组件是专有闭源，不把整个仓库当成可自由复编底座。

固定源码与采用边界统一见 [产品架构的实现参考](../plans/ARCHITECTURE.md#实现参考)；按 [开发路线](../plans/ROADMAP.md)直接推进产品，在遇到具体实现问题时按需调研，不另开前置探针项目。
