---
name: pico-native-openxr
description: 为 PICO Android Native OpenXR 应用及 BS for Pico 的 Wine/Unity ARM64 到原生 XR 桥提供开发、调研和故障定位指导。涉及 loader、Vulkan 双眼提交、帧时序、坐标、控制器和性能扩展时使用；Unity 编辑器或 Kotlin Spatial 应用的常规开发另查对应 SDK。
---

# PICO Native OpenXR

将官方 Native OpenXR 知识用于可复现的 Android XR 接入。资料核查于 **2026-10-07**；随后修改实现、发现文档变化或得到真机结果时，同步更新相关参考文件、来源日期和项目文档。

## 按任务读取

| 当前任务 | 参考文件 |
|---|---|
| 查官方入口、版本、LLM 文本和文档矛盾 | [来源与可信边界](references/sources.md) |
| 创建 APK 宿主、接 loader、处理 Manifest/生命周期、构建 | [Android 运行时与构建](references/android-runtime.md) |
| Vulkan 图像交接、双眼帧、坐标、控制器、时钟 | [渲染与输入](references/rendering-input.md) |
| 刷新率、注视点、动态分辨率、MR 和其他 Pico 扩展 | [扩展与性能](references/extensions-performance.md) |
| 修改本仓库 Unity/Wine/OpenXR 桥、桌面处理、阶段验证 | [BS for Pico 接入](references/bs4pico-bridge.md) |

只读取本次任务需要的文件。使用其中的 API 或固定版本前，复查对应官方页面与实际锁定源码；此处是维护中的开发摘要，不替代规范。

## 先确定接入边界

读取仓库 `AGENTS.md` 和现有实现，区分 Android ELF、Windows ARM64 PE、ARM64EC。替换 ARM64 Mono/Unity Player 后仍是 Windows 程序；Native OpenXR 只解决 XR 侧，不能替代 Wine、D3D 转换或真实 Steam 服务。

本项目目标是 **无 root 的 Pico Space Pro、最终 APK、优先低延迟和持续性能**。构建计划在 WSL；不能把原 Linux SteamVR 运行时直接当成 Android XR 后端。当前移植进度以仓库文档为准。

SDK 扩展表主要覆盖 Neo3/Pico 4/4 Ultra。Space Pro 的扩展、控制器 profile、Vulkan 特性、权限、刷新率与性能必须由目标机确认。标注“官方文档事实”“工程建议”“真机已验证”，不要把计划写成已完成。

选择 Khronos 标准 Android Loader 作为基础能力候选；需要 `XR_PICO_*` 私有功能时，先核查 Pico Loader、配套头文件与目标 OS。不要把 2024 年“无需独立 SDK”的公告覆盖到 2025 年新增的私有扩展。

## 实施时保留的约束

- XR 帧时间、参考空间、双眼 pose/FOV 和 action 必须贯通游戏与 Android runtime；不要另造一个与游戏脱节的宿主帧循环。
- Vulkan 对象必须有清晰的设备、进程、队列与同步归属。Windows/Unix thunk 的句柄不能未经转换传给 Android loader。
- 先证明基础立体渲染与手柄正确，再优化图像复制、注视点、分辨率和重投影；性能结果记录帧时间与持续运行条件。
- 不伪造扩展支持、有效 tracking 或 Steam 所有权。可选扩展缺失时保留基础路径；必要能力缺失时报告具体阻塞点。
- 设备结果写入 `docs/device-validation/`，阶段状态更新 `docs/plans/`，架构/构建变化更新对应文档与 skill，约定变化更新 `AGENTS.md`。向用户只呈现大方向、结论与必要限制。
