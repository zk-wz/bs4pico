# 项目状态

更新：2026-10-11。本文件是当前工作副本的统一状态入口；详细证据以实验记录为准，开发目标与顺序见 [ROADMAP](plans/ROADMAP.md)，共同设计见 [产品架构](plans/ARCHITECTURE.md)和 [组件／云清单契约](plans/COMPONENTS.md)。计划文件描述待做工作，不另维护执行状态。

## 总体结论

**已建立独立 Android/XR 原型，尚未建立 Android 上的 Windows 游戏运行链。**

- 已验证：x86_64 PICO 模拟器中的 Spatial 管理窗口 ↔ Native Vulkan OpenXR 双眼、五轮切换、私有文件共享、Back、Activity 重建/部分暂停恢复、Home 人工确认退出后重开，以及模拟头部移动和右 trigger。
- 两 Android ABI 已构建；本轮实际安装 APK 的主 ABI 为 arm64-v8a，x86_64 客体配置使用 libhoudini/arm64→x86_64 兼容路径。不能称纯 x86_64 APK 路径、原生 ARM64 运行或真机通过。
- 未实现或未验证：Android Wine 运行环境、Windows 程序执行、真实 Steam 服务接入、DXVK 到 Android XR 的图形桥，以及 Beat Saber 游戏闭环。
- 尚无本项目 Space Pro 真机或持续性能结论。上游 Steam Frame 的结果不属于本项目设备验证。

依据：[2026-10-09 原型结果](device-validation/2026-10-09-spatial-openxr/RESULT.md)、[E1 本轮实验](device-validation/2026-10-10-emulator-host-xr-e1/RESULT.md)、[构建入口](build/README.md)、[上游组件关系](upstream/ARCHITECTURE.md)。本轮已完成用户指定的E1轻量基础验收，前序失败保留；不进行30轮压测或六份成本对比。

## 能力与证据

| 能力 | 当前状态 | 证据与限制 |
|---|---|---|
| 原型 APK 构建/部署 | 两 ABI 构建、x86_64 客体部署通过；实际应用选择 ARM64 兼容路径 | [E1 记录](device-validation/2026-10-10-emulator-host-xr-e1/RESULT.md)的 PackageManager/ISA/native-bridge 证据；不包含游戏或 Wine |
| Spatial/Native XR 场景交接 | 模拟器基线通过 | 管理 Activity/容器关闭，Native session 正常释放；不证明 SDK 零后台开销或真机模式支持 |
| 追踪与输入 | 模拟头部、右 aim/trigger 部分通过；右 haptic API 预检成功 | 左侧已测模式 inactive；右 grip 报 valid 但零四元数/头部位置；物理振动与真实双手 6DoF 未验证 |
| 生命周期与数据 | 本轮轻量范围通过，专项覆盖不完整 | Home取消/确认、定向Native重建、正常释放和暖/受控冷重开首次读取通过；自然LMK/后台死亡、更长回归及摘戴/待机未覆盖 |
| Windows ARM64 DLL 构建 | 上游构建代码保留，本工作副本完整构建未验证 | 根 `build.sh` 不构建完整 Android Wine，也不构建 APK |
| Android Windows 运行环境 | 未实现/未运行验证 | 已选 GameNative Bionic ARM64 Wine／Proton 为开发基线；尚未建立产品构建与实际游戏执行链，不能把方案选定写成运行通过 |
| 真实 Steam 服务 | 未接入 | 现有上游桥依赖 Proton Unix 半边及真实 Steam 客户端；登录、所有权、DLC、回调均未在本项目通过 |
| D3D11/DXVK → Android OpenXR | 未接入 | 原型仅渲染自己的 Vulkan 场景，不接 Windows 图像或 ABI |
| 原版游戏菜单/歌曲/音频 | 未验证 | 正版 1.44.1 输入已提供；没有对游戏执行替换、启动或 Pico 验证 |
| 组件与云端清单 | 已定义文档契约和广泛模块登记，未实现安装／解析／更新能力 | [清单源](plans/component-catalog.json)尚无 release 或兼容 profile；云服务未部署，不代表远程组件已可用 |
| 真机与持续性能 | 未验证，本轮不安排 | 模拟器 NVIDIA GPU、CPU ticks 或上游 benchmark 不能证明 Space Pro 表现 |

## 当前开发队列：直接开发原版游戏

用户已调整为**先开发、在实现中调研选型与轻量验证**，实质取舍用 Ask。已有 E1 宿主交接成果直接复用，不继续独立模拟器可行性项目。产品架构、D1–D5 和组件／云清单设计已编写。本轮为 D1 的**现状调查与必要只读验证**：未部署云服务、未构建运行时、未启动模拟器、未修改正版游戏原件（只做了只读检查），也未编写实现代码；只额外获取官方 Unity OpenXR 1.14.3 包到忽略目录做架构／版本／摘要核对。

本轮文档与清单结构冒烟（范围：`docs/**`、根 README／AGENTS／CHANGELOG 与项目自有的 interop／Native OpenXR skill 文档；外部 URL 跳过、同文件锚点校验）：44 份 Markdown 的 264 个本地链接／锚点全部有效，清单引用双向一致（27 个模块、15 个升级单元，`profiles` 与全部 `releases` 仍为空）；原始输出留在本机忽略目录。该检查只覆盖文档与清单结构，**不证明**组件解析器、云更新或游戏运行能力。

| 顺序 | 计划 | 当前状态 |
|---|---|---|
| D1 | [游戏运行链与宿主](plans/game-runtime.md) | 现状调查与实施规划完成，**尚未实现**；窗口／音频复用边界待决定，受限 Player／Mono 输入待取得 |
| D2 | [Steam 接入](plans/steam-integration.md) | 已规划，待实现：真实登录／库／下载和游戏运行时 Steamworks 服务 |
| D3 | [游戏 OpenXR 闭环](plans/game-openxr.md) | 已规划，待实现：双眼菜单、双手控制、音频、一首正版歌曲及返回管理 |
| D4 | [原版产品交付](plans/game-delivery.md) | 已规划，待 D1–D3 集成：日常启动、恢复／更新、安装包与基本性能 |
| D5（后续） | [BSIPA 与 mod／谱面管理](plans/mod-chart-manager.md) | 已规划；原版可玩后实施，首轮仅保留数据和启动边界 |

D1 本轮结论：宿主的现状调查与实施规划已完成，**尚未实现**——正版输入实测为纯 x86-64 且本轮未写入；官方 Unity OpenXR 1.14.3 包已获取并核对通过（ARM64 PE、版本 1.14.3.0，包内 desktop 变体与游戏自带插件一致），但 Unity Player 的官方模块在本机 canonical 路由最终 404、受限输入尚未取得；窗口／音频复用边界仍需决定。详细观察、来源与证据摘要归入 [D1 研究专题](research/2026-10-11-d1-bionic-wine-runtime.md)；机器路径与大型原始输出保留在本机忽略目录，不入 Git。

D3 的图形／输入实现可以与 D2 并行，不以先完成下载器作为写游戏桥代码的条件；完整可玩仍要求真实 Steam 服务、图像、输入与音频实际成立。

## 范围与设备使用

- 当前产品目标包括实际游戏，不再把“不得运行游戏”作为开发限制；**唯一原始副本必须保持不可变**（本轮只读、未写入；不可变基线待导入事务落地时建立并校验），实际启动／替换前按 [备份流程](build/README.md#正版游戏输入与备份)建立并校验可恢复备份与独立工作副本。
- LIV／混合现实录制不做，不安排其适配或专项验证；既有无捕获调用兼容只用于不让闲置 SDK 影响游戏。
- 首轮不加载 mod；BSIPA 和 Spatial mod／谱面管理在原版可玩后实施。
- 默认 WSL 开发与构建；只在当前实现需要运行时使用设备，后台 CLI、不自动截图或抢焦点，不默认重跑原型、循环压力或成本对照。设备操作细节见 [根约定](../AGENTS.md)。
- 本项目仍无 Space Pro 运行或性能证据；真机缺失不阻止可构建实现推进，也不能将模拟器结果升级为目标机通过。

## 状态维护方式

新实验按 [记录规范](device-validation/AGENTS.md)保存结果、版本和证据校验值，再更新本文件的能力与队列状态。失败、部分通过、前提不足均应记录，不以计划存在或构建成功标记运行通过。

`ROADMAP.md` 维护阶段目标、依赖与计划入口；索引只讲概况与导航，目录维护细节放在就近的 `AGENTS.md`，见 [文档约定](AGENTS.md)；skill 维护接入边界。历史实验记录不因新计划而改写。
