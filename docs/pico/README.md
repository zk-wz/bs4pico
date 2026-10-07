# Pico 迁移文档

最后更新：2026-10-07。本文档树随项目实现和实验结果持续更新。

原 `docs/` 中的上游资料保留在原位置；本目录记录 BS for Pico 的计划、实现和证据。项目当前仍是 Steam Frame/Linux 版本的 Fork，没有完成 Pico 移植。

| 目录 | 内容与入口 |
|---|---|
| `device-validation/` | [真机记录规范](device-validation/README.md)、[记录模板](device-validation/_TEMPLATE.md)。每次实际实验建立独立目录。 |
| `plans/` | [阶段规划](plans/ROADMAP.md)，后续阶段细化文件也放这里。 |
| `decisions/` | [技术决策](decisions/README.md)，记录选择、理由及重新评估条件。 |
| `research/` | [调研索引](research/README.md)，保留来源、事实及未验证推断。 |
| `build/` | [构建和缓存方案](build/README.md)，实际配置完成后补充复现命令。 |

记录采用 `YYYY-MM-DD-主题.md`；真机实验目录采用 `YYYY-MM-DD-序号-主题/`。文档使用相对链接，方便迁入 WSL。

短结论和必要的证据索引进入 Git；大型日志、trace、录屏和 APK 放在构建/实验产物位置，记录路径及校验值。不要提交登录凭据、授权票据、签名私钥或游戏资源。

计划不代表实现；构建成功不代表真机成功；其他设备或其他运行路径的实验不代表本项目已经通过验证。
