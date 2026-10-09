cmake_minimum_required(VERSION 3.22.1)
project(xrprobe LANGUAGES CXX)

# org.khronos.openxr:openxr_loader_for_android:1.1.49 exposes this prefab target.
find_package(OpenXR REQUIRED CONFIG)
add_library(xrprobe SHARED xrprobe.cpp)
target_compile_features(xrprobe PRIVATE cxx_std_17)
target_compile_definitions(xrprobe PRIVATE XR_USE_PLATFORM_ANDROID XR_USE_GRAPHICS_API_VULKAN)
target_compile_options(xrprobe PRIVATE -Wall -Wextra -Wno-missing-field-initializers)
target_link_options(xrprobe PRIVATE "-Wl,-z,max-page-size=16384")
target_link_libraries(xrprobe PRIVATE OpenXR::openxr_loader android log vulkan)
