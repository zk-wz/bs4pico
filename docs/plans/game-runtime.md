# D1 · 正版游戏工作副本与 Android 产品宿主

## 产品成果与边界

- 把已有 `prototypes/spatial-openxr/` 演进为同一个产品 APK，不另做运行时探针或第二个 APK。
- Spatial 页面能导入用户正版 Beat Saber 1.44.1、显示复制/组件准备状态、启动真实 Windows ARM64 Unity 游戏、查看本次实际启动日志并正常返回。
- 首轮保持原版：Windows ARM64 Player + ARM64 Mono，原 Managed IL 在 Mono 内 JIT 为 ARM64；不是 Android Unity 重编译、ARM64EC 或 x64 游戏翻译。
- D1 的成果是可使用的导入/准备/启动产品路径；Steam init 或 XR 尚待 D2/D3 时，真实游戏启动可以在对应阶段失败，页面必须如实说明。
- `engine-running` 只证明真实 Player/Mono 已执行，不证明菜单可交互、授权成功或歌曲可玩；原版完整可玩由 D2+D3 的游戏闭环判定。
- 总体约束见 [架构](ARCHITECTURE.md)、[组件共享契约](COMPONENTS.md)、[路线图](ROADMAP.md)；已完成事实只查 [状态](../STATUS.md)，构建入口查 [构建说明](../build/README.md)。

## 已有代码落点与新增位置

下表 Android Kotlin 路径均相对 `prototypes/spatial-openxr/app/src/main/java/io/github/zkwz/bs4pico/probe/`；Manifest 位于 `app/src/main/AndroidManifest.xml`。

| 落点 | 直接开发的修改 |
| --- | --- |
| `platform/LaunchActivity.kt`、`content/HomePage.kt` | 将“进入验证场景”改成正版导入、实例准备、真实启动、失败说明与本次日志；沿用现有 Spatial 主题和页面。 |
| `platform/SpatialApplication.kt`、`platform/VrActivity.kt`、Manifest | 加入管理/游戏进程分工、串行交接和进程条件初始化；原弱引用所有权不能跨进程沿用。 |
| `ProbeData.kt` | 将临时访问计数数据替换为产品实例清单与运行状态；不把原型计数当游戏状态。 |
| 原型 `app/src/main/cpp/CMakeLists.txt`、`xrprobe.cpp`、Gradle 与 `build-apk.sh` | 复用 Android loader、Surface/VM 生命周期基础，接入游戏宿主库；D3 替换测试场景帧循环，不保留假游戏画面。 |
| `versions.env`、`build.sh`、`patches/wine/`、`src/wine-runtime/` | 保留 Windows ARM64 组件构建，新增 Bionic Wine 宿主/Unix 半部的明确构建目标与补丁锁。 |
| `src/unityopenxr/patch_unityopenxr.py`、`patches/openxr-loader/`、`src/monoposixhelper/`、`src/steam-api/` | 复用已存在的 Unity 插件适配、runtime 发现、Mono 辅助库及 Steam API 转接；分别接 D3/D2。 |
| `install/bs-arm64.sh` | 复用其组件清单、安装记录与替换规则，重写为 Android 受控安装事务；它仍是 Frame 脚本，不能直接在 Android 执行。 |

实施时在现有 app 内新增实例存储/导入/启动协调类，在 `src/wine-runtime/android/` 新增宿主与 Android 后端源码；这些是待实现位置，不是现有可调用能力。同步修改局部 `AGENTS.md`，将原型限制切换为产品边界。

## 共享数据与启动接口

- 沿用 [架构的共享契约](ARCHITECTURE.md#数据与后续扩展契约)中的版本化 `GameInstance`、`LaunchRequest` 与 `RunState`；D1 实现其存储、读取、安装记录和跨进程交接。
- `GameInstance` 与 `LaunchRequest` 交接 `resolutionSnapshotRef`，引用按 [组件共享契约](COMPONENTS.md) 冻结的 `ResolutionSnapshot`；D1 负责本地解析、持久化与启动消费，D2 提供真实服务绑定，本文不复制快照或目录 schema。
- `manifestRef` 指向源文件相对路径、大小/摘要、原始版本、组件替换/新增记录及恢复位置；凭据和授权票据不在其中。
- 首轮 mod 加载保持关闭；先确定独立 mod/谱面/配置路径，D5 再实现加载及管理，不预建假的 mod 页面。
- 管理端提交不可变启动请求，游戏端从已提交清单读取路径；不能接受任意 shell 字符串或可写源目录。
- `steamSessionRef` 是 D2 的真实服务引用，不是明文密码/票据；本地导入无需先完成下载器，实际游戏授权仍由 Steamworks 判断。
- `runtimeReady` 不能把游戏标为已授权或 `playing`；状态转换必须对应实际 Player／Mono／XR／游戏行为，stage/error/logRefs 保留失败位置。
- 用 runId/生命周期 epoch 拒绝旧回调，运行日志通过引用回看，不把逐帧 pose/图像传给 Spatial 管理进程。

## 实现顺序 1 · 可恢复的正版导入

1. 在现有 Spatial 页面接系统文档授权，选择设备可访问的正版目录；WSL 已有输入先按备份约定准备校验过的导入副本，再通过受控文件交接放到设备可导入位置，不把 WSL 路径当 SAF URI。检查 1.44.1 的数据、Managed、插件与 Unity 版本，不把下载或账号登录作为本地导入前提。
2. 只读枚举源目录，计算清单、估算备份和工作副本空间；读取授权只作为导入入口，后续游戏使用私有存储，不把 SAF URI 当 Wine 文件路径。
3. 首次任何可能写入之前，独立复制不可变原始基线与可恢复备份，逐文件核对摘要和恢复映射，再建立独立工作副本；不用硬链接，不覆盖旧备份。
4. 采用临时目录复制、成功后原子提交实例清单；中断不发布半完成实例，已有实例/备份保留。空间或恢复条件不足时准确说明并集中请求用户选择，不冒险写原件。
5. 仅修改 workRoot，prefixRoot 和 userDataRoot 单独存放；保留原始源、备份与运行可写路径的明确区分，为 D2 更新和 D5 mod 实例复用同一模型。
6. 页面呈现真实复制进度、可启动性和失败文件；导入完成不显示“已经可玩”。恢复操作依据安装记录撤销替换/新增文件，不粗暴覆盖用户存档。

## 实现顺序 2 · 本地解析并锁定可安装的 ARM64 组件链

1. 依 [组件共享契约](COMPONENTS.md) 使用广义 `ComponentCatalog` 与本地 `component-catalog.json` 来源，记录 APK 内置、本地导入、用户合法导入、Steam depot、系统管理及未来远程模块；目录列出不等于模块可下载或可执行，也不扩大 D1 功能范围。D1 只实现已批准组件的固定版本本地解析/安装，远程发布、完整更新 UX、安全与恢复由 D4 实现，不在启动或帧热路径查询云目录。
2. 本地解析产出明确 `runtimeSetId` 与 `ResolutionSnapshot`，锁定源码 commit、补丁摘要、NDK/API、ABI、组件摘要及 PE/Unix 协议兼容关系；将快照引用提交至实例与启动请求，不以下载缓存存在代替兼容锁。`RuntimeSet` 成对绑定 Wine、DXVK、Windows XR、Steam PE/Unix 转接与引擎兼容性，安装器只激活已实现且允许的合法兼容组件。
3. 沿用 `versions.env` 的 Unity `6000.0.40f1`、Unity OpenXR `1.14.3` 与原版 1.44.1 配套；WindowsPlayer/UnityPlayer/Mono 和必经 native DLL 必须是纯 Windows ARM64。
4. Unity 受限组件由用户侧合法获取并验证版本/摘要，不进 Git/APK；游戏资源与凭据同样排除。可再分发组件同时保留来源和许可证。
5. Wine Unix 侧使用 Android ARM64 ELF/Bionic；GameNative/proton-wine 是当前移植候选而非唯一允许方案，不运行普通 glibc Wine tar 包，不使用 root/PRoot。实施相关功能时查主文档、源码、上游问题及更新/替代方案，比较 ABI、性能、许可、生命周期和维护成本。
6. 当前 `WINE_COMMIT` 是 Frame 上游组件基线，不代表已完成 Bionic 移植；选择并记录 Android fork 与 PE/Unix 接口兼容的组合，成对重建 `lsteamclient`/`wineopenxr`，不能混用两个分支的结构定义。内部 bootstrap/服务适配及其依赖变化须匹配更新，不承诺永久免维护或自动升级任意库。
7. 复用现有 Wine EH/私有 C++ runtime 补丁，并把所需 FPCR/FPSR 修正在源码层集成；不把 Linux `mprotect` 二进制修改当成 Android 必须依赖。
8. 已批准首选为系统 Vulkan ICD 与 Windows ARM64 DXVK `dxgi.dll/d3d11.dll`；出现实际功能/性能问题时调查包括但不限于 Turnip 的替代方案，重大取舍先 Ask，再采用；不默认加 VKD3D、glibc 或游戏热路径的 Box64/FEX。
9. 安装器依据工作副本清单部署 Player/Mono、UnityOpenXR、MonoPosixHelper、私有 C++ runtime、Steam/XR 转接 DLL，配置 prefix/runtime JSON/库优先级；原版禁用 BSIPA/Doorstop 注入。
10. 既有无捕获 LIV ABI 若是游戏启动所需可以沿用，避免缺 DLL 每帧异常；不增加 LIV 捕获能力、UI、构建专项或专项测试。
11. 根 `build.sh` 当前只产出 Windows 组件；实际开发补齐 Bionic 与 APK 依赖目标，并同步现有 APK 构建入口和文档，不宣称不存在的一键 Android 命令已可用。

## 实现顺序 3 · 实现真正 Wine 游戏宿主

1. Manifest 将 VrActivity 和宿主放入独立 `:game` 进程；Application 按实际进程初始化，管理进程才启动 Spatial，游戏进程只准备 VM/Activity/Native Surface 与游戏依赖。
2. 首选在 `:game` 内实现可嵌入 Wine 启动入口，使 Windows 游戏与 Android XR 后端共享 native 进程及兼容 Vulkan device；这不是 GameNative 已提供的 JNI 能力。
3. 将 Wine 启动、线程/TLS、信号处理、Windows 异常、JNI 引用和 native teardown 接到 Activity 生命周期；隔离 Wine 的进程级退出，不能让 `exit()` 或残留 handler 损坏管理进程。
4. 搭建 Wine 必要窗口/Surface、文件映射、注册表、字体与音频后端，保留 Unity 启动要求的窗口系统；不因最终不展示桌面镜像就假设 Unity 可以无窗口执行。
5. 用 LaunchRequest 启动工作副本内真实 Beat Saber executable，加载 ARM64 UnityPlayer/Mono；将 stdout/stderr、Wine 错误、Unity Player.log 和 native crash 关联到同一 runId。
6. 若现场实现证明无法可靠嵌入，调查包括 Wine 子进程 + Android XR 外部内存/fence 与帧 RPC 在内的方案；用证据和推荐集中 Ask 2–5 个实际选项，用户选择后再切换。进程边界详见 [D3](game-openxr.md)，不退回独立可行性项目。
7. 子进程布局还必须实现可合法执行的 Bionic 载荷位置、app UID 内文件访问、进程回收和真实音频路径；GameNative 的 linker64/ProcessBuilder 只能作参考，不等于 Android 任意可写目录都允许 exec。
8. D2 负责真实 Steam 后端；合法 Bionic 后端/自有 bootstrap 不可行时，研究包括隔离运行官方 Windows Steam 辅助进程的替代方案并先 Ask。若获准，仅该辅助 x86 路径允许 FEX/Box64，并真正接通服务/回调，游戏热路径保持 ARM64。
9. 后端来源、许可或 ABI 的实现问题在真实启动中解决；不得复制未获许可的专有 bootstrap/redirect/WX/kgslshim，也不得用 Steam API emulator、伪票据或 Steamless 补齐“成功”。
10. 重大性能、架构、后端、许可、隐私、维护、范围、体验、模块交付边界或侵入式环境变更，在相关实现中按 [组件共享契约](COMPONENTS.md) 先研究再 Ask，待选择才采纳；记录决策及重开条件。已批准默认方案与日常实现照常推进，失败不自动切换列出的备选，也不把当前候选当研究白名单。

## 实现顺序 4 · 页面与真实启动闭环

1. 页面按 GameInstance 清单显示“未导入/正在准备/可尝试启动/缺真实服务/启动失败”，点击启动先提交请求，再销毁管理场景/Surface并确认交接。
2. 用跨进程协议代替 SpatialApplication 的单进程弱引用所有权；确认旧 immersive Activity 销毁事务后才再次进入，Back/Home/退出不能靠强杀模拟成功。
3. `:game` 加载真实组件后回报阶段：PE 装载、Player 初始化、Mono Managed 入口、Steam 调用、XR 会话；不能以 PID 存活或探针画面推断游戏已运行。
4. 接 D2 真实服务后重用相同启动入口；接 D3 后由真实 session/frame/gameplay 事件推进 `xr-ready/playing`，日志阶段不直接驱动虚构游戏状态。
5. 正常退出写出状态、关闭 Wine/音频/XR、确认资源释放，再打开 Spatial 页面并展示真实退出原因和日志；异常退出由管理端观察进程死亡，保留证据和恢复入口。

## 边实现边做的必要轻量验收

- 导入接好时走一次真实页面路径：只读源摘要未变、备份可读且摘要匹配、工作副本独立；安装事务前的恢复核对是数据保护，不是反复游戏探针。
- 组件及宿主接好时用同一正版副本启动一次真实 Unity；保留实际 DLL/Mono 装载、Player.log、Steam/XR 成功或失败阶段，失败直接修复对应实现，不另建最小测试运行时。
- 本地解析接好时经同一页面准备与真实 Unity 启动核对实际载入版本/摘要、RuntimeSet 与 `resolutionSnapshotRef` 一致；缺失、不兼容或未知组件如实阻止激活，当前运行固定快照不被替换。此为实现中的真实路径验收，不是本轮文档运行设备。
- 页面交接接好时在该次启动后正常退出回 Spatial，一次确认数据/日志可读和管理/游戏渲染互斥；涉及歌曲的判定留给 D3 同一产品路径。
- 构建/必要静态工作优先 WSL；需要设备才使用后台 CLI 与已有实例，不自动截图、恢复窗口或抢焦点；空间人工交互或前台截图确有必要时集中 Ask 一次。
- 无目标机仍完成可构建的代码与产品页面，明确设备行为未跑；模拟器 ARM 翻译不证明 Space Pro 原生 ARM64 性能。

## 完成条件与不做内容

- D1 完成须交付可恢复导入、固定本地组件解析及快照交接、明确锁定的 Bionic/PE 组件、真实 Unity 启动入口、可见失败/日志及正常返回；只有规划路径或探针成功不算完成。广义目录不要求 D1 实现云完整更新器或所有未来模块。
- D1 尚未接通真实服务/XR 时不能宣布菜单/歌曲可玩；如果所有合法真实 Steam 后端最终均不可接入，记录实现尝试、不可替代缺项及用户可决定停止的依据，而非伪造授权。
- 不重跑已有切换原型、不先建测试运行时、不做完整 Steam 下载器或 mod 管理、不扩充 LIV、不自行压测或反复跑整套检查。
- 与 [D2](steam-integration.md)、[D3](game-openxr.md) 接口并行实现；原版闭环后由 [D4](game-delivery.md) 收敛安装恢复，D5 才开启 mod 加载。

## 已核实移植参考

- [GameNative 固定源码](https://github.com/utkarshdalal/GameNative/tree/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a)：以共享架构记录的 checkout 为准；BionicProgramLauncherComponent、ProcessHelper 与 SteamBootstrap 是独立进程启动参考，不证明 Wine 已内嵌。
- [bs-arm64 固定源码](https://github.com/DaVarga/bs-arm64/tree/5a318356703ac3835ee62bba677ba0778c76c7c5)：复用纯 ARM64 组件链与安装规则；Frame 运行实证不升级为 Pico 结论。
