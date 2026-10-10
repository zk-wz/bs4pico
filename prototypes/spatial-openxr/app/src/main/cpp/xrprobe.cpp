#include <jni.h>
#include <android/log.h>
#include <vulkan/vulkan.h>
#include <openxr/openxr.h>
#include <openxr/openxr_platform.h>
#include "scene_spirv.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <inttypes.h>
#include <limits>
#include <stdexcept>
#include <string>
#include <thread>
#include <unistd.h>
#include <vector>

namespace {
constexpr char kTag[] = "BS4PicoXR";
constexpr XrViewConfigurationType kStereo = XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
std::atomic<uint64_t> nextWorkerId{1};
void vkCheck(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) {
        char message[192];
        std::snprintf(message, sizeof(message), "%s: VkResult=%d", operation, result);
        throw std::runtime_error(message);
    }
}
XrPosef identityPose() { return {{0, 0, 0, 1}, {0, 0, 0}}; }
struct Matrix { float m[16]{}; };
Matrix multiply(const Matrix& a, const Matrix& b) {
    Matrix result;
    for (int col = 0; col != 4; ++col)
        for (int row = 0; row != 4; ++row)
            for (int k = 0; k != 4; ++k)
                result.m[col * 4 + row] += a.m[k * 4 + row] * b.m[col * 4 + k];
    return result;
}
Matrix poseMatrix(const XrPosef& pose) {
    const auto& q = pose.orientation;
    Matrix result;
    result.m[0] = 1 - 2 * (q.y * q.y + q.z * q.z);
    result.m[1] = 2 * (q.x * q.y + q.z * q.w);
    result.m[2] = 2 * (q.x * q.z - q.y * q.w);
    result.m[4] = 2 * (q.x * q.y - q.z * q.w);
    result.m[5] = 1 - 2 * (q.x * q.x + q.z * q.z);
    result.m[6] = 2 * (q.y * q.z + q.x * q.w);
    result.m[8] = 2 * (q.x * q.z + q.y * q.w);
    result.m[9] = 2 * (q.y * q.z - q.x * q.w);
    result.m[10] = 1 - 2 * (q.x * q.x + q.y * q.y);
    result.m[12] = pose.position.x;
    result.m[13] = pose.position.y;
    result.m[14] = pose.position.z;
    result.m[15] = 1;
    return result;
}
constexpr Matrix localScaleOffset(float sx, float sy, float sz, float x, float y, float z) {
    return {{sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, sz, 0, x, y, z, 1}};
}
struct DrawRange { uint32_t firstVertex{}, count{}; };
constexpr Matrix kGripLocal = localScaleOffset(0.035f, 0.035f, 0.07f, 0, 0, 0);
// Unit boxes span [-1,+1]. Shaft runs from local z=0 to z=-0.30m.
// Two fixed 45-degree box arms end at z=-0.35m; no per-frame trigonometry.
constexpr std::array<Matrix, 3> kAimLocal{{
    localScaleOffset(0.008f, 0.008f, 0.15f, 0, 0, -0.15f),
    {{0.005f, 0, -0.005f, 0, 0, 0.008f, 0, 0, 0.025f, 0, 0.025f, 0, 0.025f, 0, -0.32f, 1}},
    {{0.005f, 0,  0.005f, 0, 0, 0.008f, 0, 0, -0.025f, 0, 0.025f, 0, -0.025f, 0, -0.32f, 1}}
}};
static_assert(sizeof(Matrix) == 64, "Vertex push constants must remain 64 bytes");
Matrix viewProjection(const XrView& view) {
    const auto& q = view.pose.orientation;
    // Inverse rigid pose, column-major. OpenXR is right-handed, -Z forward.
    Matrix inverse;
    inverse.m[0] = 1 - 2 * (q.y * q.y + q.z * q.z);
    inverse.m[1] = 2 * (q.x * q.y - q.z * q.w);
    inverse.m[2] = 2 * (q.x * q.z + q.y * q.w);
    inverse.m[4] = 2 * (q.x * q.y + q.z * q.w);
    inverse.m[5] = 1 - 2 * (q.x * q.x + q.z * q.z);
    inverse.m[6] = 2 * (q.y * q.z - q.x * q.w);
    inverse.m[8] = 2 * (q.x * q.z - q.y * q.w);
    inverse.m[9] = 2 * (q.y * q.z + q.x * q.w);
    inverse.m[10] = 1 - 2 * (q.x * q.x + q.y * q.y);
    const auto& p = view.pose.position;
    for (int i = 0; i != 3; ++i)
        inverse.m[12 + i] = -(inverse.m[i] * p.x + inverse.m[4 + i] * p.y + inverse.m[8 + i] * p.z);
    inverse.m[15] = 1;
    const float left = std::tan(view.fov.angleLeft), right = std::tan(view.fov.angleRight);
    const float down = std::tan(view.fov.angleDown), up = std::tan(view.fov.angleUp);
    constexpr float nearZ = 0.05f, farZ = 40.0f;
    Matrix projection;
    projection.m[0] = 2 / (right - left);
    projection.m[5] = -2 / (up - down); // Vulkan positive viewport height: flip clip Y.
    projection.m[8] = (right + left) / (right - left);
    projection.m[9] = -(up + down) / (up - down);
    projection.m[10] = -farZ / (farZ - nearZ); // Vulkan depth 0..1.
    projection.m[11] = -1;
    projection.m[14] = -(farZ * nearZ) / (farZ - nearZ);
    return multiply(projection, inverse);
}
struct Vertex { float position[3]; float color[3]; };
struct Eye {
    XrSwapchain swapchain{XR_NULL_HANDLE};
    uint32_t width{}, height{};
    std::vector<XrSwapchainImageVulkan2KHR> images;
    std::vector<VkImageView> imageViews;
    std::vector<VkFramebuffer> framebuffers;
    VkImage depth{VK_NULL_HANDLE};
    VkDeviceMemory depthMemory{VK_NULL_HANDLE};
    VkImageView depthView{VK_NULL_HANDLE};
};
struct HandState {
    XrActionStateFloat trigger{XR_TYPE_ACTION_STATE_FLOAT};
    XrActionStateBoolean exit{XR_TYPE_ACTION_STATE_BOOLEAN};
    XrBool32 gripActive{}, aimActive{};
    XrSpaceLocation grip{XR_TYPE_SPACE_LOCATION}, aim{XR_TYPE_SPACE_LOCATION};
};
struct HandHistory {
    XrBool32 triggerActive{}, gripActive{}, aimActive{};
    float triggerValue{};
    XrTime triggerChangeTime{};
    XrSpaceLocationFlags gripFlags{}, aimFlags{};
};
struct ProfileCache {
    XrPath path{XR_NULL_PATH};
    char text[XR_MAX_PATH_LENGTH]{"none"};
    XrResult queryResult{XR_SUCCESS}, stringResult{XR_SUCCESS};
    bool changed{};
};
struct ProfileSuggestion {
    XrPath path{XR_NULL_PATH};
    XrResult result{XR_ERROR_PATH_UNSUPPORTED};
};
struct HapticState {
    bool attempted{}, applied{}, pending{}, boundChecked{};
    XrPath boundProfile{XR_NULL_PATH};
    uint32_t boundCount{};
    XrResult boundResult{XR_SUCCESS};
    XrResult applyResult{XR_SUCCESS}, stopResult{XR_SUCCESS};
};

class Probe {
public:
    JavaVM* vm{};
    jobject activity{}, context{}, surface{};
    jmethodID statusMethod{}, exitMethod{};
    std::string dataPath;
    std::atomic<bool> stop{false};
    std::thread worker;
    jint activityId{};
    jlong epoch{};
    bool hapticProbe{};
    const pid_t pid{::getpid()};
    const uint64_t workerId{nextWorkerId.fetch_add(1, std::memory_order_relaxed)};
    uint64_t sessionId{}, sequence{};

    void log(const char* format, ...) {
        char text[2048];
        const int prefix = std::snprintf(text, sizeof(text),
            "pid=%d activity=%d epoch=%" PRId64 " worker=%" PRIu64 " session=%" PRIu64 " seq=%" PRIu64 " ",
            pid, activityId, static_cast<int64_t>(epoch), workerId, sessionId, ++sequence);
        if (prefix < 0 || static_cast<size_t>(prefix) >= sizeof(text)) return;
        va_list args;
        va_start(args, format);
        std::vsnprintf(text + prefix, sizeof(text) - static_cast<size_t>(prefix), format, args);
        va_end(args);
        for (char* p = text; *p; ++p)
            if (*p == '\n' || *p == '\r') *p = ' ';
        __android_log_write(ANDROID_LOG_INFO, kTag, text);
    }

    void run() noexcept {
        if (vm->AttachCurrentThread(&env, nullptr) != JNI_OK) {
            log("ERROR attaching native worker to JavaVM");
            return;
        }
        log("worker started; tid=%d Android Surface is lifecycle gate only hapticProbe=%u", ::gettid(), hapticProbe);
        bool notifyExit = false;
        try {
            initialize();
            while (!stop.load(std::memory_order_acquire)) {
                pollEvents();
                if (runtimeExit) { notifyExit = true; break; }
                if (running) {
                    frame();
                    if (runtimeExit) { notifyExit = true; break; }
                    if (controllerExit) {
                        status("Controller requested return to manager");
                        notifyExit = true;
                        break;
                    }
                } else {
                    std::this_thread::sleep_for(std::chrono::milliseconds(10));
                }
            }
        } catch (const std::exception& e) {
            notifyExit = runtimeExit;
            status(std::string("OpenXR failed: ") + e.what());
        } catch (...) {
            notifyExit = runtimeExit;
            status("OpenXR failed: unexpected native exception");
        }
        shutdown();
        if (notifyExit && !stop.load(std::memory_order_acquire)) {
            env->CallVoidMethod(activity, exitMethod);
            clearJavaException("onNativeExit");
        }
        log("worker exit cleanup complete");
        env = nullptr;
        vm->DetachCurrentThread();
    }

private:
    JNIEnv* env{};
    XrInstance instance{XR_NULL_HANDLE};
    XrSystemId system{XR_NULL_SYSTEM_ID};
    XrSession session{XR_NULL_HANDLE};
    XrSpace world{XR_NULL_HANDLE};
    XrSpace head{XR_NULL_HANDLE};
    XrReferenceSpaceType worldType{XR_REFERENCE_SPACE_TYPE_LOCAL};
    XrActionSet actionSet{XR_NULL_HANDLE};
    XrAction gripAction{XR_NULL_HANDLE}, aimAction{XR_NULL_HANDLE}, exitAction{XR_NULL_HANDLE}, triggerAction{XR_NULL_HANDLE}, hapticAction{XR_NULL_HANDLE};
    std::array<XrPath, 2> handPaths{};
    std::array<XrSpace, 2> gripSpaces{}, aimSpaces{};
    std::array<HandState, 2> hands{};
    std::array<HandHistory, 2> previousHands{};
    XrResult syncResult{XR_SESSION_NOT_FOCUSED};
    bool syncAttempted{};
    std::array<ProfileCache, 2> handProfiles{};
    std::array<ProfileSuggestion, 3> profileSuggestions{};
    std::array<HapticState, 2> haptics{};
    bool profilesInitialized{}, forceSample{true};
    XrTime pendingChangeTime{}, frameDisplayTime{};
    bool pendingReferenceChange{};
    bool picoBindings{}, running{}, runtimeExit{}, controllerExit{};
    XrSessionState sessionState{XR_SESSION_STATE_UNKNOWN};
    XrEnvironmentBlendMode blendMode{XR_ENVIRONMENT_BLEND_MODE_OPAQUE};
    VkInstance vkInstance{VK_NULL_HANDLE};
    VkPhysicalDevice physical{VK_NULL_HANDLE};
    VkDevice device{VK_NULL_HANDLE};
    VkQueue queue{VK_NULL_HANDLE};
    uint32_t queueFamily{};
    VkRenderPass renderPass{VK_NULL_HANDLE};
    VkPipelineLayout pipelineLayout{VK_NULL_HANDLE};
    VkPipeline pipeline{VK_NULL_HANDLE};
    VkShaderModule vertexShader{VK_NULL_HANDLE}, fragmentShader{VK_NULL_HANDLE};
    VkCommandPool commandPool{VK_NULL_HANDLE};
    VkCommandBuffer commandBuffer{VK_NULL_HANDLE};
    VkFence fence{VK_NULL_HANDLE};
    VkBuffer vertices{VK_NULL_HANDLE};
    VkDeviceMemory vertexMemory{VK_NULL_HANDLE};
    DrawRange worldRange;
    std::array<DrawRange, 2> handRanges{};
    std::array<bool, 2> drawGrip{}, drawAim{};
    std::array<Matrix, 2> gripModels{};
    std::array<std::array<Matrix, 3>, 2> aimModels{};
    VkFormat colorFormat{VK_FORMAT_UNDEFINED}, depthFormat{VK_FORMAT_UNDEFINED};
    std::array<Eye, 2> eyes;
    std::array<XrView, 2> views{{{XR_TYPE_VIEW}, {XR_TYPE_VIEW}}};
    std::array<XrCompositionLayerProjectionView, 2> projectionViews{{{XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}, {XR_TYPE_COMPOSITION_LAYER_PROJECTION_VIEW}}};
    uint64_t frameCount{}, stereoCount{};
    bool firstStereo{};

    void clearJavaException(const char* operation) {
        if (env->ExceptionCheck()) {
            log("Java callback exception: %s", operation);
            env->ExceptionDescribe();
            env->ExceptionClear();
        }
    }
    void status(const std::string& message) {
        log("%s", message.c_str());
        jstring text = env->NewStringUTF(message.c_str());
        if (text) {
            env->CallVoidMethod(activity, statusMethod, text);
            env->DeleteLocalRef(text);
        }
        clearJavaException("onNativeStatus");
    }
    void xrCheck(XrResult result, const char* operation) {
        if (XR_FAILED(result)) {
            noteLoss(result);
            char name[XR_MAX_RESULT_STRING_SIZE]{};
            if (instance) xrResultToString(instance, result, name);
            char message[256];
            std::snprintf(message, sizeof(message), "%s: XrResult=%d %s", operation, result, name);
            throw std::runtime_error(message);
        }
    }
    template<typename T> T function(const char* name) {
        PFN_xrVoidFunction address{};
        xrCheck(xrGetInstanceProcAddr(instance, name, &address), name);
        if (!address) throw std::runtime_error(std::string("Missing function: ") + name);
        return reinterpret_cast<T>(address);
    }
    XrPath path(const char* text) {
        XrPath result{};
        xrCheck(xrStringToPath(instance, text, &result), "xrStringToPath");
        return result;
    }
    void initialize() {
        auto initLoader = function<PFN_xrInitializeLoaderKHR>("xrInitializeLoaderKHR");
        XrLoaderInitInfoAndroidKHR loaderInfo{XR_TYPE_LOADER_INIT_INFO_ANDROID_KHR};
        loaderInfo.applicationVM = vm;
        loaderInfo.applicationContext = context;
        xrCheck(initLoader(reinterpret_cast<const XrLoaderInitInfoBaseHeaderKHR*>(&loaderInfo)), "xrInitializeLoaderKHR");
        uint32_t count{};
        xrCheck(xrEnumerateInstanceExtensionProperties(nullptr, 0, &count, nullptr), "enumerate extensions");
        std::vector<XrExtensionProperties> extensions(count, {XR_TYPE_EXTENSION_PROPERTIES});
        xrCheck(xrEnumerateInstanceExtensionProperties(nullptr, count, &count, extensions.data()), "enumerate extensions");
        auto supported = [&](const char* name) {
            return std::any_of(extensions.begin(), extensions.end(), [&](const auto& e) { return std::strcmp(e.extensionName, name) == 0; });
        };
        for (const char* required : {XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME})
            if (!supported(required)) throw std::runtime_error(std::string("Runtime missing required extension ") + required);
        std::vector<const char*> enabled{XR_KHR_ANDROID_CREATE_INSTANCE_EXTENSION_NAME, XR_KHR_VULKAN_ENABLE2_EXTENSION_NAME};
        // Request OpenXR 1.0 for older Android runtimes; enable the Pico profile extension only when advertised.
        picoBindings = supported(XR_BD_CONTROLLER_INTERACTION_EXTENSION_NAME);
        if (picoBindings) enabled.push_back(XR_BD_CONTROLLER_INTERACTION_EXTENSION_NAME);
        log("runtime extensions available=%u enabled=%zu", count, enabled.size());
        for (const char* name : enabled) log("enabled runtime extension %s", name);
        XrInstanceCreateInfoAndroidKHR androidInfo{XR_TYPE_INSTANCE_CREATE_INFO_ANDROID_KHR};
        androidInfo.applicationVM = vm;
        androidInfo.applicationActivity = activity;
        XrInstanceCreateInfo create{XR_TYPE_INSTANCE_CREATE_INFO};
        create.next = &androidInfo;
        std::snprintf(create.applicationInfo.applicationName, XR_MAX_APPLICATION_NAME_SIZE, "BS4Pico phase probe");
        std::snprintf(create.applicationInfo.engineName, XR_MAX_ENGINE_NAME_SIZE, "Native Vulkan probe");
        create.applicationInfo.applicationVersion = 1;
        create.applicationInfo.engineVersion = 1;
        create.applicationInfo.apiVersion = XR_MAKE_VERSION(1, 0, 0);
        create.enabledExtensionCount = static_cast<uint32_t>(enabled.size());
        create.enabledExtensionNames = enabled.data();
        xrCheck(xrCreateInstance(&create, &instance), "xrCreateInstance");
        XrInstanceProperties properties{XR_TYPE_INSTANCE_PROPERTIES};
        xrCheck(xrGetInstanceProperties(instance, &properties), "xrGetInstanceProperties");
        log("loader headers=%u.%u.%u requested API=1.0 runtime=%s version=%u.%u.%u",
            unsigned(XR_VERSION_MAJOR(XR_CURRENT_API_VERSION)), unsigned(XR_VERSION_MINOR(XR_CURRENT_API_VERSION)), unsigned(XR_VERSION_PATCH(XR_CURRENT_API_VERSION)),
            properties.runtimeName, unsigned(XR_VERSION_MAJOR(properties.runtimeVersion)), unsigned(XR_VERSION_MINOR(properties.runtimeVersion)), unsigned(XR_VERSION_PATCH(properties.runtimeVersion)));
        XrSystemGetInfo systemInfo{XR_TYPE_SYSTEM_GET_INFO};
        systemInfo.formFactor = XR_FORM_FACTOR_HEAD_MOUNTED_DISPLAY;
        xrCheck(xrGetSystem(instance, &systemInfo, &system), "xrGetSystem HMD");
        XrSystemProperties systemProperties{XR_TYPE_SYSTEM_PROPERTIES};
        xrCheck(xrGetSystemProperties(instance, system, &systemProperties), "xrGetSystemProperties");
        log("system=%s vendor=%u positionTracking=%u orientationTracking=%u maxImage=%ux%u",
            systemProperties.systemName, systemProperties.vendorId, systemProperties.trackingProperties.positionTracking,
            systemProperties.trackingProperties.orientationTracking, systemProperties.graphicsProperties.maxSwapchainImageWidth,
            systemProperties.graphicsProperties.maxSwapchainImageHeight);
        xrCheck(xrEnumerateViewConfigurations(instance, system, 0, &count, nullptr), "enumerate view configurations");
        std::vector<XrViewConfigurationType> configurations(count);
        xrCheck(xrEnumerateViewConfigurations(instance, system, count, &count, configurations.data()), "enumerate view configurations");
        for (auto configuration : configurations) log("view configuration=%d", configuration);
        if (std::find(configurations.begin(), configurations.end(), kStereo) == configurations.end())
            throw std::runtime_error("Runtime has no PRIMARY_STEREO view configuration");
        xrCheck(xrEnumerateEnvironmentBlendModes(instance, system, kStereo, 0, &count, nullptr), "enumerate blend modes");
        std::vector<XrEnvironmentBlendMode> blends(count);
        xrCheck(xrEnumerateEnvironmentBlendModes(instance, system, kStereo, count, &count, blends.data()), "enumerate blend modes");
        for (auto blend : blends) log("blend mode=%d", blend);
        if (std::find(blends.begin(), blends.end(), XR_ENVIRONMENT_BLEND_MODE_OPAQUE) == blends.end())
            throw std::runtime_error("Opaque stereo rendering is not supported by this runtime");
        createVulkan();
        XrGraphicsBindingVulkan2KHR binding{XR_TYPE_GRAPHICS_BINDING_VULKAN2_KHR};
        binding.instance = vkInstance;
        binding.physicalDevice = physical;
        binding.device = device;
        binding.queueFamilyIndex = queueFamily;
        binding.queueIndex = 0;
        XrSessionCreateInfo sessionInfo{XR_TYPE_SESSION_CREATE_INFO};
        sessionInfo.next = &binding;
        sessionInfo.systemId = system;
        xrCheck(xrCreateSession(instance, &sessionInfo, &session), "xrCreateSession");
        sessionId = workerId;
        log("XR session created");
        updateSharedFile();
        createSpaces();
        createActions();
        createRenderer();
        createSwapchains();
        status(std::string("OpenXR session created: ") + properties.runtimeName + "; waiting for READY");
    }

    void createVulkan() {
        XrGraphicsRequirementsVulkan2KHR requirements{XR_TYPE_GRAPHICS_REQUIREMENTS_VULKAN2_KHR};
        auto getRequirements = function<PFN_xrGetVulkanGraphicsRequirements2KHR>("xrGetVulkanGraphicsRequirements2KHR");
        xrCheck(getRequirements(instance, system, &requirements), "xrGetVulkanGraphicsRequirements2KHR");
        log("Vulkan requirements min=%u.%u.%u max=%u.%u.%u",
            unsigned(XR_VERSION_MAJOR(requirements.minApiVersionSupported)), unsigned(XR_VERSION_MINOR(requirements.minApiVersionSupported)), unsigned(XR_VERSION_PATCH(requirements.minApiVersionSupported)),
            unsigned(XR_VERSION_MAJOR(requirements.maxApiVersionSupported)), unsigned(XR_VERSION_MINOR(requirements.maxApiVersionSupported)), unsigned(XR_VERSION_PATCH(requirements.maxApiVersionSupported)));
        uint32_t loaderVersion = VK_API_VERSION_1_0;
        auto enumerateVersion = reinterpret_cast<PFN_vkEnumerateInstanceVersion>(vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkEnumerateInstanceVersion"));
        if (enumerateVersion) vkCheck(enumerateVersion(&loaderVersion), "vkEnumerateInstanceVersion");
        XrVersion available = XR_MAKE_VERSION(VK_VERSION_MAJOR(loaderVersion), VK_VERSION_MINOR(loaderVersion), VK_VERSION_PATCH(loaderVersion));
        XrVersion version = std::min(available, requirements.maxApiVersionSupported);
        if (version < requirements.minApiVersionSupported) throw std::runtime_error("Vulkan loader API is below XR runtime minimum");
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "BS4PicoXR";
        app.apiVersion = VK_MAKE_VERSION(XR_VERSION_MAJOR(version), XR_VERSION_MINOR(version), XR_VERSION_PATCH(version));
        VkInstanceCreateInfo info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        info.pApplicationInfo = &app;
        XrVulkanInstanceCreateInfoKHR xrInfo{XR_TYPE_VULKAN_INSTANCE_CREATE_INFO_KHR};
        xrInfo.systemId = system;
        xrInfo.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
        xrInfo.vulkanCreateInfo = &info;
        VkResult result{};
        auto createInstance = function<PFN_xrCreateVulkanInstanceKHR>("xrCreateVulkanInstanceKHR");
        xrCheck(createInstance(instance, &xrInfo, &vkInstance, &result), "xrCreateVulkanInstanceKHR");
        vkCheck(result, "runtime vkCreateInstance");
        XrVulkanGraphicsDeviceGetInfoKHR deviceGet{XR_TYPE_VULKAN_GRAPHICS_DEVICE_GET_INFO_KHR};
        deviceGet.systemId = system;
        deviceGet.vulkanInstance = vkInstance;
        auto getDevice = function<PFN_xrGetVulkanGraphicsDevice2KHR>("xrGetVulkanGraphicsDevice2KHR");
        xrCheck(getDevice(instance, &deviceGet, &physical), "xrGetVulkanGraphicsDevice2KHR");
        VkPhysicalDeviceProperties properties{};
        vkGetPhysicalDeviceProperties(physical, &properties);
        log("Vulkan physical device=%s API=%u.%u.%u selectedAPI=%u.%u.%u", properties.deviceName,
            VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion), VK_VERSION_PATCH(properties.apiVersion),
            VK_VERSION_MAJOR(app.apiVersion), VK_VERSION_MINOR(app.apiVersion), VK_VERSION_PATCH(app.apiVersion));
        if (properties.apiVersion < app.apiVersion) {
            // Instance API may be newer than the physical device; only core 1.0 features are used below.
            if (XR_MAKE_VERSION(VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion), VK_VERSION_PATCH(properties.apiVersion)) < requirements.minApiVersionSupported)
                throw std::runtime_error("XR-selected GPU Vulkan API is below runtime minimum");
        }
        uint32_t count{};
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
        std::vector<VkQueueFamilyProperties> queues(count);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, queues.data());
        bool found = false;
        for (uint32_t i = 0; i < count; ++i)
            if (queues[i].queueCount && (queues[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { queueFamily = i; found = true; break; }
        if (!found) throw std::runtime_error("XR-selected Vulkan device has no graphics queue");
        const float priority = 1;
        VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queueInfo.queueFamilyIndex = queueFamily;
        queueInfo.queueCount = 1;
        queueInfo.pQueuePriorities = &priority;
        VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        deviceInfo.queueCreateInfoCount = 1;
        deviceInfo.pQueueCreateInfos = &queueInfo;
        XrVulkanDeviceCreateInfoKHR xrDeviceInfo{XR_TYPE_VULKAN_DEVICE_CREATE_INFO_KHR};
        xrDeviceInfo.systemId = system;
        xrDeviceInfo.pfnGetInstanceProcAddr = vkGetInstanceProcAddr;
        xrDeviceInfo.vulkanPhysicalDevice = physical;
        xrDeviceInfo.vulkanCreateInfo = &deviceInfo;
        auto createDevice = function<PFN_xrCreateVulkanDeviceKHR>("xrCreateVulkanDeviceKHR");
        xrCheck(createDevice(instance, &xrDeviceInfo, &device, &result), "xrCreateVulkanDeviceKHR");
        vkCheck(result, "runtime vkCreateDevice");
        vkGetDeviceQueue(device, queueFamily, 0, &queue);
    }

    void createSpaces() {
        uint32_t count{};
        xrCheck(xrEnumerateReferenceSpaces(session, 0, &count, nullptr), "enumerate reference spaces");
        std::vector<XrReferenceSpaceType> spaces(count);
        xrCheck(xrEnumerateReferenceSpaces(session, count, &count, spaces.data()), "enumerate reference spaces");
        for (auto space : spaces) log("reference space=%d", space);
        if (std::find(spaces.begin(), spaces.end(), XR_REFERENCE_SPACE_TYPE_STAGE) != spaces.end())
            worldType = XR_REFERENCE_SPACE_TYPE_STAGE;
        else if (std::find(spaces.begin(), spaces.end(), XR_REFERENCE_SPACE_TYPE_LOCAL) == spaces.end())
            throw std::runtime_error("No STAGE or LOCAL reference space");
        XrReferenceSpaceCreateInfo info{XR_TYPE_REFERENCE_SPACE_CREATE_INFO};
        info.referenceSpaceType = worldType;
        info.poseInReferenceSpace = identityPose();
        xrCheck(xrCreateReferenceSpace(session, &info, &world), "create world reference space");
        info.referenceSpaceType = XR_REFERENCE_SPACE_TYPE_VIEW;
        xrCheck(xrCreateReferenceSpace(session, &info, &head), "create head reference space");
        log("world reference=%s; %s", worldType == XR_REFERENCE_SPACE_TYPE_STAGE ? "STAGE" : "LOCAL",
            worldType == XR_REFERENCE_SPACE_TYPE_STAGE ? "ground grid y=0, cubes at standing eye height" : "uncalibrated floor: grid y=-1.5m relative to LOCAL origin");
    }

    XrAction action(const char* name, XrActionType type) {
        XrActionCreateInfo info{XR_TYPE_ACTION_CREATE_INFO};
        std::snprintf(info.actionName, sizeof(info.actionName), "%s", name);
        std::snprintf(info.localizedActionName, sizeof(info.localizedActionName), "%s", name);
        info.actionType = type;
        info.countSubactionPaths = 2;
        info.subactionPaths = handPaths.data();
        XrAction result{};
        xrCheck(xrCreateAction(actionSet, &info, &result), "xrCreateAction");
        return result;
    }
    void suggestBindings(const char* profile, bool pico, int suggestion) {
        std::array<XrActionSuggestedBinding, 10> bindings{};
        uint32_t count{};
        for (int i = 0; i != 2; ++i) {
            const char* hand = i == 0 ? "left" : "right";
            char text[128];
            auto bind = [&](XrAction act, const char* input) {
                std::snprintf(text, sizeof(text), "/user/hand/%s/input/%s", hand, input);
                bindings[count++] = {act, path(text)};
            };
            bind(gripAction, "grip/pose");
            bind(aimAction, "aim/pose");
            bind(exitAction, pico ? (i == 0 ? "y/click" : "b/click") : "select/click");
            if (pico) bind(triggerAction, "trigger/value");
            std::snprintf(text, sizeof(text), "/user/hand/%s/output/haptic", hand);
            bindings[count++] = {hapticAction, path(text)};
        }
        XrInteractionProfileSuggestedBinding info{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};
        info.interactionProfile = path(profile);
        info.countSuggestedBindings = count;
        info.suggestedBindings = bindings.data();
        XrResult result = xrSuggestInteractionProfileBindings(instance, &info);
        profileSuggestions[suggestion] = {info.interactionProfile, result};
        log("suggest profile=%s result=%d (suggestion does not prove active controller support)", profile, result);
        if (!pico) xrCheck(result, "suggest simple controller bindings");
    }
    void createActions() {
        handPaths = {path("/user/hand/left"), path("/user/hand/right")};
        XrActionSetCreateInfo info{XR_TYPE_ACTION_SET_CREATE_INFO};
        std::snprintf(info.actionSetName, sizeof(info.actionSetName), "probe");
        std::snprintf(info.localizedActionSetName, sizeof(info.localizedActionSetName), "Probe controls");
        xrCheck(xrCreateActionSet(instance, &info, &actionSet), "xrCreateActionSet");
        gripAction = action("grip", XR_ACTION_TYPE_POSE_INPUT);
        aimAction = action("aim", XR_ACTION_TYPE_POSE_INPUT);
        exitAction = action("return_to_manager", XR_ACTION_TYPE_BOOLEAN_INPUT);
        triggerAction = action("trigger", XR_ACTION_TYPE_FLOAT_INPUT);
        hapticAction = action("haptic", XR_ACTION_TYPE_VIBRATION_OUTPUT);
        suggestBindings("/interaction_profiles/khr/simple_controller", false, 0);
        if (picoBindings) {
            suggestBindings("/interaction_profiles/bytedance/pico4_controller", true, 1);
            suggestBindings("/interaction_profiles/bytedance/pico_neo3_controller", true, 2);
        } else log("XR_BD_controller_interaction absent; Pico bindings not enabled");
        XrSessionActionSetsAttachInfo attach{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};
        attach.countActionSets = 1;
        attach.actionSets = &actionSet;
        xrCheck(xrAttachSessionActionSets(session, &attach), "xrAttachSessionActionSets");
        for (int i = 0; i != 2; ++i) {
            XrActionSpaceCreateInfo spaceInfo{XR_TYPE_ACTION_SPACE_CREATE_INFO};
            spaceInfo.subactionPath = handPaths[i];
            spaceInfo.poseInActionSpace = identityPose();
            spaceInfo.action = gripAction;
            xrCheck(xrCreateActionSpace(session, &spaceInfo, &gripSpaces[i]), "create grip space");
            spaceInfo.action = aimAction;
            xrCheck(xrCreateActionSpace(session, &spaceInfo, &aimSpaces[i]), "create aim space");
        }
    }

    uint32_t memoryType(uint32_t bits, VkMemoryPropertyFlags flags) {
        VkPhysicalDeviceMemoryProperties properties{};
        vkGetPhysicalDeviceMemoryProperties(physical, &properties);
        for (uint32_t i = 0; i < properties.memoryTypeCount; ++i)
            if ((bits & (1u << i)) && (properties.memoryTypes[i].propertyFlags & flags) == flags) return i;
        throw std::runtime_error("No compatible Vulkan memory type");
    }
    VkShaderModule shader(const uint32_t* words, size_t bytes) {
        VkShaderModule result{};
        VkShaderModuleCreateInfo info{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        info.codeSize = bytes;
        info.pCode = words;
        vkCheck(vkCreateShaderModule(device, &info, nullptr, &result), "vkCreateShaderModule");
        return result;
    }
    void createGeometry() {
        std::vector<Vertex> data;
        // 26 original boxes, 3 axis shafts, 3 closed pyramid heads, 2 hand boxes.
        data.reserve(1170);
        auto box = [&](float x, float y, float z, float sx, float sy, float sz, float red, float green, float blue) {
            const float corners[8][3] = {
                {x-sx,y-sy,z-sz},{x+sx,y-sy,z-sz},{x+sx,y+sy,z-sz},{x-sx,y+sy,z-sz},
                {x-sx,y-sy,z+sz},{x+sx,y-sy,z+sz},{x+sx,y+sy,z+sz},{x-sx,y+sy,z+sz}};
            const int indices[36] = {0,1,2,0,2,3,4,6,5,4,7,6,0,4,5,0,5,1,3,2,6,3,6,7,0,3,7,0,7,4,1,5,6,1,6,2};
            for (int i = 0; i != 36; ++i) {
                float shade = 0.55f + 0.09f * (i / 6);
                const auto& p = corners[indices[i]];
                data.push_back({{p[0], p[1], p[2]}, {red*shade, green*shade, blue*shade}});
            }
        };
        const float centerY = worldType == XR_REFERENCE_SPACE_TYPE_STAGE ? 1.5f : 0.0f;
        const float floorY = centerY - 1.5f;
        worldRange.firstVertex = static_cast<uint32_t>(data.size());
        box(-0.65f, centerY, -2, 0.22f, 0.22f, 0.22f, 1, 0.08f, 0.04f);
        box(0.65f, centerY, -2, 0.22f, 0.22f, 0.22f, 0.04f, 0.3f, 1);
        box(0, centerY + 0.15f, -4, 0.35f, 0.35f, 0.35f, 0.08f, 1, 0.2f);
        box(-1.5f, centerY - 0.3f, -6, 0.45f, 0.45f, 0.45f, 1, 0.7f, 0.05f);
        for (int i = -5; i <= 5; ++i)
            box(float(i), floorY, -5, 0.012f, 0.008f, 5, 0.2f, 0.35f, 0.45f);
        for (int i = 0; i <= 10; ++i)
            box(0, floorY, -float(i), 5, 0.008f, 0.012f, 0.2f, 0.35f, 0.45f);
        // Arrows start at (0,floorY,-2): 0.42m shafts plus 0.08m pyramid heads.
        box(0.21f, floorY, -2, 0.21f, 0.008f, 0.008f, 1, 0, 0);
        box(0, floorY + 0.21f, -2, 0.008f, 0.21f, 0.008f, 0, 1, 0);
        box(0, floorY, -2.21f, 0.008f, 0.008f, 0.21f, 0, 0, 1);
        auto arrowHead = [&](const XrVector3f& direction, const XrVector3f& side, const XrVector3f& up,
                             float red, float green, float blue) {
            const float origin[3] = {0, floorY, -2};
            const float d[3] = {direction.x, direction.y, direction.z};
            const float s[3] = {side.x, side.y, side.z};
            const float u[3] = {up.x, up.y, up.z};
            const float signs[4][2] = {{-1,-1},{1,-1},{1,1},{-1,1}};
            float corners[5][3];
            for (int axis = 0; axis != 3; ++axis) {
                for (int corner = 0; corner != 4; ++corner)
                    corners[corner][axis] = origin[axis] + 0.42f * d[axis]
                        + 0.04f * (signs[corner][0] * s[axis] + signs[corner][1] * u[axis]);
                corners[4][axis] = origin[axis] + 0.5f * d[axis];
            }
            const int indices[18] = {0,1,4,1,2,4,2,3,4,3,0,4,0,3,2,0,2,1};
            for (int i = 0; i != 18; ++i) {
                const auto& p = corners[indices[i]];
                data.push_back({{p[0], p[1], p[2]}, {red, green, blue}});
            }
        };
        arrowHead({1,0,0}, {0,1,0}, {0,0,1}, 1, 0, 0);
        arrowHead({0,1,0}, {1,0,0}, {0,0,1}, 0, 1, 0);
        arrowHead({0,0,-1}, {1,0,0}, {0,1,0}, 0, 0, 1);
        worldRange.count = static_cast<uint32_t>(data.size()) - worldRange.firstVertex;
        for (int hand = 0; hand != 2; ++hand) {
            handRanges[hand].firstVertex = static_cast<uint32_t>(data.size());
            box(0, 0, 0, 1, 1, 1, hand == 0 ? 0.0f : 1.0f, hand == 0 ? 1.0f : 0.0f, 1);
            handRanges[hand].count = static_cast<uint32_t>(data.size()) - handRanges[hand].firstVertex;
        }
        VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
        info.size = data.size() * sizeof(Vertex);
        info.usage = VK_BUFFER_USAGE_VERTEX_BUFFER_BIT;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        vkCheck(vkCreateBuffer(device, &info, nullptr, &vertices), "vkCreateBuffer");
        VkMemoryRequirements requirements{};
        vkGetBufferMemoryRequirements(device, vertices, &requirements);
        VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memoryType(requirements.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
        vkCheck(vkAllocateMemory(device, &allocation, nullptr, &vertexMemory), "allocate vertex memory");
        vkCheck(vkBindBufferMemory(device, vertices, vertexMemory, 0), "bind vertex memory");
        void* mapped{};
        vkCheck(vkMapMemory(device, vertexMemory, 0, info.size, 0, &mapped), "map vertices");
        std::memcpy(mapped, data.data(), info.size);
        vkUnmapMemory(device, vertexMemory);
    }

    void createRenderer() {
        uint32_t count{};
        xrCheck(xrEnumerateSwapchainFormats(session, 0, &count, nullptr), "enumerate swapchain formats");
        std::vector<int64_t> formats(count);
        xrCheck(xrEnumerateSwapchainFormats(session, count, &count, formats.data()), "enumerate swapchain formats");
        for (auto format : formats) log("swapchain VkFormat=%" PRId64, format);
        for (auto candidate : {VK_FORMAT_R8G8B8A8_SRGB, VK_FORMAT_B8G8R8A8_SRGB, VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_B8G8R8A8_UNORM}) {
            VkFormatProperties properties{};
            vkGetPhysicalDeviceFormatProperties(physical, candidate, &properties);
            if (std::find(formats.begin(), formats.end(), candidate) != formats.end() && (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_COLOR_ATTACHMENT_BIT)) { colorFormat = candidate; break; }
        }
        if (colorFormat == VK_FORMAT_UNDEFINED) throw std::runtime_error("No supported RGBA/BGRA XR color attachment format");
        for (auto candidate : {VK_FORMAT_D32_SFLOAT, VK_FORMAT_D16_UNORM}) {
            VkFormatProperties properties{};
            vkGetPhysicalDeviceFormatProperties(physical, candidate, &properties);
            if (properties.optimalTilingFeatures & VK_FORMAT_FEATURE_DEPTH_STENCIL_ATTACHMENT_BIT) { depthFormat = candidate; break; }
        }
        if (depthFormat == VK_FORMAT_UNDEFINED) throw std::runtime_error("No supported depth format");
        log("render colorFormat=%d depthFormat=%d sampleCount=1; vertex colors are linear", colorFormat, depthFormat);
        VkAttachmentDescription attachments[2]{};
        attachments[0].format = colorFormat;
        attachments[0].samples = VK_SAMPLE_COUNT_1_BIT;
        attachments[0].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachments[0].storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        attachments[0].stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachments[0].stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[0].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachments[0].finalLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
        attachments[1].format = depthFormat;
        attachments[1].samples = VK_SAMPLE_COUNT_1_BIT;
        attachments[1].loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachments[1].storeOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[1].stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachments[1].stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachments[1].initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachments[1].finalLayout = VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL;
        VkAttachmentReference colorReference{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkAttachmentReference depthReference{1, VK_IMAGE_LAYOUT_DEPTH_STENCIL_ATTACHMENT_OPTIMAL};
        VkSubpassDescription subpass{};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &colorReference;
        subpass.pDepthStencilAttachment = &depthReference;
        VkSubpassDependency dependency{};
        dependency.srcSubpass = VK_SUBPASS_EXTERNAL;
        dependency.dstSubpass = 0;
        dependency.srcStageMask = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT | VK_PIPELINE_STAGE_EARLY_FRAGMENT_TESTS_BIT;
        dependency.dstStageMask = dependency.srcStageMask;
        dependency.dstAccessMask = VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT | VK_ACCESS_DEPTH_STENCIL_ATTACHMENT_WRITE_BIT;
        VkRenderPassCreateInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
        pass.attachmentCount = 2;
        pass.pAttachments = attachments;
        pass.subpassCount = 1;
        pass.pSubpasses = &subpass;
        pass.dependencyCount = 1;
        pass.pDependencies = &dependency;
        vkCheck(vkCreateRenderPass(device, &pass, nullptr, &renderPass), "vkCreateRenderPass");
        vertexShader = shader(kVertexShader, sizeof(kVertexShader));
        fragmentShader = shader(kFragmentShader, sizeof(kFragmentShader));
        VkPushConstantRange push{VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(Matrix)};
        VkPipelineLayoutCreateInfo layout{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        layout.pushConstantRangeCount = 1;
        layout.pPushConstantRanges = &push;
        vkCheck(vkCreatePipelineLayout(device, &layout, nullptr, &pipelineLayout), "vkCreatePipelineLayout");
        VkPipelineShaderStageCreateInfo stages[2]{};
        stages[0].sType = stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
        stages[0].module = vertexShader;
        stages[0].pName = "main";
        stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
        stages[1].module = fragmentShader;
        stages[1].pName = "main";
        VkVertexInputBindingDescription vertexBinding{0, sizeof(Vertex), VK_VERTEX_INPUT_RATE_VERTEX};
        VkVertexInputAttributeDescription attributes[2]{{0, 0, VK_FORMAT_R32G32B32_SFLOAT, 0}, {1, 0, VK_FORMAT_R32G32B32_SFLOAT, 3 * sizeof(float)}};
        VkPipelineVertexInputStateCreateInfo vertexInput{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
        vertexInput.vertexBindingDescriptionCount = 1;
        vertexInput.pVertexBindingDescriptions = &vertexBinding;
        vertexInput.vertexAttributeDescriptionCount = 2;
        vertexInput.pVertexAttributeDescriptions = attributes;
        VkPipelineInputAssemblyStateCreateInfo assembly{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
        assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
        VkPipelineViewportStateCreateInfo viewport{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
        viewport.viewportCount = viewport.scissorCount = 1;
        VkPipelineRasterizationStateCreateInfo raster{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
        raster.polygonMode = VK_POLYGON_MODE_FILL;
        raster.cullMode = VK_CULL_MODE_NONE;
        raster.frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE;
        raster.lineWidth = 1;
        VkPipelineMultisampleStateCreateInfo multisample{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
        multisample.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
        VkPipelineDepthStencilStateCreateInfo depth{VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
        depth.depthTestEnable = depth.depthWriteEnable = VK_TRUE;
        depth.depthCompareOp = VK_COMPARE_OP_LESS;
        VkPipelineColorBlendAttachmentState colorBlend{};
        colorBlend.colorWriteMask = VK_COLOR_COMPONENT_R_BIT | VK_COLOR_COMPONENT_G_BIT | VK_COLOR_COMPONENT_B_BIT | VK_COLOR_COMPONENT_A_BIT;
        VkPipelineColorBlendStateCreateInfo blend{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
        blend.attachmentCount = 1;
        blend.pAttachments = &colorBlend;
        VkDynamicState dynamics[]{VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
        VkPipelineDynamicStateCreateInfo dynamic{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
        dynamic.dynamicStateCount = 2;
        dynamic.pDynamicStates = dynamics;
        VkGraphicsPipelineCreateInfo pipelineInfo{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
        pipelineInfo.stageCount = 2;
        pipelineInfo.pStages = stages;
        pipelineInfo.pVertexInputState = &vertexInput;
        pipelineInfo.pInputAssemblyState = &assembly;
        pipelineInfo.pViewportState = &viewport;
        pipelineInfo.pRasterizationState = &raster;
        pipelineInfo.pMultisampleState = &multisample;
        pipelineInfo.pDepthStencilState = &depth;
        pipelineInfo.pColorBlendState = &blend;
        pipelineInfo.pDynamicState = &dynamic;
        pipelineInfo.layout = pipelineLayout;
        pipelineInfo.renderPass = renderPass;
        vkCheck(vkCreateGraphicsPipelines(device, VK_NULL_HANDLE, 1, &pipelineInfo, nullptr, &pipeline), "vkCreateGraphicsPipelines");
        VkCommandPoolCreateInfo pool{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        pool.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
        pool.queueFamilyIndex = queueFamily;
        vkCheck(vkCreateCommandPool(device, &pool, nullptr, &commandPool), "vkCreateCommandPool");
        VkCommandBufferAllocateInfo command{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        command.commandPool = commandPool;
        command.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        command.commandBufferCount = 1;
        vkCheck(vkAllocateCommandBuffers(device, &command, &commandBuffer), "vkAllocateCommandBuffers");
        VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        vkCheck(vkCreateFence(device, &fenceInfo, nullptr, &fence), "vkCreateFence");
        createGeometry();
    }

    VkImageView imageView(VkImage image, VkFormat format, VkImageAspectFlags aspect) {
        VkImageViewCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        info.image = image;
        info.viewType = VK_IMAGE_VIEW_TYPE_2D;
        info.format = format;
        info.subresourceRange = {aspect, 0, 1, 0, 1};
        VkImageView result{};
        vkCheck(vkCreateImageView(device, &info, nullptr, &result), "vkCreateImageView");
        return result;
    }
    void createSwapchains() {
        uint32_t count{};
        xrCheck(xrEnumerateViewConfigurationViews(instance, system, kStereo, 0, &count, nullptr), "enumerate stereo views");
        if (count != 2) throw std::runtime_error("PRIMARY_STEREO must have exactly two views");
        std::array<XrViewConfigurationView, 2> config{{{XR_TYPE_VIEW_CONFIGURATION_VIEW}, {XR_TYPE_VIEW_CONFIGURATION_VIEW}}};
        xrCheck(xrEnumerateViewConfigurationViews(instance, system, kStereo, 2, &count, config.data()), "enumerate stereo views");
        for (int i = 0; i != 2; ++i) {
            Eye& eye = eyes[i];
            eye.width = config[i].recommendedImageRectWidth;
            eye.height = config[i].recommendedImageRectHeight;
            log("eye=%d recommended=%ux%u recommendedSamples=%u maxSamples=%u usingSamples=1", i, eye.width, eye.height, config[i].recommendedSwapchainSampleCount, config[i].maxSwapchainSampleCount);
            XrSwapchainCreateInfo info{XR_TYPE_SWAPCHAIN_CREATE_INFO};
            info.usageFlags = XR_SWAPCHAIN_USAGE_COLOR_ATTACHMENT_BIT;
            info.format = colorFormat;
            info.sampleCount = 1;
            info.width = eye.width;
            info.height = eye.height;
            info.faceCount = info.arraySize = info.mipCount = 1;
            xrCheck(xrCreateSwapchain(session, &info, &eye.swapchain), "xrCreateSwapchain");
            xrCheck(xrEnumerateSwapchainImages(eye.swapchain, 0, &count, nullptr), "enumerate swapchain images");
            eye.images.resize(count, {XR_TYPE_SWAPCHAIN_IMAGE_VULKAN2_KHR});
            xrCheck(xrEnumerateSwapchainImages(eye.swapchain, count, &count, reinterpret_cast<XrSwapchainImageBaseHeader*>(eye.images.data())), "enumerate Vulkan images");
            eye.imageViews.resize(count, VK_NULL_HANDLE);
            eye.framebuffers.resize(count, VK_NULL_HANDLE);
            VkImageCreateInfo depthInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
            depthInfo.imageType = VK_IMAGE_TYPE_2D;
            depthInfo.format = depthFormat;
            depthInfo.extent = {eye.width, eye.height, 1};
            depthInfo.mipLevels = depthInfo.arrayLayers = 1;
            depthInfo.samples = VK_SAMPLE_COUNT_1_BIT;
            depthInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
            depthInfo.usage = VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT;
            depthInfo.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
            vkCheck(vkCreateImage(device, &depthInfo, nullptr, &eye.depth), "create depth image");
            VkMemoryRequirements requirements{};
            vkGetImageMemoryRequirements(device, eye.depth, &requirements);
            VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
            allocation.allocationSize = requirements.size;
            allocation.memoryTypeIndex = memoryType(requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
            vkCheck(vkAllocateMemory(device, &allocation, nullptr, &eye.depthMemory), "allocate depth memory");
            vkCheck(vkBindImageMemory(device, eye.depth, eye.depthMemory, 0), "bind depth memory");
            eye.depthView = imageView(eye.depth, depthFormat, VK_IMAGE_ASPECT_DEPTH_BIT);
            for (uint32_t image = 0; image < count; ++image) {
                eye.imageViews[image] = imageView(eye.images[image].image, colorFormat, VK_IMAGE_ASPECT_COLOR_BIT);
                VkImageView attachments[]{eye.imageViews[image], eye.depthView};
                VkFramebufferCreateInfo framebuffer{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
                framebuffer.renderPass = renderPass;
                framebuffer.attachmentCount = 2;
                framebuffer.pAttachments = attachments;
                framebuffer.width = eye.width;
                framebuffer.height = eye.height;
                framebuffer.layers = 1;
                vkCheck(vkCreateFramebuffer(device, &framebuffer, nullptr, &eye.framebuffers[image]), "vkCreateFramebuffer");
            }
        }
    }

    static const char* handName(int hand) { return hand == 0 ? "left" : "right"; }
    void noteLoss(XrResult result) noexcept {
        if (result == XR_SESSION_LOSS_PENDING || result == XR_ERROR_SESSION_LOST || result == XR_ERROR_INSTANCE_LOST)
            runtimeExit = true;
    }
    void profiles() {
        for (int i = 0; i != 2; ++i) {
            auto& cache = handProfiles[i];
            XrInteractionProfileState state{XR_TYPE_INTERACTION_PROFILE_STATE};
            cache.queryResult = xrGetCurrentInteractionProfile(session, handPaths[i], &state);
            noteLoss(cache.queryResult);
            const XrPath current = cache.queryResult == XR_SUCCESS ? state.interactionProfile : XR_NULL_PATH;
            const bool changed = current != cache.path || !profilesInitialized;
            cache.changed = cache.changed || changed;
            forceSample = forceSample || changed;
            cache.path = current;
            if (!current) {
                cache.stringResult = XR_SUCCESS;
                if (changed) std::snprintf(cache.text, sizeof(cache.text), "none");
            } else if (changed) {
                // Path strings are immutable; refresh queries on sample frames
                // without reformatting/reconverting an unchanged cached profile.
                uint32_t length{};
                cache.stringResult = xrPathToString(instance, current, sizeof(cache.text), &length, cache.text);
                noteLoss(cache.stringResult);
                if (cache.stringResult != XR_SUCCESS)
                    std::snprintf(cache.text, sizeof(cache.text), "unavailable");
            }
            log("hand=%s currentProfile=%s result=%d pathToStringResult=%d profilePath=%" PRIu64,
                handName(i), cache.text, cache.queryResult, cache.stringResult, uint64_t(cache.path));
            if (runtimeExit) break;
        }
        profilesInitialized = true;
    }
    static void poseText(const XrSpaceLocation& location, char (&position)[96], char (&orientation)[96]) {
        const auto& p = location.pose.position;
        const auto& q = location.pose.orientation;
        if (location.locationFlags & XR_SPACE_LOCATION_POSITION_VALID_BIT)
            std::snprintf(position, sizeof(position), "(%.9g,%.9g,%.9g)", p.x, p.y, p.z);
        else std::snprintf(position, sizeof(position), "unavailable");
        if (location.locationFlags & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT)
            std::snprintf(orientation, sizeof(orientation), "(%.9g,%.9g,%.9g,%.9g)", q.x, q.y, q.z, q.w);
        else std::snprintf(orientation, sizeof(orientation), "unavailable");
    }
    void handSample(int i, XrTime time) {
        const auto& h = hands[i];
        char gp[96], gq[96], ap[96], aq[96];
        poseText(h.grip, gp, gq);
        poseText(h.aim, ap, aq);
        const auto gf = h.grip.locationFlags, af = h.aim.locationFlags;
        log("HAND_SAMPLE frame=%" PRIu64 " displayTime=%" PRId64 " hand=%s profile=%s syncResult=%d syncAttempted=%u triggerActive=%u value=%.9g changedSinceLastSync=%u lastChangeTime=%" PRId64
            " gripActive=%u gripFlags=0x%" PRIx64 " gripPositionValid=%u gripOrientationValid=%u gripPositionTracked=%u gripOrientationTracked=%u gripPosition=%s gripOrientation=%s"
            " aimActive=%u aimFlags=0x%" PRIx64 " aimPositionValid=%u aimOrientationValid=%u aimPositionTracked=%u aimOrientationTracked=%u aimPosition=%s aimOrientation=%s",
            frameCount, time, handName(i), handProfiles[i].text, syncResult, unsigned(syncAttempted), h.trigger.isActive, h.trigger.currentState, h.trigger.changedSinceLastSync, h.trigger.lastChangeTime,
            h.gripActive, uint64_t(gf), unsigned(bool(gf & XR_SPACE_LOCATION_POSITION_VALID_BIT)), unsigned(bool(gf & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT)),
            unsigned(bool(gf & XR_SPACE_LOCATION_POSITION_TRACKED_BIT)), unsigned(bool(gf & XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT)), gp, gq,
            h.aimActive, uint64_t(af), unsigned(bool(af & XR_SPACE_LOCATION_POSITION_VALID_BIT)), unsigned(bool(af & XR_SPACE_LOCATION_ORIENTATION_VALID_BIT)),
            unsigned(bool(af & XR_SPACE_LOCATION_POSITION_TRACKED_BIT)), unsigned(bool(af & XR_SPACE_LOCATION_ORIENTATION_TRACKED_BIT)), ap, aq);
    }
    static const char* hapticClassification(XrResult result) noexcept {
        if (result == XR_SUCCESS) return "api_success";
        if (result == XR_SESSION_NOT_FOCUSED) return "no_output_expected";
        if (result == XR_ERROR_PATH_UNSUPPORTED) return "unsupported";
        if (result == XR_SESSION_LOSS_PENDING || result == XR_ERROR_SESSION_LOST || result == XR_ERROR_INSTANCE_LOST) return "loss_pending";
        return "probe_failure";
    }
    void hapticLog(int hand, const char* operation, XrResult result, XrTime time, const char* reason) noexcept {
        char name[XR_MAX_RESULT_STRING_SIZE]{"unavailable"};
        if (instance) xrResultToString(instance, result, name);
        const bool apply = std::strcmp(operation, "apply") == 0;
        log("HAPTIC_API frame=%" PRIu64 " displayTime=%" PRId64 " hand=%s profile=%s subaction=%" PRIu64 " subactionPath=/user/hand/%s op=%s result=%d resultName=%s classification=%s duration=%s amplitude=%s frequency=%s reason=%s",
            frameCount, time, handName(hand), handProfiles[hand].text, uint64_t(handPaths[hand]), handName(hand), operation,
            result, name, hapticClassification(result), apply ? "100000000" : "not_applicable",
            apply ? "0.25" : "not_applicable", apply ? "0" : "not_applicable", reason);
    }
    void stopHaptics(const char* reason) noexcept {
        if (!session || !hapticAction) return;
        for (int i = 0; i != 2; ++i) {
            auto& state = haptics[i];
            if (!state.pending) continue;
            XrHapticActionInfo info{XR_TYPE_HAPTIC_ACTION_INFO};
            info.action = hapticAction;
            info.subactionPath = handPaths[i];
            const XrResult result = xrStopHapticFeedback(session, &info);
            hapticLog(i, "stop", result, frameDisplayTime, reason);
            noteLoss(result);
            if (result == XR_SUCCESS) state.pending = false;
            // The first immediate stop result remains the summary's result.
        }
    }
    void probeHaptics(int i, XrTime time) {
        auto& state = haptics[i];
        const auto& profile = handProfiles[i];
        if (!hapticProbe || state.attempted || runtimeExit || sessionState != XR_SESSION_STATE_FOCUSED ||
            syncResult != XR_SUCCESS || profile.queryResult != XR_SUCCESS || !profile.path ||
            (!hands[i].gripActive && !hands[i].aimActive)) return;
        bool suggested = false;
        for (const auto& suggestion : profileSuggestions)
            if (suggestion.path == profile.path && suggestion.result == XR_SUCCESS) suggested = true;
        if (!suggested) return;
        state.attempted = true;
        if (!state.boundChecked || state.boundProfile != profile.path) {
            state.boundChecked = true;
            state.boundProfile = profile.path;
            XrBoundSourcesForActionEnumerateInfo enumerate{XR_TYPE_BOUND_SOURCES_FOR_ACTION_ENUMERATE_INFO};
            enumerate.action = hapticAction;
            state.boundResult = xrEnumerateBoundSourcesForAction(session, &enumerate, 0, &state.boundCount, nullptr);
            noteLoss(state.boundResult);
            if (state.boundResult == XR_SUCCESS && state.boundCount) {
                // This action-wide opaque list is not evidence that a particular hand is bound.
                std::vector<XrPath> sources(state.boundCount);
                state.boundResult = xrEnumerateBoundSourcesForAction(session, &enumerate, static_cast<uint32_t>(sources.size()), &state.boundCount, sources.data());
                noteLoss(state.boundResult);
            }
            log("HAPTIC_BOUND frame=%" PRIu64 " displayTime=%" PRId64 " hand=%s profile=%s result=%d count=%u scope=action opaqueSources=1 classification=%s",
                frameCount, time, handName(i), profile.text, state.boundResult, state.boundCount,
                state.boundResult != XR_SUCCESS ? hapticClassification(state.boundResult) : state.boundCount ? "bound_action_not_hand_proof" : "unbound");
        }
        if (state.boundResult != XR_SUCCESS || !state.boundCount || runtimeExit) return;
        XrHapticActionInfo info{XR_TYPE_HAPTIC_ACTION_INFO};
        info.action = hapticAction;
        info.subactionPath = handPaths[i];
        XrHapticVibration vibration{XR_TYPE_HAPTIC_VIBRATION};
        vibration.duration = 100'000'000;
        vibration.frequency = XR_FREQUENCY_UNSPECIFIED;
        vibration.amplitude = 0.25f;
        state.applied = true;
        state.applyResult = xrApplyHapticFeedback(session, &info, reinterpret_cast<const XrHapticBaseHeader*>(&vibration));
        hapticLog(i, "apply", state.applyResult, time, "preflight");
        noteLoss(state.applyResult);
        state.pending = state.applyResult == XR_SUCCESS;
        state.stopResult = xrStopHapticFeedback(session, &info);
        hapticLog(i, "stop", state.stopResult, time, "immediate");
        noteLoss(state.stopResult);
        if (state.stopResult == XR_SUCCESS) state.pending = false;
    }
    void pollEvents() {
        XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
        while (true) {
            XrResult result = xrPollEvent(instance, &event);
            if (result == XR_EVENT_UNAVAILABLE) break;
            xrCheck(result, "xrPollEvent");
            switch (event.type) {
            case XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED: {
                const auto& state = *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                if (state.session != session) break;
                if (sessionState != state.state) forceSample = true;
                sessionState = state.state;
                char name[XR_MAX_STRUCTURE_NAME_SIZE]{};
                // Session states are logged numerically as well for unambiguous automated evidence.
                const char* names[]{"UNKNOWN", "IDLE", "READY", "SYNCHRONIZED", "VISIBLE", "FOCUSED", "STOPPING", "LOSS_PENDING", "EXITING"};
                unsigned index = static_cast<unsigned>(state.state);
                std::snprintf(name, sizeof(name), "%s", index < 9 ? names[index] : "OTHER");
                log("XR session state=%s(%d) time=%" PRId64, name, state.state, state.time);
                if (state.state != XR_SESSION_STATE_FOCUSED && state.state != XR_SESSION_STATE_STOPPING)
                    stopHaptics("focus_loss");
                if (state.state == XR_SESSION_STATE_READY && !running && !stop.load()) {
                    XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
                    begin.primaryViewConfigurationType = kStereo;
                    xrCheck(xrBeginSession(session, &begin), "xrBeginSession");
                    running = true;
                    status("OpenXR READY: session begun, waiting for valid stereo tracking");
                } else if (state.state == XR_SESSION_STATE_STOPPING && running) {
                    stopHaptics("stopping");
                    const XrResult endResult = xrEndSession(session);
                    log("xrEndSession result=%d", endResult);
                    noteLoss(endResult);
                    if (endResult == XR_SUCCESS) running = false;
                    xrCheck(endResult, "xrEndSession");
                } else if (state.state == XR_SESSION_STATE_EXITING || state.state == XR_SESSION_STATE_LOSS_PENDING) {
                    running = false;
                    runtimeExit = true;
                    status(state.state == XR_SESSION_STATE_EXITING ? "OpenXR runtime requested exit" : "OpenXR session loss pending; returning to manager");
                }
                break;
            }
            case XR_TYPE_EVENT_DATA_INSTANCE_LOSS_PENDING:
                runtimeExit = true;
                running = false;
                status("OpenXR instance loss pending; returning to manager");
                break;
            case XR_TYPE_EVENT_DATA_INTERACTION_PROFILE_CHANGED: {
                const auto& change = *reinterpret_cast<XrEventDataInteractionProfileChanged*>(&event);
                if (change.session != session) break;
                forceSample = true;
                profiles();
                break;
            }
            case XR_TYPE_EVENT_DATA_REFERENCE_SPACE_CHANGE_PENDING: {
                const auto& change = *reinterpret_cast<XrEventDataReferenceSpaceChangePending*>(&event);
                if (change.session != session) break;
                if (change.poseValid) {
                    const auto& p = change.poseInPreviousSpace.position;
                    const auto& q = change.poseInPreviousSpace.orientation;
                    log("reference space change type=%d changeTime=%" PRId64 " worldType=%d poseValid=%u position=(%.9g,%.9g,%.9g) orientation=(%.9g,%.9g,%.9g,%.9g); identity world remains runtime anchored",
                        change.referenceSpaceType, change.changeTime, worldType, change.poseValid, p.x, p.y, p.z, q.x, q.y, q.z, q.w);
                } else {
                    log("reference space change type=%d changeTime=%" PRId64 " worldType=%d poseValid=%u transform=unavailable; identity world remains runtime anchored",
                        change.referenceSpaceType, change.changeTime, worldType, change.poseValid);
                }
                pendingChangeTime = change.changeTime;
                pendingReferenceChange = true;
                break;
            }
            case XR_TYPE_EVENT_DATA_EVENTS_LOST:
                log("XR events lost=%u", reinterpret_cast<XrEventDataEventsLost*>(&event)->lostEventCount);
                break;
            default:
                log("XR event type=%d", event.type);
                break;
            }
            if (runtimeExit) return;
            event = {XR_TYPE_EVENT_DATA_BUFFER};
        }
    }

    void input(XrTime time, bool report) {
        hands = {};
        if (!runtimeExit && (!profilesInitialized || report)) profiles();
        XrActiveActionSet active{actionSet, XR_NULL_PATH};
        XrActionsSyncInfo sync{XR_TYPE_ACTIONS_SYNC_INFO};
        sync.countActiveActionSets = 1;
        sync.activeActionSets = &active;
        const XrResult previousSync = syncResult;
        syncAttempted = !runtimeExit;
        if (syncAttempted) {
            syncResult = xrSyncActions(session, &sync);
            noteLoss(syncResult);
        }
        if (syncAttempted && previousSync == XR_SUCCESS && syncResult == XR_SESSION_NOT_FOCUSED)
            stopHaptics("sync_focus_loss");
        if (!runtimeExit && syncAttempted && sessionState == XR_SESSION_STATE_FOCUSED && syncResult == XR_SUCCESS) {
            for (int i = 0; i != 2; ++i) {
                auto& h = hands[i];
                XrActionStateGetInfo get{XR_TYPE_ACTION_STATE_GET_INFO};
                get.subactionPath = handPaths[i];
                get.action = exitAction;
                xrCheck(xrGetActionStateBoolean(session, &get, &h.exit), "get exit action");
                if (h.exit.isActive && h.exit.changedSinceLastSync && h.exit.currentState) {
                    log("controller return button hand=%s active=%u changed=%u", handName(i), h.exit.isActive, h.exit.changedSinceLastSync);
                    controllerExit = true;
                }
                get.action = triggerAction;
                xrCheck(xrGetActionStateFloat(session, &get, &h.trigger), "get trigger action");
                for (int pose = 0; pose != 2; ++pose) {
                    get.action = pose == 0 ? gripAction : aimAction;
                    XrActionStatePose poseState{XR_TYPE_ACTION_STATE_POSE};
                    xrCheck(xrGetActionStatePose(session, &get, &poseState), "get pose action");
                    auto& location = pose == 0 ? h.grip : h.aim;
                    (pose == 0 ? h.gripActive : h.aimActive) = poseState.isActive;
                    if (poseState.isActive)
                        xrCheck(xrLocateSpace(pose == 0 ? gripSpaces[i] : aimSpaces[i], world, time, &location), "locate controller pose");
                }
            }
        }
        for (int i = 0; i != 2; ++i) {
            const auto& h = hands[i];
            const auto& old = previousHands[i];
            const bool changed = syncResult != previousSync || handProfiles[i].changed || h.trigger.isActive != old.triggerActive ||
                h.trigger.currentState != old.triggerValue || h.trigger.changedSinceLastSync ||
                h.trigger.lastChangeTime != old.triggerChangeTime || h.gripActive != old.gripActive || h.aimActive != old.aimActive ||
                h.grip.locationFlags != old.gripFlags || h.aim.locationFlags != old.aimFlags;
            if (report || changed) handSample(i, time);
            handProfiles[i].changed = false;
            previousHands[i] = {h.trigger.isActive, h.gripActive, h.aimActive, h.trigger.currentState,
                h.trigger.lastChangeTime, h.grip.locationFlags, h.aim.locationFlags};
            probeHaptics(i, time);
        }
        xrCheck(syncResult, "xrSyncActions");
    }

    void prepareHandGeometry() {
        drawGrip.fill(false);
        drawAim.fill(false);
        if (sessionState != XR_SESSION_STATE_FOCUSED || syncResult != XR_SUCCESS) return;
        constexpr XrSpaceLocationFlags validPose = XR_SPACE_LOCATION_POSITION_VALID_BIT
            | XR_SPACE_LOCATION_ORIENTATION_VALID_BIT;
        for (int hand = 0; hand != 2; ++hand) {
            const auto& state = hands[hand];
            drawGrip[hand] = state.gripActive && (state.grip.locationFlags & validPose) == validPose;
            drawAim[hand] = state.aimActive && (state.aim.locationFlags & validPose) == validPose;
            if (drawGrip[hand])
                gripModels[hand] = multiply(poseMatrix(state.grip.pose), kGripLocal);
            if (drawAim[hand]) {
                const Matrix pose = poseMatrix(state.aim.pose);
                for (size_t part = 0; part != kAimLocal.size(); ++part)
                    aimModels[hand][part] = multiply(pose, kAimLocal[part]);
            }
        }
    }

    void renderEye(int index, uint32_t image) {
        Eye& eye = eyes[index];
        vkCheck(vkResetCommandBuffer(commandBuffer, 0), "vkResetCommandBuffer");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        vkCheck(vkBeginCommandBuffer(commandBuffer, &begin), "vkBeginCommandBuffer");
        VkClearValue clear[2]{};
        clear[0].color = {{0.015f, 0.025f, 0.045f, 1.0f}};
        clear[1].depthStencil = {1.0f, 0};
        VkRenderPassBeginInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
        pass.renderPass = renderPass;
        pass.framebuffer = eye.framebuffers.at(image);
        pass.renderArea.extent = {eye.width, eye.height};
        pass.clearValueCount = 2;
        pass.pClearValues = clear;
        vkCmdBeginRenderPass(commandBuffer, &pass, VK_SUBPASS_CONTENTS_INLINE);
        VkViewport viewport{0, 0, float(eye.width), float(eye.height), 0, 1};
        VkRect2D scissor{{0, 0}, {eye.width, eye.height}};
        vkCmdSetViewport(commandBuffer, 0, 1, &viewport);
        vkCmdSetScissor(commandBuffer, 0, 1, &scissor);
        vkCmdBindPipeline(commandBuffer, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
        VkDeviceSize offset = 0;
        vkCmdBindVertexBuffers(commandBuffer, 0, 1, &vertices, &offset);
        const Matrix view = viewProjection(views[index]);
        vkCmdPushConstants(commandBuffer, pipelineLayout, VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(view), &view);
        vkCmdDraw(commandBuffer, worldRange.count, 1, worldRange.firstVertex, 0);
        if (sessionState == XR_SESSION_STATE_FOCUSED && syncResult == XR_SUCCESS) {
            auto drawHand = [&](const DrawRange& range, const Matrix& model) {
                const Matrix matrix = multiply(view, model);
                vkCmdPushConstants(commandBuffer, pipelineLayout, VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(matrix), &matrix);
                vkCmdDraw(commandBuffer, range.count, 1, range.firstVertex, 0);
            };
            for (int hand = 0; hand != 2; ++hand) {
                if (drawGrip[hand]) drawHand(handRanges[hand], gripModels[hand]);
                if (drawAim[hand])
                    for (const Matrix& model : aimModels[hand]) drawHand(handRanges[hand], model);
            }
        }
        vkCmdEndRenderPass(commandBuffer);
        vkCheck(vkEndCommandBuffer(commandBuffer), "vkEndCommandBuffer");
        vkCheck(vkResetFences(device, 1, &fence), "vkResetFences");
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &commandBuffer;
        vkCheck(vkQueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit");
        // Only the small submitted command buffer is awaited, never deviceWaitIdle per frame.
        // GPU completion is required before returning the runtime-owned image.
        VkResult result;
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        do {
            result = vkWaitForFences(device, 1, &fence, VK_TRUE, 10'000'000);
            if (result == VK_TIMEOUT && std::chrono::steady_clock::now() >= deadline)
                throw std::runtime_error("Vulkan submission fence timed out after 2 seconds");
        } while (result == VK_TIMEOUT);
        vkCheck(result, "vkWaitForFences");
    }

    void frame() {
        using Clock = std::chrono::steady_clock;
        // Pending change frames are sampled until the first crossing: selection
        // precedes WaitFrame, so every published timing has a real pre-wait start.
        bool report = forceSample || frameCount == 0 || (frameCount + 1) % 180 == 0 || pendingReferenceChange;
        const auto started = report ? Clock::now() : Clock::time_point{};
        auto mark = [&]() { return report ? Clock::now() : Clock::time_point{}; };
        auto elapsed = [&](Clock::time_point from, Clock::time_point to) -> int64_t {
            return report ? std::chrono::duration_cast<std::chrono::nanoseconds>(to - from).count() : 0;
        };
        int64_t waitFrameNs{}, inputLocateNs{}, imageWaitNs{}, renderSubmitFenceNs{}, endFrameNs{}, frameCpuNs{};
        XrFrameWaitInfo wait{XR_TYPE_FRAME_WAIT_INFO};
        XrFrameState state{XR_TYPE_FRAME_STATE};
        XrResult result = xrWaitFrame(session, &wait, &state);
        const auto waited = mark();
        waitFrameNs = elapsed(started, waited);
        noteLoss(result);
        xrCheck(result, "xrWaitFrame");
        XrFrameBeginInfo begin{XR_TYPE_FRAME_BEGIN_INFO};
        result = xrBeginFrame(session, &begin);
        noteLoss(result);
        xrCheck(result, "xrBeginFrame");
        ++frameCount;
        frameDisplayTime = state.predictedDisplayTime;
        forceSample = false;
        if (pendingReferenceChange && state.predictedDisplayTime >= pendingChangeTime) {
            log("reference space change effective frame=%" PRIu64 " displayTime=%" PRId64 " changeTime=%" PRId64 " worldType=%d",
                frameCount, state.predictedDisplayTime, pendingChangeTime, worldType);
            pendingReferenceChange = false;
        }
        bool submitStereo = false;
        XrViewState viewState{XR_TYPE_VIEW_STATE};
        XrSpaceLocation headLocation{XR_TYPE_SPACE_LOCATION};
        uint32_t viewCount{};
        auto samples = [&](bool submitted) {
            if (!report) return;
            log("FRAME_SAMPLE frame=%" PRIu64 " stereo=%" PRIu64 " predictedDisplayTime=%" PRId64 " predictedDisplayPeriod=%" PRId64
                " state=%d shouldRender=%u submitted=%u viewCount=%u viewFlags=0x%" PRIx64 " headFlags=0x%" PRIx64 " worldType=%d"
                " waitFrameNs=%" PRId64 " inputLocateNs=%" PRId64 " imageWaitNs=%" PRId64 " renderSubmitFenceNs=%" PRId64 " endFrameNs=%" PRId64 " frameCpuNs=%" PRId64,
                frameCount, stereoCount, state.predictedDisplayTime, state.predictedDisplayPeriod, sessionState, state.shouldRender,
                unsigned(submitted), viewCount, uint64_t(viewState.viewStateFlags), uint64_t(headLocation.locationFlags), worldType,
                waitFrameNs, inputLocateNs, imageWaitNs, renderSubmitFenceNs, endFrameNs, frameCpuNs);
            char p[96], q[96];
            poseText(headLocation, p, q);
            log("HEAD_SAMPLE frame=%" PRIu64 " displayTime=%" PRId64 " flags=0x%" PRIx64 " position=%s orientation=%s",
                frameCount, state.predictedDisplayTime, uint64_t(headLocation.locationFlags), p, q);
            for (int i = 0; i != 2; ++i) {
                XrSpaceLocation eye{XR_TYPE_SPACE_LOCATION};
                if (uint32_t(i) < viewCount) {
                    // XrViewState and XrSpaceLocation use the corresponding bit positions.
                    eye.locationFlags = viewState.viewStateFlags;
                    eye.pose = views[i].pose;
                }
                poseText(eye, p, q);
                log("EYE_SAMPLE frame=%" PRIu64 " displayTime=%" PRId64 " eye=%s flags=0x%" PRIx64 " position=%s orientation=%s",
                    frameCount, state.predictedDisplayTime, handName(i), uint64_t(eye.locationFlags), p, q);
            }
        };
        const auto inputStarted = mark();
        enum class Segment { Input, ImageWait, Render, None };
        Segment segment = Segment::Input;
        Clock::time_point segmentStarted = inputStarted;
        // End every successfully begun frame, including errors and shouldRender=false.
        try {
            input(state.predictedDisplayTime, report);
            prepareHandGeometry();
            if (!runtimeExit) {
                xrCheck(xrLocateSpace(head, world, state.predictedDisplayTime, &headLocation), "locate head");
                if (state.shouldRender || report) {
                    XrViewLocateInfo locate{XR_TYPE_VIEW_LOCATE_INFO};
                    locate.viewConfigurationType = kStereo;
                    locate.displayTime = state.predictedDisplayTime;
                    locate.space = world;
                    xrCheck(xrLocateViews(session, &locate, &viewState, 2, &viewCount, views.data()), "xrLocateViews");
                }
            }
            inputLocateNs = elapsed(inputStarted, mark());
            segment = Segment::None;
            constexpr XrViewStateFlags valid = XR_VIEW_STATE_POSITION_VALID_BIT | XR_VIEW_STATE_ORIENTATION_VALID_BIT;
            if (state.shouldRender && !stop.load() && !controllerExit && !runtimeExit &&
                viewCount == 2 && (viewState.viewStateFlags & valid) == valid) {
                for (int i = 0; i != 2; ++i) {
                    uint32_t image{};
                    XrSwapchainImageAcquireInfo acquire{XR_TYPE_SWAPCHAIN_IMAGE_ACQUIRE_INFO};
                    xrCheck(xrAcquireSwapchainImage(eyes[i].swapchain, &acquire, &image), "xrAcquireSwapchainImage");
                    XrSwapchainImageWaitInfo imageWait{XR_TYPE_SWAPCHAIN_IMAGE_WAIT_INFO};
                    imageWait.timeout = 10'000'000;
                    segment = Segment::ImageWait;
                    segmentStarted = mark();
                    const auto deadline = Clock::now() + std::chrono::seconds(2);
                    do {
                        result = xrWaitSwapchainImage(eyes[i].swapchain, &imageWait);
                        if (result == XR_TIMEOUT_EXPIRED && (stop.load() || Clock::now() >= deadline))
                            throw std::runtime_error("XR swapchain wait interrupted or timed out; destroying session without releasing an unwaited image");
                    } while (result == XR_TIMEOUT_EXPIRED);
                    imageWaitNs += elapsed(segmentStarted, mark());
                    segment = Segment::None;
                    xrCheck(result, "xrWaitSwapchainImage");
                    segment = Segment::Render;
                    segmentStarted = mark();
                    renderEye(i, image);
                    renderSubmitFenceNs += elapsed(segmentStarted, mark());
                    segment = Segment::None;
                    XrSwapchainImageReleaseInfo release{XR_TYPE_SWAPCHAIN_IMAGE_RELEASE_INFO};
                    xrCheck(xrReleaseSwapchainImage(eyes[i].swapchain, &release), "xrReleaseSwapchainImage");
                    auto& projection = projectionViews[i];
                    projection.pose = views[i].pose;
                    projection.fov = views[i].fov;
                    projection.subImage.swapchain = eyes[i].swapchain;
                    projection.subImage.imageRect = {{0, 0}, {int32_t(eyes[i].width), int32_t(eyes[i].height)}};
                    projection.subImage.imageArrayIndex = 0;
                }
                submitStereo = true;
            }
        } catch (...) {
            const auto failed = mark();
            if (segment == Segment::Input) inputLocateNs = elapsed(inputStarted, failed);
            else if (segment == Segment::ImageWait) imageWaitNs += elapsed(segmentStarted, failed);
            else if (segment == Segment::Render) renderSubmitFenceNs += elapsed(segmentStarted, failed);
            XrFrameEndInfo end{XR_TYPE_FRAME_END_INFO};
            end.displayTime = state.predictedDisplayTime;
            end.environmentBlendMode = blendMode;
            const auto endStarted = mark();
            result = xrEndFrame(session, &end);
            const auto ended = mark();
            endFrameNs = elapsed(endStarted, ended);
            frameCpuNs = elapsed(started, ended);
            noteLoss(result);
            log("error frame ended with zero layers result=%d", result);
            samples(false);
            throw;
        }
        XrCompositionLayerProjection projection{XR_TYPE_COMPOSITION_LAYER_PROJECTION};
        projection.space = world;
        projection.viewCount = 2;
        projection.views = projectionViews.data();
        const XrCompositionLayerBaseHeader* layers[]{reinterpret_cast<const XrCompositionLayerBaseHeader*>(&projection)};
        XrFrameEndInfo end{XR_TYPE_FRAME_END_INFO};
        end.displayTime = state.predictedDisplayTime;
        end.environmentBlendMode = blendMode;
        end.layerCount = submitStereo ? 1 : 0;
        end.layers = submitStereo ? layers : nullptr;
        const auto endStarted = mark();
        result = xrEndFrame(session, &end);
        const auto ended = mark();
        endFrameNs = elapsed(endStarted, ended);
        frameCpuNs = elapsed(started, ended);
        noteLoss(result);
        const bool submitted = submitStereo && result == XR_SUCCESS;
        if (submitted) {
            ++stereoCount;
            if (!firstStereo) {
                firstStereo = true;
                log("FIRST_STEREO_FRAME frame=%" PRIu64 " displayTime=%" PRId64 " views=2 viewFlags=0x%" PRIx64 " left=(%.3f,%.3f,%.3f) right=(%.3f,%.3f,%.3f)", frameCount, state.predictedDisplayTime, uint64_t(viewState.viewStateFlags), views[0].pose.position.x, views[0].pose.position.y, views[0].pose.position.z, views[1].pose.position.x, views[1].pose.position.y, views[1].pose.position.z);
                status("Real OpenXR stereo projection submitted: two Vulkan eyes, head-tracked cubes/grid");
            }
        }
        samples(submitted);
        xrCheck(result, "xrEndFrame");
    }

    static uint64_t parseInteger(const char* line, const char* prefix) {
        const char* start = line + std::strlen(prefix);
        if (*start < '0' || *start > '9') throw std::runtime_error("Shared file contains invalid nonnegative integer");
        errno = 0;
        char* end{};
        unsigned long long value = std::strtoull(start, &end, 10);
        if (errno == ERANGE || *end != '\0') throw std::runtime_error("Shared file integer is out of range or malformed");
        return static_cast<uint64_t>(value);
    }
    void updateSharedFile() {
        FILE* file = std::fopen(dataPath.c_str(), "r");
        if (!file) throw std::runtime_error("Cannot read manager private state file: " + std::string(std::strerror(errno)));
        char input[512]{};
        size_t size = std::fread(input, 1, sizeof(input) - 1, file);
        bool failed = std::ferror(file) || !std::feof(file);
        std::fclose(file);
        if (failed || size == 0) throw std::runtime_error("Manager private state file is empty, too long or unreadable");
        log("shared file input path=%s bytes=%zu content=%s", dataPath.c_str(), size, input);
        uint64_t generation{}, visits{};
        bool gotGeneration{}, gotVisits{}, gotWriter{};
        char* save{};
        for (char* line = strtok_r(input, "\n", &save); line; line = strtok_r(nullptr, "\n", &save)) {
            if (std::strncmp(line, "manager_generation=", 19) == 0 && !gotGeneration) {
                generation = parseInteger(line, "manager_generation="); gotGeneration = true;
            } else if (std::strncmp(line, "native_visits=", 14) == 0 && !gotVisits) {
                visits = parseInteger(line, "native_visits="); gotVisits = true;
            } else if ((!std::strcmp(line, "last_writer=manager") || !std::strcmp(line, "last_writer=native")) && !gotWriter) {
                gotWriter = true;
            } else throw std::runtime_error("Manager private state file has unknown or duplicate fields");
        }
        if (!gotGeneration || !gotVisits || !gotWriter || visits == std::numeric_limits<uint64_t>::max())
            throw std::runtime_error("Manager private state file has missing fields or overflowing session counter");
        char output[192];
        int length = std::snprintf(output, sizeof(output), "manager_generation=%" PRIu64 "\nnative_visits=%" PRIu64 "\nlast_writer=native\n", generation, visits + 1);
        std::string temporary = dataPath + ".native.tmp";
        int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0600);
        if (fd < 0) throw std::runtime_error("Cannot create private state temporary file");
        size_t written{};
        int error{};
        while (written < static_cast<size_t>(length)) {
            ssize_t result = ::write(fd, output + written, length - written);
            if (result < 0 && errno == EINTR) continue;
            if (result <= 0) { error = result < 0 ? errno : EIO; break; }
            written += static_cast<size_t>(result);
        }
        if (!error && ::fsync(fd) != 0) error = errno;
        if (::close(fd) != 0 && !error) error = errno;
        if (!error && ::rename(temporary.c_str(), dataPath.c_str()) != 0) error = errno;
        if (error) {
            ::unlink(temporary.c_str());
            throw std::runtime_error("Atomic native private state write failed: " + std::string(std::strerror(error)));
        }
        auto separator = dataPath.find_last_of('/');
        std::string directory = separator == std::string::npos ? "." : dataPath.substr(0, separator);
        int directoryFd = ::open(directory.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (directoryFd >= 0) {
            if (::fsync(directoryFd) != 0) log("directory fsync failed errno=%d", errno);
            ::close(directoryFd);
        }
        log("shared file committed generation=%" PRIu64 " native_visits=%" PRIu64 " last_writer=native (count is successful XR session creations)", generation, visits + 1);
    }

    void shutdown() noexcept {
        log("cleanup begin running=%u state=%d frames=%" PRIu64 " stereo=%" PRIu64, running, sessionState, frameCount, stereoCount);
        stopHaptics("shutdown");
        if (session && running && !runtimeExit) {
            XrResult result = xrRequestExitSession(session);
            log("xrRequestExitSession cleanup result=%d", result);
            noteLoss(result);
            // Bound the IDLE/READY-independent stop path. DestroySession remains valid if
            // runtime never sends STOPPING; do not call EndSession in an illegal state.
            auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(200);
            while (running && !runtimeExit && std::chrono::steady_clock::now() < deadline) {
                XrEventDataBuffer event{XR_TYPE_EVENT_DATA_BUFFER};
                result = xrPollEvent(instance, &event);
                noteLoss(result);
                if (result == XR_EVENT_UNAVAILABLE) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
                    continue;
                }
                if (XR_FAILED(result)) break;
                if (event.type == XR_TYPE_EVENT_DATA_SESSION_STATE_CHANGED) {
                    const auto& changed = *reinterpret_cast<XrEventDataSessionStateChanged*>(&event);
                    if (changed.session != session) continue;
                    sessionState = changed.state;
                    log("cleanup XR session state=%d", sessionState);
                    if (sessionState == XR_SESSION_STATE_STOPPING) {
                        stopHaptics("cleanup_stopping");
                        const XrResult endResult = xrEndSession(session);
                        log("cleanup xrEndSession result=%d", endResult);
                        noteLoss(endResult);
                        if (endResult == XR_SUCCESS) running = false;
                        else break;
                    } else if (sessionState == XR_SESSION_STATE_EXITING || sessionState == XR_SESSION_STATE_LOSS_PENDING) running = false;
                }
            }
        }
        for (int i = 0; i != 2; ++i) {
            const auto& state = haptics[i];
            const char* classification = !state.attempted ? "not_covered" :
                state.boundResult != XR_SUCCESS ? hapticClassification(state.boundResult) :
                !state.boundCount ? "unbound" :
                !state.applied ? "not_covered" :
                state.applyResult != XR_SUCCESS ? hapticClassification(state.applyResult) :
                state.stopResult != XR_SUCCESS ? hapticClassification(state.stopResult) : "api_preflight_success";
            log("HAPTIC_SUMMARY hand=%s enabled=%u attempted=%u applyCalled=%u boundResult=%d boundCount=%u applyResult=%d stopResult=%d pending=%u classification=%s physicalVibration=not_verified",
                handName(i), unsigned(hapticProbe), unsigned(state.attempted), unsigned(state.applied), state.boundResult, state.boundCount,
                state.applyResult, state.stopResult, unsigned(state.pending), classification);
        }
        if (device) {
            // Teardown only, not in the frame loop. Outstanding work must finish before destruction.
            log("cleanup vkDeviceWaitIdle result=%d", vkDeviceWaitIdle(device));
            for (auto& eye : eyes) {
                for (auto framebuffer : eye.framebuffers) if (framebuffer) vkDestroyFramebuffer(device, framebuffer, nullptr);
                for (auto view : eye.imageViews) if (view) vkDestroyImageView(device, view, nullptr);
                if (eye.depthView) vkDestroyImageView(device, eye.depthView, nullptr);
                if (eye.depth) vkDestroyImage(device, eye.depth, nullptr);
                if (eye.depthMemory) vkFreeMemory(device, eye.depthMemory, nullptr);
                if (eye.swapchain) log("destroy swapchain result=%d", xrDestroySwapchain(eye.swapchain));
            }
            if (vertices) vkDestroyBuffer(device, vertices, nullptr);
            if (vertexMemory) vkFreeMemory(device, vertexMemory, nullptr);
            if (fence) vkDestroyFence(device, fence, nullptr);
            if (commandPool) vkDestroyCommandPool(device, commandPool, nullptr);
            if (pipeline) vkDestroyPipeline(device, pipeline, nullptr);
            if (pipelineLayout) vkDestroyPipelineLayout(device, pipelineLayout, nullptr);
            if (fragmentShader) vkDestroyShaderModule(device, fragmentShader, nullptr);
            if (vertexShader) vkDestroyShaderModule(device, vertexShader, nullptr);
            if (renderPass) vkDestroyRenderPass(device, renderPass, nullptr);
        }
        for (auto space : aimSpaces) if (space) xrDestroySpace(space);
        for (auto space : gripSpaces) if (space) xrDestroySpace(space);
        if (head) xrDestroySpace(head);
        if (world) xrDestroySpace(world);
        if (session) log("destroy session result=%d", xrDestroySession(session));
        if (actionSet) xrDestroyActionSet(actionSet); // Also destroys its actions, after their spaces/session.
        if (device) vkDestroyDevice(device, nullptr);
        if (vkInstance) vkDestroyInstance(vkInstance, nullptr);
        if (instance) log("destroy instance result=%d", xrDestroyInstance(instance));
    }
};

void throwJava(JNIEnv* env, const char* message) {
    jclass exception = env->FindClass("java/lang/IllegalStateException");
    if (exception) { env->ThrowNew(exception, message); env->DeleteLocalRef(exception); }
}
void releaseReferences(JNIEnv* env, Probe* probe) {
    if (probe->surface) env->DeleteGlobalRef(probe->surface);
    if (probe->context) env->DeleteGlobalRef(probe->context);
    if (probe->activity) env->DeleteGlobalRef(probe->activity);
}
} // namespace

extern "C" JNIEXPORT jlong JNICALL
Java_io_github_zkwz_bs4pico_probe_platform_VrActivity_nativeStart(JNIEnv* env, jobject activity, jobject surface, jstring dataPath, jint activityId, jlong epoch, jboolean hapticProbe) {
    if (!surface || !dataPath) { throwJava(env, "Native XR requires a live Surface and private file path"); return 0; }
    Probe* probe = nullptr;
    try {
        probe = new Probe;
        probe->activityId = activityId;
        probe->epoch = epoch;
        probe->hapticProbe = hapticProbe == JNI_TRUE;
        if (env->GetJavaVM(&probe->vm) != JNI_OK) throw std::runtime_error("Cannot obtain JavaVM");
        probe->activity = env->NewGlobalRef(activity);
        probe->surface = env->NewGlobalRef(surface);
        jclass type = env->GetObjectClass(activity);
        if (!type) throw std::runtime_error("Cannot obtain VrActivity class");
        probe->statusMethod = env->GetMethodID(type, "onNativeStatus", "(Ljava/lang/String;)V");
        if (env->ExceptionCheck()) { env->DeleteLocalRef(type); throw std::runtime_error("Missing onNativeStatus callback"); }
        probe->exitMethod = env->GetMethodID(type, "onNativeExit", "()V");
        if (env->ExceptionCheck()) { env->DeleteLocalRef(type); throw std::runtime_error("Missing onNativeExit callback"); }
        jmethodID getContext = env->GetMethodID(type, "getApplicationContext", "()Landroid/content/Context;");
        env->DeleteLocalRef(type);
        if (!getContext || env->ExceptionCheck()) throw std::runtime_error("Missing application context");
        jobject context = env->CallObjectMethod(activity, getContext);
        if (!context || env->ExceptionCheck()) throw std::runtime_error("Cannot obtain application context");
        probe->context = env->NewGlobalRef(context);
        env->DeleteLocalRef(context);
        const char* path = env->GetStringUTFChars(dataPath, nullptr);
        if (!path) throw std::runtime_error("Cannot access private state path");
        try { probe->dataPath = path; } catch (...) { env->ReleaseStringUTFChars(dataPath, path); throw; }
        env->ReleaseStringUTFChars(dataPath, path);
        if (!probe->activity || !probe->surface || !probe->context) throw std::runtime_error("Cannot retain JNI lifecycle references");
        probe->worker = std::thread(&Probe::run, probe);
        return static_cast<jlong>(reinterpret_cast<intptr_t>(probe));
    } catch (const std::exception& error) {
        if (probe) { releaseReferences(env, probe); delete probe; }
        if (!env->ExceptionCheck()) throwJava(env, error.what());
        return 0;
    }
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_zkwz_bs4pico_probe_platform_VrActivity_nativeStop(JNIEnv* env, jobject, jlong handle) {
    if (!handle) return;
    auto* probe = reinterpret_cast<Probe*>(static_cast<intptr_t>(handle));
    probe->stop.store(true, std::memory_order_release);
    if (probe->worker.joinable()) probe->worker.join();
    releaseReferences(env, probe);
    probe->log("nativeStop joined worker and released Java lifecycle references");
    delete probe;
}
