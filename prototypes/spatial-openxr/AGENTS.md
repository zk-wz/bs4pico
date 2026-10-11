# Spatial / Native OpenXR 宿主约定

当前实现仍是独立切换原型，尚未包含游戏运行链。后续按 [产品架构](../../docs/plans/ARCHITECTURE.md)和 [开发路线](../../docs/plans/ROADMAP.md)在本目录演进同一产品 APK，允许集成真实游戏宿主、账号与获许可运行时；不另建一套前置探针或第二个 APK。原始游戏副本保持不可变，实际执行前遵循根备份约定；游戏、凭据和受限二进制不提交或默认打包。

- `app/src/main/java/` 承担 Spatial 管理界面、场景所有权、Activity 生命周期和私有数据；`app/src/main/cpp/` 承担 Native Vulkan / OpenXR。切换保持管理场景与 Native 会话互斥，不能只隐藏仍在渲染的管理界面。
- `build-apk.sh` 是 APK 构建入口，ABI 选择、部署和复现命令见 [构建说明](../../docs/build/README.md)；版本以 Gradle/CMake 配置为准，不在本文件复制。
- `windows-tools.sh`、`capture-emulator.py` 是 interop skill 的薄入口；通用调用/窗口捕获实现放回该 skill，机器路径仍使用忽略的本地配置。
- `verify-emulator.py` 保留为已有原型的显式回归工具，不是每次产品开发的默认前置步骤；运行会停止/重启调试应用。实际功能只确认本次受影响路径，必要证据按 [验证约定](../../docs/device-validation/AGENTS.md)归档。无运行需要不开模拟器，需要设备时后台 CLI、不自动截图或抢焦点。
