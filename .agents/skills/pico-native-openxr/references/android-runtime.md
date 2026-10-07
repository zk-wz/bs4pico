# Android 宿主、Loader 与构建

## Loader 选择与初始化

Pico 的当前 [Loader 文档](https://developer.picoxr.com/document/native/openxr-loader/) 描述两条路径：Khronos 标准 Android Loader 负责标准接口；Pico Loader 配合厂商头文件开放未进入 Khronos 的私有扩展。基础双眼、控制器与 Vulkan 优先证明标准路径；私有功能按需接入，记录 SDK/loader/OS 组合。同一宿主避免同时装载两个具有相同 OpenXR 导出的 loader。

Android C/C++ 侧使用 `XR_USE_PLATFORM_ANDROID`，Vulkan 路径另设 `XR_USE_GRAPHICS_API_VULKAN`。这只是头文件配置，不能代替运行时的扩展枚举。

通过空 instance 的 `xrGetInstanceProcAddr` 获取 `xrInitializeLoaderKHR`，用 `XrLoaderInitInfoAndroidKHR` 提供有效的 JavaVM 与 Android Context，再调用需要 runtime 的入口。创建 instance 时启用 `XR_KHR_android_create_instance` 并在 `next` 链加入 VM/Activity 信息。区分 loader 初始化所需 Context 与 instance 所需 Activity；JNI 对象需要正确引用寿命和线程附着。规范见 [Android loader 初始化结构](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrLoaderInitInfoAndroidKHR.html)。

创建 instance 前枚举扩展；只启用已支持且实际实现的扩展。记录 instance API 版本、runtime 名称/版本、system 属性、图形要求。不能因为编译头文件里有扩展，就把它向游戏宣告为可用。

## Manifest 与打包

以选定版本的官方样例和最终 merged Manifest 为依据。Khronos Android loader AAR 通常合并 runtime broker 查询和相关权限；直接构建 `.so` 时要自行核对这些声明。参考 [hello_xr Manifest](https://github.com/KhronosGroup/OpenXR-SDK-Source/blob/main/src/tests/hello_xr/AndroidManifest.xml)。

重点检查：

- Activity 的 Android 导出/启动配置、`IMMERSIVE_HMD` 类别，以及采用 NativeActivity 时的 `android.app.lib_name`；自定义 Kotlin/Java Activity 不应生搬 NativeActivity 配置。
- runtime broker providers、OpenXR runtime/API layer 服务的 package visibility 与 OpenXR 权限。
- Pico 的 `pvr.app.type=vr`、`pvr.sdk.version=OpenXR`；最低 OS 的版本键名存在文档冲突，处理方式见 [来源说明](sources.md#已发现的文档矛盾)。不要把旧版 `5120` 当成新设备最低要求。
- APK 中 Android ELF `.so` 的 `arm64-v8a` ABI、NDK API、依赖库；Windows DLL 是兼容层载荷，不能放成 Android JNI 库来加载。
- 检查使用中的 Android 系统页大小及所有原生依赖的对齐兼容性。网络、震动、眼动等权限按实际功能添加；不复制旧样例已过时的外部存储权限。

Pico 系统 XR runtime 是设备服务。APK 打包应用 loader 和应用依赖，不打包桌面 SteamVR 或试图替换系统 XR runtime。

## 生命周期

Android Activity/Surface 生命周期与 OpenXR session 状态分别处理。`xrPollEvent` 驱动 XR 状态，不能仅靠 Android resume 就开始提交。

| XR 状态 | 应用行为 |
|---|---|
| READY | 调用 `xrBeginSession`，进入帧同步。 |
| SYNCHRONIZED | 保持帧同步，依据 `shouldRender` 避免不必要 GPU 工作。 |
| VISIBLE | 继续有效画面提交；没有输入焦点时暂停需互动的游戏进程。 |
| FOCUSED | 正常交互；仍检查 action 和 tracking 的有效性。 |
| STOPPING | 停止帧循环并调用 `xrEndSession`。 |
| LOSS_PENDING | 销毁失效资源，按 runtime 状态决定重建。 |
| EXITING | 结束 XR 体验，避免自动重新进入。 |

来源：[session 状态规范](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrSessionState.html)。暂停音乐/计分是本游戏的工程策略，不是 OpenXR 自动完成的功能。摘下、待机、系统菜单、跟踪丢失、Activity 重建都要验证；重建不得复用旧 session 的资源句柄。

## WSL 构建边界

工程建议：Gradle Wrapper + AGP 打 APK；NDK Clang/CMake 编 Android XR 宿主；LLVM-MinGW 编 Windows ARM64 DLL；Wine/DXVK 按各自的构建系统生成匹配组件。锁定这些版本及源码提交。上游 `build.sh` 目前只构建 PC 兼容模块，不是 APK 入口。

Android CLI 可辅助工具链与项目操作；Pico CLI 可安装 APK、启动应用、收集日志；它们不替代上述编译器。官方 quickstart 使用 Android Studio 展示操作，并不意味着 Gradle 工程必须依赖 IDE。来源：[Android CLI 构建](https://developer.android.com/build/building-cmdline)、[NDK CMake](https://developer.android.com/ndk/guides/cmake)。

沿用项目 WSL 缓存策略：源码与 `.gradle`/build、SDK/NDK、Gradle user home、CMake 中间文件及 shader 缓存留在 Linux 文件系统。Windows Pico CLI 只消费 APK/日志时无需调用 Windows Gradle；其自身状态、ADB 状态与临时文件另计，不能承诺零 Windows 写入。具体环境现状见 `docs/pico/build/README.md`，不要在调研任务中顺手安装或迁移环境。

首个可验证目标：安装一个最小 Native Vulkan XR APK，枚举 runtime/扩展并显示立体画面；随后验证手柄、生命周期，再接游戏。模拟器有助于打包/启动验证，不能证明 Space Pro GPU 和追踪性能。
