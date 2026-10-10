# 技术决策

当前工作方向为 Wine/Proton 组件的安卓适配、DXVK 和 Native OpenXR，构建放在 WSL。同一 APK 内用 Spatial SDK 提供管理界面、Native OpenXR 提供 VR 渲染；不把游戏画面绕经 Spatial 二次渲染。两 Activity方案已有 [模拟器实验依据](../device-validation/2026-10-09-spatial-openxr/RESULT.md)，目标机兼容与后台成本仍未确定；若不满足要求，重新评估管理界面的实现。具体实现/验证进度统一见 [项目状态](../STATUS.md)。

下一步先做 [模拟器前期验证](../plans/ROADMAP.md#当前实施批次模拟器前期验证)：运行环境和真实 Steam后端尚未选定；模拟器 x64诊断构建不改变纯 Windows ARM64产品目标。单 APK不预设同进程/同 Vulkan device，图形资源布局按候选运行时及 E4证据决定。

分发建议为宿主 APK 加用户正版游戏导入，后续再评估真实 Steam 登录下载。二者最终使用同一应用私有目录；下载成功不代表运行时 Steam 初始化和授权验证已经解决。

重要选择另建 `YYYY-MM-DD-主题.md`，简短记录：问题、候选方案、当前选择、依据、仍未验证的假设、重新评估条件，以及相关实验链接。状态可为“建议”“采用”“替代”。

当前约束：Pico Space Pro、设备无 root、单 APK、真实 Steam 授权、高性能。约束和工作方向改变时，同步更新根目录 `AGENTS.md`、构建说明及阶段规划。
