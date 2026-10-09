# Pico 构建入口

更新：2026-10-09。WSL 编译，Windows 模拟器部署；两份 checkout 不自动同步。

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
