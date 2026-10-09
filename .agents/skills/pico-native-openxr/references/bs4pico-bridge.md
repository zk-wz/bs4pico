# BS for Pico 的原生 XR 接入边界

游戏 XR 桥仍是工程方向，**尚非已完成的 Android 游戏桥实现**。2026-10-09 新增独立 `prototypes/spatial-openxr/` 单 APK，在 x86_64 PICO 模拟器验证真正 Spatial 管理窗口 ↔ C/C++ OpenXR Vulkan 双眼、持久数据、重复切换、生命周期和模拟追踪/右侧 trigger；ARM64 仅构建，未真机验证。进度以 `docs/plans/ROADMAP.md` 和 `docs/device-validation/2026-10-09-spatial-openxr/RESULT.md` 为准，根 `AGENTS.md` 只维护约定。

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

GameNative 的 x64 路径可作为诊断参考，但不证明本项目 Windows ARM64 组件链已经可用。上游 Steam Frame benchmark 不能用于承诺 Space Pro FPS。

## 建议的验证分段

| 验证段 | 可观察的通过条件 |
|---|---|
| 原生 XR 基线 | Space Pro APK 正确进入 immersive 模式，日志有 runtime/扩展清单，立体 Vulkan 画面正确。 |
| 空间与输入 | 头/手/双眼/地面与重置朝向正确，profile/actions/haptics 可用，摘戴/系统菜单后恢复。 |
| Wine 图形桥 | Windows 最小 XR 客户端得到真实姿态和正确双眼，图像/同步无验证错误，测得桥开销。 |
| 游戏闭环 | 正版 Steam 服务、菜单、谱面、击打/计分与声音正常，恢复与退出可靠。 |
| 持续性能 | 相同测试条件比较 baseline 与优化，验证热稳定后帧时间、延迟、画质及补帧比例。 |

这不是要求每次改动都重新完整跑一遍；选择能证明当前变化的验证段。真实结果与失败证据写到项目真机记录，不写成未经测量的 skill“已验证能力”。
