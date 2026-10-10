# 项目状态

更新：2026-10-10。本文件是当前工作副本的统一状态入口；详细证据以实验记录为准，阶段目标与依赖见 [ROADMAP](plans/ROADMAP.md)。计划文件描述待做工作，不另维护执行状态。

## 总体结论

**已建立独立 Android/XR 原型，尚未建立 Android 上的 Windows 游戏运行链。**

- 已验证：x86_64 PICO 模拟器中的 Spatial 管理窗口 ↔ Native Vulkan OpenXR 双眼、五轮切换、私有文件共享、Back、Activity 重建/部分暂停恢复、Home 人工确认退出后重开，以及模拟头部移动和右 trigger。
- 已构建但未运行验证：原型的 Android arm64-v8a ABI。
- 未实现或未验证：Android Wine 运行环境、Windows 程序执行、真实 Steam 服务接入、DXVK 到 Android XR 的图形桥，以及 Beat Saber 游戏闭环。
- 尚无本项目 Space Pro 真机或持续性能结论。上游 Steam Frame 的结果不属于本项目设备验证。

依据：[2026-10-09 原型结果](device-validation/2026-10-09-spatial-openxr/RESULT.md)、[构建入口](build/README.md)、[上游组件关系](upstream/ARCHITECTURE.md)。本次只新增计划和整理状态，没有新的构建或运行结果。

## 能力与证据

| 能力 | 当前状态 | 证据与限制 |
|---|---|---|
| 原型 APK 构建/部署 | 两 ABI 构建、x86_64 模拟器部署通过 | [原型结果](device-validation/2026-10-09-spatial-openxr/RESULT.md)；不包含游戏或 Wine |
| Spatial/Native XR 场景交接 | 模拟器基线通过 | 管理 Activity/容器关闭，Native session 正常释放；不证明 SDK 零后台开销或真机模式支持 |
| 追踪与输入 | 模拟头部、右 aim/trigger 部分通过 | 左侧在已测模式 inactive；真实双手 6DoF、振动未验证，原型尚无 haptic action |
| 生命周期与数据 | 已测场景通过，覆盖不完整 | Home 取消、进程死亡恢复及更长切换回归待补；摘戴/待机留待真机 |
| Windows ARM64 DLL 构建 | 上游构建代码保留，本工作副本完整构建未验证 | 根 `build.sh` 不构建完整 Android Wine，也不构建 APK |
| Android Windows 运行环境 | 未实现/未运行验证 | 无已采用并验证的候选运行时；Android ELF、Windows ARM64、ARM64EC 必须分开 |
| 真实 Steam 服务 | 未接入 | 现有上游桥依赖 Proton Unix 半边及真实 Steam 客户端；登录、所有权、DLC、回调均未在本项目通过 |
| D3D11/DXVK → Android OpenXR | 未接入 | 原型仅渲染自己的 Vulkan 场景，不接 Windows 图像或 ABI |
| 原版游戏菜单/歌曲/音频 | 未验证 | 正版 1.44.1 输入已提供；没有对游戏执行替换、启动或 Pico 验证 |
| 真机与持续性能 | 未验证，本轮不安排 | 模拟器 NVIDIA GPU、CPU ticks 或上游 benchmark 不能证明 Space Pro 表现 |

## 当前开发队列：仅模拟器前期验证

以下四份计划已编写，**实现与新增实验均未开始**。不要求先取得 Space Pro，也不把模拟器结果升级为 ARM64 验证。

| 编号 | 计划 | 当前状态 | 执行依赖 |
|---|---|---|---|
| E1 | [宿主/XR 回归与诊断](plans/emulator-host-xr.md) | 已规划；复用已有原型 | 可先复现旧基线，再实现新增探针 |
| E2 | [Windows 运行环境与 ABI 探针](plans/emulator-windows-runtime.md) | 已规划；候选未选定 | 先审计模拟器可用的 Android x86_64 运行时，再实现最小 PE 探针 |
| E3 | [真实 Steam 服务探针](plans/emulator-steam-service.md) | 已规划；后端未选定 | 服务来源/ABI 调研可并行；Windows 正向链路依赖 E2 和可用真实后端 |
| E4 | [D3D11/Vulkan/OpenXR 图形桥](plans/emulator-graphics-xr.md) | 已规划；桥未实现 | Native 图像交接预实验依赖 E1；Windows 图形/XR 客户端依赖 E2 |

优先推进 E1 和 E2；E3 的服务/许可核查可同时做。E2 的图形前提通过后推进 E4，无需为独立图形探针等待 Steam 登录；完整游戏接入仍须真实授权路径成立。

E2/E3 的正向运行依赖尚未实现的组件，不能理解为已有脚本可以一键执行。若只有 ARM64 后端、没有适用的模拟器运行机制，记录具体阻塞并停止该分支，不新增真机任务来冒充本轮完成。

## 暂不进入本轮的工作

- Space Pro 的纯 Windows ARM64 执行、目标 GPU/控制器、Manifest 模式、摘戴/重定位/待机和持续性能。
- Beat Saber 原版接入、模组、游戏下载器和最终发行打包。
- 零复制、注视点等优化承诺；允许早期记录模拟器协议/等待成本，不作真机性能排名。

游戏原始副本保持不可变；后续确需运行或修改游戏时先按 [备份流程](build/README.md#正版游戏输入与备份)建立并校验可恢复备份。本轮探针使用自有测试程序和资源，不需要游戏文件。

## 状态维护方式

新实验按 [记录规范](device-validation/AGENTS.md)保存结果、版本和证据校验值，再更新本文件的能力与队列状态。失败、部分通过、前提不足均应记录，不以计划存在或构建成功标记运行通过。

`ROADMAP.md` 维护阶段目标、依赖与计划入口；索引只讲概况与导航，目录维护细节放在就近的 `AGENTS.md`，见 [文档约定](AGENTS.md)；skill 维护接入边界。历史实验记录不因新计划而改写。
