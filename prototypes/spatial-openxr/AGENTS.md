# Spatial / Native OpenXR 原型约定

本目录是独立切换探针，不是游戏宿主；仅使用自有测试场景，不引入游戏、账号或第三方 Windows 运行时。

- `app/src/main/java/` 承担 Spatial 管理界面、场景所有权、Activity 生命周期和私有数据；`app/src/main/cpp/` 承担 Native Vulkan / OpenXR。切换保持管理场景与 Native 会话互斥，不能只隐藏仍在渲染的管理界面。
- `build-apk.sh` 是 APK 构建入口，ABI 选择、部署和复现命令见 [构建说明](../../docs/build/README.md)；版本以 Gradle/CMake 配置为准，不在本文件复制。
- `windows-tools.sh`、`capture-emulator.py` 是 interop skill 的薄入口；通用调用/窗口捕获实现放回该 skill，机器路径仍使用忽略的本地配置。
- `verify-emulator.py` 是模拟器回归入口，运行会停止/重启本调试应用；实验使用新的输出目录。生命周期与显示证据按 [验证约定](../../docs/device-validation/AGENTS.md)归档，不以脚本成功替代未覆盖的人工或真机场景。
