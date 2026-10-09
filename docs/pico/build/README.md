# 构建环境与缓存方案

最后更新：2026-10-09。用户提供的 Agent 诊断已确认 WSL 项目目录和知识库可用；完整构建工具链及跨端 APK 部署仍需检查，尚未执行本项目构建。用户已安装并启动 Windows PICO 模拟器，实测结果见 [Windows 模拟器验证](WINDOWS_EMULATOR_VALIDATION.md)。现有 `build.sh` 只构建上游 Windows ARM64 组件和发布包。

## 分工

- WSL：oh my pi、Android CLI、Android SDK/NDK 和 Linux Pico CLI/知识库；Gradle Wrapper、JDK、CMake/Ninja 等按原型需求检查。LLVM-MinGW、Make/Meson 等属于后续游戏兼容组件构建，不作为 Activity 原型的全量前置条件。
- Windows：现有 Pico CLI/模拟器包内 ADB 用于模拟器及真机操作。将来通过我们的调度脚本调用 `wsl.exe` 构建，再安装 WSL 输出的 APK；不默认让 Windows 工作流直接运行 `gradlew.bat`。
- WSL 向 Windows 的显式调用已验证：即使不继承 Windows PATH，仍可经绝对路径的 Windows PowerShell 调用 Windows Node、Pico CLI 和 ADB，启动、确认就绪及停止模拟器。命令与边界见 [WSL 调用验证](WINDOWS_EMULATOR_VALIDATION.md#wsl-调用-windows-pico-cli-验证)。不要在 WSL 直接运行依赖 Windows PATH 的 npm shim；APK 路径转换及安装仍需后续验证。
- 若连 Pico CLI 的状态/下载缓存也要保留在 WSL，优先改用 Linux 版 Pico CLI；需要 Windows 工具的操作单独处理。不能承诺任意 Windows 程序零写入。

## 已知安装（只表示曾定位到，不代表完整环境检查通过）

| 项目 | 位置或版本 |
|---|---|
| WSL | `archlinux`，x86_64 |
| Android CLI | `/home/zkwz/.local/bin/android`，1.0.16486076 |
| Android SDK | `/home/zkwz/Android/Sdk`，已发现 NDK 和 platform/build-tools 组件 |
| Windows Pico CLI | 0.6.0，npm 安装在 `D:/Cache/npm/npm/` 下 |
| WSL Pico CLI / Graphify | 用户提供的诊断确认 0.6.0 / Graphify Vault 0.5.9，已加载 Spatial 图谱且有实际查询成功证据 |
| WSL 项目与知识库 | `/home/zkwz/projects/bs4pico`；PICO_HOME `/home/zkwz/pico/toolbox`；全局配置 `~/.pico/.pico-env.json` |
| Windows PICO 模拟器 | 大陆正式版 6.1.0，位于 `D:/SDK/PICO/6.1/emulator/`；首次启动及 ADB 在线已验证 |

Android CLI 曾在版本查询时自动解包内置安装文件。后续检查工具启动副作用，不将帮助/版本命令一概视为零文件写入。未运行其更新、初始化或 SDK 安装命令。

## 游戏文件与 .NET

- 迁移源码、编译现有兼容组件和开发 Android 外壳，不以完整游戏安装为前置条件。分析真实游戏程序集、生成改装实例和实际运行时，需要用户通过 Steam 或已授权的管理工具取得的完整 Windows 安装目录；普通 Windows x64 原版即可作为输入，后续按引擎版本匹配并替换 ARM64 Player、Mono 和原生插件。
- 保留一份未修改、无模组的游戏副本，不直接改唯一的 Steam 安装。可将完整目录保存在仓库内已忽略的 `private/games/BeatSaber/<version>/`，或仓库外的 `/home/zkwz/projects/bs4pico-artifacts/games/BeatSaber/<version>/`；这些位置只是建议，尚未创建或迁移。不要将游戏文件、Steam 凭据或授权票据提交 Git；发布打包也必须明确排除私有输入，不能只依赖 Git 忽略规则。
- 当前 `versions.env` 的引擎锁定为 Unity `6000.0.40f1`，上游列出的游戏版本为 `1.40.9` 至 `1.44.1` 中的指定版本。以实际引擎检查为准，不默认任意最新游戏版本都兼容。这是上游输入要求，不代表 Pico 已支持这些版本。
- WSL 暂不需要安装 .NET SDK 或主机 Mono。当前构建使用 C/C++ 工具链与 Python；`build.sh monomod` 从固定的 NuGet 包提取已编译 DLL，不执行 `dotnet build`。游戏内嵌的 Unity ARM64 Mono 是运行时移植输入，不等于 WSL 主机 .NET 安装。
- 将来编写并编译自有 C# 工具或模组时，再根据其项目目标安装 .NET SDK；Android APK 的 JDK/Gradle/NDK 需求另行管理。

## 建议的 WSL 路径

| 内容 | 建议位置 |
|---|---|
| 源码与项目内 `.gradle/`、`.cxx/`、`build/` 等 | `/home/zkwz/projects/bs4pico/` |
| 已有 SDK/NDK | `/home/zkwz/Android/Sdk/` |
| Gradle 用户目录 | `/home/zkwz/.cache/bs4pico/gradle/`，由 `GRADLE_USER_HOME` 指定 |
| 编译缓存（启用时） | `/home/zkwz/.cache/bs4pico/ccache/` |
| 构建临时文件 | `/home/zkwz/.cache/bs4pico/tmp/`，构建进程单独指定 |
| 真机大型实验产物 | `/home/zkwz/projects/bs4pico-artifacts/device-validation/` |

实际配置时再确定 Android 用户状态目录（`ANDROID_USER_HOME`）、可选模拟器目录和各工具日志路径。项目位于 WSL 时，项目内构建缓存也位于 WSL；只设置 `GRADLE_USER_HOME` 不会迁移项目自身的缓存。

Windows 可经 `\\wsl.localhost\archlinux\home\zkwz\projects\bs4pico\` 访问产物。工具是否支持 UNC 输入/输出仍需验证；必要时仅复制最终 APK，不复制编译缓存。

## 构建层与复现

1. Windows ARM64 DLL：复用上游固定版本和分步骤构建。
2. 安卓运行环境与 OpenXR 桥：使用 NDK，独立构建及缓存。
3. Android 工程：Gradle 整合原生组件和资源，签名生成 APK。
4. 真机验证：Windows Pico CLI 或 Linux Pico CLI 调用设备工具，结果写入真机记录。

组件按自身的上游构建系统编译，不强行全部改成 CMake。建立统一入口后补充确切命令、版本清单、输出路径和增量重建规则；当前没有可执行的 APK 构建命令。

## 跨端运行的边界

从 Windows 通过 `wsl.exe` 调用 Linux 构建，使用 Linux 工具链和 WSL 路径，可将 Android 构建缓存留在 WSL。

从 WSL 启动 Windows 程序，进程仍是 Windows 进程。缓存依程序的用户目录、配置和临时目录规则决定，不随启动终端自动迁移。`WSLENV` 能传递/转换环境变量，但只对实际支持该变量的工具有效。

`PICO_HOME` 指定部分 Pico 工具和知识数据位置，不是所有 Pico 缓存的总开关。官方还列出 `~/.pico/` 与 `~/.pico-cli/` 等状态目录。本机 CLI 代码也有按用户目录定位的文件，后续需要逐项核对。

## 参考

- [Android 命令行构建](https://developer.android.com/build/building-cmdline)
- [Gradle 目录与缓存](https://docs.gradle.org/current/userguide/directory_layout.html)
- [Android 工具环境变量](https://developer.android.com/tools/variables)
- [WSL 跨系统运行和环境变量](https://learn.microsoft.com/en-us/windows/wsl/filesystems)
- [Pico CLI 环境及缓存位置](https://developer.picoxr.com/document/pico-cli/config/)

本机 Pico CLI 0.6.0 的 `spatial-codegen-workflow` 文档明确包含 Gradle/JDK 21 的构建阶段，并调用现有 `gradlew` 或 `gradlew.bat`。它是特定 Spatial 代码工作流，不是本项目 Native OpenXR 构建已获支持的证明。
