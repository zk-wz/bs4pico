# 调研索引

本目录收录专题调研与候选线索；维护要求见 [本目录约定](AGENTS.md)。

优先专题：安卓 Wine/Proton 与纯 ARM64 模块、真实 Steam 服务、Native OpenXR 图像与输入桥、坐标和帧时序、音频延迟、缓存与构建隔离，以及 Spatial 外部双眼画面。

已确认的架构事实：ARM64 Player 替换后仍为 Windows 应用；Proton 包含图形 API 转换组件；Steam 桥仍依赖真实客户端服务。上游源码关系见 [ARCHITECTURE.md](../upstream/ARCHITECTURE.md)。

Pico CLI 的项目/设备工具和其 Agent 工作流要分开评估：有工作流可以调用 Gradle 构建，不代表具备独立编译器，也不代表自动支持跨 WSL 构建。缓存方案见 [构建说明](../build/README.md)。

## Native OpenXR 知识入口

2026-10-07 整理了项目 skill：[pico-native-openxr](../../.agents/skills/pico-native-openxr/SKILL.md)。官方网页及已检查 LLM 文本入口见 [来源说明](../../.agents/skills/pico-native-openxr/references/sources.md)；Android 接入、渲染/坐标/输入、扩展性能和 BS for Pico 桥接分别放在其 references 中。

这些内容是开发资料与工程建议，尚未证明本 Fork 已在 Space Pro 上运行。

## 模拟器运行环境与 Steam 候选

2026-10-10 的讨论检索到以下上游候选资料；只取得检索返回的 PR/发布说明，完整网页及源码抓取未成功。以下不是已复核源码、许可结论、采用决策或本项目运行证据。

| 候选来源 | 本轮要核查的问题 |
|---|---|
| [GameNative Android Proton 发布说明](https://github.com/GameNative/proton-wine/releases) | Android/Bionic补丁、实际 ELF宿主与 PE客体 ABI、构建/依赖闭包、匹配版本的 Unix-call与 Vulkan路径；x86_64/arm64ec标签不证明纯 ARM64客体可用 |
| [Bionic Steam PR #1430](https://github.com/utkarshdalal/GameNative/pull/1430) | 真实客户端/bootstrap的来源、ABI、许可与可获取性，应用内登录和 Steamworks授权/回调语义；专有或 DRM组件需单独审查，不能直接复用未经核实的资产 |

对应执行计划：[E2运行环境](../plans/emulator-windows-runtime.md)、[E3真实服务](../plans/emulator-steam-service.md)、[E4图形桥](../plans/emulator-graphics-xr.md)。本轮以 x86_64模拟器可执行的自有探针为边界；候选缺少适用组件时不满足本地闭环前提，mock或额外 PC服务不作为本地闭环证据。
