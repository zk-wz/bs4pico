# WSL/Windows 环境与模拟器调用记录

记录日期：2026-10-09。构建由 WSL 完成；Windows 仅负责模拟器和设备操作。Windows checkout 不自动同步到此仓库。

## 已验证的工具路径与本地配置

以下为本机已验证值。保存到 WSL checkout 的 `private/windows-tools.json`（已忽略）；其他机器先核实路径再替换，不改全局环境：

```json
{
  "powershell_exe": "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
  "cwd": "D:\\SDK\\PICO",
  "env": {"PICO_HOME": "D:\\SDK\\PICO"},
  "aliases": {
    "pico": {
      "exe": "D:\\WorkTools\\Development\\NodeJs\\node.exe",
      "prefix_args": ["D:\\Cache\\npm\\npm\\node_modules\\@picoxr\\pico-cli\\dist\\index.js"]
    },
    "adb": {
      "exe": "D:\\SDK\\PICO\\6.1\\emulator\\system-images\\platform-tools\\adb.exe",
      "prefix_args": []
    }
  }
}
```

模拟器 EXE 为 `D:\SDK\PICO\6.1\emulator\emulator.exe`；现有 AVD `Pico_Emulator_6_1`、bundle 6.1.0、设备 `emulator-5554`。npm 入口另有 `D:\Cache\npm\npm\pico-cli.cmd`，不依赖它的 PATH 查找。

`/etc/wsl.conf` 实测为 `interop.enabled=true`、`appendWindowsPath=false`。不启用 Windows PATH 自动追加或 WSLENV 环境共享。[通用 skill](../../.agents/skills/wsl-windows-interop/SKILL.md) 说明配置、原生参数、退出码与文件交接边界。

## 本次验证原型的环境检查

只检查 Spatial/OpenXR APK，不要求 Wine/Proton、LLVM-MinGW、Steam 或游戏文件。

| 工具 | 本次实测 / 选择 |
|---|---|
| WSL Node / npm / Pico CLI | 24.21.0 / 12.2.0 / 0.6.0 public |
| PICO 知识库 | global Spatial 6.1，Graphify Vault 0.5.9；本次 MCP 查询成功 |
| 插件 | 会话已挂载 General 0.1.0 / Spatial 0.6.0；doctor 未登记 Agent Host，不代表未加载 |
| JDK | 用户已安装系统 `jdk21-openjdk` 21.0.12.1 并卸载 JDK 25；Wrapper 实测使用 `/usr/lib/jvm/java-21-openjdk`。已删除本次隔离 `deps/jdk21` 与下载包 |
| Gradle / AGP / Kotlin | 官方模板 Wrapper 8.13 / 8.13.2 / 2.1.20 |
| Spatial BOM | 官方 6.1 模板实际选中 6.1.9，与知识库 6.1 对齐；CLI `--sdk 6.1.0` 是模板线，不是 BOM 版本 |
| Android 平台 | 全局 `/home/zkwz/Android/Sdk/platforms/android-35`；用户授权后移除原有平台 36.1，没有项目级 SDK |
| build-tools / NDK | 复用原有 36.1.0 / 30.0.16248370 |
| CMake / Ninja | 复用 WSL `/usr` 的 4.4.4 / 1.13.2，不重复下载 SDK CMake |
| OpenXR loader | Khronos Android AAR 1.1.49，prefab，x86_64 和 arm64-v8a |
| Windows 模拟器 | 已安装 6.1.0；原有 AVD `Pico_Emulator_6_1`，ADB `emulator-5554`，boot completed=1 |

API 35 是此 Spatial 6.1 模板/文档的最低配置线，本工程固定 `compileSdk/minSdk/targetSdk=35`，并不声称官方只允许 35。JDK 21 是本工程选择的兼容 LTS，不是 PICO 唯一强制版本；AGP 8.13 要求 JDK 17+，Wrapper 8.13 不支持用 JDK 25 运行。平台 36.1 和 JDK 25 对本原型不需要，因此按用户授权移除；build-tools 与 Android 平台版本是不同组件，36.1.0 build-tools 不应一并删除。

`pico-cli doctor --format json --platform spatial` 在本进程报告 PICO_HOME/Android SDK 未配置，即使显式 export 路径也如此；实际 Primer 项目生成已正确识别 `/home/zkwz/pico/toolbox` 与 `/home/zkwz/Android/Sdk`，知识库和 Android CLI 均可用。记录为诊断器结果不一致，不运行 `doctor --fix` 或全套 setup。Overview 原样：CLI `0.6.0 (public)`，Plugin `null`，SDK `no-project`（生成前），Knowledge `6.1`，Emulator `null`，Editor `null`。这里 Emulator/Editor 是 WSL 安装状态，不是 Windows 状态。perf 依赖警告不阻塞本次切换正确性检查，不补齐完整性能工具链。

WSL 知识库使用用户配置的 global scope：配置文件 `/home/zkwz/.pico/.pico-env.json`，PICO_HOME `/home/zkwz/pico/toolbox`，Spatial workspace `6.1/agent-vault/spatial`。本次未重装插件或切换知识库；用户报告过的查询超时已解决，修复细节未记录。

## 环境整理与变更边界

用户已通过 pacman 安装 `jdk21-openjdk`、删除 `jdk25-openjdk`，并执行 `archlinux-java set java-21-openjdk`。本会话随后验证 Wrapper 使用系统 JDK 21，并按授权删除隔离 JDK 和 `/tmp` 下载/着色器中间文件。Android CLI 已移除全局 `platforms/android-36.1`，保留平台 35、build-tools 36.1.0、NDK 30.0.16248370、platform-tools 37.0.1。源码内不包含 SDK/JDK，也不在 Windows 安装构建环境。

构建入口默认从系统 `javac` 解析 JDK，`ANDROID_HOME` 默认指向全局 `$HOME/Android/Sdk`；可显式覆盖，不依赖项目私有工具链。PICO 模板、Gradle/依赖及 Android CLI 的正常缓存保留，不能把共用缓存当作临时残留全盘删除。后续必要依赖缺失或环境增删必须先用 Ask 给出最小操作并阻断，不自行安装、切换默认版本或更新整套工具。

## 可复现调用

```bash
./prototypes/spatial-openxr/windows-tools.sh pico emulator start \
  --avd Pico_Emulator_6_1 \
  --emulator-path 'D:\SDK\PICO\6.1\emulator\emulator.exe' \
  --source cn --format json
```

同样的 Node/CLI 调用可执行 `emulator list/status/stop --format json`。启动先确认 AVD 存在；保留启动会话，从另一个调用读取状态、安装 APK 和收集日志。启动成功 JSON 后 CLI 可能继续留在前台，不能用短超时误杀。此 WSL 会话启动结果为 `SUCCESS`、`bootCompleted=true`；独立 ADB 返回 `sys.boot_completed=1`。`ro.product.cpu.abilist` 为 `arm64-v8a,x86_64`，系统镜像为 x86_64；不能把 ARM 翻译支持当作真机。

```bash
./prototypes/spatial-openxr/windows-tools.sh adb -s emulator-5554 shell getprop sys.boot_completed
```

用户提供的前次会话已验证 start/status/stop；本次 WSL 会话又实测 list/status/start、ADB 查询和 APK 部署。包列表包含 `com.pico.xr.openxr_runtime`、`com.pico.spatial.runtime`；Vulkan 查询显示 NVIDIA GeForce RTX 4070 Laptop GPU、API 1.3。原型已实际创建 Pico XRRuntime/Pico-emulator HMD session 并提交 Vulkan 双眼层，见 [运行证据](2026-10-09-spatial-openxr/README.md)；这仍不证明 ARM64 真机能力。

## APK 文件交接边界

APK 和 Gradle/NDK/CMake 缓存保留 WSL。用 `wslpath -w <APK绝对路径>` 得到 UNC 路径，实际为 `\\wsl.localhost\archlinux\home\zkwz\projects\bs4pico\prototypes\spatial-openxr\app\build\outputs\apk\debug\app-debug.apk`；Windows Node/Pico CLI `app install ... --device emulator-5554 --replace` 已返回 `Performing Streamed Install / Success`，无需复制到 Windows。UNC 只是路径交接，不会同步 Windows checkout。
如果其他消费程序不支持 UNC，仅复制最终产物到独立 Windows 临时目录，不复制源码、缓存或整套 SDK。

## 实际调试入口与工具选择

首次原型使用内联 PowerShell 与 NUL 分隔 Base64 参数。现在 `prototypes/spatial-openxr/windows-tools.sh pico|adb <args>` 只做薄适配，统一调用 interop skill 的 `windows_interop.py`；机器路径由忽略的 `private/windows-tools.json` 提供。通用实现使用 JSON/Base64 数据、Windows CRT 参数引用和 `ProcessStartInfo`，避免 PowerShell 5.1 丢失内嵌引号；保留原生退出码和输入输出，不共享 PATH 或修改执行策略。

本次尝试 `.ps1 -File` 时，Windows 拒绝未签名 UNC 脚本。最终改为固定 inline 调用，没有修改或绕过全局执行策略，也没有开启 PATH/WSLENV 共享。

```bash
./prototypes/spatial-openxr/windows-tools.sh pico emulator status --format json
./prototypes/spatial-openxr/windows-tools.sh pico app logcat \
  --device emulator-5554 --package io.github.zkwz.bs4pico.probe --tag BS4PicoProbe --lines 100
./prototypes/spatial-openxr/windows-tools.sh pico capture screenshot \
  --device emulator-5554 --out "$(python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py path private/validation/current.png)"
./prototypes/spatial-openxr/windows-tools.sh pico emulator stop --format json
./prototypes/spatial-openxr/windows-tools.sh pico emulator status --format json
```

Pico CLI 安装、启动、状态和单 tag 日志可用；单 tag 输出会提示有界筛选可能丢旧行。本次多 tag `--filter` 未得到预期窄输出，完整生命周期记录采用包内 ADB `logcat -d --pid=<PID> -s BS4PicoProbe:I BS4PicoXR:I AndroidRuntime:E`，不扩大环境改动。

Pico CLI screenshot 生成了有效 PNG，但 Spatial 管理窗口图只含背景/启动器，Native 场景图大部黑色；实际 Windows 模拟器窗口能看到管理窗口/立体方块。保留两者作为截图能力边界证据；`capture-emulator.py` 仅对此合成层遗漏提供精确窗口 `PrintWindow` 后备，不捕获整个桌面。

WSL `android-cli screen capture --device=emulator-5554` 实测报设备不存在。Linux ADB 与 Windows ADB 是独立服务；Windows ADB 在 `127.0.0.1:5037` 监听，WSL NAT 网关 `172.27.0.1:5037` 只读连接超时。选择 Windows Pico CLI/包内 ADB；没有重绑 ADB、改防火墙、增加端口转发或安装 Windows SDK。新增 `android-cli`/`testing-setup` skills 可作 Linux 开发参考，但不能据此假定跨宿主设备连接可用。

## 本次调试结束状态

本次通过 Windows Pico CLI `emulator stop --format json` 得到 SUCCESS、`stopped=true`、`targetMatched=true`、`runningTargets=[]`。随后 status 得到 PARTIAL、退出码 4、`processRunning=false`、`adbOnline=false`、`candidates=[]`、`errors=[]`。此退出码表示没有运行目标，不能按部署错误处理或因此重新启动模拟器。原始结果保留在实验目录 `emulator-stop.json` 和 `emulator-final-status.json`，参见 [完整实验记录](2026-10-09-spatial-openxr/RESULT.md)。

## 通用脚本整合后的脱机验证

本轮没有重启模拟器、操作鼠标或改变系统环境；只验证脚本与真实 Windows 工具的连接和数据边界：

- 原型薄入口调用 Windows Pico CLI `--version` 输出 `0.6.0 (public) win32-x64 node-v24.12.0`；status 仍为离线、退出码 4，包内 ADB devices 无设备。
- Windows Node 实际收到空参数、空格、Unicode/emoji、内嵌引号、末尾反斜杠和 `--`；退出码 37 正确传回，cwd/PICO_HOME 与配置一致。
- 原生输入/输出逐字节往返 1 MiB，stderr 同时输出 128 KiB；ready → 输入 → done 的长进程交互通过，不等到进程退出才显示 ready。
- Windows Node 直接读取 WSL UNC 上的原 APK，SHA256 与原实验一致；也能读取含中文和空格的临时文件名。临时测试文件/配置已清理，本地工具配置保留并忽略。
- 无目标窗口时 capture 返回 1、提示 found 0、不生成截图，不因此启动应用或抢焦点。PrintWindow 核心沿用之前实测的实现，本轮未重新验证运行中模拟器截图。

曾复现 `ProcessStartInfo` 未重定向标准流时退出 0 却没有返回输出；已改为固定 C# 原始字节并发转发，以上实际内容检查通过。文档迁移后 107 个本地链接可达，原实验 21 份索引证据的大小和 SHA256 不变。
