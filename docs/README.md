# BS for Pico 文档

最后更新：2026-10-09。本文档树随项目实现和实验结果持续更新。

本目录记录 BS for Pico 的计划、实现和证据；原 bs-arm64 的架构、构建、安装与许可资料归档到 `upstream/`。游戏主体仍是 Steam Frame/Linux Fork，没有完成 Pico 移植；独立 Spatial/Native OpenXR 单 APK 原型已在 x86_64 模拟器运行，见 [实验结果](device-validation/2026-10-09-spatial-openxr/RESULT.md)，不是真机性能或游戏验证。

| 目录 | 内容与入口 |
|---|---|
| `device-validation/` | [验证记录规范](device-validation/README.md)、[模板](device-validation/_TEMPLATE.md)、[Spatial/OpenXR 模拟器实验](device-validation/2026-10-09-spatial-openxr/RESULT.md)。 |
| `plans/` | [阶段规划](plans/ROADMAP.md)，后续阶段细化文件也放这里。 |
| `decisions/` | [技术决策](decisions/README.md)，记录选择、理由及重新评估条件。 |
| `research/` | [调研索引](research/README.md)，保留来源、事实及未验证推断。 |
| `build/` | [APK 构建与部署](build/README.md)。机器路径、已验证环境和调用历史见 [Windows/WSL 记录](device-validation/WINDOWS_EMULATOR_VALIDATION.md)。 |
| `upstream/` | 上游 [架构](upstream/ARCHITECTURE.md)、[构建](upstream/BUILD.md)、[安装](upstream/INSTALL.md)、[发现](upstream/FINDINGS.md)、[问题](upstream/UPSTREAM.md)及[许可](upstream/LEGAL.md)，不作为 Pico 实测结果。 |

记录采用 `YYYY-MM-DD-主题.md`；真机实验目录采用 `YYYY-MM-DD-序号-主题/`。文档使用相对链接，方便迁入 WSL。

短结论和必要的证据索引进入 Git；大型日志、trace、录屏和 APK 放在构建/实验产物位置，记录路径及校验值。不要提交登录凭据、授权票据、签名私钥或游戏资源。

计划不代表实现；构建成功不代表真机成功；其他设备或其他运行路径的实验不代表本项目已经通过验证。

## 实现入口

| 入口 | 职责 |
|---|---|
| [`prototypes/spatial-openxr/`](../prototypes/spatial-openxr/) | 独立切换 APK：Spatial 管理窗口、C++ Vulkan OpenXR、私有数据和生命周期验证；不接入游戏。 |
| [`build.sh`](../build.sh)、[`versions.env`](../versions.env) | 上游 Windows ARM64 DLL 构建及输入锁定，不构建 APK。 |
| [`src/`](../src/)、[`patches/`](../patches/) | 兼容代码、生成器、二进制检查及锁定上游补丁；组件说明见上游架构。 |
| [`install/`](../install/)、[`tools/`](../tools/) | 上游游戏实例安装/恢复与提取、加载诊断工具。 |
| [interop skill](../.agents/skills/wsl-windows-interop/SKILL.md) | 通用 Windows 命令调用、UNC 交接和无抢焦点截图；原型只保留薄适配入口。 |

环境路径和实验历史以 `device-validation/` 中的独立记录为准；AGENTS.md 只维护约定。生成产物与私有输入按 `.gitignore` 隔离，不放入文档源。
