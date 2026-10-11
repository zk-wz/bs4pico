# 组件清单、兼容组合与独立更新

本文是待实现的组件管理契约，供 [产品架构](ARCHITECTURE.md)与 D1–D5 共用。清单源文件为 [`component-catalog.json`](component-catalog.json)；它将来发布到云端，当前没有部署地址、发布密钥或可下载组件版本。清单存在不代表组件安装、远程更新或游戏运行已经实现。

## 目标与范围

- 稳定应用主体，尽量独立更新运行包、Steam 服务和游戏内容；不承诺永久不更新 APK 或无人维护。
- 清单登记整个产品的组件边界，不仅登记下载项：包含 APK 内置代码、受限用户输入、Steam 内容、本地数据、生成缓存、系统组件和后续扩展。
- 模块边界、交付方式和远程能力分别描述。先本地实现的模块以后可以增加合法远程获取方式，不需要另外维护一份在线模块名单。
- 广泛登记不扩大当前开发范围：原版可玩仍是 D1–D4，BSIPA／mod／谱面是 D5；缓存、诊断、语言和策略等登记项不自动成为新增功能任务。
- 云端清单只分发受信任的描述和允许分发的载荷；不承担 Steam 所有权判定、不包含游戏文件、凭据、票据、私钥或受限 Unity 二进制。

## 清单源与覆盖面

`component-catalog.json` 是未来云端目录的版本控制源，不是构建锁文件或某台机器的安装状态。当前所有模块的 `implementationStatus` 均为 `planned`，仅指本清单下的产品封装尚未实现；已有原型与上游能力仍以 [STATUS](../STATUS.md) 为准。所有 `releases` 和 `profiles` 初始为空，不生成假版本、假下载链接或假兼容结论。

清单涵盖以下边界；具体模块 ID、责任阶段和交付策略只维护在 JSON，本文不复制完整条目表：

- Android 宿主、Spatial 页面与 Android XR 桥。
- Wine、DXVK／Vulkan、Windows XR／Steam 桥、Unity Player／Mono 及辅助库。
- Steam 账号／下载适配、真实客户端服务与 bootstrap；独立音频后端。
- 用户游戏／DLC、BSIPA、mod、谱面与配置。
- 可选 GPU 驱动、输入／性能策略、生成缓存、诊断及语言资源。
- PICO 系统 XR runtime 与系统 Vulkan 驱动；登记所需兼容条件，安装更新仍由系统负责。

新增条目先描述当前真实边界。只有相应安装器、装载接口、合法来源和产品路径实际完成后，才发布可激活版本；不能为了把清单填满而先写所有后端。

## 描述契约

以下名称均是项目接口设计，不是现有 SDK API。D1 先实现当前用到的最小字段，其余随所属功能落地；不预建任意插件执行框架。

### ComponentCatalog

| 字段 | 含义与约束 |
|---|---|
| `schemaVersion` | 当前结构版本为 1；不支持的版本不能自动应用，提示需升级应用，不猜测解析。 |
| `catalogRevision` | 单调递增的发布修订号；用于缓存、审计和启动快照，不能当组件版本。 |
| `modules` | `ModuleDescriptor` 列表，模块 ID 唯一、稳定；移除／改名须迁移持久引用，不复用旧 ID 表示不同组件。 |
| `compatibilityUnits` | 发布单元及成员 ID；`policy=matched-release` 要求配套升级，`independent` 允许成员分别更新但仍需符合所选 profile，`system-owned` 由系统管理。 |
| `profiles` | 明确锁定的兼容组合列表；未知组合保持未知，不自动把所有模块的最新版本拼起来。 |

### ModuleDescriptor

| 字段 | 含义与约束 |
|---|---|
| `id/name/kind/purpose` | 稳定身份、显示名称、类别及职责；类别为 `code/content/data/cache/system`，不决定是否执行。 |
| `stage` | `D1`–`D5` 或 `external`，说明落地责任／系统所有权，不是所有登记项的交付承诺。 |
| `implementationStatus` | `planned/implemented`；只有项目真实产品封装完成才能改为 implemented，运行覆盖仍另记。 |
| `deliveryMode` | 当前计划方式：`apk/runtime-bundle/licensed-user-import/steam-depot/local-import/generated-local/system`。 |
| `remotePolicy` | `disabled/eligible-after-implementation/external-owner`；eligible 只预留扩展资格，不表示应用已支持远程安装。 |
| `updateUnit` | 所属兼容升级单元；与 `compatibilityUnits` 一致。 |
| `compatibilityKeys` | 该模块需要检查的兼容维度，不是已满足的声明；具体值放在真实 release／profile 中。 |
| `licenseStatus` | 当前条目使用 `release-review-required`；每个实际载荷发布前独立核实许可、用户获取方式和来源。 |
| `releases` | 真实 `ModuleRelease` 列表；没有载荷时为空，不放占位版本。 |
| `extensions` | 可选的命名空间元数据，初始条目无需提供；未知可选字段不得触发执行或改变安全判断。新必需语义通过结构版本／必需能力声明表达，旧应用必须明确拒绝而不是忽略。 |

### ModuleRelease 与兼容组合

实际发布时，每个 release 必须记录不可变 `releaseId/version`、模块 ID、来源 commit／补丁与许可引用、支持平台／Android API／页大小／ELF ABI／PE ABI、宿主及服务接口版本、装载所需能力、依赖／冲突、安装方式及文件摘要。版本文本仅用于展示，选择依据为明确的 release ID 和兼容约束。

- 可再分发载荷记录获准的 HTTPS 地址、长度、SHA256、包格式和安装文件清单；地址可变不意味着载荷摘要可变。
- `apk` 记录 APK 内置版本或正常 APK 升级要求，不允许目录中的 URL 随意替换宿主代码。
- `licensed-user-import`／`steam-depot` 使用相应合法获取描述和内容校验；不把付费游戏或受限库改为项目 CDN 下载。
- `system` 仅记录兼容要求和已识别版本，不包含由应用刷写／替换系统 runtime 或驱动的安装步骤。
- 依赖使用明确 release ID／允许组合和接口范围；未知 ABI、来源、必需能力或依赖失败时说明原因，不通过猜测／降级绕过。

`RuntimeSet` 锁定 Wine／DXVK／Windows XR／Steam PE–Unix 桥的配套发布版本及 Unity／Mono、Android 宿主、GPU／XR 的兼容约束。`SteamBackendBundle` 锁定真实客户端、bootstrap 与服务适配器，向游戏暴露版本化私有协议。账号／下载协议实现独立登记；若其 Kotlin／Java 库仍编译在 APK 内，修复它仍需 APK 更新，不能因逻辑分层就宣称可下载替换。

兼容升级单元是逻辑上的配套提交，不要求所有文件合成一个下载包。特别是 Steam 服务可以同时包含合法用户准备的客户端与项目获准分发的适配器；不能为了统一更新把专有客户端或 Unity 文件搬到项目 CDN。

`profiles` 是维护者发布的明确兼容组合：`profileId/moduleReleases/runtimeSetId/hostApi/serviceApi/platformConstraints/requiredCapabilities`。维护已选组合即可，不要求先做通用依赖求解器或遍历所有版本组合。系统版本、驱动和用户输入还需安装时与本机核对；组合声明不代替 Space Pro 的实际行为证据。

`ResolutionSnapshot` 在准备实例／启动前生成并提交：`snapshotId/catalogRevision/profileId/runtimeSetId/moduleReleases/hostApi/serviceApi/platformIdentity/inputManifestRefs`；`moduleReleases` 固定具体版本和摘要，`platformIdentity` 固定实际 OS／ABI／驱动／XR 身份，输入引用保持私有。`GameInstance.resolutionSnapshotRef` 指向已准备快照，`LaunchRequest.resolutionSnapshotRef` 固定本次快照；日志按 runId 引用它。运行中不重新解析云端目录或追随“最新版”。

## 不能拆散的边界与性能约束

- Wine PE／Unix 两半、对应 thunk／结构布局成套重建和发布。DXVK、Wine Vulkan 与 XR interop 保持匹配，禁止用户单独换 DLL 破坏内部 ABI。
- Unity Player／Mono／UnityOpenXR 与正版游戏版本匹配；同为 ARM64 不等于同 ABI，Managed IL 不代表其 native 依赖兼容。
- Steam 客户端与 bootstrap／服务适配器匹配；尽量使用公开、版本化接口，内部符号依赖必须记录。开源协议库不能冒充真实客户端，PC 下载链接不能证明存在可合法使用的 ARM64/Bionic client。
- Android 宿主／JNI／Native Activity 等先随 APK 发布。外置代码须在开发中处理 Android linker namespace、执行／动态代码限制和发行政策；可远程下载的数据不代表 native／DEX 可任意执行。必须升级宿主时明确要求新 APK，不绕过系统限制。
- 同进程 XR／Vulkan 对象归属、唯一帧时间线、ARM64 游戏热路径仍按产品架构；组件边界不强制进程边界，不为可下载拆分引入逐帧 IPC、反射加载或额外图像复制。
- 云端解析、选型、下载和校验只在管理准备路径发生；游戏使用本地固定快照，更新不进入帧／输入／音频热路径。

## 云端发布、信任与更新生命周期

云端采用静态 HTTPS 清单与获准载荷入口；不需要先建自有账号后台。D4 实现发布入口和应用消费路径，云服务提供商、域名、发布权限、签名信任根与轮换策略在实际开发时经 Ask 选择。本轮仅定义可发布源文件，不部署云服务、不配置凭据。

1. 发布前核实真实来源／许可和兼容组合，生成清单及独立签名；应用用随 APK 信任的公钥验证清单，SHA256 只验证载荷完整性，不能替代清单来源认证。私钥不进 Git/APK。
2. 记录最高接受修订、受信任快照和密钥轮换；拒绝未授权旧目录重放。用户显式选择已保留旧组件是正常回退，不等于降低目录信任版本。密钥失窃或宿主接口变化可能要求 APK 更新，不能保证全部由远端自修复。
3. 新目录先解析到候选状态：不支持的结构不应用；未知模块或尚无安装能力的可选项仅展示不可用，不能执行；所选组合含未知必需能力则阻止激活。缺组件的原因区分需新版 APK、需用户输入、系统不兼容、无许可来源和普通下载失败。
4. 应用内置允许的安装／装载类型，不接受云端 shell 命令、任意 installer、任意脚本或任意文件写入路径。实际安装器处理路径穿越、越界链接、包格式与摘要／空间检查，不能写原始游戏、凭据、系统或其他实例。
5. 用户选择兼容组合后，独立 staging 获取／校验并准备实例，成功后原子提交快照和版本指针。中断不发布半完成状态；正在使用的文件／库／目录不替换。分开的兼容单元若相互依赖，也要按整个已选组合提交。
6. 切换在当前游戏和相关服务释放后生效；保留上一可用快照、工作实例和迁移前数据备份。组件回退与存档／prefix 迁移恢复分别处理，不盲目回退数据库或覆盖新存档。
7. 没有网络时使用本地已校验组件和快照，不因云目录不可达禁止本地准备／启动；游戏是否可离线仍由真实 Steam 缓存授权决定。服务端不再支持旧客户端时，本地回退不能承诺恢复登录。
8. 显示组件版本、来源、兼容范围、更新影响和需 APK／用户操作的原因。默认推荐兼容组合，不默认任意追新、不无声扩大下载／执行范围、不在游戏时切换。

未来新增模块可先 `remotePolicy=disabled`；允许云端获取时更新该条目、实现其受控安装能力并发布支持它的应用。纯数据格式仍被既有安装器支持的新增项可不改 APK；新 native ABI、安装类型、协议或必需能力不能靠多写一个 JSON 条目凭空支持。

## 各阶段开发责任

| 阶段 | 清单与组件任务如何进入产品实现 |
|---|---|
| D1 | 使用本地清单／锁定输入，落地实例、最小兼容组合与启动快照；先完成真实导入和引擎入口，不等待云服务。 |
| D2 | 登记账号／下载实现与真实 Steam 服务包，落实合法来源、配套适配及版本化服务接口；游戏／DLC 仍从正版来源获得。 |
| D3 | 把 XR、GPU、音频与输入身份绑定到实际快照；在游戏路径修正兼容问题，不为目录拆坏热路径。 |
| D4 | 发布真实签名云清单，完成获取、兼容选择、更新页面、提交／回退和离线快照；只发布已实现且获准分发的组件。 |
| D5 | 复用清单／安装／快照管理 BSIPA、mod 与谱面；先本地，是否在线获取及其来源按需求经 Ask 选择。 |

技术候选并非封闭列表；涉及这些接口／边界的实质选择按 [开发与验证方式](ARCHITECTURE.md#开发与验证方式)调研并使用 Ask。校验、选型和运行确认跟随正在实现的功能，不增加独立可行性阶段。
