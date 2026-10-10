# 阶段规划

本文件概述阶段目标、完成条件和计划依赖。当前实现/验证状态见 [项目状态](../STATUS.md)；目录维护见 [本目录约定](AGENTS.md)。

## 产品阶段

| 阶段 | 目标与完成条件 | 相关入口与边界 |
|---|---|---|
| 0. 建立项目入口 | 源码、约定、文档和私有输入分离；当前 WSL checkout 是开发入口 | [文档索引](../README.md)；Windows 副本不自动同步 |
| 1. 可重复构建 | APK、Windows 客体组件及 Android 运行时有匹配版本/ABI、可复现输入和构建入口 | [构建说明](../build/README.md)、E2；原型 APK路径与上游 `build.sh` 是不同构建链 |
| 2. 同 APK Spatial/OpenXR 基线 | 场景互斥、管理渲染停止、XR/session释放、输入、数据、Back/Home及恢复正确 | [既有模拟器证据](../device-validation/2026-10-09-spatial-openxr/RESULT.md)、E1；产品验收仍须 Space Pro，真机计划另行讨论 |
| 3. ARM64 运行环境与 Steam | Android应用沙箱中运行纯 Windows ARM64程序，并接通真实服务、账号与游戏/DLC授权 | E2/E3仅先验证模拟器诊断路径；x64/ARM翻译结果不满足 ARM64完成条件 |
| 4. 游戏接入 | Windows图形/XR桥成立，原版游戏菜单及一首歌曲可玩，输入、坐标、声音、暂停恢复与退出正确 | E4先用自有最小客户端；完整游戏仍依赖阶段3及目标架构验证，不依赖模组 |
| 5. 性能优化 | 固定回放/配置比较帧时间、输入延迟、音画同步和持续表现；再评估复制、镜像、缓存及注视点 | 早期小探针就记录等待/图形成本；模拟器或上游结果不代表 Space Pro性能 |
| 6. 打包与扩展 | 单 APK安装/升级、合法运行时准备、正版游戏导入和授权流程可靠；再扩展模组、可选下载和 CI | 游戏资源独立更新；APK只包含自有及可再分发组件 |

单 APK是交付目标，不预设单进程或可直接共享 Vulkan device。Android ELF、Windows ARM64 PE、ARM64EC必须分别核实；可选扩展不支持时保留基础路径，必要能力缺失时报告阻塞，不伪造能力或授权。

## 当前实施批次：模拟器前期验证

本批次不安排真机，不运行或改写正版游戏。计划已编写不表示探针已实现；进度见 [STATUS](../STATUS.md#当前开发队列仅模拟器前期验证)。

| 编号 | 计划与交付 | 依赖 |
|---|---|---|
| E1 | [宿主/XR回归与诊断](emulator-host-xr.md)：旧基线、Home取消、场景交接压力、数据恢复、模拟输入和受限成本观察 | 现有原型；先复现，再实现新增检查 |
| E2 | [Windows运行环境与ABI探针](emulator-windows-runtime.md)：候选审计，应用UID中的 PE/DLL/线程/异常/Unix-call与退出 | 可与 E1并行；先确认候选 ELF和 PE实际架构 |
| E3 | [真实Steam服务探针](emulator-steam-service.md)：后端来源/许可、完整初始化、只读授权与回调、服务缺失/恢复 | 调研可并行；Windows正向链路依赖 E2和适用的真实后端 |
| E4 | [D3D11/Vulkan/OpenXR图形桥](emulator-graphics-xr.md)：Native交接、DXVK离屏正确性、Windows XR双眼、生命周期与成本 | Native预实验依赖 E1；Windows部分依赖 E2，无需等待 Steam |

建议顺序：E1与 E2优先，E3后端审计并行；E2具备图形前提后进入 E4。完整游戏工作需真实授权及目标架构路径成立，不因模拟器图形成功提前进入。

### 模拟器证据门禁

- 当前镜像为 x86_64。E2–E4可采用 Windows x64自有客户端作为诊断链，不能混装现有 ARM64 DLL，也不能标记纯 Windows ARM64通过。
- ARM ABI列表或一段 Android ARM库可加载，不证明 Wine子进程、ARM64 PE/JIT、Steam或Vulkan thunk都可运行；任何翻译路径单独记录。
- 真正模拟器 XR projection不等于 Windows桥已接入；Native预实验、Windows离屏绘制和Windows双眼提交分别验收。
- 无适用运行时或真实Steam后端时，记录具体前提不足及已测的负向结果，不用 mock/远端PC服务冒充本地闭环。该候选阻塞不否定其余独立探针。
