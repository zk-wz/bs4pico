# BS for Pico 的原生 XR 接入边界

游戏 XR 桥仍是工程方向，**尚非已完成的 Android 游戏桥实现**。2026-10-09 新增独立 `prototypes/spatial-openxr/` 单 APK，在 x86_64 PICO 客体验证真正 Spatial 管理窗口 ↔ C/C++ OpenXR Vulkan 双眼、持久数据、切换、生命周期和模拟追踪/右 trigger；未真机验证。2026-10-10 当前安装应用主 ABI 为 arm64-v8a，系统配置 ARM64→x86_64/libhoudini 兼容路径，不能因 guest CPU=x86_64 假设应用加载 x86_64 库，也不能升格原生 ARM64 或 Windows ABI 结论。当前状态见 `docs/STATUS.md`，阶段目标见 `docs/plans/ROADMAP.md`，实际 ABI/身份及证据见本轮 E1 记录；根 `AGENTS.md` 只维护约定。

E1 历史结果见 `docs/device-validation/2026-10-10-emulator-host-xr-e1/RESULT.md`，直接复用，不默认重新运行。后续按 [产品架构](../../../../docs/plans/ARCHITECTURE.md)、[组件与云清单契约](../../../../docs/plans/COMPONENTS.md)和 [开发路线](../../../../docs/plans/ROADMAP.md)实现真实游戏，在实现中调研／选型和轻量验证；不再单设可行性探针阶段。候选不是穷尽列表，按当时官方资料、源码与上游问题继续搜索；实质取舍遵守根约定，先用 Ask 决定，常规已批准实施不反复确认。规范原生日志只读取 `BS4PicoXR` 的 PID/Activity/epoch/worker/session/seq，不双计 Java 转发；数据恢复比较新进程首次 `private read` 和上次提交快照，不比较之后合法写入的最终值。设备调用按根约定的实际能力门槛，不因 Windows Primer 构建诊断重复安装工具链。

原型的 FRAME/HAND/HEAD/EYE_SAMPLE 以同帧预测时间关联，采样包括焦点/profile 变化；失焦清空当前手有效性。haptic 仅显式 DEBUG input 配置预检，每 worker/侧一次 apply 后立即 stop；精确 XR_SUCCESS 才是 API 成功，不是物理振动。reference-space-change 不累积校准变换，真实事件与 crossing 样本才能证明重定位；未覆盖保持未覆盖。E1 runner 的 checkpoint、身份/seq 与 CLI 用法复用构建说明，不新增第二套编排。

启动扩展诊断只记录可用/启用数量及实际启用项，不为每次 session 逐个刷全量可用扩展；必需扩展存在检查不变。规范序列缺口仍是采证失败，不跳过、不推断为 XR 崩溃；日志缓冲丢失旧区间时不得拼补存活图，先另行观察正常释放再建立新场景。

## 分清三段接口

| 段 | 现有材料与待做工作 |
|---|---|
| 游戏/Unity → Windows OpenXR | `src/unityopenxr/patch_unityopenxr.py` 调整 Windows ARM64 Unity 插件；`patches/openxr-loader/` 调整 Windows runtime 发现。确认游戏真正调用的 API、扩展、图形绑定及 Unity 版本，不假设已变成 Android Unity 项目。 |
| Windows OpenXR → Wine/Unix 桥 | 上游 `wineopenxr` 来自锁定的依赖，Windows/Unix 两半有匹配 ABI；读取 `versions.env` 和实际源码。需处理结构链、句柄、回调、动作、时钟和 Vulkan thunk。 |
| Android 桥 → Pico system runtime | 独立原型已有 Android Activity、Khronos loader、生命周期与 native Vulkan 双眼；尚未接 Windows/Wine 图形和 ABI 桥。原来面向 Linux SteamVR 的 Unix 部分不能直接使用。 |

直接在产品宿主中接入 Bionic ARM64 Wine、真实 Windows ARM64 Unity／Mono 与 Android XR，优先实现游戏／XR 同进程同 Vulkan device，不把独立宿主或自有 Windows 探针作为先行项目。Wine 同进程入口尚需开发；出现实际嵌入冲突时调查修复及其他布局，不只限定于既有外部内存／同步候选，实质切换先用 Ask 决定；不直接跨进程传句柄。无 root 不等于必须 PRoot，也不证明 glibc Linux 二进制可直接运行在 Bionic 上。

D1 的源码／输入证据集中在 [Bionic Wine 专题](../../../../docs/research/2026-10-11-d1-bionic-wine-runtime.md)，分段依赖与停止条件只维护于 [游戏运行链计划](../../../../docs/plans/game-runtime.md#实施门槛与并行安排)。fork 有 WineAndroid JNI 源码入口，但并非本产品已可返回的嵌入宿主；x18／ART信号／退出须源码适配，不能仅加编译flag。当前等待窗口／音频复用边界选择，不把规划或原型画面当D1运行成功。

## 桥必须正确转接的内容

从游戏启动 trace/源码明确实际需要的核心函数与扩展，并建立兼容范围：instance/system/session、空间与 events、帧时序、views、swapchains、actions/bindings/haptics、Vulkan 图形要求和创建。不同系统可用的 graphics binding 可能不同；例如 Windows D3D11 XR 绑定需要转成真正的 Android Vulkan 绑定，不能把 D3D 句柄传给 Pico。

`xrGetInstanceProcAddr` 返回的函数必须是对应 ABI 的入口。输入/输出 `next` 链逐类型转换并正确保留寿命，handle 与 Vulkan 对象维护映射；未实现扩展拒绝或不宣告支持，不能静默丢弃游戏依赖的数据。Wine Unix 侧可调用 Android loader 的事实本身不解决结构 ABI 和资源所有权。

整条路径复用 runtime 的帧时间和预测 pose；各层都遵守 OpenXR 坐标时保持原值，Unity 内部转换留在已有插件负责的位置。更详细的图像与坐标约束见 [渲染与输入](rendering-input.md)。

## 桌面与系统 UI

XR projection 是最终双眼画面；桌面镜像属于游戏/Unity/Wine 窗口系统，OpenXR 没有“关闭游戏桌面渲染”的通用命令。先保留启动所需窗口/Surface，用现有设置或适配降低镜像分辨率、刷新或停止额外 mirror blit，检查是否仍正确产生 XR 帧。

不显示桌面窗口不代表镜像 GPU 成本消失，也不代表游戏能够无窗口运行。Steam 登录与启动诊断仍需要可访问的界面，可按需展示 Android 页面或受控面板；正式游玩不必持续把桌面投到 VR 层。登录/账号交互不能因主画面隐藏而不可用。

Spatial SDK 的统一渲染/窗口与 OpenXR 自渲染 projection 是不同契约。本次两 Activity 配置在模拟器可切换，官方未保证此组合；PICO 可分配不同任务，必须显式保证单场景所有权，并等待旧 immersive Activity 的销毁事务后再次进入 VR。管理容器关闭不等于 application 级 SDK 卸载或零后台开销；真实显示模式、焦点与资源成本仍需 Space Pro 复核，不能把 Spatial wrapper 当成 Windows XR adapter。

## 配套产品范围与实现边界

Windows ARM64 Player／Mono、Bionic Wine、DXVK、音频和真实 Steam 服务在实际游戏开发中集成。本 skill 不提供 Steam 授权替代物；沿用 `docs/upstream/LEGAL.md` 与真实账号／DLC 所有权要求。LIV／混合现实录制不开发，不做其专项验证；既有无捕获 ABI 仅防止闲置 SDK 干扰游戏。先原版可玩，BSIPA 与 Spatial mod／谱面管理在后续计划中实施。

GameNative 已有真正 Windows OpenXR 双眼／动作桥，但当前 Windows runtime 按 x86／x64 构建，Android 侧是跨进程 GLES 提交；参考其协议与生命周期，不照搬忽略请求时间、同步失败合成成功或 CPU 上传的行为。Bionic Proton 是开发基线，不代表本项目纯 ARM64 Unity 链已运行；源码与采用边界见产品架构。上游 Frame benchmark、模拟器和任何 ARM 翻译结果不能升级为 Space Pro 原生运行／性能结论。

云清单登记不等于远程代码装载已实现；APK 内置、用户／Steam 输入、系统与未来下载模块都在同一契约内。游戏只使用已提交的 `resolutionSnapshotRef`，记录实际 XR／GPU／音频／输入与组件身份；不在帧热路径查云目录、不热替换 native 模块、不为下载模块化增加图像复制／逐帧 IPC。完整安装／许可／信任／回退规则统一维护在组件契约；云发布和更新在 D4，不能阻塞 D1–D3 写实际游戏。


## 开发时的必要检查

检查正在实现的实际路径，不把以下内容拆成必须先全部通过的验证阶段。

| 实现能力 | 一次轻量检查的实际结果 |
|---|---|
| 游戏启动与授权 | 产品宿主执行真实 Unity 游戏，日志对应实际 ARM64 组件与真实 Steam 服务；页面不是假启动成功。 |
| 双眼与输入 | 游戏菜单有真实 projection、头与双手驱动内容，时间／空间／图像同步符合 runtime 契约。 |
| 游玩与音频 | 一首正版歌曲实际击打、计分和出声；暂停／返回管理正常。 |
| 交接与恢复 | 对本次改动影响的 Back／Home／失焦或重建边界各确认一次，复用已有 E1，不默认重跑整套原型。 |
| 性能修正 | 在实际游戏里记录被修复瓶颈的帧时间／等待／复制；持续或重复采样仅在用户专项要求时执行。 |

默认 WSL 构建与静态检查；无运行必要不启动模拟器，需要设备时后台 CLI、不自动抢焦点或截图。人工交互确有必要时集中请求用户操作。失败在当前功能内修复或换实现，不恢复前置探针循环；结果和未覆盖条件更新 `docs/STATUS.md`，必要设备证据按既有记录规范保存，不写成未经测量的 skill“已验证能力”。
