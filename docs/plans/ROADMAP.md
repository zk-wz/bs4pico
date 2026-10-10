# 阶段规划

最后更新：2026-10-09。随着阶段进展更新状态及关联证据。

| 阶段 | 状态 | 工作与完成条件 |
|---|---|---|
| 0. 建立项目入口 | 文档骨架已建立，WSL 工作目录已有用户提供的诊断证据 | 移除原 `.github/`，梳理源码和文档；WSL 为后续开发入口，Windows 副本不自动同步。 |
| 1. 可重复构建 | 原型 APK 子路径通过；上游 DLL/完整移植构建仍未验证 | WSL 系统 JDK 21、全局 SDK 35、现有 build-tools/NDK/CMake/Ninja + Wrapper 构建同 APK 两 ABI并由 Windows CLI 安装；入口 `prototypes/spatial-openxr/build-apk.sh`。Windows ARM64 DLL/安卓兼容组件的统一构建仍待做。 |
| 2. 同一 APK 的 Spatial/OpenXR 基线 | x86_64 模拟器基线通过；ARM64 Space Pro 待验证 | 真正 Spatial 管理窗口 ↔ C/C++ Vulkan OpenXR、五轮切换、私有文件、Back、Activity 重建/暂停恢复、人工 Home 确认退出/重开、头部移动和模拟右 trigger 已验证；直接 Native 对照可运行。见 [结果](../device-validation/2026-10-09-spatial-openxr/RESULT.md)。左控制器、Home 取消、重定位/摘戴/待机、进程死亡与持续性能仍待测。 |
| 3. ARM64 运行环境与 Steam | 未开始 | 验证安卓兼容环境可运行 Windows ARM64 程序，并连到真实 Steam 服务完成登录和游戏/DLC 授权；与阶段 2 可独立推进。 |
| 4. 游戏接入 | 未开始 | 原版游戏菜单及一首歌曲可玩，输入、坐标、声音和暂停恢复正确；先不依赖模组。 |
| 5. 性能优化 | 未开始 | 以固定回放比较帧时间、延迟和持续运行；评估图像共享、镜像关闭、着色器缓存及设备支持的注视点优化。 |
| 6. 打包与扩展 | 未开始 | 验证单 APK 安装、升级、正版游戏导入和授权流程；再扩展模组、可选 Steam 下载和自己的 CI。 |

没有真机证据不标记对应阶段通过。单 APK 是交付目标，游戏资源及不可直接再分发组件的准备方式需要在实现时明确。

用户已提供兼容版本 1.44.1 的唯一正版游戏副本，位置及不可变基线/备份流程见 [游戏输入与备份](../build/README.md#正版游戏输入与备份)。这仅补齐私有输入，不改变阶段 3/4 的未开始状态；尚未对游戏执行替换、启动或 Pico 验证。

高风险待验证项：纯 ARM64 Wine/Proton 安卓移植、真实 Steam 服务集成、D3D11/Vulkan 图像到安卓 OpenXR 的接入，以及无 root 条件下的持续性能。构建方案本身不能替代这些验证。

Activity 原型不依赖完整游戏。模拟器实测支持当前 Manifest 两种 Activity，但官方资料未保证 Activity 级 pvr 元数据/两 SDK 共存，必须真机复核。PICO 会把两类 Activity 放到不同任务；原型显式退休旧场景，旧 Native onDestroy 后才启动下一次 Native，避免 fullscreen 启动被系统拒绝。进入 VR 已关闭管理 Activity/Spatial 容器；进程仍有线程和内存保留，不能宣称零后台开销。x86_64 模拟器真实 OpenXR 双眼及直接入口通过，不代表 ARM64 真机功能和性能通过。
