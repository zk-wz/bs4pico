# D2：真实 Steam 登录、正版内容与游戏服务

## 目标、依赖与首轮边界

- 在同一 APK 的 Spatial 管理页登录真实 Steam 账号，处理 Steam Guard，显示用户库中的 Beat Saber、版本与 DLC 权益，导入已有正版文件或下载正版内容。
- 在 D1 的实际 Beat Saber 1.44.1 启动路径上接通真正的 Steamworks 初始化、所有权、DLC 与回调；网页登录、库列表或 DLL 成功加载不算运行时服务完成。
- 依赖 [D1 游戏运行时](game-runtime.md) 的宿主、备份、独立工作副本和启动接口；与 [D3 OpenXR](game-openxr.md) 并行实现，不要求先完成完整下载器 UI 才写 XR。
- 用户已有 `private/BeatSaber/1.44.1/`，先用该正版输入建立工作实例并接 Steam 服务，不强制重新下载，也不让内容更新覆盖这一原始副本。
- 本文是实施计划，不宣称以下接口或设备行为已存在；路线、共享契约、状态及构建入口见 [架构](ARCHITECTURE.md)、[组件共享契约](COMPONENTS.md)、[路线图](ROADMAP.md)、[状态](../STATUS.md)、[构建说明](../build/README.md)。

## 已有代码与借鉴边界

| 落点 | 已有内容与实际用途 |
| --- | --- |
| `prototypes/spatial-openxr/` | 将现有管理入口演进为账号、库、导入和下载页面，继续使用同一产品 APK |
| `src/steam-api/steam_api_core.cpp` | ARM64 `steam_api64.dll` 的 init、pipe、interface、callback，真实转接 `lsteamclient_a64.dll` |
| `src/steam-api/steam_api_helpers.cpp`、`gen.py` | 已有 flat API 与接口生成；按游戏实际调用补齐 ABI，不引入模拟授权实现 |
| `src/wine-runtime/`、`build.sh`、`versions.env` | Windows ARM64 与 Wine Unix 半边的构建和版本锁；Android Bionic 构建入口需要随实现接入 |
| `install/bs-arm64.sh` | 参考 appid、runtime 路径与加载顺序；这是 Steam Frame 脚本，不能当成可直接 Android 执行的安装器 |
| `private/GameNative/.../service/SteamService.kt` | JavaSteam 真实认证、账号会话、许可证、depot 与下载状态的参考 |
| `private/GameNative/.../ui/screen/login/UserLoginScreen.kt`、`ui/model/UserLoginViewModel.kt` | Guard/登录状态参考，不搬入完整多商店客户端 |
| `private/GameNative/.../ui/screen/library/LibraryScreen.kt`、`data/StoreDetailsRepository.kt` | 库展示、公开商店 metadata 的参考；商店资料不是 ownership 证据 |

GameNative 的 `BionicProgramLauncherComponent.java` 与 `ProcessHelper.java` 通过 linker64/子进程启动 Wine，不证明 Wine 已 JNI 内嵌。
`SteamBootstrap.kt.prepareApp()` 实际 `ProcessBuilder` 执行独立 AArch64 ELF PIE host；注释或 notices 中的 JNI 描述不能替代该进程事实。
其 ready/status 文件、Steam3Master、SteamClientService 和退出管理可作为协议参考，不能直接沿用静默返回成功或含 token 的日志。
`THIRD_PARTY_NOTICES` 明示 steambootstrap、redirect/WX、kgslshim 专有且相关源码缺失；它们不是已可自由复编、复制或再分发的依赖。
JavaSteam 等开源协议库提供认证/账号/depot 能力，不等于专有真实 Steam client 或可用 Steamworks 后端；下载能力也不产生合法且适配 Bionic 的 client binary。GameNative/Bionic 与官方 Windows 辅助客户端只是当前候选，不是研究白名单。

## 共享数据与进程接口

- 沿用 [架构的共享契约](ARCHITECTURE.md#数据与后续扩展契约)中的 `GameInstance` 与 `LaunchRequest`，D2 不另建安装或启动模型；服务引用不是 token、ticket 或网页 session。
- `GameInstance` 与 `LaunchRequest` 复用 `resolutionSnapshotRef`；D2 向 D1 本地解析器提供选定 `SteamBackendBundle`、服务协议与匹配 RuntimeSet 的绑定，D1 固化快照并交接，后端准备及游戏启动消费同一快照。结构、兼容与激活规则由 [组件共享契约](COMPONENTS.md) 唯一维护，本文不另建 schema。
- `SteamBackendBundle` 由真实 client 与匹配 bootstrap/服务适配器组成，受版本化私有 IPC 边界约束；D2 负责获取来源/许可、配对、生命周期和实际 Steamworks 服务，不能只升级 client 而忽略内部依赖。账号/协议库、下载器与该 bundle 分开维护；若编入 APK，更新仍需 APK 发布，不自动变成独立可云更新模块。
- 广义目录分别记录模块及本地/远程交付能力，`component-catalog.json` 是未来云目录发布来源，不是现成下载端点。D1 负责固定本地组件解析，D2 负责真实账号/Steam 内容来源与后端集成，D4 负责云发布、完整组件更新 UX、安全与恢复；目录不能授权或再分发受限内容，当前 D2 不扩展到全部目录模块。
- 管理侧新增账号会话、库权益及下载记录：SteamID、appid、branch、buildID、depot/manifestID、所选 DLC、校验状态、任务阶段、已校验 chunk 与 staging 路径；来源未知必须明确标记。
- 账号状态为未登录、登录中、等待 Guard、已登录、凭据过期、失败；下载状态为解析、下载中、暂停、校验、可导入、失败，不用单一“已准备”混合所有阶段。
- D2 向 D1 提供 `prepareRuntime(instanceId, runId)` 的会话引用/`runtimeReady` 或真实错误，以及与 runId 绑定的正常退出清理；名称为待实现项目接口，不是现有 SDK API。
- `runtimeReady` 仅表示后端进程与通信已就绪；最终 Steamworks init/ownership/DLC 结果来自游戏调用，不能由库中的 owned 标记写成成功。
- 管理进程只负责页面、认证和任务；独立真实 Steam 服务 host 与 D1 `:game`/Wine 通过本地受控接口通信。Steam callbacks 不经 Spatial UI 每帧 IPC。
- 密码仅用于当次认证；refresh token 等由私有凭据存储保护，普通配置、LaunchRequest、日志、Git、APK 不含秘密。注销后销毁本项目会话引用与凭据，不碰用户桌面 Steam。

## 实现顺序与每步可见成果

### 1. 先接账号与库，同时保留本地导入入口

1. 在现有 Spatial 管理页增加真实登录和 Guard challenge 状态；GameNative 的认证调用是当前参考，实施时结合协议库主文档、源码、上游问题与较新/替代实现比较维护、许可、隐私及能力后接入真实邮件码/手机码/批准等待，取消与过期可明确返回，不打印凭据。已批准常规接入不反复 Ask，重大库/后端或模块边界选择按下述决策规则先 Ask。
2. 登录成功后读取真实 license/package 和 Beat Saber 库记录；显示账号、是否持有本体、可用 DLC、内容版本与文件状态。公开 appdetails 只补标题/封面，不能修改授权状态。
3. 商店入口只打开 Beat Saber 的官方购买/详情路径，交易交给 Steam；购买后显式刷新权益，不把商店网页成功加载等同购买完成。不扩展通用商店浏览器。
4. 从用户选择的正版目录读版本与所需文件清单，通过 D1 建立校验备份和独立工作副本；未知 buildID 保留未知，不伪造 depot manifest。导入不等于获得授权。
5. 可见成果：用户能登录、完成实际 Guard、看到 Beat Saber 与 DLC，选择已有文件后看到导入进度及真实准备状态；即使下载 UI 未完成，也能走同一实际游戏启动入口。

### 2. 接真实 Steamworks 后端，尽早启动游戏

1. 当前首选候选为可复编自有 Bionic bootstrap，通过公开接口接依法获取、获许可且实际适配 ARM64/Bionic 的真实 Steam client 后端；记录获取来源、许可、架构和版本，不能假定已有可分发 Android 客户端。实施此功能时研究候选以外的新方案，不另开可行性阶段；主方案尚待关键后端证据，不能因已命名就跳过重大选择的 Ask。
2. 如采用 GameNative 专有 host/运行组件，先取得明确使用/再分发授权，按授权外置获取或打包；只有公开 Kotlin/Java 源码并不授予这些 binary 的许可。
3. 在开发现场实现配对 `SteamBackendBundle` 的 host 配置、启动、真实登录/pipe ready、状态上报、退出与故障传播，按版本化私有 IPC 对接 D1；敏感认证通过受控私有通道传递，避免照搬环境变量/命令日志泄露。
4. 配置实际 `SteamAppId`/`SteamGameId`、prefix、服务端点和 `STEAMAPI_ARM64_CLIENT_DLL`；ARM64 PE、Wine Unix ARM64 Bionic 半边、bootstrap/服务适配器与真实 client 必须匹配 RuntimeSet 和本次快照，不能把 Linux/glibc steamclient 直接当 Bionic 库，也不采用 root/PRoot。内嵌依赖/协议变化须成组构建与兼容验证，不承诺永久免维护或自动升级任意第三方库。
5. 用现有 ARM64 shim 转接游戏所需 SteamClient/Apps/User 等接口及 callback 数据布局、线程和生命周期；保留真实结果/错误，不写恒真 ownership/DLC 或虚构票据。
6. 直接启动 D1 的正版 Beat Saber，沿游戏日志观察 init、ownership 与 callback 分发；按实际缺失接口修复，保持 D3 可继续开发，不另造独立 Steam 探针项目。
7. 若 Bionic 后端获取、自有 bootstrap 或 ABI 接入确实不可行，研究包括真实官方 Windows Steam 辅助进程在内的替代方案，比较性能、接口/ABI、许可、生命周期与维护代价；形成证据及推荐后先 Ask，不静默切换。获准时仅该辅助 x86/x64 路径允许隔离使用 FEX/Box64，游戏 Unity/Mono 与渲染热路径仍是纯 ARM64。
8. 该备选在独立受控进程/prefix 中运行依法取得的官方客户端，明确 x86 与 ARM64 两侧客户端协议、接口封送和 callback 来源；不能把架构不同的 DLL 直接装进 ARM64 游戏，也不能让辅助进程持有游戏 XR/Vulkan device。
9. 按 [组件共享契约](COMPONENTS.md) 在相关实现中查主文档、源码、上游问题及更新/替代方案；重大性能、架构/后端、许可、隐私、维护、范围、体验、模块交付边界或侵入式环境改变，集中 Ask 2–5 个真实选项、证据与推荐，用户选择后才采纳，期间推进无关工作。记录决策/重开条件和真实启动证据；已批准默认及日常执行无需逐步批准，不恢复前置可行性流程。
10. 可见成果：从管理页启动真实游戏，游戏实际初始化真实 Steam 服务；已购内容可用，未购 DLC 不解锁。D3 尚未接齐时不能声称歌曲可玩。

### 3. 补齐可续下载、校验与更新

1. 复用 SteamService 的 depot/manifest、license、key 获取思路，只实现 Beat Saber 及其合法 DLC。选择 Windows 正版内容，ARM64 Unity/runtime 替换由 D1 管理，不虚构 Steam ARM64 游戏 depot。
2. 下载到独立 staging；持久化 appid、branch、manifestID、chunk 校验及任务状态。恢复前对照相同 manifest 与磁盘校验结果，仅复用已确认内容，不以进度百分比代表文件完整。
3. 页面显示解析 depot、下载/暂停/继续、校验和错误；空间不足可明确暂停并保留已校验数据，不删除用户原件或备份腾空间。
4. 完整校验后发布新只读 source，再让 D1 创建可恢复备份和独立 work 实例；从未校验 staging 或正在更新的目录启动必须被真实状态阻止。
5. 更新先解析目标版本与 D1 runtime 兼容性；用户选定版本可被 Steam 合法渠道提供才下载，不能承诺旧版 1.44.1 永远可从当前分支取回。
6. 新版本用新 source/work/manifest，保留旧可玩实例；游戏运行中不改 workRoot。数据迁移、更新失败恢复由 [D4 交付](game-delivery.md) 统一收口。
7. Steam 游戏内容/depot 更新不等于账号库、下载器代码或 `SteamBackendBundle` 更新；候选后端变更先作上述研究/Ask，基本匹配本地安装沿 D1 快照完成，未来远程 bundle 发布/升级沿 D4 交付契约完成，不能边运行边替换 client、bootstrap 或游戏组件。
8. 可见成果：一次实际暂停/继续后完成所选正版内容，看到校验完成和版本，选择新实例启动；已有本地文件用户无需等待这一步才能接 D3。

### 4. 联通 DLC、callback 与正常退出

1. 将游戏实际调用的 `BIsSubscribedApp`、`BIsDlcInstalled`、安装信息和 license 变更传到真实服务，区分已购、未购、尚未安装和无可用数据，不用本地文件存在替代授权。
2. 由游戏自己的 callback 生命周期驱动真实回调与异步 call result，按接口版本封送尺寸；进程死亡/账号失效返回实际失败，禁止重复合成成功事件。
3. 正常游戏退出后先停止消费/注销游戏接口，再释放 pipe/user、关闭本项目 host 与本地引用；重新进入 Spatial 页可准确看到结束或故障原因。
4. 离线仅采用真实客户端允许的缓存授权语义；无有效授权就显示实际错误，不新增“离线总可玩”保证、DRM 绕过或票据合成。

## 开发中的轻量实际路径验收

- 每个已实现路径必要一次：真实账号完成当次 Guard → 库权益 → 已有正版导入 → 同一游戏启动。Guard 由账号实际挑战决定，不能用假挑战截图充数。
- 本体授权以游戏 init/实际请求及可进入游戏的行为共同判断；有已购 DLC 就观察其真实可用状态，无已购 DLC 则注明正向 DLC 未验，不购买新 DLC 只为验收。
- callback 用实际游戏调用/分发日志关联 runId 与真实后端，不以伪造事件或独立 Steam 探针代替；必要失败边界只覆盖当前修复路径。
- 后端集成时在同一次实际游戏启动核对 `resolutionSnapshotRef`、实际 client/适配器版本、RuntimeSet 及私有 IPC 协议一致；真实登录或下载成功不代替 client 合法来源与 Bionic/ABI 兼容证据，不兼容组合不激活。
- 下载实现后做一次暂停/恢复并完成校验；更新存在合法可获取目标时走一次新实例发布，检查旧实例/原件不变。无目标则注明未运行更新路径，不能假造新版。
- D3 接好后共享一次双眼菜单/正版曲目/正常退出证据；D2 不再要求额外全套曲目或重复启动轮次。
- 构建/静态工作优先 WSL；需要运行才用已有设备/模拟器后台 CLI，不自动恢复窗口、截图或抢焦点；必须空间操作时集中一次 Ask。无目标设备则明确设备行为未验证。
- 失败直接修复当前实现；需要改变架构/后端则重新研究并先 Ask，不自动切换列出的备选。所有合法真实后端均无法接入时，说明缺失组件、已尝试实现和停止项目依据，不交付假授权。本轮文档编写不启动设备；后续实现仍执行必要的当前路径运行检查。

## 完成条件与非目标

- 首轮完成包含真实账号/Guard、库权益、本地正版导入、可续正版下载/更新、独立实例以及实际游戏 Steamworks 服务；实现顺序允许导入+服务+XR先得到可玩结果，再补完整下载体验。
- 凭据不出私有边界，原件和既有备份不变，实际错误可见，退出释放完整；可玩结论需 D1/D2/D3 的同一实际路径证据。
- 完成时须有合法真实 client 与匹配 bootstrap/服务适配器的 bundle、固定快照交接和版本化服务边界证据；账号/协议库、下载代码与 backend bundle 的维护/升级责任分明。D2 的 Steam 内容下载/更新不要求提前实现 D4 云完整组件更新器，目录的未来模块也不扩大首轮范围。
- 不使用 Steam API emulator、Steamless、伪造所有权/票据；不做全商店、多账号社交、云存档平台、通用 overlay、社区服务或 LIV/混合现实录制。

## 核实来源

- [GameNative SteamService](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/java/app/gamenative/service/SteamService.kt)、[库页面](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/java/app/gamenative/ui/screen/library/LibraryScreen.kt)、[商店资料](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/java/app/gamenative/data/StoreDetailsRepository.kt)。
- [GameNative bootstrap 实际子进程入口](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/app/src/main/java/app/gamenative/SteamBootstrap.kt)、[专有组件 notices](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/THIRD_PARTY_NOTICES)。
- [GameNative Wine 移植基线](https://github.com/GameNative/proton-wine/tree/77eed5501e077f5f0422d063b171a3a4491f52a6)、[bs-arm64 ARM64 Steam 转接](https://github.com/DaVarga/bs-arm64/tree/5a318356703ac3835ee62bba677ba0778c76c7c5/src/steam-api)；上游 Frame 行为不等于 Pico 已验证。
