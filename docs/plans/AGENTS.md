# 计划目录约定

- `ROADMAP.md` 汇总按产品成果执行的顺序；`ARCHITECTURE.md` 维护共同运行层、进程、数据与接口契约；`COMPONENTS.md` 维护组件／更新契约，`component-catalog.json` 是未来云清单的唯一条目源，涵盖非下载项与后续扩展。专题 Plan 链接共同契约，不重复定义清单结构或把目录存在写成已部署。
- 专题 Plan 写实现步骤、实际路径交付与必要验收，不重新建立独立前置可行性探针；候选保持开放，技术选型与 Ask 执行根约定。新增模块不自动扩充当前阶段范围，原版与后续 mod 的责任分开。
- 实施计划时查阅 [构建说明](../build/README.md) 和 [设备验证规范](../device-validation/AGENTS.md)。单次实验记录留在设备验证目录，大型产物使用新的 `private/validation/` 子目录，不把执行日志或证据填回计划。
