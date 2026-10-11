# D3：实际游戏的 OpenXR、输入与音频闭环

## 产品成果与依赖

从 Spatial 管理页启动 D1 的正版工作实例，进入真正的双眼 Beat Saber 菜单，以头部和左右手控制器交互，完成一首正版歌曲的击打／计分／出声，再正常返回管理页。不是自有方块、平面投屏、预录视频或只会创建 session 的探针。

- 依赖 [D1](game-runtime.md) 的真实 ARM64 Unity／Mono／Bionic Wine／DXVK 与实例启动；完整游玩需要 [D2](steam-integration.md) 的真实 Steam 服务。
- XR／输入／音频代码可以与 D2 并行开发，不等下载器或全部账号页面完成；尚未获得真实授权时不能把歌曲闭环记为通过。
- 共同进程、图像和时间契约见 [架构](ARCHITECTURE.md)，执行顺序见 [ROADMAP](ROADMAP.md)，实际结果只维护在 [STATUS](../STATUS.md)。

## 已有落点与实施时新增模块

| 落点 | 开发内容 |
|---|---|
| `prototypes/spatial-openxr/app/src/main/cpp/xrprobe.cpp`、`CMakeLists.txt` | 复用 Android loader、VM／Activity、Vulkan 与 lifecycle 基础；以游戏 XR 后端替换自有场景和独立渲染循环。 |
| 同一 app 的 `platform/VrActivity.kt`、`SpatialApplication.kt`、`LaunchActivity.kt` | 接 D1 的跨进程交接、真实启动／退出状态、Home／失焦／重建；游戏进程不初始化 Spatial 管理渲染。 |
| `src/unityopenxr/patch_unityopenxr.py`、`patches/openxr-loader/` | 保留匹配版本 ARM64 UnityOpenXR 和 Windows runtime 发现，指向本产品桥而非 SteamVR。 |
| Proton `wineopenxr` 与 `winevulkan`，`build.sh`、`versions.env` | 构建匹配的 ARM64 PE／Android Bionic Unix 两半，复用 DXVK D3D11 interop、句柄与结构转换。 |
| `src/wine-runtime/android/`（D1 实施时新增） | 接入 Android XR 生命周期／图形／输入／时钟和音频后端；对应源码必须纳入产品构建，不依赖研究 checkout。 |

Kotlin 路径相对 `app/src/main/java/io/github/zkwz/bs4pico/probe/`。新增 native 桥按上述职责拆入现有 app 和运行时模块，不创建第二个 APK、独立 XR 探针或通用完整 OpenXR runtime。

## 共享接口与归属

- 沿用 [共享契约](ARCHITECTURE.md#数据与后续扩展契约)的 GameInstance／LaunchRequest／RunState；日志与错误关联 runId，旧 session／Activity 回调不能推进新会话状态。
- Windows 游戏拥有客户端 XR 调用顺序；Android 桥拥有对应 native instance／session，Activity 提供有效 VM／Activity 引用及 lifecycle。没有第二个自由运行的宿主帧循环。
- DXVK 与 runtime 必须绑定兼容的同一 native Vulkan device／queue；句柄先由 Wine 映射解包，图像由 runtime 所有，桥仅维护客户端包装和使用租约。
- 管理进程只接收低频启动／结束／错误；高频 pose、action 和图像留在游戏／XR 数据通路，不能逐帧绕经 Spatial。
- XR 桥、Vulkan 驱动、音频后端和输入 profile 的组件身份遵循 [组件契约](COMPONENTS.md)，绑定 GameInstance／LaunchRequest 的 `resolutionSnapshotRef`；启动采用已解析的不可变 ResolutionSnapshot，不能在运行中替换驱动、桥或输入／音频配置。云目录只在准备阶段参与解析，不承担远程帧处理，也不进入逐帧 IPC／查询；本机布局确需拆进程时仅使用下述受控协议。
- 实施相关功能时核对当前主要文档、源码和 upstream issue，并搜索所列候选之外的新方案；比较实际性能、ABI、许可证、生命周期和维护成本。替换进程布局／驱动或其他重大架构、隐私、维护与体验取舍前，将 2～5 个真实选项、证据与推荐集中 Ask，等待选择再落地，继续无关工作；既定默认与日常修正不重复询问。决策／重开条件写入现有 decisions，证据写入 STATUS／设备记录，不建立独立探针阶段。

## 实现顺序 1：游戏实际调用接到 Android runtime

1. 随真实游戏启动日志梳理必要核心调用与扩展，复用 Proton 现有分派／结构转换，只宣告实际实现的支持；不假造 Unity 请求的必要能力。
2. 将 Windows ARM64 loader 配到自己的 runtime JSON／DLL；Wine PE 和 Unix 两半按同一 commit／协议成对构建，禁止混用 Frame glibc Unix 库与 Android Bionic。
3. 在 Native Activity 所在进程初始化唯一 Android loader：有效 JavaVM／Context，instance 创建加入 Android Activity 信息，JNI 引用与线程 attach/detach 有明确寿命。
4. 转接 instance/system、events、session、reference spaces、views、swapchains、actions/bindings/haptics 和真实帧调用；处理用到的 `next` 链，未实现扩展拒绝而非静默丢弃。
5. 生命周期按 XR READY／STOPPING／LOSS_PENDING／EXITING 和 Android Activity 状态共同执行；不能仅因 onResume 开始提交，也不能在运行时退出后自动无限重进。
6. 修复当前游戏调用暴露的 ABI／异常／时钟问题，沿同一次产品启动继续接入，不先建立最小 Windows 客户端项目。

## 实现顺序 2：D3D11 到双眼 Vulkan 图像

1. 沿 Windows 图形 requirements 与 Proton interop，把 runtime 所需物理设备、Vulkan 版本／扩展／queue 约束传到 DXVK 设备创建；不能先建不兼容设备，再替换一个 physicalDevice 句柄冒充匹配。
2. 默认系统驱动，枚举实际格式、sample count、尺寸和 sRGB／线性支持；选定组合进入游戏。能力不足、渲染错误或瓶颈时，以当前主要来源研究 Turnip 和其他可行驱动，不把 Turnip 当唯一自动后备；有重大性能／ABI／许可／维护取舍先 Ask，选定驱动随兼容组件集合写入下次启动快照。
3. 复用 DXVK interop 取得 instance/device/queue，将 runtime swapchain VkImage 包装成 Unity 得到的 D3D11 texture；Wine client→native 映射固定到所选源码，不使用私有布局的启发式偏移猜测。
4. 如直接包装暂时受实际格式／用法限制，实施同 device GPU copy／resolve，并保留正确的 acquire/wait/render/release、layout、queue ownership 与完成同步。不得以 CPU readback 或每帧 vkDeviceWaitIdle 作为正式数据通路。
5. 保留双眼数组层、eye order、FOV 和原渲染 pose；Windows/D3D 图形绑定转换为 Android Vulkan，不把 D3D 句柄直接交给 Android loader。
6. 以实际游戏菜单看到内容为首个图形成果；平面镜像仅作诊断，不充当双眼 projection。先保证正确，不默认启用上游有内容丢弃风险的 MSAA 优化。

## 实现顺序 3：唯一帧时间、头部与双手

1. 转接游戏的 xrWaitFrame／xrBeginFrame／xrEndFrame 到唯一真实 runtime 时间线，保持返回的 predictedDisplayTime；shouldRender=false 时按协议零层结束并跳过昂贵渲染。
2. 按调用请求的时间 locate views／spaces，不把最近快照当任意时刻的正确 pose；Wine QPC 和 XrTime 按真实转换契约接通，不为同步失败生成固定周期假成功。
3. 保持 OpenXR 米制、参考空间和坐标语义；Unity 插件已做的转换不重复翻 Z。地面空间不足时实施真实校准并处理重定位的生效时间／空间变化。
4. 按实际 PICO profile 补齐游戏左右手 grip／aim、按钮、trigger 与 haptic 绑定，不伪报另一设备。分别处理 active、valid/tracked flags、焦点及控制器重连。
5. 直接在菜单与歌曲中修正剑柄位置、方向、左右眼、击打与暂停输入；无效 tracking 不可映射为世界原点或继续计分。haptic 走真实动作，有 API 支持但未观察体感时明确区分。
6. 双眼菜单可交互后，进入一首用户拥有的原版歌曲，确认游戏自身实际击打／计分；不注入 mod 作为首轮输入或判定的替代。

## 实现顺序 4：音频、暂停与返回

1. 接 D1 的 Wine Windows 音频后端到 Android 输出；优先复用合法可获取的 PulseAudio／AAudio 集成，明确输出进程、缓冲、格式与线程，按实际需要降低延迟。
2. 音频时钟、游戏节拍和 XR 预测时间分开保持语义；不因 XR 图像同步就宣称音画同步已解决。按实际歌曲偏差修复输出／缓冲与校准，不合成假时间戳。
3. 菜单／歌曲失焦、系统 Home 和暂停时，通过游戏实际生命周期／输入语义暂停音乐及判定；不能只停宿主绘制而让歌曲在后台继续。
4. Back／正常结束先结束游戏／XR 使用，确认 GPU 图像不再被写入，再释放 session、Surface 和本会话 Wine／音频资源，之后恢复 Spatial 管理页。
5. Activity 重建或 runtime loss 销毁旧资源并重建；若无法保留歌曲现场，明确返回菜单／重启游戏，不继续复用旧句柄或声称无缝恢复。

## 同进程无法可靠实现时的产品切换

D1 如已确认 Wine／ART 嵌入冲突且常规修正无效，在当前实现中研究 Wine 子进程＋Native XR 进程及其他可行布局，比较当前主要来源、实际性能、ABI、生命周期和维护成本，提交有证据的选项并 Ask 后再切换，不自动采用列出的后备，也不重新开启可行性阶段。若选择本机拆进程：

- 实现受控帧请求／结果协议：runId、session、frame序号、请求时间／预测时间、pose/FOV、输入、图像租约及错误。Android runtime 仍是唯一 wait/begin/end 来源，游戏调用驱动该协议，不设置独立重放循环。
- AHardwareBuffer／dma-buf／external memory 和 fence／semaphore 依双端真实能力导入，接收端 Vulkan device 不使用生产端裸句柄；同步对象失败要传播实际错误。
- 用 Vulkan 生成 runtime projection，先允许必要 GPU copy；不照搬 GameNative 的 GLES／CPU 上传后备或合成同步成功。
- 游戏未交出新帧、会话结束或进程死亡时，按 runtime 契约结束／回收租约，不将旧图像配新 pose 标记为已成功渲染帧。
- 记录所采用布局并移除被替代默认实现。若关键 external memory／同步在目标组合确实不可实现，保留具体失败与修正尝试供用户决定，不以平面投屏缩减“VR 可玩”。

## 随实现进行的轻量路径检查与完成条件

在上述实施步骤接通当前路径时，沿一次连贯产品会话确认：Spatial 启动 → 真实授权游戏双眼菜单 → 头／左右手实际交互 → 一首正版曲目的击打、计分、出声 → 游戏暂停／继续 → 正常返回 Spatial。不是独立验收阶段；只对本次改动涉及的失焦或重建必要边界各确认一次，不默认五轮／压力／独立图形探针，不为检查另增环境／设备动作。记录实际 runtime、GPU/driver、ABI、组件版本、`resolutionSnapshotRef`、所用配置与未覆盖条件。

- 观察真实双眼和动作，不用截图背景、DLL加载、API成功或日志帧计数代替游戏显示／行为。模拟器不支持的双手或真机能力保持未覆盖。
- 无音频回环／测量时只报告实际出声与观察到的偏差，不给精确输出延迟结论；游戏帧率与合成／补帧帧率分别描述。
- 日常开发优先 WSL；无运行需要不开模拟器，需要运行时后台 CLI，不自动前台／截图；确需用户空间操作时把这次会话目标集中一次 Ask。
- 完成须包含真实游戏图像、双手输入、歌曲行为、音频和正常退出；构建好但缺目标设备的运行路径明确待验收，不伪造“可玩”。结果更新 STATUS 和必要设备记录。
- 非目标：LIV／混合现实录制、模组加载、通用 PC VR 平台、眼动／注视点专项、长时间压测；可玩的原版交给 [D4](game-delivery.md)，mod 后续由 [D5](mod-chart-manager.md)实施。

## 实现参考

[Proton D3D11／XR interop](https://github.com/ValveSoftware/Proton/blob/bc896217ffcd67f892f952b010f898fe7bd0f0a1/wineopenxr/openxr_loader.c)、[GameNative Windows XR](https://github.com/utkarshdalal/GameNative/tree/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/windows/openxr_runtime)、[GameNative Android XR](https://github.com/utkarshdalal/GameNative/tree/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/cpp/xrimmersive)和 [Native OpenXR skill](../../.agents/skills/pico-native-openxr/SKILL.md)仅提供已有机制与规范；移植后使用本产品 ABI、真实时间与 Vulkan 所有权，不把源码存在写成已通过。
