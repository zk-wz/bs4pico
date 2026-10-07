# Vulkan、帧时序、坐标与输入

## Vulkan 图形绑定

先确认 runtime 支持 `XR_KHR_vulkan_enable2`。获取图形要求，再通过 `xrCreateVulkanInstanceKHR`、`xrGetVulkanGraphicsDevice2KHR`、`xrCreateVulkanDeviceKHR` 建立符合 runtime 要求的 Vulkan 对象，按适用路径绑定 `XrGraphicsBindingVulkan2KHR`。兼容已有设备的路径也必须核验 runtime 所需扩展/特性、physical device 和队列，不应任取 Vulkan device。

来源：[vulkan_enable2](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XR_KHR_vulkan_enable2.html)、[runtime 对应物理设备](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrGetVulkanGraphicsDevice2KHR.html)。

枚举 view configurations、各眼推荐尺寸/MSAA 和 swapchain 格式，选择游戏、DXVK、runtime 都能正确处理的组合。明确 sRGB/线性颜色、alpha、深度与 resolve 位置。OpenXR swapchain 的 VkImage 由 runtime 所有；应用只在规定的图像使用区间写入，不自行销毁或另绑其内存。

图像交接的工程优先级：

1. 能让 DXVK 在兼容的同一 native Vulkan device 上渲染到 XR image 时，尝试直接路径，并正确处理 Wine Vulkan 句柄解包。
2. 无法直接使用 XR image 时，先用受控 GPU copy/blit 证明画面与同步正确，再评估省掉复制的收益。
3. 跨 device/进程时，外部内存、semaphore 或 Android HardwareBuffer 需要双端支持及 import/export 能力；共享系统 Vulkan 驱动不等于可以共享任意句柄。

上面是待验证设计选择，不是 Pico 已提供“Windows 游戏直连”接口。记录 queue ownership、layout、GPU 完成与 runtime 读取的边界；不以每帧 `vkDeviceWaitIdle` 做最终同步，也不能为了减少等待提前释放仍被应用写入的 image。

## 帧的唯一时间线

保持 `xrWaitFrame → xrBeginFrame → xrEndFrame` 顺序，使用该帧返回的 `predictedDisplayTime` 定位 views/action spaces，并传到游戏更新和 layer 提交。桥接宿主与游戏共同维护一条真实 runtime 帧时间线；不能让两边各调用一轮 wait/begin/end。

`shouldRender=false` 时仍按帧协议结束，提交零层并跳过昂贵渲染。图像按 acquire/wait/render/release 交接；处理等待超时，不在尚未取得可写资格时使用图像。普通双眼视图提交 projection layer 和对应两眼 pose/FOV/subimage。来源：[xrWaitFrame](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrWaitFrame.html)、[xrReleaseSwapchainImage](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrReleaseSwapchainImage.html)。

重投影由 runtime/相应扩展契约控制。不要把补帧后的显示 FPS 当成游戏实际渲染率，也不要为赶帧对手柄 pose 再额外预测一次。

## 坐标与参考空间

OpenXR 使用右手坐标，+X 右、+Y 上、-Z 前；位置单位是米，方向是单位四元数。Unity 侧通常 +Z 前，但 Unity OpenXR 插件可能已经完成转换。先画出数据实际经过哪些转换层；**Android OpenXR 到 Windows OpenXR 的桥通常应保留 OpenXR 语义**，不能看到 Unity 就再翻一次 Z。

来源：[参考空间](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrReferenceSpaceType.html)、[pose](https://registry.khronos.org/OpenXR/specs/1.1/man/html/XrPosef.html)。

只有跨确实不同的坐标约定时才显式转换。工程例：若仅使用 `C=diag(1,1,-1)` 反射改变前向，位置 `p'=Cp`，旋转 `R'=CRC⁻¹`；相应四元数可取 `(-x,-y,z,w)`，须保持归一化且理解 q/-q 等价。不能只翻位置而遗漏旋转、线速度或角速度；后者是轴向量，反射下规则不同。此例不是所有插件通用配方。

STAGE 是地面中心且可缺失；LOCAL 并不自动提供地板高度。LOCAL_FLOOR 属 OpenXR 1.1 核心，旧版本可通过相应扩展提供。实际枚举可用空间，按游戏需要选地板基准；回退到 LOCAL 时明确保存/更新校准变换。

处理 `XrEventDataReferenceSpaceChangePending` 的生效时间、旧/新空间变换与 pose 有效性；同步头、左右手、双眼和地板。尊重 orientation/position valid/tracked flags，不把无效 pose 当成零坐标。投影还涉及 FOV、Vulkan/D3D 裁剪深度、Y 方向和纹理坐标，不能用同一个“翻 Z”同时解决全部问题。

先用方向箭头、地板网格和左右手颜色验证：头转/平移、手柄旋转、左右眼、米制比例、重置朝向后高度及剑柄偏移。不要直接用复杂歌曲判断坐标是否正确。

## Actions 与控制器

创建 action set、左右手 subaction paths 和 pose/button/trigger/haptic actions，suggest profile bindings 后 attach 到 session。每轮同步 action 状态，创建 action spaces，用本帧目标显示时间 locate；检查 `isActive` 与空间 flags。失去焦点时 actions 不可用。来源：[xrSyncActions](https://registry.khronos.org/OpenXR/specs/1.1/man/html/xrSyncActions.html)。

Pico 旧手柄的公开 profile 包括 `/interaction_profiles/bytedance/pico4_controller` 和 `/interaction_profiles/bytedance/pico_neo3_controller`；来源于 `XR_BD_controller_interaction`，已提升到 OpenXR 1.1 核心。是否需启用扩展取决于应用请求版本与 runtime；Space Pro 的 profile 以实际查询为准。来源：[Khronos profile 定义](https://registry.khronos.org/OpenXR/specs/1.1-khr/html/xrspec.html#semantic-paths).

grip pose 用于持物、aim pose 用于指向，不相互替代。剑柄校准是握姿到武器的额外变换，不是 world 坐标转换。左右手绑定分别检查；系统键可能保留给系统。profile 改变、控制器重连时重新确认当前绑定，振动使用 haptic action 并核验时长/幅度单位。

游戏原先建议其他设备 profile 时，桥应保留动作语义，补充真实 Pico 支持的 bindings；不能只伪报设备名。手部追踪或 gaze 可以补充菜单输入，不等同于已满足节奏光剑高速持柄判定。

## 时钟

`XrTime` 不是 Windows QPC 或普通 Unix 时间戳。Wine 桥需要保持转换契约；Android侧可核验 `XR_KHR_convert_timespec_time`。渲染 pose、游戏节拍和低延迟音频输出分别测量，再建立校准；OpenXR 本身不提供游戏音频设备或自动音画同步。
