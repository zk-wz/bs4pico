# 实验：E1 模拟器宿主/XR 回归与诊断

- 日期、运行编号：2026-10-10，`e1-20261010T074455Z`；电脑重启后新批次 `e1-20261010T132646Z-reboot`，不覆盖旧证据。
- 结论：**用户指定的轻量基础验收通过**；Home取消/确认、真实按钮及支持侧输入、定向重建、正常释放、暖/受控冷首次读取已验证。不执行30轮压测/六份成本对比；前序采证失败保留，不宣称完整新版五轮、长稳定性或性能通过。
- 目标：复现独立 Spatial/Native OpenXR 原型，补充身份、帧/输入/坐标/haptic 诊断与宿主回归；不接游戏、Wine、Steam 或真机。

## 条件

- Windows PICO CLI：0.6.0 public，Node v24.12.0；`update --check` 返回 latest=0.6.0，未更新工具。
- 模拟器：已有 bundle 6.1.0 / `Pico_Emulator_6_1` / `emulator-5554`；本次初始离线，由 Agent 启动，Windows 宿主 PID 52876。启动返回 `createdNewAvd=false`、`bootCompleted=true`，独立 ADB `sys.boot_completed=1`。
- 用户报告电脑重启、模拟器已关闭后，CLI 重开同一现有 AVD；宿主 PID 18136，`createdNewAvd=false`、`bootCompleted=true`、独立 status 在线及 ADB boot=1。未新建 AVD，未跑 doctor。
- Android 客体：x86_64、API 36；本轮当前安装 APK 的 `primaryCpuAbi=arm64-v8a`、`secondaryCpuAbi=null`，实际进程 `mRequiredAbi=arm64-v8a instructionSet=arm64`。系统支持顺序为 `arm64-v8a,x86_64`、`ro.dalvik.vm.isa.arm64=x86_64`、native bridge=`libhoudini.so`；属于模拟器 Android ARM64 兼容路径，不是真机、原生 ARM64 或 Windows ARM64/ARM64EC 证据，不能把客体架构当作应用加载 ABI。
- WSL 构建：系统 OpenJDK 21.0.12.1、共享平台 35/NDK 30.0.16248370、CMake 4.4.4、Ninja 1.13.2；不在 Windows 重复安装构建工具。
- Spatial BOM 6.1.9；Khronos loader/headers 1.1.49，instance 请求 API 1.0。实际 runtime `Pico XRRuntime()` version=0.0.0，system=`Pico-emulator HMD`。
- 实际 GPU：NVIDIA GeForce RTX 4070 Laptop GPU，日志 `API=1.3.0 selectedAPI=1.4.0`；STAGE 空间。保留实际诊断值，不套用历史日志。
- 未修改基线 APK：39,227,121 bytes，SHA256 `8d96313d52c6e5130aa63540634e7b19fa0fc59269fc0c120ba694fb1458bb1b`；默认 x86_64 + arm64-v8a，Windows CLI 从 WSL UNC 安装成功。
- 重启后所有权修正版 APK：39,742,964 bytes，SHA256 `842b925bd32d571a6ea7790bd6ce894c365ecfecd835727cdf899300e1a1f406`，含两 ABI；默认构建 26 秒成功并通过 Windows CLI 安装。
- 日志收敛版 APK：39,744,044 bytes，SHA256 `d015737d550f00500d73b2dccc6f36f9ebbf9408a70b51ae4517f5c97a675780`；两 ABI 构建7秒成功、Windows CLI install成功。仅减少启动期扩展枚举刷屏：保留可用/启用数量及实际启用项，不放宽 runner 的序列/释放检查。
- 账号、所有权、游戏资源、曲目、音频：不适用；未访问游戏原件。

## 步骤与结果

| 项目 | 实际步骤与证据 | 结果/边界 |
|---|---|---|
| 运行前提 | 实际 CLI version/help、AVD list、精确 status、device list、独立 boot；WSL 构建成功 | 运行能力通过；按用户要求跳过后续 doctor，见根 `AGENTS.md` |
| 未修改基线首次运行 | `baseline-before/` 五轮新双眼、Back 和数据一致，管理重建完成；随后等待 Native 时有限 logcat 返回 1 | 整项失败保留；原 runner 未保存失败 stdout/stderr，精确原因无法补证。现场 PID 3570 仍在提交双眼，实际截图为方块/网格 |
| 采证修正后的第二次 | `baseline-before-instrumented/` 改为保存全缓冲/命令日志，APK 未改 | UTF-8 解码在 byte 1109319 失败；未自动清理现场 |
| 字节安全采证后的旧基线 | `baseline-before-byte-safe/`，同一 APK，direct Native→五轮→manager recreate→Native recreate→新 Intent pause/resume→Home overlay→debug return | 完整通过，108.70 秒；保留原始命令字节、JSON 和快照。Home 仅失焦/调试返回，不计取消或确认 |
| 实际管理界面 | `baseline-manager-window.png` 显示 Spatial 管理窗口、持久值及“进入 VR”按钮 | 已观察，不是背景或普通平面页 |
| 实际 Native 画面 | `baseline-failure-window.png` 显示彩色方块和地板；同时日志有 views=2 projection | 已观察；`baseline-native-window.png` 实际为管理窗口，不作为 Native 证据 |
| 身份/JNI/退出探针 | 两 ABI 构建成功（14 秒），安装后 `identity-smoke/ --cycles 1` 执行完整重建/失焦/正常清理路径（60.55 秒） | 7 workers、1004 条规范原生事件 seq 连续；worker/session 存活集合各最多 1，旧 session 销毁及 worker join 后才开始下一份 |
| 首次读取与持久值 | 新进程首次 `private read` 为 generation=36、visits=53、last_writer=native，与旧基线最终提交一致 | 首次 read 契约通过；尚不能代替完整分类 recovery |
| 正常关闭管理窗口 | Native 已正常返回后 debug `finish`；独立 Activity dump 无管理历史实例 | 通过；未用 force-stop 冒充正常释放 |
| 新帧/输入诊断 | 两 ABI 构建成功；重建/新 Intent 实跑，新 worker 8 的 FRAME_SAMPLE 校验非负分段、分段和≤total，READY 零层图像/提交计时为 0，FOCUSED 两眼提交 | 计时/快照实跑通过；CPU/等待墙钟，不是 GPU 时间或显示 FPS |
| 新几何实际显示 | 用户恢复窗口并反馈“场景可见”；`native-haptic-restored-geometry.png` 显示世界方块、地板、方向箭头与品红近场几何 | 已观察；右 grip 在头部附近且零四元数但 runtime flags=valid，导致近场遮挡，不能称有效双手 6DoF |
| haptic 受控预检 | 显式 DEBUG true 的 worker 8，右 apply/立即 stop 各 result=0；正常 Back 两 swapchain/session/instance 销毁各 result=0、join，summary pending=0 | 右 API 预检成功，不是物理振动；左 inactive，summary not_covered；默认 false 无调用 |
| reference-space 诊断 | 已实现 session 过滤、实际变换/生效时间与跨越采样 | 尚无真实 recenter 事件，不计运行通过 |
| 新诊断 smoke 首次 | `native-diagnostics-smoke/` 启动返回 kept-for-user 警告，系统记录 fullscreen 拒绝；无新 PID | 失败保留；脚本补实际冷条件等待及文本拒绝检查，不重试 launch |
| 新诊断 smoke 第二次 | `native-diagnostics-smoke-cold-checked/` 重建与 pause/resume 通过；Home 等待旧日志措辞失败 | 失败保留；实际同帧 state=4 / syncAttempted=1 / syncResult=8 已捕获，改为结构化语义检查 |
| 前台截图对比 | `capture-comparison-background.png`：foregroundBefore/After=false；`capture-comparison-foreground.png`：false→true；默认入口再次 false→true | 同一 Native 场景两图均非黑，本轮不能归因“后台必黑”；已验证精确激活，按用户授权以后截图先前台 |
| 新诊断语义 smoke | `native-diagnostics-smoke-semantic/ --cycles 1`，重建、新 Intent、Home overlay/debug-return 与正常清理 | 完整通过，79.96 秒；仍不计 Home 人工两分支 |
| 新 runner 首次五轮 | 原批次 `baseline-after/` 五轮切换完成；管理重建后新实例被旧已销毁实例的 finish 关闭 | 整项失败保留；`SpatialApplication` 对 Manager 增加与 Native 相同的 isDestroyed 门控，不加延迟或 launch 重试 |
| 重启后修正版五轮 | `baseline-after-ownership-fix/` 五轮和管理重建稳定点完成，generation=54/visits=89/native；Native 重建时 pidof 输出 `4111 5756` | 整项仍失败保留（363.45 秒），不能标全基线通过；finally 观察仍为 PID 4111/starttime=48334，worker/session 9 仍存活，待定位 PID 采证边界 |
| PID 采证边界 | 同时段系统请求 native backtrace；AMS 只登记主进程 4111。对保存的两候选输出、AMS 和 stat 做一次离线边界验证 | 多候选时改用 AMS 登记的唯一主进程，不取 pidof 第一项；真实登记歧义仍失败；离线验证不计重建运行通过 |
| 轻量定向尝试 | `targeted-recreate-and-data/` 已恢复实际 worker/session 9 的完整规范区间；第一张窗口截图被最小化保护拒绝（21.16 秒） | 保留失败，在任何新重建动作前停止；现场未自动清理，仍有实际 worker/session 9。需恢复精确窗口后用新目录继续单次定向验收 |
| 临时前台截图 | `capture-transient-safe-owner.png` 实际显示世界方块、网格及近场品红几何，foregroundAtCapture=true；借用275.427ms，minimizedAfter=true、foregroundAfter=false | 非黑且截图后不持续前台；previousFocusRestored=false，不宣称已交还原工作焦点。此前两次交还被拒绝也保存，不改写为成功 |
| 原现场的日志保留边界 | `targeted-recreate-and-data-visible/` 第一阶段发现 worker9 创建事件已不在当前有限日志缓冲；未执行重建，20.18秒失败保留 | 不拼补缺失规范序列、不虚构存活图；之后以正常 Back 观察 worker9 两 swapchain/session/instance 销毁全部0及 join、数据未变，再正常 finish，Activity 无本包历史实例 |
| 单次新场景重建的采证失败 | `targeted-fresh-native-and-data/` 在重建后 worker12 的扩展枚举原始日志缺 seq7，57.96秒失败；finally仍保留该异常 | 不把日志缺失等同XR崩溃、不跳过缺口；正常 Back另行观察 worker12资源销毁全0、join、数据未变和 Manager finish。日志突发是待证实原因，收敛无用全量扩展输出后只复核受影响路径 |
| 轻量定向复核 | `targeted-reduced-noise-native-and-data/` 单次 Native 重建、正常 Back/finish、一次暖重开和一次受控冷重开 | 250.24秒通过，所测 worker/session最多各1且最终全释放，无 collection error；保留全部前序失败，不把该结果升级为完整五轮回归或压测通过 |
| 暖/冷首次读取 | 已提交 generation=57、visits=98、last_writer=native；暖重开 PID12480/starttime537255不变；正常 finish 后受控 force-stop，冷重开PID13287/starttime555589 | 两次首次 private read完整等于旧提交值；仅受控冷条件，不是自然LMK/后台死亡恢复。实际管理窗口两图均显示57/98/native，重建Native图实际可见方块/网格/近场几何 |
| 压测 / 成本对比 | 用户明确取消本轮30轮压测和六份重复成本采样 | 未执行、不作为基础验收前提；不声明长轮次、资源无累积或性能通过 |
| Home 取消 | prepare真实弹窗；用户点取消并短按右 trigger一次；`home-cancel/check/`检查通过（66.78秒） | 原PID13287/starttime555589/session1恢复FOCUSED双眼和同帧sync，无重建；右trigger 0→1→0、实测按住2.950秒，左inactive。取消后实际图为方块/网格；数据57/99/native未变，随后正常Back/finish、存活集合空 |
| Home 确认 | 用户点确定停在系统主界面；`home-confirm/check/`检查通过（105.59秒） | 原session2 SurfaceDestroyed/onPause/onStop、正常资源释放及join；重开前AMS实际前台为解析出的launcher。首次read为57/100/native，重开新session3后正常Back/finish，最终58/101/native、存活集合空。管理及Native重开图已查看；首页图仅环境，不单凭背景判定首页 |
| 真实按钮与输入 | 同一次人工操作的`input-basic-evidence-recheck/check/`通过（65.91秒），真实Manager按钮后新session4；头部及双眼平移/旋转、右aim变化、trigger低→高→低 | 实际新视角图已查看，用户确认场景可见；右haptic同帧apply/stop均XR_SUCCESS，左inactive/not_covered；正常Back/finish后最终59/102/native、存活集合空 |
| 输入检查额外时长门槛 | `input/check/`29.00秒失败：最长XR lastChangeTime差值4.017816436秒；用户随后补充“按的时间可能确实短了点，算是预期之中” | 保留原失败与实测时长，不归因模拟器时钟、不宣称五秒通过。原基本check判据是输入周期，移除脚本额外五秒门槛；新目录复用原checkpoint/原seed逐字节副本及SHA256来源记录，只复核同一次交互，不重做按钮/动作 |
| 结束与范围 | 各通过场景正常Back/finish已释放；官方stop精确匹配`emulator-5554`/原AVD/宿主PID18136 | stop成功，随后精确device status退出4但实际processRunning=false、adbOnline=false，无errors。曾误给status传`--avd`的usage错误保留，查help后改为其实际支持的`--adb-device`；未泛化停止其他实例 |

`native_visits` 计成功 session 创建数，不是导航轮数；重建/新 Intent 可合法增加多次，不约束每轮只加一。

## 性能

本轮按用户要求不采六份成本样本。GPU 时间、实际显示 FPS、输入延迟、音画同步、持续热性能、资源无累积及 Space Pro 性能未测；模拟器输出不能升级为真机结论。

## 证据

原始证据位于忽略的 `private/validation/e1-20261010T074455Z/` 和 `private/validation/e1-20261010T132646Z-reboot/`；各次失败目录保留、不覆盖。旧批次包含基线/身份元数据和原始日志；重启批次包含重开/部署、窗口焦点元数据、定向重建、首次读取及人工 prepare/check 的命令原始字节。

以下路径均相对于重启批次根目录，SHA256 校验实际文件：

| 文件 | Bytes | SHA256 |
|---|---:|---|
| `reduced-noise-apk-metadata.json` | 244 | `86f55da30d4f8d0f8cea2e7e40ea05fc749ae86a4137353d08a9fa5ab74a1f14` |
| `capture-transient-safe-owner.png` | 62305 | `c949bb6226a4668f9df150ba575da4700960887cc51135243fdf19ee32eb88c4` |
| `capture-transient-safe-owner.json` | 1038 | `a61117b395c3a8e70ef06925c65b4fd7ece8ac513e136047dda9e506ae4d4d19` |
| `targeted-reduced-noise-native-and-data/targeted-result.json` | 31563 | `360e1ab40d195b311e6e067bf058d6dd460fcffafca1a9b41fe0892c952af567` |
| `home-cancel/check/result.json` | 6046 | `485e459238e989fa3b138459975f4eff7844b89a4c1928cd5c2e652490dfee11` |
| `home-confirm/check/result.json` | 4159 | `9baeb827987a0321943ac2ceca9e4d1716c512b0bd041ac3a4bfbccf059b1ddb` |
| `input/check/result.json`（原失败） | 476 | `a1a03aa26a5a7091fc13cbb563ad4ccd09128c026d7891b768a34e161fffcf4b` |
| `input-basic-evidence-recheck/check/result.json` | 116277 | `de07b6edfab3ebf211af7ec04dbf21a8bf4d8e7ffa878fd992b6eedd45e389fc` |
| `input-basic-evidence-recheck/continuation-provenance.json` | 623 | `dc46af294370c1eebf8b731da49647bfb4ffa62baee88d1d722a968e4c4a2a2a` |
| `input/manual-duration-clarification.json` | 327 | `bd09e5e35fdabe3f5b24201db0bdfb18dc6ed40b7ba7a9705fd0f9c5c1a9c5a9` |
| `official-final-stop.json` | 1022 | `3618f1adfba79449565b2c2cfb4cc35e56df50579cbf4062c03c0e2298fe1f12` |
| `official-final-exact-device-status.json` | 858 | `d1e33143eeb80730ccd4f4803e958eaa456cad6e945a3b52ef9d642d7e2bdbb2` |

## 判断与下一步

本轮基础范围已验收并结束，不继续30轮或性能重复采样，也不进入E2–E4。左侧、无用grip及重定位保持未覆盖；haptic仅API预检，非物理振动或真实双手6DoF。截图采用授权的临时前台租约，用户切走优先，交还失败则最小化目标；本轮后台/前台对比均非黑，不能推出“后台必黑”。后续仅按新任务指定范围验证。
