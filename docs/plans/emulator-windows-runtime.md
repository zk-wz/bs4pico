# E2：模拟器 Windows 运行环境与 ABI 探针

待实施验证计划；执行状态见 [项目状态](../STATUS.md)。目标是建立模拟器可运行的诊断链，不把 Windows x64 结果当成纯 Windows ARM64 路线通过。

## 要回答的问题

不使用游戏、root 或 PRoot，能否在 Android 应用 UID/沙箱内启动自有 Windows 程序，并打通 DLL、线程、异常和 Windows↔Unix 调用？候选运行时能否为后续 Steam、Vulkan/XR 探针提供明确的进程与 ABI 边界？

当前只有 Native Android XR 原型。根 `build.sh` 构建上游 Windows ARM64 组件，不提供完整 Android Wine；上游 [组件图](../upstream/ARCHITECTURE.md)不能视为可直接部署的 Android 运行时。

## 模拟器 ABI 门禁

现有系统镜像为 x86_64，虽报告 `arm64-v8a,x86_64`，ARM 翻译能力不证明任意 Wine 子进程、ARM64 PE/JIT 或 Vulkan thunk 可以运行。

**本计划主路径：Android x86_64 ELF 运行时 → Windows x64 PE 自有探针。**这是一条独立诊断构建，不替换产品的 ARM64 目标，也不混装仓库现有 ARM64 DLL。

候选若仅提供 Android ARM64 ELF，先核实模拟器已具备的加载/子进程机制；不能只凭 APK ABI 列表认定可运行。没有适配的可执行路径时记录阻塞，换模拟器候选或停止，不安装额外翻译环境冒充默认能力。可选 ARM64 探针即使运行成功也只算模拟器翻译路径结果，纯原生 ARM64 验证留待后续。

## 候选审计与选择

优先检查已有 Android/Bionic Wine/Proton 工作的可复用部分，不把普通 glibc Linux ELF 直接交给 Android linker。GameNative 的 Android Proton 可作候选，参考 [调研入口](../research/README.md#模拟器运行环境与-steam-候选)；发布说明中的 x86_64/arm64ec 命名不足以确定 ELF 宿主 ABI或纯 ARM64 客体能力。

每个候选产出简短清单：源码 commit、补丁、ELF interpreter/依赖和实际架构、PE 模块 machine、许可/分发边界、子进程启动方式、wineserver/prefix、窗口与音频依赖、Vulkan/Unix-call 接入。版本必须锁定；Unix-call 的编号/参数布局与 Windows/Unix 两半须一起核验，不能拼接不同 Proton 版本。

只有“存在可获取、许可可审查、适用于模拟器 ABI 的实现/构建方案”才进入运行实验。必要工具安装或环境变化先 Ask；不部署整套未经审计的容器，也不修改系统安全/网络设置。

## 分段实验

| 段 | 最小程序与操作 | 要保存的证据 |
|---|---|---|
| R0：运行布局 | 调试宿主准备独立应用数据目录/prefix；从 APK 支持的入口启动 Wine及自有 PE | UID、进程树、实际 ELF/PE 架构、工作目录、依赖闭包；ADB root/shell 身份运行不算应用沙箱通过 |
| R1：PE/DLL | 程序做 Win32 文件读写、LoadLibrary/GetProcAddress、调用自有 DLL，再返回确定退出码 | 真正执行后的结果文件/返回值，DLL 路径与加载架构；“文件已放进去”不算执行 |
| R2：线程/异常 | 多线程 event/mutex 等待与唤醒；C++ throw/catch；单独加载匹配 ABI 的私有 CRT 诊断版本 | 重复执行的计数与错误码，异常被正确捕获；与宿主线程/信号故障分开定位 |
| R3：Unix-call | 用与候选 Wine 匹配的最小 Windows/Unix 两半传标量、数组、结构和错误状态 | 双端参数/长度/结果一致、寿命及句柄归属明确；先同步请求，不扩大到全部 API |
| R4：进程管理 | 正常结束探针、关闭本次会话/prefix 的辅助进程；重复启动；Android 暂停/恢复与冷启动 | 明确哪些进程存续、哪些退出，无僵死等待或跨实验干扰；不误杀其他实例 |
| R5：音频冒烟 | 生成自有短音，走 Windows 音频 API→候选 Wine→Android 后端；测默认设备/失焦与恢复 | 实际出声及 API 状态；无回环测量则不宣称精确输出延迟或音画同步 |

R0–R4 是核心交付；R5 是独立的早期音频结果，不阻止不依赖音频的图形探针。内核同步加速不可用时评估候选已有用户态后备，不因优化需求申请 root 或开启未授权内核/环境变更。

## 通过、阻塞与范围

- 继续条件：R0–R4 有真实运行证据，正常退出可重复，版本/ABI清单完整，能够区分宿主、Wine 与 Windows 探针的失败。
- 必要依赖不适用、子进程执行受限制、异常/Unix-call 不成立时，指出阻塞属于哪一候选/层次；这只否定该组合，不宣称 Android 方案整体不可能。
- 模拟器 x64 通过不代表现有 ARM64 `steam_api64.dll`、Unity Player/Mono 或 ARM64EC 可以加载。ARM64 DLL完整构建和真机运行仍是后续门槛。
- 不运行上游游戏安装器，不调用唯一游戏副本，不借 PC/WSL 中运行的 Wine 结果冒充 Android 应用执行。

## 交付

交付候选审计结论、锁定输入、独立诊断宿主/PE/Unix-call 源码与可复现构建部署入口；新目录在实施时确定，不把尚不存在的命令写成已可执行脚本。实验依 [记录规范](../device-validation/README.md)保存在新目录，大型产物留 `private/validation/`。结果分别标识 ELF 宿主 ABI、PE 客体 ABI和是否使用翻译。

E1 可并行。E2 核心通过后支持 E3 Windows 服务探针和 E4 Windows 图形实验；Steam 候选来源审计无需等待 E2。
