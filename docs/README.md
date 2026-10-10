# BS for Pico 文档

当前进度见 [项目状态](STATUS.md)。本页只提供文档与实现导航；文档维护约定见 [AGENTS.md](AGENTS.md)，局部规则见对应目录。

| 目录 | 概况与入口 |
|---|---|
| `plans/` | [阶段目标与计划依赖](plans/ROADMAP.md)。 |
| `build/` | [APK 构建、部署与正版输入保护](build/README.md)。 |
| `device-validation/` | [设备与模拟器实验索引](device-validation/README.md)，含环境记录和复现证据。 |
| `decisions/` | [技术选择与重新评估条件](decisions/README.md)。 |
| `research/` | [调研资料与待验证问题](research/README.md)。 |
| `upstream/` | bs-arm64 原始[架构](upstream/ARCHITECTURE.md)、[构建](upstream/BUILD.md)、[安装](upstream/INSTALL.md)、[发现](upstream/FINDINGS.md)、[问题](upstream/UPSTREAM.md)及[许可](upstream/LEGAL.md)。不是 Pico 实测结论。 |

## 实现入口

| 入口 | 职责 |
|---|---|
| [`prototypes/spatial-openxr/`](../prototypes/spatial-openxr/) | 独立 Spatial / Native OpenXR 切换原型；局部入口与边界见其 [AGENTS.md](../prototypes/spatial-openxr/AGENTS.md)。 |
| [`build.sh`](../build.sh)、[`versions.env`](../versions.env) | 上游 Windows ARM64 DLL 构建及输入锁定，不构建 APK。 |
| [`src/`](../src/)、[`patches/`](../patches/) | 上游兼容组件与补丁，细节见[上游架构](upstream/ARCHITECTURE.md)。 |
| [`install/`](../install/)、[`tools/`](../tools/) | 上游游戏实例安装/恢复与提取、加载诊断工具。 |
| [Native OpenXR](../.agents/skills/pico-native-openxr/SKILL.md)、[interop](../.agents/skills/wsl-windows-interop/SKILL.md) | OpenXR 接入与跨系统工具，按任务查阅。 |
| [android-cli](../.agents/skills/android-cli/SKILL.md)、[testing-setup](../.agents/skills/testing-setup/SKILL.md) | 用户安装的 Android 工具与测试资料。 |

两份 Android skills 来自官方 [android/skills](https://github.com/android/skills)（[Android CLI](https://github.com/android/skills/tree/main/devtools/android-cli)、[testing-setup](https://github.com/android/skills/tree/main/testing/testing-setup)），各目录附上游 Apache-2.0 `LICENSE.txt`；正文与引用保留安装内容。收录不代表已安装工具、引入测试依赖或验证 Windows 设备连接。
