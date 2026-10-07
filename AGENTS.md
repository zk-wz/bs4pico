# BS for Pico 项目说明

最后更新：2026-10-07。

**这是持续维护的项目入口。随着源码、目录、构建方式和验证结果发生变化，必须随时更新本文及对应文档；完成相关变更时一并更新，不要等到阶段结束。**

## 目标与现状

- 本仓库是 `zk-wz/bs4pico`，Fork 自 `DaVarga/bs-arm64`，目标是在 **Pico Space Pro、无 root** 的条件下运行 PC 版 Beat Saber，并交付一个 APK。
- 上游通过替换同版本的 Windows ARM64 Unity Player、Mono 和原生插件，保留游戏的托管程序集及数据。结果仍是 Windows ARM64 应用，需要 Windows 兼容层。
- 当前源码和安装器仍面向 ARM64 Linux 上的 Proton、Steam 客户端及 SteamVR/OpenXR。上游 Steam Frame 的验证和性能数据不能当成 Pico 的验证结果。
- 目前没有 Android Gradle 工程、安卓运行时移植、Pico OpenXR 桥或可安装的 Pico APK；尚未执行本 Fork 的构建和真机验证。
- 用户另一个会话已验证 GameNative 运行 PC 版的路径；那不证明本仓库的纯 ARM64 路径已经在 Pico 跑通。
- 原 `.github/` 已移除，当前没有 GitHub Actions。后续自己的 CI 应复用本地构建入口。
- 迁移方向：安卓适配的 Wine/Proton 组件 + DXVK + Native OpenXR；Spatial 显示作为后续实验候选。真实 Steam 登录、游戏及 DLC 授权仍需接入和验证。

## 开发与验证约定

- 构建计划在 WSL 完成。Android CLI 辅助开发；Gradle、NDK 和 LLVM-MinGW 分别承担 APK、安卓原生组件和 Windows ARM64 DLL 的构建。
- 源码、SDK/NDK、Gradle 缓存和编译中间产物优先留在 WSL 的 Linux 文件系统。Windows Pico CLI 可负责设备操作；它自己的状态和缓存需要另行管理。
- WSL 项目建议路径为 `/home/zkwz/projects/bs4pico`，目前仍在 Windows，**尚未迁移**。用户表示将后续自行操作；本文的路径规划不是已执行的配置。
- 不引入依赖设备 root 或 PRoot 的主运行方案。游戏、运行时和原生模块的架构需分别确认，不能把 Windows ARM64、ARM64EC、Android ARM64 库混为一谈。
- Steam 兼容桥负责转接真实服务，不提供独立授权。保留真实账号及所有权校验；打包范围参考 `docs/LEGAL.md`。
- 先验证原版游戏，再扩展模组。性能以真机帧时间、输入延迟、音画同步和持续运行表现为依据，不只看平均 FPS。
- 每次真机实验保留版本、设置、操作、结果和证据，失败也记录。明确区分“已验证”“推断”“待验证”。

## 目录地图

| 路径 | 用途 |
|---|---|
| `src/` | 本仓库维护的兼容代码、生成器和二进制检查工具，详见下表。 |
| `patches/` | 应用于锁定上游源码的补丁，不是完整的 Wine/Proton/DXVK 源码。 |
| `install/` | 上游 Steam Frame/Linux 游戏实例安装、恢复和启动脚本。 |
| `tools/` | Unity 包提取及上游安装器、Steam 和 DLL 加载验证工具。 |
| `docs/` | 原有上游架构、构建、安装、发现、上游问题和打包许可资料。 |
| `docs/pico/` | 本 Fork 的 Pico 迁移文档入口，不覆盖上游参考资料。 |
| `docs/pico/device-validation/` | 真机实验记录、证据索引和记录模板。 |
| `docs/pico/plans/` | 阶段目标、进度及完成条件。 |
| `docs/pico/decisions/` | 关键技术选择及选择依据。 |
| `docs/pico/research/` | 调研结论、来源和待验证问题。 |
| `docs/pico/build/` | 环境清单、构建流程、缓存位置和复现说明。 |
| `.agents/skills/` | 本项目维护的 Agent skills；技能知识与代码、验证状态一起更新。 |
| `.agents/skills/pico-native-openxr/` | Pico Native OpenXR 接入 skill，涵盖官方来源、Android loader、Vulkan、输入/坐标、扩展性能及本仓库桥接边界。 |
| `deps/` | 构建时下载的上游源码和工具链；忽略的生成目录。 |
| `obj/` | 编译中间产物；忽略的生成目录。 |
| `out/` | 上游构建输出 DLL 和辅助脚本；忽略的生成目录。 |
| `dist/` | 上游发布包、清单和校验文件；忽略的生成目录。 |

生成目录可能尚不存在。新增 Android 工程等代码目录时，应及时补充本文，不预先把计划目录写成已有实现。

## 入口与代码文件

| 文件 | 大致职责 |
|---|---|
| `build.sh` | 分步骤获取依赖、交叉编译 ARM64 DLL、检查并生成上游发布包；目前不构建 APK，也不提供完整安卓运行环境。 |
| `versions.env` | 锁定工具链、Proton/Wine/DXVK、Unity、Steam SDK 相关输入及支持版本。 |
| `install/bs-arm64.sh` | 从官方来源获取 Unity 组件，备份并替换游戏文件、配置 Wine prefix、恢复安装和通过 Proton 启动。 |
| `src/steam-api/steam_api_core.cpp` | Steam 初始化、客户端加载、接口版本适配、回调与关闭逻辑。 |
| `src/steam-api/steam_api_helpers.cpp` | Steam 接口访问器及网络等辅助 API 实现。 |
| `src/steam-api/steam_api_shim.h` | Steam 桥的公共声明、接口辅助定义和调用日志开关。 |
| `src/steam-api/gen.py` | 从 SDK 和 Proton 接口定义生成 Steam flat API 转接代码及导出信息。 |
| `src/steam-api/gen_sdk_inline.py` | 提取并适配 SDK 内联网络类型实现，供辅助 API 编译。 |
| `src/unityopenxr/patch_unityopenxr.py` | 调整 Unity ARM64 UWP OpenXR 插件的 PE 导入，使其用于 Windows 桌面兼容环境。 |
| `src/wine-runtime/verify.py` | 检查游戏私有 C++ 运行时 DLL 的架构、导入及异常处理转发。 |
| `src/monoposixhelper/config.h` | Mono zlib helper 所需的最小配置头。 |
| `src/monoposixhelper/glib.h` | Mono zlib helper 所需的最小 GLib 类型与宏。 |
| `src/liv-bridge/liv_bridge.c` | 提供 LIV 桥占位导出，报告捕获未启用；没有实现 LIV 捕获。 |
| `src/doorstop/doorstop_arm64.c` | 用 ARM64 兼容定义编译上游 Doorstop，作为 BSIPA 模组注入入口。 |
| `src/doorstop/compat.c` | 提供最小内存操作实现。 |
| `src/doorstop/gen_proxy_arm64.py` | 生成 ARM64 winhttp 代理跳转桩。 |
| `src/doorstop/shim/Windows.h` | 将上游大写头文件引用转接到 MinGW 的 Windows 头。 |
| `src/doorstop/shim/Shlwapi.h` | 将上游大写头文件引用转接到 MinGW 的 Shlwapi 头。 |
| `tools/unity_pkg_extract.py` | 从 Unity 安装包流式提取需要的 Player 文件。 |
| `tools/test_installer_runtime.py` | 在临时目录验证安装、旧版升级及卸载，不需要真实 Wine 或下载。 |
| `tools/loadtest.c` | 最小 Windows DLL 加载诊断程序；含上游 SteamOS 固定日志路径，尚未适配 Pico。 |
| `tools/smoketest.cpp` | 最小 Steam 客户端连接和登录状态诊断程序；含上游固定日志路径，尚未适配 Pico。 |

`lsteamclient`、`wineopenxr`、DXVK 和 Mono zlib helper 的主体来自 `deps/` 中的锁定上游源码，不在上述 `src/` 内重复维护。

## 补丁与参考文档

- `patches/wine/`：ARM64 C++ 异常处理修复及游戏私有运行时命名和链接适配。
- `patches/dxvk/`：构建头文件修复，以及 MSAA resolve 后附件存储优化和后续加载兼容处理；移植后需检查画面正确性。
- `patches/openxr-loader/`：Windows ARM64 OpenXR runtime 发现逻辑；不是安卓 loader 接入实现。
- `README.md`、`CHANGELOG.md`：保留上游介绍和变更历史；新增 Pico 状态以 `docs/pico/` 为准。
- `docs/ARCHITECTURE.md`：组件关系；`BUILD.md`：上游 DLL 构建；`INSTALL.md`：上游安装；`FINDINGS.md`：已知问题和实验；`UPSTREAM.md`：上游问题；`LEGAL.md`：许可及打包范围。
- `LICENSE`：项目许可；`.gitignore`：当前生成产物忽略规则，新构建系统产生新缓存目录时需补充。

下一步见 [Pico 文档入口](docs/pico/README.md) 和 [阶段规划](docs/pico/plans/ROADMAP.md)。

涉及 Native OpenXR 调研、接入或诊断时，使用 [pico-native-openxr skill](.agents/skills/pico-native-openxr/SKILL.md)，按任务读取其 references。官方旧设备支持表不等于 Space Pro 真机结论；当前已查 LLM 文本入口及文档冲突见 skill 的来源说明。
