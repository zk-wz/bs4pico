# D1 · Bionic Wine 嵌入、组件输入与实施风险

查验：2026-10-11。本文记录源码事实与必要只读验证，不代表运行时已构建、已嵌入或真实 Unity 已执行。唯一执行计划仍为 [D1 游戏运行链](../plans/game-runtime.md)，已完成能力查 [STATUS](../STATUS.md)。Android/OpenXR 通用接入不在此重复，见 [Native OpenXR skill](../../.agents/skills/pico-native-openxr/SKILL.md)。

## 结论与采用边界

- 保持已批准基线：GameNative Bionic ARM64 Wine、同 APK `:game` 内游戏与 XR 同 native 进程、系统 Vulkan、纯 Windows ARM64 Player／Mono／DXVK。当前证据**不足以要求改成子进程游戏**，也不足以证明同进程已可运行。
- Wine 源码确有 Android JNI 初始化路径，但 GameNative 的实际构建关闭 Android driver、应用使用独立进程。现有入口不是本产品已实现的可返回宿主；普通 `dlopen`、加 JNI wrapper 或 `-ffixed-x18` 都不能代替线程／ABI／信号／退出适配。
- 窗口与音频不是可全部延后到 D3 的附属物。需用户决定其公开实现的复用边界；推荐原生窗口方向，但音频对应源码／许可尚未核齐，不能发布“已就绪依赖”或虚构 RuntimeSet。
- 本次没有正式 runtime 编辑、构建、设备部署、游戏启动或原件写入。公开关键源码下载留在临时研究目录；不将其机器路径作为产品依赖。

## 固定源码实证

Wine 研究基线为 [`77eed5501e077f5f0422d063b171a3a4491f52a6`](https://github.com/GameNative/proton-wine/tree/77eed5501e077f5f0422d063b171a3a4491f52a6)；查询到的当前官方分支为 [`f323a4d3eb4387bab684710ca1b38251ca7854e1`](https://github.com/GameNative/proton-wine/tree/f323a4d3eb4387bab684710ca1b38251ca7854e1)。**查验版本不是已采用的新构建锁**。源码按 symbol 定位，不用网页提取行号生成 `#L` 锚点。

| 边界 | 已读取源码事实 | 实施含义／待验证项 |
|---|---|---|
| 真实初始化 | [loader/main.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/loader/main.c)调 `__wine_main`；[ntdll loader.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/ntdll/unix/loader.c)有 `JNI_OnLoad → wine_init_jni → start_main_thread`，建立 TEB／服务／栈并载系统PE；[WineActivity.java](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/wineandroid.drv/WineActivity.java)真实加载／调用 | 复用真路径并适配类名、VM／引用、错误／teardown；`__wine_main`可re-exec，不是可重入库API；JNI的`error`数组未见填充，不能信任其失败回报 |
| TLS 与 x18 | [thread.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/ntdll/unix/thread.c)用pthread TLS取TEB；[signal_arm64.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/ntdll/unix/signal_arm64.c)手写汇编把TEB放入／读取x18 | 不能泛称覆盖Bionic thread pointer；[Android保留x18](https://developer.android.com/ndk/guides/abis#arm64-v8a)。每个PE↔Bionic／JNI／驱动及异步信号边界须保存恢复；编译flag不修复PE／汇编 |
| 信号与 ART | Wine `signal_init_process`安装进程级handler，部分路径直接取Wine TEB；[固定ART sigchain](https://android.googlesource.com/platform/art/+/6484611fd45e69db9f33f98bfd6864014b030ecf/sigchainlib/sigchain.cc) `SignalChain::Handler`先special handler，`__sigaction`为claimed signal保存用户action | 非Wine线程须保留ART／原handler及mask／alt-stack。此ART源码不是目标OS实测；不依赖私有注册接口，不在handler做JNI／malloc／不安全锁 |
| 退出与服务 | thread.c `abort_process`用`_exit`，最后线程可走`process_exit_wrapper`；[process.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/ntdll/unix/process.c) `NtTerminateProcess`调用相应路径。loader.c仍启动wineserver／子Windows进程 | 正常退出须线程／窗口／音频／XR清理与回报，不是libc拦截／跨活跃线程longjmp。独立wineserver服务须合法ELF位置、UID／prefix／socket，不等于游戏改Unix子进程 |
| 窗口／WSI | [driver Makefile](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/wineandroid.drv/Makefile.in)与 [init.c](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/dlls/wineandroid.drv/init.c)有窗口／GDI／OpenGL、私有gralloc；`android_drv_funcs`无Vulkan接口，[当前init.c](https://github.com/GameNative/proton-wine/blob/f323a4d3eb4387bab684710ca1b38251ca7854e1/dlls/wineandroid.drv/init.c)仍如此 | 需真实HWND→ANativeWindow→Android Vulkan WSI及公开NDK替代，不能仅开`--with-vulkan`／用假窗口／取消Unity窗口 |

[JNI 官方线程／引用约束](https://developer.android.com/ndk/guides/jni-tips#threads)同样适用：JNIEnv不跨线程，native attach线程退出前 detach，对象引用有明确寿命。低频宿主事件可由持有 Android ABI状态的线程转发，不让每个 Wine worker承担一般 Java 回调。

### 纯 ARM64 与构建配套

[基线 build-step-arm64ec.sh](https://github.com/GameNative/proton-wine/blob/77eed5501e077f5f0422d063b171a3a4491f52a6/build-scripts/build-step-arm64ec.sh)选择 `arm64ec,aarch64,i386`、关闭 `wineandroid_drv`、使用NDK27／API28、bylaws MinGW和Termux依赖；configure后另加Android patch series。**raw树不是最终补丁树，aarch64构建机不证明纯ARM64载荷。** [当前脚本](https://github.com/GameNative/proton-wine/blob/f323a4d3eb4387bab684710ca1b38251ca7854e1/build-scripts/build-step-arm64ec.sh)及 [CI](https://github.com/GameNative/proton-wine/blob/f323a4d3eb4387bab684710ca1b38251ca7854e1/.github/workflows/build-proton.yml)仍是ARM64EC组合，依赖外部prefixPack；不直接执行其环境安装／系统清理。

D1须实际构建纯ARM64 Bionic及builtins，核ELF依赖、PE imports、页大小、patch顺序／摘要／许可、匹配PE–Unix协议。区分ARM64 `0xaa64`、ARM64EC `0xa641`与ARM64X实际入口；现有Frame `WINE_COMMIT`／仅三个私有CRT的`wine-runtime`目标不等于Android运行时。`lsteamclient/wineopenxr`成套重建，EH／CRT与FPCR／FPSR修复在源码层核对。

### 音频、许可与 Android执行限制

[GameNative固定源码](https://github.com/utkarshdalal/GameNative/tree/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a)的launcher配置DISPLAY／ALSA、Java XServer提供socket；`PulseAudioComponent`执行APK内Pulse服务、加载`module-aaudio-sink`，`alsa_client.c`调用AAudio。**未核齐对应ALSA插件／Pulse模块的源码、版本、许可**；不是可直接采用的合法音频依赖。

[GameNative许可](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/LICENSE)为GPLv3，Wine为LGPL2.1；[第三方声明](https://github.com/utkarshdalal/GameNative/blob/1fbd2221da0ec90c4bcddf607c24fa338e4abe2a/THIRD_PARTY_NOTICES)列redirect、Steam bootstrap、KGSL shim及部分helpers专有／未提供源码，不能直接复制补缺。系统Vulkan尚无证据必需KGSL shim，Steam服务缺项属于D2。

[API29限制](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission)针对直接execve可写app home文件；ELF服务须合法APK载荷位置，不以linker64绕过。PE映射不同于execve；execmem／execmod／W^X／Mono JIT仍须目标验证，不先断言禁止或允许。

## 输入与必要只读验证

本轮输入工作流核官方元数据／原版输入、一次下载官方插件包并做 PE／摘要／字节对比；未给游戏打补丁或运行。官方 [Unity release API](https://services.api.unity.com/unity/editor/release/v1/releases?limit=1&version=6000.0.40f1)确认 changeset `157d81624ddf`，`windows-mono`模块 [canonical URL](https://download.unity3d.com/download_unity/157d81624ddf/MacEditorTargetInstaller/UnitySetup-Windows-Mono-Support-for-Editor-6000.0.40f1.pkg)与现有安装脚本一致，声明大小 `512962929` B、MD5 `db2d4aefabd56cebb753bc9b56c199e1`。本机 follow-HEAD因 geo跳转到 UnityChina后**最终404，Player／Mono未取得**；仅此 URL／路由结果，不推断站点全局缺失，也不是已下载包的校验值。

| 实际验证对象 | 来源／结果 | 摘要与强度 |
|---|---|---|
| `com.unity.xr.openxr 1.14.3`官方 tgz | [官方 registry](https://packages.unity.com/com.unity.xr.openxr)，`11687016` B；sha1与 dist.shasum一致 | SHA1 `3903c1059bcf18e6a894f8aa2076f2a8267716bd`；SHA256 `abf0f6e5d7e2d16b1dfa6394e9f7fd87dd5e5768f0e0c2f7e5d43e2d62907b7b` |
| `Runtime/universalwindows/arm64/UnityOpenXR.dll` | machine `0xaa64`，FileVersion `1.14.3.0`，`537600` B；UWP／WindowsStore形态 | SHA256 `30c29d0fc34b3a7143dbcec0bf34775ee8a00fd160bf203bba2dd1b6ee6a9b70`；未打补丁／未安装／未运行，需已有 desktop适配 |
| `Runtime/windows/x64/UnityOpenXR.dll`与用户1.44.1自带插件 | desktop x64，`831488` B，实际字节比较相同；包内无 desktop ARM64变体 | 两者 SHA256 `de72c50d3b99ef05482d4ea658acad2faa236b24c8398773bddc4f2c3c65448e`；证明版本对应，不证明 ARM64插件已工作 |
| 正版引擎／Mono输入与备份 | 原有 exe／UnityPlayer／Mono及必经 native plugins为 x64；未建立本轮源摘要基线／独立校验备份 | 需合法同版本 ARM64 Player／Mono、全量源清单与恢复核对；工作副本不能当备份，不用硬链接 |
| 原型 APK构建输入 | 已发现 JDK21、SDK35、NDK r30、Gradle8.13、CMake／Ninja及历史产物 | 仅 APK输入；没有完整 Bionic／PE工具链或 runtime构建通过证据。当前 Wine／MinGW依赖未准备，不复刻上游整套环境 |

Player／Mono缺失阻断真实Unity验收，不阻止导入／runtime推进，不能归为D2／D3失败。可用合法同版本离线模块；不擅改网络／地区／安全策略或引擎版本。查询／下载／工具版本检查不是设备运行证据。

## 待用户决定与重开条件

| 选项 | 工作边界与风险 | 推荐／前提 |
|---|---|---|
| A 原生窗口／Vulkan WSI +公开 ALSA→AAudio链 | 适配 WineAndroid窗口语义，替换私有 gralloc依赖，补 WSI；复用音频需对应插件源码、版本、许可与构建锁 | 推荐方向；**音频依赖未核齐，不是已可用选择**。若来源不成立，带证据再选，不无声降级 |
| B 公开 GameNative XServer／X11／ALSA复用 | 复用真实窗口／socket／音频服务器，大幅增加 APK宿主接线、Bionic依赖、GPL复用及维护边界 | 用户明确接受边界才实施；不复制闭源 redirect或其跨进程 GLES XR |
| C 原生窗口／Vulkan WSI +自有 Wine AAudio驱动 | 窗口同A，直接完整实现 Windows音频 endpoint／format／clock／buffer／pause／释放 | 减少音频服务依赖但新增驱动可靠性负担；不能以空壳AAudio／假设备代替 |

三项均保留同进程纯ARM64／系统Vulkan。实际产品装载若证明x18／TLS／ART／teardown无法可靠适配，再带调用链证据重开架构Ask。最小环境方案优先现有NDK／host工具；缺MinGW则独立取得可信包、仅设构建子进程路径；不默认安装旧NDK／Termux全家桶／i386 multiarch。版本／后端待定，不预写release／profile／RuntimeSet。

## 关键源码证据校验值

以下为本轮下载的原始字节 SHA256；版本／文件名与上文固定源码一致。大型源码／私有输入不进 Git，不把临时路径或机器配置写入 AGENTS。

| 固定提交与文件 | SHA256 |
|---|---|
| `77eed550…` `dlls/ntdll/unix/loader.c` | `f2e50931a692529189eeaaf1f9208ad18cbc8be39fde8d82cbb06e349b11c8cc` |
| `77eed550…` `dlls/ntdll/unix/thread.c` | `8a5a82ddeea3b647197128345f815736d45f3db90bbfe2608288dcb551d52745` |
| `77eed550…` `dlls/ntdll/unix/signal_arm64.c` | `5b9ac27a19117ddcc1f1fd31d7ed09b6445ab5fc365a5d4b1564ae09de61a968` |
| `77eed550…` `dlls/wineandroid.drv/init.c` | `322c4497d2b312f42ef3d71dac341222103ed6ee80600199da20cc474d29e954` |
| `77eed550…` `build-scripts/build-step-arm64ec.sh` | `bb36cea70bd8de8382b71a43bc76cdf2749f8132352b6302ab86a308d29cb7cb` |
| `f323a4d3…` `dlls/wineandroid.drv/init.c` | `e3e4febe6f55928500e38f15786eb53a375fa9a77033e2a820791c805f4cc31b` |
| ART `6484611f…` `sigchainlib/sigchain.cc?format=TEXT` | `7fa60f5e2f49b3d8ca168c9089301a15099c83f830d5b52d2808a31019be3d84`（Gitiles base64响应；已解码阅读，不是解码源码摘要） |
