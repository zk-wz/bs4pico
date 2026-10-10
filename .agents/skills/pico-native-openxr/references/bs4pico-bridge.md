# BS for Pico 的原生 XR 接入边界

游戏 XR 桥仍是工程方向，**尚非已完成的 Android 游戏桥实现**。2026-10-09 新增独立 `prototypes/spatial-openxr/` 单 APK，在 x86_64 PICO 客体验证真正 Spatial 管理窗口 ↔ C/C++ OpenXR Vulkan 双眼、持久数据、切换、生命周期和模拟追踪/右 trigger；未真机验证。2026-10-10 当前安装应用主 ABI 为 arm64-v8a，系统配置 ARM64→x86_64/libhoudini 兼容路径，不能因 guest CPU=x86_64 假设应用加载 x86_64 库，也不能升格原生 ARM64 或 Windows ABI 结论。当前状态见 `docs/STATUS.md`，阶段目标见 `docs/plans/ROADMAP.md`，实际 ABI/身份及证据见本轮 E1 记录；根 `AGENTS.md` 只维护约定。

E1 本轮结果见 `docs/device-validation/2026-10-10-emulator-host-xr-e1/RESULT.md`；按用户最新范围只做轻量基础验收，默认 baseline 一轮，不自行加压测或重复成本对比。规范原生日志只读取 `BS4PicoXR` 的 PID/Activity/epoch/worker/session/seq，不双计 Java 转发；数据恢复比较新进程首次 `private read` 和上次提交快照，不比较之后合法写入的最终值。现有模拟器操作按根 `AGENTS.md` 的实际运行能力门槛，不把 Windows 构建 doctor 作为设备操作前提。

原型的 FRAME/HAND/HEAD/EYE_SAMPLE 以同帧预测时间关联，采样包括焦点/profile 变化；失焦清空当前手有效性。haptic 仅显式 DEBUG input 配置预检，每 worker/侧一次 apply 后立即 stop；精确 XR_SUCCESS 才是 API 成功，不是物理振动。reference-space-change 不累积校准变换，真实事件与 crossing 样本才能证明重定位；未覆盖保持未覆盖。E1 runner 的 checkpoint、身份/seq 与 CLI 用法复用构建说明，不新增第二套编排。

启动扩展诊断只记录可用/启用数量及实际启用项，不为每次 session 逐个刷全量可用扩展；必需扩展存在检查不变。规范序列缺口仍是采证失败，不跳过、不推断为 XR 崩溃；日志缓冲丢失旧区间时不得拼补存活图，先另行观察正常释放再建立新场景。

## 分清三段接口

| 段 | 现有材料与待做工作 |
|---|---|
| 游戏/Unity → Windows OpenXR | `src/unityopenxr/patch_unityopenxr.py` 调整 Windows ARM64 Unity 插件；`patches/openxr-loader/` 调整 Windows runtime 发现。确认游戏真正调用的 API、扩展、图形绑定及 Unity 版本，不假设已变成 Android Unity 项目。 |
| Windows OpenXR → Wine/Unix 桥 | 上游 `wineopenxr` 来自锁定的依赖，Windows/Unix 两半有匹配 ABI；读取 `versions.env` 和实际源码。需处理结构链、句柄、回调、动作、时钟和 Vulkan thunk。 |
| Android 桥 → Pico system runtime | 独立原型已有 Android Activity、Khronos loader、生命周期与 native Vulkan 双眼；尚未接 Windows/Wine 图形和 ABI 桥。原来面向 Linux SteamVR 的 Unix 部分不能直接使用。 |

推荐先验证 Android Native Vulkan XR 宿主，再选择与宿主共享进程/设备的桥布局以减少开销。跨进程方案若必须采用，应显式设计资源与同步协议并测延迟；无 root 不等于必须 PRoot，也不证明普通 Linux 二进制可直接运行在 Android Bionic 上。

## 桥必须正确转接的内容

从游戏启动 trace/源码明确实际需要的核心函数与扩展，并建立兼容范围：instance/system/session、空间与 events、帧时序、views、swapchains、actions/bindings/haptics、Vulkan 图形要求和创建。不同系统可用的 graphics binding 可能不同；例如 Windows D3D11 XR 绑定需要转成真正的 Android Vulkan 绑定，不能把 D3D 句柄传给 Pico。

`xrGetInstanceProcAddr` 返回的函数必须是对应 ABI 的入口。输入/输出 `next` 链逐类型转换并正确保留寿命，handle 与 Vulkan 对象维护映射；未实现扩展拒绝或不宣告支持，不能静默丢弃游戏依赖的数据。Wine Unix 侧可调用 Android loader 的事实本身不解决结构 ABI 和资源所有权。

整条路径复用 runtime 的帧时间和预测 pose；各层都遵守 OpenXR 坐标时保持原值，Unity 内部转换留在已有插件负责的位置。更详细的图像与坐标约束见 [渲染与输入](rendering-input.md)。

## 桌面与系统 UI

XR projection 是最终双眼画面；桌面镜像属于游戏/Unity/Wine 窗口系统，OpenXR 没有“关闭游戏桌面渲染”的通用命令。先保留启动所需窗口/Surface，用现有设置或适配降低镜像分辨率、刷新或停止额外 mirror blit，检查是否仍正确产生 XR 帧。

不显示桌面窗口不代表镜像 GPU 成本消失，也不代表游戏能够无窗口运行。Steam 登录与启动诊断仍需要可访问的界面，可按需展示 Android 页面或受控面板；正式游玩不必持续把桌面投到 VR 层。登录/账号交互不能因主画面隐藏而不可用。

Spatial SDK 的统一渲染/窗口与 OpenXR 自渲染 projection 是不同契约。本次两 Activity 配置在模拟器可切换，官方未保证此组合；PICO 可分配不同任务，必须显式保证单场景所有权，并等待旧 immersive Activity 的销毁事务后再次进入 VR。管理容器关闭不等于 application 级 SDK 卸载或零后台开销；真实显示模式、焦点与资源成本仍需 Space Pro 复核，不能把 Spatial wrapper 当成 Windows XR adapter。

## 不属于 OpenXR 的其他阻塞项

Windows ARM64 Player/Mono、Wine 的 Android 适配、DXVK Vulkan backend、原生插件、资源存储、音频和 Steam 真实客户端服务需分别推进。本 skill 不提供 Steam 授权替代物；沿用 `docs/upstream/LEGAL.md` 与实际账号/DLC 所有权要求。

GameNative 的 x64 路径可作为诊断参考，但不证明本项目 Windows ARM64 组件链已经可用。E1–E4 只覆盖模拟器宿主、Windows 运行环境、真实 Steam 和图形桥探针；执行状态与未覆盖项以 `docs/STATUS.md` 及独立实验矩阵为准。x86_64 诊断与任何 ARM 翻译结果不得升级为纯 ARM64 或真机通过。候选运行时/真实服务缺少可用 ABI 时保留阻塞，不假定 APK 的 ARM ABI 列表能解决任意子进程、PE/JIT 和 Vulkan thunk。上游 Steam Frame benchmark 不能用于承诺 Space Pro FPS。

## 建议的验证分段

| 验证段 | 可观察的通过条件 |
|---|---|
| 原生 XR 基线 | Space Pro APK 正确进入 immersive 模式，日志有 runtime/扩展清单，立体 Vulkan 画面正确。 |
| 空间与输入 | 头/手/双眼/地面与重置朝向正确，profile/actions/haptics 可用，摘戴/系统菜单后恢复。 |
| Wine 图形桥 | Windows 最小 XR 客户端得到真实姿态和正确双眼，图像/同步无验证错误，测得桥开销。 |
| 游戏闭环 | 正版 Steam 服务、菜单、谱面、击打/计分与声音正常，恢复与退出可靠。 |
| 持续性能 | 相同测试条件比较 baseline 与优化，验证热稳定后帧时间、延迟、画质及补帧比例。 |

这不是要求每次改动都重新完整跑一遍；选择能证明当前变化的验证段。真实结果与失败证据写到项目真机记录，不写成未经测量的 skill“已验证能力”。
