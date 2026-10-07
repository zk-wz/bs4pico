# 官方来源、版本与 LLM 文本

核查日期：2026-10-07。下面是可追溯摘要与开发入口，不保存整站网页或完整厂商手册。

## PICO Native 主线

| 官方来源 | 本 skill 使用的事实或用途 |
|---|---|
| [SDK 概览](https://developer.picoxr.com/document/native/openxr-mobile-sdk-overview/) | 标准 OpenXR 基础与 Pico 私有扩展的分工。 |
| [快速入门](https://developer.picoxr.com/document/native/openxr-sdk-quickstart/) | 旧设备基线：OS 5.13+、JDK 17+；SDK Samples 包含 basicdemo 与 securemrdemo，示例采用 AGP 8.4.0。不是 Space Pro 的版本锁定表。 |
| [Loader 说明](https://developer.picoxr.com/document/native/openxr-loader/) | Android 初始化；标准 Khronos Loader 与能访问 Pico 私有扩展的 Pico Loader 的差别。 |
| [发布说明](https://developer.picoxr.com/document/native/release-notes/) | Native SDK 3.0.0 于 2025-04-22 发布；OS 5.13+；新增 Pico Loader/私有扩展。 |
| [支持扩展](https://developer.picoxr.com/document/native/about-extensions/) | 3.0.0 的公开/私有扩展和旧设备支持矩阵；不是目标机的实测清单。 |
| [Manifest 元数据](https://developer.picoxr.com/document/native/metadata-setting/) | VR 类型、OpenXR 标记、最低 Pico OS 元数据；版本键名有冲突，见下文。 |
| [合成图层](https://developer.picoxr.com/document/native/composition-layer/) | cube/cylinder/equirect/fisheye 等辅助显示能力。 |
| [图像增强](https://developer.picoxr.com/document/native/image-enhancement/) | 私有 layer 设置、超分辨率/锐化/颜色矩阵及设备限制。 |
| [动态分辨率](https://developer.picoxr.com/document/native/adaptive-resolution/) | `XR_PICO_adaptive_resolution`；需要渲染端实际采用返回尺寸。 |
| [眼动](https://developer.picoxr.com/document/native/eye-tracking/) | gaze pose 与私有详细眼数据是不同接口，具体硬件有额外限制。 |
| [安全边界](https://developer.picoxr.com/document/native/openxr-sdk-controller/) | 此 URL 的正文实际是 Boundary，不能按 URL 误认为控制器 action 教程。 |
| [2024 标准 Loader 公告](https://developer.picoxr.com/blog/muz6s63x/) | OS 5.9 起支持 Khronos 标准 Android Loader；是历史基础能力说明。 |
| [Native SDK 3.0 公告](https://developer.picoxr.com/blog/native-sdk-3/) | 2025 年私有扩展与 SecureMR 发布背景。 |
| [PICO 官方示例源码](https://github.com/picoxr/OpenXR_Demos) | Android 原生工程、输入和扩展示例；读取对应提交，不照搬旧 Manifest 权限/存储设置。 |

## 标准与构建来源

- [Khronos OpenXR 规范](https://registry.khronos.org/OpenXR/specs/1.1/html/xrspec.html)：接口语义、坐标、动作、帧、swapchain。详细正文按功能查对应 man page，避免只读扩展名称页。
- [OpenXR-SDK](https://github.com/KhronosGroup/OpenXR-SDK)、[SDK-Source](https://github.com/KhronosGroup/OpenXR-SDK-Source)：loader、构建方式与 hello_xr。Android loader Maven 坐标为 `org.khronos.openxr:openxr_loader_for_android`；版本需项目显式锁定。
- [hello_xr Manifest](https://github.com/KhronosGroup/OpenXR-SDK-Source/blob/main/src/tests/hello_xr/AndroidManifest.xml)：Android runtime broker 可见性、服务查询、权限与 immersive Activity 参考。此样例也有 GLES 声明，Vulkan 项目需调整。
- [Android 命令行构建](https://developer.android.com/build/building-cmdline)、[NDK CMake](https://developer.android.com/ndk/guides/cmake)：Gradle Wrapper 与 Android toolchain，不依赖必须打开 Android Studio。
- [Pico CLI 命令参考](https://developer.picoxr.com/document/pico-cli/command-reference/)：设备与 APK 工具；`spatialml` 提到 Native OpenXR 集成，不代表通用 Native 工程生成/knowledge 已完整覆盖。

## 已发现的文档矛盾

1. 2024 公告称不再单独提供 SDK；2025 的 3.0 发布说明重新提供私有扩展头文件和 Pico Loader。按功能与时间选择，基础标准开发可采用 Khronos，Pico 私有扩展另查当前包。
2. Metadata 页正文写 `pvr.sdk.version_code`，代码块却写 `pxr.sdk.version_code`。同页示例 `5120` 对应 OS 5.12；quickstart 又要求 5.13。不能直接复制成为项目配置：核对目标版本官方样例的**最终合并 Manifest**与 Space Pro 行为，记录所选键名的证据。
3. 扩展总表的支持勾选比具体眼动页面宽；硬件/权限/系统属性仍需核验。扩展能枚举不等于相关传感器可用。
4. 归档区的 Android Native XR / PXR 旧接口不是当前 OpenXR 接入方式。Unity/Unreal 包的教程和新 Spatial 教程也不能替代 Native C API。

## LLM 文本入口的核查

截至核查日，**没有在已检查的 Native 文档页面中发现可用的专属 `llms.txt` 或 Markdown 导出入口**。这是有限范围的核查结论，不代表全站或未来版本没有该功能。

| 实际检查的地址 | 结果 |
|---|---|
| `https://developer.picoxr.com/llms.txt` | HTTP 200，但 Content-Type 为 HTML，正文是首页，不是 LLM 索引。 |
| `https://developer.picoxr.com/llms-full.txt` | 同样返回首页 HTML。 |
| `https://developer-cn.picoxr.com/llms.txt` | 返回首页 HTML。 |
| `https://developer.picoxr.com/document/llms.txt` | HTTP 404。 |
| `https://developer.picoxr.com/document/native/llms.txt` | HTTP 404。 |
| `https://developer.picoxr.com/document/native/openxr-sdk-quickstart.md` | HTTP 404。 |
| `https://developer.picoxr.com/document/native/openxr-sdk-quickstart/llms.txt` | HTTP 404。 |

已读取普通 Native 网页正文；部分抓取器只显示导航，但网页自身包含正文数据，本次据此核对了 loader、版本、扩展、元数据、渲染和眼动内容。不能把导航页或 HTTP 200 当成文档正文已读取。

后续遇到官方 LLM 链接，先确认内容类型、标题、语言、SDK 版本与普通网页一致，再加入此表。按官方链接发现入口，避免大量猜路径；只保留相关摘要与来源。记录新查验日期，失效链接保留迁移说明。
