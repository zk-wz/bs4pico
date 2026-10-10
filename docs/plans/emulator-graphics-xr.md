# E4：模拟器 D3D11/Vulkan/OpenXR 图形桥

待实施验证计划；执行状态见 [项目状态](../STATUS.md)。用自有图形/OpenXR 客户端逐层隔离问题，不接游戏，不要求 Steam 登录或真机。

## 要回答的问题

Windows D3D11 图像能否经 DXVK/Wine 转成 Android native Vulkan 资源，并在同一条真实 XR 帧时间线上提交双眼？进程、设备、句柄和同步边界是否清楚且能测量？

当前 `prototypes/spatial-openxr/app/src/main/cpp/xrprobe.cpp` 只创建自己的 Vulkan device/session、场景和帧循环。它不是 Windows 图像接收器。上游 [DXVK/OpenXR 关系](../upstream/ARCHITECTURE.md#graphics-dxvk)提供 interop 参考，但 Linux SteamVR 的 Unix 后端不能直接当成 Android 后端。

## 前提与布局选择

- Native 预实验依赖 E1 可复现基线；Windows 实验依赖 E2 的匹配 ABI 执行和 Unix-call。主路径用模拟器 x64诊断构建，不混装现有 ARM64 DLL。
- 先记录真实 Vulkan physical device、必要扩展/特性、formats、sample count与 runtime 图形要求；模拟器 NVIDIA GPU 不能代表 Space Pro GPU。
- 检查匹配源码的 `wineopenxr` D3D11/DXVK interop、Wine Vulkan 句柄解包及 Windows/Unix 结构链；优先复用已有转换，而不是盲目重写完整 runtime。
- 在第一张 Windows XR图像前明确 Activity、Wine 子进程、loader、instance/session、VkDevice/queue 的所有者。单 APK≠同进程≠同 Vulkan device。
- 可共享兼容的同一 native device时优先受控 direct 或 GPU copy；跨进程/device则先证明实际 external memory/semaphore import/export 的支持和同步协议。不能跨设备直接使用 VkImage，也不预先承诺零复制。

## 分段实验

### G0：Native 图像交接预实验

在单一 native Vulkan device 中用自有 producer 生成每帧变化的色块/网格，写入或复制到 runtime swapchain；显示左右眼标签、方向轴、帧号和颜色。

确认 acquire/wait/render/release、layout、queue ownership、颜色空间和提交 pose/FOV。此段可不依赖 Wine先运行，但只证明 Native 交接，不能记为 D3D11或 Windows XR 通过。

### G1：Windows D3D11 → Android Vulkan

新增匹配 ABI 的自有 PE，创建 D3D11 device，以 DXVK 路径离屏绘制确定图案并 readback 检查。记录实际 DLL、Vulkan driver/physical device和资源格式，不接受 WineD3D 后备冒充 DXVK。

先 sampleCount=1，再独立验证 MSAA resolve 和 resolve 后继续加载目标的场景。首次正确性基线禁用上游有行为影响的 MSAA discard 优化，或使用未引入它的诊断构建，随后才做单变量对照；不能只因设备支持 Vulkan就认定锁定 DXVK 的必要特性满足。

### G2：最小 Windows OpenXR 客户端 → Android runtime

新增自有 D3D11/OpenXR 客户端，打通 instance/system/session、events、reference spaces、views、swapchains、actions及图像提交的实际必要子集。Android Activity/loader 初始化和应用暂停状态必须传播到桥，不把 Wine 子进程当作现成 Android Activity。

- Windows 调用唯一 `xrWaitFrame → xrBeginFrame → xrEndFrame` 链路；Android 桥转接这一链路，不同时运行原型独立帧循环。
- 同一 `predictedDisplayTime` 贯穿头部/双眼/action spaces与 layer 提交；核实 XrTime与 Wine/QPC 转换，不重新额外预测。
- 初始使用左右眼标记/网格/方块，验证眼序、FOV、米制比例、Y/深度方向、sRGB与线性颜色；不按“Unity”一词重复翻转 OpenXR坐标。
- 显示与模拟头部/右侧 trigger状态一起变化；不支持的左侧/profile能力单列。haptic API只验证契约，不报告真实振动。
- `xrGetInstanceProcAddr` 入口ABI、结构 `next` 链、句柄映射和对象寿命明确；未实现的扩展不宣告，客户端请求不支持能力时返回具体错误。

### G3：生命周期、故障与成本

对成功路径做至少五轮启动/Back 正常退出，并覆盖系统 Home 取消/确认、失焦/恢复。测试 `shouldRender=false` 时零层结束、图像等待失败/超时以及 session终止处理；能稳定触发的才记实测，注入失败只能标为受控错误路径，不冒充真实 runtime事件。

不得释放仍由 GPU写入的图像；不用每帧 `vkDeviceWaitIdle` 掩盖同步设计。记录 CPU 分段等待、实际 GPU timestamp（若可用）、copy 次数与字节、帧序号/预测时间和资源创建/释放计数。宿主日志或受控资源计数不等于验证层通过；启用可用的 validation layer时另记录配置与错误，缺少验证层则明确证据缺口。

## 通过、停止与证据

| 层 | 通过条件 | 不足以通过的现象 |
|---|---|---|
| G0 | Native双眼图案、帧序号、合法同步和正常退出正确 | 只显示原型方块 |
| G1 | 自有 Windows D3D11程序由 DXVK渲染，readback/resolve内容正确 | D3D device创建成功或仅有平面窗口 |
| G2 | Windows客户端实际驱动真实 runtime，头追踪双眼图像和动作正确，唯一时间线有证据 | Android宿主独立循环显示一张 Windows截图 |
| G3 | 所测生命周期正常交接，错误路径明确，资源无持续累积，成本可复现 | 强杀清理、平均 FPS或模拟器进程存在 |

缺少必要 Vulkan特性、无法共享/导入资源或 ABI映射不正确时停止该分支并保存失败。正确性先于性能；CPU readback只用于 G1内容校验，不作为实时双眼传输方案的完成条件。

交付匹配版本/ABI的最小客户端与桥、进程/资源归属说明、支持函数/扩展清单，以及遵循 [记录规范](../device-validation/AGENTS.md)的实验报告和证据索引。保留旧原型作为独立对照，新增代码位置在实现时确定。

G0–G3结果必须分别报告。即使全部模拟器通过，也只证明诊断 ABI上的桥协议，不证明 ARM64 Unity/游戏兼容、音画同步或 Space Pro持续性能；游戏接入还依赖真实 Steam和后续目标架构验证。
