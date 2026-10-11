# 技术决策

本目录概述技术选择及依据；记录要求见 [本目录约定](AGENTS.md)。

当前首选产品基线见 [架构](../plans/ARCHITECTURE.md)：Windows ARM64 Unity／Mono、GameNative Bionic ARM64 Wine／Proton 移植、ARM64 DXVK 和 Android Native OpenXR。同一 APK 用 Spatial UI Activity 管理、Native OpenXR Activity 游玩；游戏图像不绕经 Spatial 二次渲染。基线不是封闭候选列表，开发当前功能时按 [研发循环](../plans/ARCHITECTURE.md#开发与验证方式)检索最新资料和其他技术方案。

执行 [开发路线](../plans/ROADMAP.md)：直接实现正版实例、Steam 服务和实际游戏 XR，问题在开发中解决，不再先做独立可行性探针。管理／游戏分进程，Wine／XR 优先同进程同 Vulkan device；实际实现不可靠时调查修复及替代布局，实质切换先用 Ask 决定。两 Activity 已有 [模拟器原型依据](../device-validation/2026-10-09-spatial-openxr/RESULT.md)，不是游戏或 Space Pro 通过结论；实际进度见 [STATUS](../STATUS.md)。

本地正版导入与真实 Steam 登录下载进入同一工作实例流程；已有文件无需重新下载。先原版可玩，再做 BSIPA、mod 与谱面管理；LIV／混合现实录制不开发。

稳定应用＋可更新兼容组件包采用 [共同契约](../plans/COMPONENTS.md)，广泛清单登记不增加当前功能承诺；云清单、下载能力与模块实现状态分别维护。实质技术／模块／交付选择按 [根约定](../../AGENTS.md#环境与操作)使用 Ask；决定记录候选与来源日期、实际依据／未知条件、推荐、用户选择、落地版本和重新评估触发条件，不把待选方案写成运行通过或另建验证阶段。


当前约束：Pico Space Pro、设备无 root、单 APK、真实 Steam 授权、高性能。
