# Windows PICO 模拟器验证

日期：2026-10-09（Asia/Shanghai）。操作由用户执行，本会话只核查日志、文件与 CLI 状态记录。后续环境或验证结果变化时更新本文。

## 结果与边界

- Pico CLI 0.6.0，大陆正式版模拟器 6.1.0（SpaceOS、API 36、x86_64）。
- 使用 `--artifact-url` 与官方 SHA-1 校验值直接安装；安装、启动命令均指定 `--source cn`。此版本的 CLI 在明确指定 artifact URL 时绕过 Primer 安装引擎。
- 当前 PowerShell 使用 `PICO_HOME=D:\SDK\PICO`。没有执行 `doctor --fix`、整套 `setup` 或项目构建。
- 主日志记录 14:59:23 启动完成，耗时 49,931 ms；CLI 历史状态记录 `bootCompleted=true`、`startupStatus=ready`、`adbStatus=online`，设备为 `emulator-5554`。
- 用户随后关闭模拟器；检查时当前状态列表为空，历史成功状态不表示现在仍在运行。
- Windows Hypervisor Platform 加速生效，图形使用 RTX 4070 Laptop GPU、ANGLE/Vulkan。
- 未发现本次流程下载 Primer Java 或完整 Android 构建 SDK。检查时 `~/.pico/primer-cli`、`~/AppData/Local/Android/Sdk`、`~/.gradle` 均不存在；这不是全盘工具安装审计。
- 仅证明模拟器主机环境可用，不证明本项目 APK、OpenXR 桥或 ARM64 游戏运行成功。x86_64 模拟器不能用作 ARM64 真机性能结论。

## 日志检查

证据：`D:\SDK\PICO\emulator-first-start.log`（341 行），以及 Windows 临时目录的 qemu/eventTracker 辅助日志。

- 主日志没有标为 ERROR/FATAL 的记录，有 18 条 WARNING。
- 14 条警告为 `vkCreateDebugUtilsMessengerEXT` 查询失败；该接口负责 Vulkan 调试回调，后续 Vulkan 实例与设备创建成功，未阻断本次渲染。
- ADB platformPath 未指定根路径；实际调用了包内 `system-images/platform-tools/adb.exe`，最终在线。
- 启动早期调用 MeterService 时 ADB 暂时 offline，之后启动完成、ADB 在线。没有验证 MeterService 本身是否重试成功。
- `saveSnToFile` 的序列号为空，以及 TrackingEventClient 消息解析警告。eventTracker 辅助日志另有 `DeviceId is: 0 some error happen`，来自事件统计辅助进程；尚未证实具体原因，未阻断本次启动。
- 未标级别的消息另有一次 `whpx: injection failed ... c0350005` 和六次 CPU `tsc-adjust` 特性不支持。后续启动完成，当前不据此改虚拟化配置；若反复出现卡死、异常退出需回查。
- 进一步核对：微软将 `c0350005` 定义为 `STATUS_HV_INVALID_PARAMETER`，属于虚拟化操作参数无效；具体触发原因未定位。六条 CPU 消息均针对同一特性，很可能在六个虚拟 CPU 初始化时重复打印。CPU 特性屏蔽或 QEMU 中断控制器路径调整只是待验证方向，不是已验证修复。
- ADB 上游查找分别尝试环境变量根目录、程序路径推导的 SDK 根目录与 PATH；某次根目录探测为空不等于全部候选失败。另发现 PATH 中的 `D:\SDK\Android\platform-tools\adb.exe` 为 37.0.1，包内 ADB 为 34.0.5；两者协议版本均为 1.0.41。本次没有变更二者路径或版本。
- `not found in map` 后紧接 DLL 加载成功，是首次加载提示，不是缺失 DLL。
- crash 数据库目录仅发现 settings/空 metadata 与空 reports，没有发现本次崩溃报告。

## 实际文件分布

占用为检查时近似值，运行、安装 APK 后会增长。目录链接不重复计数。

| 位置 | 内容与当前占用 |
|---|---|
| `D:\SDK\PICO\6.1\emulator\` | 模拟器程序、图形库、系统镜像、包内 ADB、`.pico-cli-bundle.json`；文件合计约 7.84 GB，其中 system.img 约 6.98 GB。 |
| `D:\SDK\PICO\emulator-first-start.log` | 本次指定的主启动日志，约 36 KB。 |
| `C:\Users\zk-wz\.pico\avd\` | AVD 配置、窗口/控制器设置、userdata/cache/encryption 镜像；文件数据约 1.04 GB（逻辑长度合计约 1.10 GB）。userdata-qemu.img.qcow2 约 997 MB，将承载模拟器内应用及其私有数据。配置的数据分区容量为 10 GiB，当前尚未全部占用。 |
| `C:\Users\zk-wz\picoAvdConfig` | Junction，指向 `.pico\avd`；兼容路径，不是第二份数据。 |
| `C:\Users\zk-wz\.pico\cli\` | emulator-state.json、emulator-last-state.json、锁目录及下载缓存目录。检查时状态 JSON 共约 1.1 KB，下载缓存为空，无 ZIP 残留。 |
| `C:\Users\zk-wz\.pico\` 根目录 | 更新后的 emu-last-feature-flags.protobuf、modem-nv-ram-5554 等小型模拟器状态。config.json 与 adbkey/adbkey.pub 已在本次启动前存在。 |
| `C:\Users\zk-wz\AppData\Local\Temp\AndroidEmulator\` | qemu-log、tracker-log、applog、nativeInfo.json、PicoEmulatorCache.ini、crash 数据库等；检查时文件合计约 29 KB。 |
| `C:\Users\zk-wz\AppData\Local\Temp\avd\pico_running\` | 运行时进程发现信息与 gRPC 认证文件；本次日志记录曾创建，退出后检查为空。 |

`PICO_HOME` 不是所有状态、缓存与临时目录的统一根目录。本次没有迁移或删除这些文件。

## 官方安装输入

- 清单：<https://is.snssdk.com/service/settings/v3/?app=1&aid=13&caller_name=spatial_plugin>
- 包：<https://lf-devtools.picoxr.com/obj/spatial-toolbox/online/emulator/pico_spatial_emulator_20260902_v6.1.0_win.zip>
- SHA-1：`db851ff8aa54f05a399122896372414df385b4c6`
- Vulkan 调试接口：<https://docs.vulkan.org/refpages/latest/refpages/source/vkCreateDebugUtilsMessengerEXT.html>
- Android 上游 ADB 路径查找：<https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/emu/adb/interface/src/android/emulation/control/adb/AdbInterface.cpp>
- 微软状态码定义：<https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/shared/ntstatus.h>
