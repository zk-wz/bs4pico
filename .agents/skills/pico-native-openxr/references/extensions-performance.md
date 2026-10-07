# 扩展选择与持续性能

## 公共能力与 Pico 私有能力

[SDK 3.0 扩展表](https://developer.picoxr.com/document/native/about-extensions/) 是候选目录；**扩展枚举、system 属性、传感器权限、格式/特性查询和实际调用结果**共同决定是否可用。Space Pro 不在该旧表的设备列中。只向 Windows 游戏暴露桥实际转接或完整实现的子集。

| 需求 | 优先核查的接口/扩展 | 接入含义 |
|---|---|---|
| Vulkan | `XR_KHR_vulkan_enable2` | 必须匹配图形设备与交换链契约。 |
| 控制器 | 核心 actions/profile；旧版 `XR_BD_controller_interaction` | 优先基本持柄、按键与振动。 |
| 刷新率 | `XR_FB_display_refresh_rate` | 枚举支持值、请求并确认实际值；不能假定某个固定 Hz。 |
| CPU/GPU 性能提示 | `XR_EXT_performance_settings` | 给 runtime 提示，不等于锁频或绕过热管理。 |
| 固定注视点 | `XR_FB_foveation` 与其 configuration/Vulkan 依赖 | 针对 XR swapchain，必须验证 DXVK 渲染方式兼容。 |
| 眼动注视点 | `XR_META_foveation_eye_tracked` 等实际暴露能力 | 另查眼动硬件/权限、Vulkan 特性和 runtime 行为。 |
| 动态分辨率 | `XR_PICO_adaptive_resolution` | 私有路径；需要 render extent/subimage/投影相关设置协同。 |
| 超分/锐化/颜色 | `XR_PICO_layer_settings`、`XR_PICO_layer_color_matrix` | 私有、旧设备限制明显；不是 Space Pro 已验证能力。 |
| 深度/补帧 | composition depth、space warp/frame synthesis 等 | 游戏正确提供深度/运动数据才评估；不能由扩展名字推定可直接使用。 |

性能提示的标准来源：[XR_EXT_performance_settings](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_EXT_performance_settings.html)。其余 API 的依赖与完整语义从相应规范与选定 SDK 头文件核对，不能只启用本表名称。

## 先消除确定的开销

工程建议按实际测量瓶颈优化：避免 CPU 读回/视频编解码的主 VR 画面路径；减少跨进程往返、图像复制与额外全屏渲染；限制桌面镜像；缓存 pipeline/shader；避免逐帧分配、编译和全设备等待。保留同步正确性，不能用丢掉数据/生命周期处理换平均 FPS。

调低像素量不一定改善 CPU 限制。固定/眼动注视点也不意味着所有渲染成本都会下降。图像更改逐项验证 MSAA resolve、UI/文字、薄边缘、透明、后处理和双眼一致性；本仓库 DXVK 补丁应单独检查画面正确性。

[动态分辨率文档](https://developer.picoxr.com/document/native/adaptive-resolution/) 提供 `xrUpdateAdaptiveResolutionPICO` 建议尺寸。工程上必须有上下限及稳定策略，并把尺寸落实到真实渲染区间，不能仅修改提交矩形来声称 GPU 已少渲染；重建 swapchain 的成本另测。

[图像增强文档](https://developer.picoxr.com/document/native/image-enhancement/) 将相关私有层功能限定到旧设备/OS，不能套用为 Space Pro 的免费性能提升。先保留标准基线，再比较实际输出质量和 GPU 时间。

## 非必需能力的读取入口

- [眼动](https://developer.picoxr.com/document/native/eye-tracking/)：`XR_EXT_eye_gaze_interaction` 给 gaze pose；`XR_PICO_eye_tracker` 提供更详细的眼部数据。后者不代替 gaze 定位，表里有扩展也不能证明硬件支持。
- [合成图层](https://developer.picoxr.com/document/native/composition-layer/)：菜单/视频可用 quad 或支持的 cylinder/equirect 等；主游戏保持正确的立体 projection。辅助图层不能自动变成 OS 6 Spatial 场景对象。
- [安全边界](https://developer.picoxr.com/document/native/openxr-sdk-controller/)：私有 `XR_PICO_virtual_boundary` 是可选能力；游戏暂停/焦点处理不能依赖必须取得该扩展。
- `XR_EXT_hand_tracking`、`XR_FB_passthrough`、body/motion tracking、SecureMR 可从 [扩展表](https://developer.picoxr.com/document/native/about-extensions/) 进入各自页面。只有任务确实需要才集成；它们不是运行基础持柄 Beat Saber 的前提。

## 验证与证据

针对目标刷新率计算帧预算 `1000/Hz ms`。分别记录游戏 CPU、GPU、XR bridge/copy、compositor 可观测指标、真实渲染率、掉帧/重投影、控制器到画面延迟、音频延迟、温度及功耗条件。不要把多条并行 GPU 队列耗时简单相加当总帧时间。

对同一场景、谱面、分辨率、MSAA、刷新率和驱动版本比较基线与单项改变；报告分位数及热稳定后的表现，冷启动/首次 shader 编译另记。记录持续测试时长、设备 OS/固件、runtime 和驱动版本；未知数据写未知。

先在正确性调试构建启用可用的 OpenXR debug utils/Vulkan validation；性能采样另用验证层关闭的对应构建。系统允许的工具、计时和日志足够时无需 root；工具受设备限制时记录限制，不预设某款桌面 profiler 必定适用。
