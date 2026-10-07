# 构建环境与缓存方案

最后更新：2026-10-07。本页为规划，尚未安装依赖、设置环境变量、迁移项目或执行构建。现有 `build.sh` 只构建上游 Windows ARM64 组件和发布包。

## 分工

- WSL：Android CLI、Gradle Wrapper、JDK、Android SDK/NDK、LLVM-MinGW，以及各组件需要的 CMake/Ninja、Make/Meson 等工具。
- Windows：现有 Pico CLI/ADB 用于真机操作。将来通过我们的调度脚本调用 `wsl.exe` 构建，再安装 WSL 输出的 APK；不默认让 Windows 工作流直接运行 `gradlew.bat`。
- 若连 Pico CLI 的状态/下载缓存也要保留在 WSL，优先改用 Linux 版 Pico CLI；需要 Windows 工具的操作单独处理。不能承诺任意 Windows 程序零写入。

## 已知安装（只表示曾定位到，不代表完整环境检查通过）

| 项目 | 位置或版本 |
|---|---|
| WSL | `archlinux`，x86_64 |
| Android CLI | `/home/zkwz/.local/bin/android`，1.0.16486076 |
| Android SDK | `/home/zkwz/Android/Sdk`，已发现 NDK 和 platform/build-tools 组件 |
| Windows Pico CLI | 0.6.0，npm 安装在 `D:/Cache/npm/npm/` 下 |

Android CLI 曾在版本查询时自动解包内置安装文件。后续检查工具启动副作用，不将帮助/版本命令一概视为零文件写入。未运行其更新、初始化或 SDK 安装命令。

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
