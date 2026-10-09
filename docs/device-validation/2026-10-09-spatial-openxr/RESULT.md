# 实验：同 APK Spatial 管理窗口 / Native OpenXR 切换

- 日期、运行编号：2026-10-09，WSL 第一阶段原型；包含失败迭代、最终 CLI 场景以及用户人工操作。
- 结论：**x86_64 模拟器架构基线通过；ARM64 Space Pro 与性能结论待验证**。
- 目标：真正的 PICO Spatial SDK 管理界面与 C/C++ OpenXR Vulkan 场景双向切换、私有数据共享和生命周期释放；不接入游戏/Wine/Steam。

## 条件

- 源码：WSL `/home/zkwz/projects/bs4pico`，基于 `599c1a4feb00b3b7d4bf337ffe36ee880226222a` 的本次未提交原型和文档改动；Windows checkout 未同步。
- 设备：Windows PICO Emulator bundle 6.1.0，现有 `Pico_Emulator_6_1`，ADB `emulator-5554`，系统 x86_64、Android API 36。ABI 列表含 ARM 翻译能力，不是真机验证。
- 构建：系统 Arch JDK 21.0.12.1；全局 SDK 平台 35、build-tools 36.1.0、NDK 30.0.16248370；CMake 4.4.4、Ninja 1.13.2；Gradle 8.13 / AGP 8.13.2 / Kotlin 2.1.20。
- Spatial：官方 planar 模板线 6.1.0，实际 BOM 6.1.9；保留官方 Application.launch、SpatialLaunchActivity、DefaultWindowContainer 和 PicoTheme/SpatialUI。
- OpenXR：Khronos Android loader AAR 1.1.49；instance 请求 API 1.0。runtime `Pico XRRuntime()`，system `Pico-emulator HMD`；实测支持 Android create_instance 和 Vulkan enable2，BD controller interaction version 2。
- 图形：runtime 指定的 NVIDIA GeForce RTX 4070 Laptop GPU，物理设备 Vulkan 1.3；双眼各 1920×1920、sampleCount=1，真实 projection layer。STAGE 参考空间、地面网格和固定彩色立方体。
- APK：`prototypes/spatial-openxr/app/build/outputs/apk/debug/app-debug.apk`，debug 签名，39,227,121 bytes，x86_64 + arm64-v8a。
- SHA-256：`8d96313d52c6e5130aa63540634e7b19fa0fc59269fc0c120ba694fb1458bb1b`。`apk-metadata.json` 保存两 ABI 的 loader、xrprobe 和 libc++ 库清单；aapt2 确认 min/target/compile API 35、默认入口 LaunchActivity。
- 登录/授权、游戏/Unity/Wine/DXVK、曲目/音画同步：不适用，原型未接入。

## 步骤与结果

| 验证项 | 实际操作和证据 | 结论 |
|---|---|---|
| 构建与部署 | Wrapper 成功编译两 ABI；Windows Pico CLI 通过 WSL UNC 路径 streamed install 返回 Success，app launch 成功 | 通过 |
| 默认管理界面 | SDK 注册入口 + SpatialLaunchActivity；实际管理窗口和“进入 VR”按钮，见 `manager-window.png`、`home-relaunch-manager.png` | 通过，不是普通 Android 平面页面替代 |
| 真正 OpenXR 双眼 | instance/session、READY/beginSession、FOCUSED、FIRST_STEREO_FRAME、views=2、viewFlags=0xf；左右眼初始位置 x=-0.032/+0.032；两 Vulkan swapchain 提交 | 通过，未使用平面 VR 后备 |
| 实际按钮与恢复后输入 | 用户在 Home 退出后重开的管理窗口点击“进入 VR”，再次看到方块/网格；对应 20:35:14 的新双眼帧 | 人工 + 日志通过 |
| 头部追踪 | 用户 WASD 移动、右键拖动；head 从 (0,1.650,0) 变到 (2.545,1.668,-2.096)，四元数变到 (-0.011,0.392,0.005,0.920)，flags=0xf；画面透视改变 | 模拟头部平移/旋转通过 |
| 模拟控制器 | 实际 profile 为 Pico 4；右 aim pose 随交互改变，右 trigger 于 20:35:23.680 为 1.000，20:35:26.681 回到 0.000；右 grip/aim valid/tracked=1 | 右侧 profile、aim、trigger 通过；左侧在本次模式 inactive；grip 位置保持固定，不能写成两只真实 6DoF 控制器验证 |
| 私有数据 | Kotlin AtomicFile 写 `filesDir/switch-probe.txt`；C++ 同 UID 读取并更新；返回管理 Activity.onResume 展示 native 更新。最终 generation=24、native_visits=34、last_writer=native | 通过；冷启动、Home 和重建未丢数据 |
| 重复切换 | 最终 `verify-emulator.py --cycles 5`：五轮新双眼帧、Manager 不在 Activity 历史栈、Back 销毁 session、返回读取相同文件 | 通过；该场景未出现崩溃/恢复失败，不代表长期压力测试 |
| Android Back | 包内 ADB KEYCODE_BACK 走真实返回路径；xrRequestExitSession → STOPPING/endSession → 两 swapchain/session/instance destroy=0 → worker join，再启动管理界面 | 通过 |
| Activity 重建 | Debug Intent 触发真实 Activity.recreate，日志 restored=true；管理数据保留，Native 旧 session 释放后新 session 提交双眼 | 通过；不是进程死亡/内存压力恢复的穷举验证 |
| Android 暂停/恢复 | 向现有 Native Activity 交付新 Intent，系统产生真实 onPause/onResume；旧 worker/session 释放，新 session 渲染成功 | 通过；未测试摘戴、待机和跟踪丢失 |
| 系统 Home 弹窗 | KEYCODE_HOME 先显示“返回主界面”确认框；XR FOCUSED→VISIBLE，xrSyncActions 返回 NOT_FOCUSED；scene 仍可见，按 shouldRender 继续合法提交 | 通过；弹窗阶段不应误要求 Android onPause 或 session destroy |
| Home 确认退出/重开 | Ask 阻断，请用户点“确定”；用户确认已回到系统主界面。20:31:51 SurfaceDestroyed、onPause/onStop、session/instance destroy=0、worker join；CLI 重开管理窗口，数据 23/32 保留，再实际点击进入 VR | 人工 + 运行证据通过；“取消”按钮恢复路径未单独通过 |
| 管理渲染生命周期 | 进入 VR 后 manager finish/onStop/onDestroy；SDK `SpatialContainerStateListener onDestroy`，如 20:35:14.522 id=54；Native Activity 历史中没有管理实例 | 管理 Activity/容器已关闭；不能据此声称整个 Spatial SDK 完全退出或 GPU/CPU 零残留 |
| 直接 Native 对照 | 冷进程显式启动 VrActivity，不先打开管理窗口；同一 C++ 场景提交双眼、相同模拟 head pose，用户恢复窗口后确认可见，见 `direct-native.png`；Back 释放成功 | 功能对照通过；性能比较仅为下述受限观察 |
| 调试结束 | Pico CLI emulator stop SUCCESS；随后 status PARTIAL，processRunning=false、adbOnline=false、candidates=[] | 已关闭；status 的退出码 4 在此是“没有在线模拟器”的正常诊断结果 |

`native_visits` 统计**成功创建的 XR session**，不是导航次数；恢复/重建/新 Intent 的系统 pause/resume 都可能增加计数。判定状态用持久数据、真实 Activity/session 转移，不把每次重建只能增加 1 当作契约。

### 模式、Manifest 与生命周期决定

管理 Activity 使用官方 Activity 级 `pico.spatial.windowcontainer.*` metadata，不设置 launchMode。Native 是独立普通 Android Activity + SurfaceView 生命周期门控；实际渲染仅走 OpenXR swapchain，Android Surface 不绘制“假 VR”。Native Activity 声明 IMMERSIVE_HMD 和 Activity 级 `pvr.app.type=vr` / `pvr.sdk.version=OpenXR`，没有应用全局 VR 标记；最终 merged Manifest 保留 SDK 的 application spatial 标记，以及 Khronos AAR 合并的 runtime broker provider/service queries 和权限。

官方资料没有提供此 Spatial + Native 两 Activity 共存及 Activity 级 pvr 元数据覆盖的保证。这份 Manifest 在本次模拟器实测可用，不应直接写成 Space Pro 已支持的官方应用模式。

SDK/OS 可把管理与 Native 分到不同任务，不能依靠 Android 单任务栈确保互斥。Application 用弱引用跟踪当前场景；新入口会先退休旧 Native worker 或关闭旧管理 Activity。快速重新进入 Native 时，如果旧 immersive Activity 尚未销毁，等待它的 onDestroy，再在主线程下一事务启动；不使用固定延迟或失败重试。UI 进入后销毁管理界面；返回重新创建管理界面并读取持久文件。

### 失败迭代与真实限制

1. 初始五轮常规返回切换可用，但从 Native 活动时重新打开管理入口，旧 VR 仍活动。系统日志明确拒绝再次 fullscreen：`current full space don't allow start fullscreen`，START result=100。仅调用 finish，或仅删除 Native singleTop，均不足以解决其销毁事务尚未完成的窗口。最终增加单场景所有权和 onDestroy 后交接；回归脚本先冷启动 Native，再从管理入口进入，最终通过。
2. 初始验证脚本把“重建只创建一份新 session”当成条件；新 Intent 自身会先产生 pause/resume，因此出现多次合法创建。删除这一实现细节断言，改为检查旧 session 释放、新双眼和 generation 保留/计数单调。
3. 初始 Home 检查错误地要求立刻 session destroy；实际是空间确认框，Native 仍 VISIBLE。改为检查失焦与合法可见帧；最终通过 Ask 完成人工确认退出，不用强杀冒充正常生命周期。
4. 试过 host 鼠标/窗口消息，无法可靠完成空间确认且会与用户争用桌面，已停止此类自动化。今后只用 CLI；必须人工时在稳定场景用 Ask 说明操作，不另阻塞 todo。
5. Pico CLI screenshot 命令成功但遗漏应用合成层：`manager-start.png` 只有背景/启动器、`native-pico-cli.png` 大部黑色。真实窗口截图使用有界 PrintWindow 后备，无鼠标/焦点操作；最小化时拒绝截图并 Ask 请求用户恢复。原生直接场景最终截图由用户恢复窗口后采集。
6. WSL Android CLI 找不到 Windows emulator；Windows ADB 监听 localhost，WSL NAT 网关连接超时。使用 Windows Pico CLI/包内 ADB，未改网络、防火墙、PATH 共享或 Windows 构建环境，见 `tool-comparison.txt`。
7. 构建有 SDK XML v4/v3 解析警告，以及 onBackPressed override 废弃提示；不屏蔽警告。实际构建和 Back 路径通过，未升级环境来消除诊断。

## 性能（受限观察）

同一 APK/几何/模拟 head pose；“直接 Native”仍执行 SpatialApplication.launch 注册 SDK，因此不是剥离 Spatial 依赖的纯 Native APK。仅对应用进程 `/proc/<pid>/stat` 做各一份约 5 秒观察，未控制 Windows 前台/遮挡/最小化、主机负载或预热，不形成性能优劣结论。

| 观察 | Spatial 切换后 Native | 冷进程直接 Native |
|---|---:|---:|
| 采样间隔（秒，含读取） | 5.449 | 5.423 |
| 应用 user+kernel CPU ticks 增量 | 38 | 87 |
| 采样结束线程数 | 66 | 48 |
| 采样结束 RSS pages | 189862 | 159444 |

数据见 `direct-comparison.json`。切换后的进程确实保留更多线程/驻留页；不能把它们全部归因于 Spatial 活动渲染，可能涉及 SDK/runtime、Compose/JVM 预热与缓存，原因未剖析。容器已销毁不等于 application 级 SDK 被卸载。

GPU 时间、CPU 分线程归因、帧时间分位数、输入延迟、持续运行、热稳定、Space Pro 性能：**未测**。模拟器受桌面窗口状态影响，不能据其帧号或 CPU ticks 报真机 FPS，也不能宣称切换路径“零后台开销”。

## 复现与简短人工流程

构建、安装、默认/直接入口和全局工具链配置见 [构建说明](../../build/README.md)；机器路径、环境检查、启动长会话与 stop/status 见 [环境/Windows 记录](../WINDOWS_EMULATOR_VALIDATION.md)。不要开启 Windows PATH 追加或跨系统环境共享。

CLI 场景在仓库根运行：

```bash
./prototypes/spatial-openxr/verify-emulator.py \
  --out private/validation/spatial-openxr-smoke --cycles 5
```

脚本只操作调试应用和 ADB 事件，不操作 Windows 鼠标；输出日志、私有文件与 Native 时的 Activity 列表。复现时使用新目录，避免覆盖本次证据/校验索引。它会 force-stop 本应用建立冷启动条件，不删除应用数据；Home 确认/cancel 不自动点击，最后用调试返回入口清理 session。

人工部分（Agent 必须用 Ask 等用户完成，之后再采集日志）：

1. 默认管理界面点“进入 VR”，确认方块/网格。W/S/A/D、Q/E 移动，右键拖动旋转，观察视差/透视；保持变更后的 pose，不重置。
2. 右控制器模式下左键按住至少 5 秒并松开；检查 BS4PicoXR 的 trigger 状态和 active/flags，不以 suggest bindings 成功代替输入通过。左控制器/控制器退出键按模拟器真实支持另测。
3. VR 中系统 Home 弹窗：先测取消后恢复焦点，再测确定退出。当前这次已通过确定退出；取消路径保留待测。回系统主界面后由 CLI 重开管理界面，检查数据并再次进入 VR。
4. 对照场景用 CLI 显式启动 VrActivity；窗口最小化时请用户恢复，不抢焦点。观察相同场景后用 Back 正常返回。
5. 调试完 `windows-tools.sh pico emulator stop --format json`，再读取 status。单纯退出/清理后台可使用包级 `adb shell am force-stop`，但不计入正常退出通过证据。

## 证据

校验值见 `evidence-checksums.json`。原始 PNG/log/大段 Activity dump 保留本地并忽略提交；文本记录、APK metadata 与索引可提交，APK/构建缓存不提交。

| 文件 | 内容 |
|---|---|
| `apk-metadata.json` / `install.txt` | 最终 APK 身份、两 ABI 库和 UNC 安装成功 |
| `lifecycle.log` / `cycle-*-native-activities.txt` | 最终五轮、重建、新 Intent pause/resume、Home 失焦与清理 |
| `manual-tracking-input.log` / `native-manual-tracking.png` | 用户实际按钮、head/aim 变化、trigger 0→1→0与新视角 |
| `home-manual-after.log` / `home-confirmed-system.png` | 用户确认 Home 退出、Surface/session 释放与系统主界面 |
| `home-relaunch-manager.log` / `home-relaunch-manager.png` | Home 后重开与私有数据可见 |
| `spatial-render-lifecycle.log` | SDK SpatialContainerStateListener onDestroy 与管理生命周期 |
| `activity-task-handoff.log` | 失败 fullscreen 启动的系统 result=100 证据 |
| `direct-native.log` / `direct-native.png` / `direct-native-exit.log` | 直接冷入口双眼、用户确认画面与成功释放 |
| `direct-comparison.json` / `private-data-final.txt` | 受限 CPU/线程/RSS 观察与最终持久数据 |
| `manager-start.png` / `native-pico-cli.png` / `tool-comparison.txt` | CLI 截图与跨宿主 ADB 的能力边界 |
| `emulator-stop.json` / `emulator-final-status.json` | stop 成功；没有运行进程和在线 ADB |

## 判断与下一步

此实验支持继续采用同 APK 的两 Activity 原型架构；管理实例/容器关闭、Native 独占其 XR worker/session，不能靠不同 Android 任务自然互斥。下一次必须在 ARM64 Space Pro 验证 Manifest 分类、左右真实控制器、Home 取消/重进、重定位/摘戴/待机/进程重建和长期切换，再剖析保留线程/内存与 GPU 帧时间。没有真机、没有游戏/兼容桥、没有真实 Steam 授权接入；这些均未因本原型而通过。

来源：官方 PICO Spatial 6.1 知识库的 `spatial-sdk_project-structure-and-dependency-configuration.md`、`spatial-sdk_spatial-container_customize-the-activity-of-spatial-containers.md`、`spatial-sdk_quickstart_create-your-first-spatial-app.md`；[PICO Native loader](https://developer.picoxr.com/document/native/openxr-loader/)、[Manifest metadata](https://developer.picoxr.com/document/native/metadata-setting/)、[Khronos Vulkan enable2](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_KHR_vulkan_enable2.html)、[OpenXR session 状态](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrSessionState.html)。本次 MCP 实际查询成功；本记录不把缺少官方共存保证的实验配置写成已文档化契约。
