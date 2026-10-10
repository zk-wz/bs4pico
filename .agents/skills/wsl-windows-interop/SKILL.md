---
name: wsl-windows-interop
description: 从 WSL 安全操作 Windows CLI、GUI 应用和长期进程；显式 EXE 路径、PowerShell 参数与环境隔离、UNC 文件交接、原生退出码及独立状态验证。用于跨系统启动、查询、部署和日志获取，不用于在 Windows 重复安装 WSL 构建环境。
---

# WSL → Windows 应用操作

## 适用边界

WSL 负责 Linux 开发/构建，Windows 负责只能在主机执行的应用、设备或 GUI。先复用已安装工具，只补齐任务必需依赖。不得为了调用 EXE 开启 Windows PATH 自动追加或 WSLENV 环境共享；不得把某个用户的盘符、发行版或 SDK 路径当成通用默认值。

## 1. 核实互通与真实路径

1. 读取 `/etc/wsl.conf` 的 `[interop]`；`enabled=true` 允许通过绝对路径启动 Windows EXE，`appendWindowsPath=false` 只关闭 PATH 自动追加，不关闭互通。
2. 优先从项目记录/用户提供路径查找宿主工具；必要时在 Windows 用 `Test-Path -LiteralPath` 和 `Get-Command` 核实。不要扫描整个 Windows 文件系统。
3. 区分 Linux 路径（`/mnt/c/.../tool.exe`）和 Windows 参数路径（`C:\...`）。EXE 路径用 WSL 形式，传给 Windows 程序的文件用 Windows 形式。
4. Node/Python/.NET 等 Windows CLI 入口优先显式运行宿主解释器 + 实际脚本，避免 `.cmd/.ps1` 内部依赖 PATH 或执行策略。不要拿 Linux Node 去运行需要 Windows 平台能力的包。
5. 先 `--version/--help`、只读 status/list，再进行启动/安装。已提供的实测失败为事实，不为确认它而重跑。

## 2. 复用 runner、隔离环境与工作目录

统一入口是 `.agents/skills/wsl-windows-interop/scripts/windows_interop.py`，只依赖 Python 标准库、现有 Windows PowerShell 和路径转换时的 `wslpath`；不安装工具、不修改执行策略。

每个 checkout 的宿主路径只写入被忽略的 `private/windows-tools.json`，不把本机路径作为脚本默认值。配置示例中的路径必须替换为已核实路径：

```json
{
  "powershell_exe": "/absolute/verified/path/powershell.exe",
  "cwd": "D:\\Tools\\Example",
  "env": {
    "APP_HOME": "D:\\Tools\\Example",
    "REMOVE_ONLY_FOR_CHILD": null
  },
  "aliases": {
    "example": {
      "exe": "D:\\Runtime\\node.exe",
      "prefix_args": ["D:\\Tools\\Example\\dist\\index.js"]
    }
  }
}
```

- `powershell_exe`：现有 PowerShell EXE 的绝对 **WSL** 路径。
- `cwd`：原生子进程的绝对 **Windows** 工作目录，不以 checkout 的 UNC 目录作为隐式 cwd。
- `env`：可省略；字符串覆盖或 `null` 删除，仅影响该原生子进程，继承其他宿主环境。不写注册表、全局 PATH、用户 Profile、WSLENV 或系统配置。
- `aliases`：别名到绝对 **Windows** `exe` 路径及可省略的 `prefix_args` 字符串数组；解释器、脚本入口与用户参数保持分离。不限定 PICO，也不运行 `.cmd/.ps1` 包装器来绕过策略。

在仓库根目录调用；默认配置位置按 runner 所在 checkout 确定，不依赖调用者 cwd：

```bash
python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py run example status --format json
WSL_WINDOWS_TOOLS_CONFIG=/verified/private/tools.json \
  python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py run example --version
python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py \
  --config /verified/private/tools.json run example --help
```

环境覆盖只放在当前命令前，不全局 `export`。`--config` 放在操作名前，优先于 `WSL_WINDOWS_TOOLS_CONFIG`；相对配置路径按调用者 cwd 解析。别名之后的参数直接传给原生程序，包括 `--`；无需添加额外的分隔符。原生非零退出码经 PowerShell `exit` 原样传播；Linux/WSL 最终只能呈现其退出状态范围（通常低 8 位），不要用后一条命令的成功遮蔽失败。

## 3. 参数与编码

- runner 把配置和动态参数编码为 UTF-8 JSON / Base64 数据，固定 PowerShell 脚本经 UTF-16LE `-EncodedCommand` 运行。只替换 Base64 数据槽，不把输入拼接成代码、不使用 `Invoke-Expression`；编码不是授权或安全策略修改。
- Windows PowerShell 5.1 的 `& $exe @args` 会丢失某些原生参数引用，不能用它代替 runner。runner 在 Python 用 `subprocess.list2cmdline(prefix_args + args)` 生成 Windows CRT 参数行，再用 `System.Diagnostics.ProcessStartInfo` 的 `Arguments` 和 `UseShellExecute=false` 启动程序；保留空参数、空格、Unicode、内嵌双引号和末尾反斜杠。
- stdin/stdout/stderr 通过固定 C# helper 并发转发原始 `BaseStream` 字节，不经 PowerShell 文本管道、不解码/重新编码、不用 `ReadToEnd` 缓冲整份输出；输入 EOF 关闭原生子进程 stdin。子进程退出后等待 stdout/stderr 排空，不等待可能仍阻塞的输入读取线程。适用于有限 CLI 和长期前台调用；runner 没有强制超时，监督/取消由调用者管理，不会主动后台化或额外启动 GUI。
- 不依赖 `ProcessStartInfo` 未重定向时的“继承句柄”：本机 WSL 实测会出现子进程退出 0、输出却未传回的情况。输出转发必须验证实际内容；并发排空两条输出管道，输入 EOF 和长进程即时输出也要单独验证。
- 该引用约定适用于 Windows CRT 兼容参数解析器（如 Node/Python）；自行解析原始命令行的程序仍可能使用不同语法。受 Windows 命令行长度限制，Base64 载荷还占用空间；大批量/大数据交接用目标程序的文件接口，不将其塞进 argv。CLI 不支持 NUL 参数。
- 只有现有执行策略允许时才用 `.ps1 -File`。WSL UNC 上的未签名脚本可能被 Windows PowerShell 拒绝；不修改/绕过执行策略，复用此固定 `-EncodedCommand` runner。不要临时添加 `-ExecutionPolicy Bypass`。
- Windows 输出可能带 CRLF、BOM 或主机代码页；JSON 优先结构化读取，必要时显式 UTF-8 输出编码。二进制截图/压缩包不能经过 PowerShell 文本管道；让程序直接写文件。
- 不打印凭据、token 或整份环境。日志应只记录版本、非秘密路径、操作和状态。

## 4. 长进程与 GUI

启动器可能输出“成功”后长期驻留，直到 GUI/模拟器退出。不要用短超时杀掉启动器及其子进程，也不要把前台不退出误判为启动失败。

1. 独立命名并保留启动会话；readiness 用程序真实 ready 日志、端口或专用 status。
2. 从独立 Windows 调用查询应用/设备状态；进程存在不等于启动完成。设备场景还需连接、启动完成和应用运行证据。
3. 有限命令允许超时；长期会话使用监督服务/无短期限启动。异步结果自动交付时不循环轮询。
4. 停止通过应用官方 stop/quit 或特定 PID；不要 `taskkill /IM` 误杀用户其他实例，不删除用户数据或锁文件来“重置”。
5. 用户可能同时使用桌面，默认不抢焦点、不注入全局鼠标。CLI 不能完成的空间/GUI 步骤，先准备稳定场景，再用 Ask 明确验证目标、准确窗口、操作、完成后停在哪里；等用户反馈后采集状态。不能把普通屏幕坐标点击、消息投递成功或进程存在算作空间交互通过。
6. 如果 GUI 在 WSL interop 下无法维持会话，记录具体失败，选择 Windows 原生启动通道；不要通过重装环境或全局关闭安全策略规避。
7. 最小化/遮挡会影响 GPU 窗口显示、截图和性能。通用入口默认拒绝最小化窗口且不抢焦点；有明确授权时可使用下述临时前台租约及最小化恢复。用户中途切走优先，不反复激活、不保持置顶；截图后确认实际场景，而不是仅确认 PNG 文件存在。
8. 包级 force-stop/terminate 可用于明确授权的后台清理或冷启动条件，但强杀不能替代正常 Back/Home/close 的资源释放与恢复验证。

## 5. 文件交接

构建源码、SDK、缓存和中间文件保留 Linux 文件系统。Windows 消费最终产物：

```bash
python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py path ./build/artifact.apk
ARTIFACT="$(python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py path ./build/artifact.apk)"
python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py run example import "$ARTIFACT"
```

`path` 不要求 Windows 工具配置；先将相对 Linux 路径按调用者 cwd 解析成绝对路径，再调用实际安装的 `wslpath -w`。保留路径中的空格和 Unicode，不手写盘符/发行版映射；路径转换本身不证明文件存在或 Windows 可读。Linux 文件系统路径通常映射为 `\\wsl.localhost\<发行版>\...`。发行版名由 `wslpath` 输出确定，不能猜。先通过已配置的只读宿主工具检查可读，再观察消费命令实际成功退出。

- UNC 可读不代表所有程序支持 UNC。若程序确实不支持，只复制最终产物到独立 Windows 临时目录，再安装/导入；不要复制整个 checkout 或工具链。
- Linux 与 Windows 两份仓库不会自动同步。指出正在修改哪份；不覆盖另一份未提交变更。
- 日志/截图让 Windows 程序直接写文件；支持 UNC 时直接落到 WSL 证据目录，否则仅复制最终证据。确认文件可解码及内容，不仅报告命令成功。
- 优先产品 CLI 的截图、日志和状态接口。若截图确实遗漏 GPU/空间合成层，保留 CLI 图像作为限制证据，再对精确窗口使用有界 Windows 捕获后备；不能把背景/启动器截图当作应用显示成功。普通 ADB/UI 坐标操作不等于空间窗口输入。
- 交接记录保存产物路径、SHA256、目标设备/实例、安装命令、启动结果；明确产物是否覆盖或保留。

精确窗口捕获也复用同一 runner 与私有配置：

```bash
python3 .agents/skills/wsl-windows-interop/scripts/windows_interop.py capture \
  --process exact-process-name --title 'Exact full window title' \
  --output private/validation/window.png
```

`--process` 是不含 `.exe` 的完整进程名，`--title` 是完整窗口标题；二者区分大小写，不按 AVD 名或标题子串匹配。定位对象是 `Get-Process` 的主窗口，不枚举同一进程的所有顶层窗口，不能用于该进程的任意多窗口选择。只允许恰好一个匹配且有主窗口句柄的进程，零个或多个均报错；默认不调整焦点、不恢复最小化窗口。

用户已授权时可加 `--foreground`，需要恢复最小化窗口时同时加 `--restore-minimized`。仅借用精确目标窗口的前台；原前台无法识别为唯一可交还主窗口时不激活，按需无激活恢复。激活后一次 DWM 合成及 200ms 重绘，完成 PrintWindow 后、PNG 编码前释放：仍由本次持有焦点时尝试交还原窗口，原来最小化则恢复最小化；交还被系统拒绝则最小化目标兜底。用户已切走则不抢回、不改变其新焦点。不存在持续前台、循环激活、置顶或键鼠注入。

stderr JSON 记录实际 `foregroundAtCapture`、最小化前后状态、`foregroundBorrowed`、`previousFocusRestored`、`focusRelease` 与 `focusScopeMs`；请求前台不保证取得前台，最小化兜底也不代表交还焦点成功。沿用 `GetWindowRect` / `PrintWindow(..., 2)` 到 PNG，不捕获整个桌面。GPU/空间合成层仍可能输出黑色、背景或旧帧；成功退出/非空 PNG 不证明视觉内容正确，必须查看图像。未运行目标时只报告缺失，不为了截图重启模拟器。

## 6. 验证与报告

每条结论有独立证据：

| 结论 | 所需证据 |
|---|---|
| 互通可用 | Windows EXE 实际执行且状态返回 |
| 工具可用 | 对应宿主版本/help 输出 |
| 应用启动 | 官方 ready/status + 必需服务/设备状态 |
| 文件交接 | Windows 可读 + 消费命令成功 |
| 部署成功 | 正确目标上的安装/包信息 |
| 行为通过 | 实际 UI、业务状态、日志或运行场景，不以进程存在代替 |

工具失败时先区分路径、权限、工作目录、环境、编码、连接和目标能力。只采取最小修复，不运行全套 setup/doctor --fix，也不修改全局配置。报告已验证项、未验证项及最小缺失前提。

Linux 与 Windows 的 ADB/调试服务通常是两套进程。Linux CLI 没设备时，先查看 Windows 设备列表与服务监听地址，再只读检查 WSL 是否能连接；`127.0.0.1` 绑定在 WSL NAT 下不保证互通。优先显式调用已工作的 Windows 工具。开放服务、重绑 `0.0.0.0`、改防火墙或转发端口属于环境/安全变更，须先询问，不能为迁就某个 CLI 自动执行。

## 本仓库应用

构建说明见 `docs/build/README.md`，Windows 宿主历史记录及产品限制见 `docs/device-validation/WINDOWS_EMULATOR_VALIDATION.md`。`prototypes/spatial-openxr/windows-tools.sh pico|adb <args>` 是 `run` 的薄适配器，别名及宿主路径来自同一私有配置；`prototypes/spatial-openxr/capture-emulator.py --output PATH`（兼容旧 `--out`）保留 PICO 进程名和完整默认标题，可用 `--title` 指定实际完整标题。该 PICO 入口按根 `AGENTS.md` 的用户授权默认传 `--foreground --restore-minimized`，仅借用截图期间的前台；`--background` 跳过激活与最小化恢复，用于诊断对比，不改变通用入口的无焦点默认值。

已收敛的重复操作：宿主解释器/CLI 入口与前置参数、进程局部环境/cwd、安全动态参数传输、Windows CRT 引用、原生退出码与并发原始字节 I/O 转发、相对 Linux 路径转换、可选授权前台激活的精确窗口 PNG 捕获。新调用复用这些入口，不再复制 PowerShell 拼接、`wslpath` 和 `PrintWindow` 脚本。本 skill 不依赖 PICO；设备操作仍读取对应产品 skill 并使用真实 CLI 表面。
