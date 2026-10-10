# Pico 构建入口

WSL 编译，Windows 模拟器部署；两份 checkout 不自动同步。本文保留操作入口，维护约定见 [AGENTS.md](AGENTS.md)。

## 原型入口

源码：`prototypes/spatial-openxr/`。运行 `./prototypes/spatial-openxr/build-apk.sh`；默认两种 ABI，同一 APK。可用 `-PprobeAbis=x86_64` 或 `-PprobeAbis=arm64-v8a` 单独编译。`JAVA_HOME`、`ANDROID_HOME` 可覆盖；源码、`build/`、`.cxx/`、`.gradle/`、Gradle user home、SDK/NDK 均留在 WSL。`local.properties` 是本地忽略文件，设置 `sdk.dir`、`spatial.tools.dir`、`cmake.dir=/usr`。

已在 Windows 模拟器安装并运行双 ABI APK。完整复现命令、Manifest 边界、生命周期场景和证据见 [原型运行记录](../device-validation/2026-10-09-spatial-openxr/README.md)。机器路径、环境检查、Windows 调用、长进程边界和 UNC 文件交接见 [环境/模拟器记录](../device-validation/WINDOWS_EMULATOR_VALIDATION.md)。

上游 Windows ARM64 DLL 构建仍使用仓库根 `build.sh`，见 [上游构建说明](../upstream/BUILD.md)；不要用它构建 APK。

设备调用先配置忽略的 `private/windows-tools.json`，字段和本机已验证值见上述环境记录；不要把宿主 EXE 路径重新写进脚本。任意 Windows 工具可复用 [interop skill](../../.agents/skills/wsl-windows-interop/SKILL.md) 的 `run/path/capture` 入口。首次依赖下载的范围见环境记录，必要的工具安装仍须 Ask。

从仓库根目录构建、交接、启动：

```bash
./prototypes/spatial-openxr/build-apk.sh
APK="$(python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py path prototypes/spatial-openxr/app/build/outputs/apk/debug/app-debug.apk)"
./prototypes/spatial-openxr/windows-tools.sh pico app install "$APK" --device emulator-5554 --replace
./prototypes/spatial-openxr/windows-tools.sh pico app launch io.github.zkwz.bs4pico.probe \
  --activity .platform.LaunchActivity --device emulator-5554
./prototypes/spatial-openxr/verify-emulator.py \
  --out private/validation/spatial-openxr-smoke --cycles 5
```

前提是按 Windows 记录启动现有模拟器；验证脚本会停止/重启本调试应用，不删除其私有数据。复现使用新的 `--out` 目录，避免覆盖已记录实验及其校验值。直接 Native 对照入口为 `.platform.VrActivity`，可用 `windows-tools.sh adb -s emulator-5554 shell am start -n io.github.zkwz.bs4pico.probe/.platform.VrActivity --ez direct true`。不需要额外安装测试框架或 Linux ADB 网络转发。

输出 APK 是本地 debug 签名验证包；不包含游戏、账号或第三方运行时。Wrapper/dependency 首次构建会下载自身锁定输入到 WSL 正常缓存，不代表新增系统工具。


来源：[Gradle 8.13 Java 兼容表](https://docs.gradle.org/8.13/userguide/compatibility.html)、PICO 6.1 模板与知识库 `spatial-sdk_port-android-apps.md`（BOM、Android API、入口注册要求）。

## 正版游戏输入与备份

用户已提供 Beat Saber **1.44.1**，位于当前 WSL checkout 的 `private/BeatSaber/1.44.1/`，这是用户唯一的游戏原始副本。该版本属于原 bs-arm64 的兼容范围；这不代表已经在 Pico 上运行。本次仅记录用户提供的信息，没有启动、替换或复制游戏，也没有执行游戏备份。

后续操作遵循以下保护顺序：

1. 默认只读使用原始目录。先评估外置组件/加载配置；只有实际加载机制支持且验证原始目录不变时，才采用不替换文件的方案，不预先承诺可行。
2. 必须改文件或运行可能写入游戏的程序时，优先使用独立工作副本。不能用硬链接复制来隔离原件；写时复制须确认文件系统支持并验证写入隔离。
3. 替换、补丁、重命名、删除，以及可能写入的安装/升级/卸载或游戏启动前，先明确写入范围，建立独立、可恢复的备份。保留原始目录和已有备份；范围不明时不执行。
4. 备份清单记录源/目标、相对文件名、大小、SHA256、恢复所需属性及恢复步骤；修改前确认备份校验匹配、文件可读取，恢复目标明确。工作副本不等于已校验的备份。
5. 空间不足、备份失败或恢复条件不完整时停下用 Ask，不以“之后重新下载”作为兜底。操作后验证原始基线未变，并记录工作副本变更和回滚结果。

游戏、工作副本、备份及其私有清单放在忽略的本地存储，不加入 APK 或 Git。现有 `/private/` 忽略规则覆盖用户输入；本节记录输入位置和保护流程，根 `AGENTS.md` 保留跨目录保护边界。
