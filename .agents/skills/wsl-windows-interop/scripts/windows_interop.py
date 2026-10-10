#!/usr/bin/env python3
"""Run configured Windows executables or capture one exact window from WSL."""

import argparse
import base64
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys


# Only Base64 JSON data replaces the marker; executable PowerShell stays fixed.
_PAYLOAD_MARKER = "__BASE64_JSON_DATA__"
_DECODE = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
try {
    $data = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__BASE64_JSON_DATA__')) | ConvertFrom-Json
"""
_FAILURE = r"""
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
"""
_RUN = _DECODE + r"""
    Add-Type -TypeDefinition @"
using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
public static class NativeForwarding {
 public static int Run(ProcessStartInfo start) {
  using (Process child = Process.Start(start)) {
   Stream childInput = child.StandardInput.BaseStream;
   Stream childOutput = child.StandardOutput.BaseStream;
   Stream childError = child.StandardError.BaseStream;
   // Dedicated background pumps need no PowerShell runspace and never decode bytes.
   Task stdout = Task.Factory.StartNew(() => {
    Stream output = Console.OpenStandardOutput();
    childOutput.CopyTo(output);
    output.Flush();
   }, TaskCreationOptions.LongRunning);
   Task stderr = Task.Factory.StartNew(() => {
    Stream error = Console.OpenStandardError();
    childError.CopyTo(error);
    error.Flush();
   }, TaskCreationOptions.LongRunning);
   Task.Factory.StartNew(() => {
    try {
     Stream input = Console.OpenStandardInput();
     byte[] buffer = new byte[16384];
     int count;
     while ((count = input.Read(buffer, 0, buffer.Length)) != 0) {
      childInput.Write(buffer, 0, count);
      childInput.Flush();
     }
    } catch (IOException) {
     // The child may exit without consuming all input.
    } catch (ObjectDisposedException) {
     // Child exit closes its input while this background pump may still be reading.
    } finally {
     try { childInput.Close(); } catch (IOException) {}
    }
   }, TaskCreationOptions.LongRunning);
   child.WaitForExit();
   int code = child.ExitCode;
   childInput.Close();
   // Drain both output pipes, but never wait for a blocked console-input reader.
   Task.WaitAll(stdout, stderr);
   return code;
  }
 }
}
"@
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $data.exe
    $start.Arguments = $data.arguments
    $start.WorkingDirectory = $data.cwd
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($entry in $data.env.PSObject.Properties) {
        if ($null -eq $entry.Value) {
            $start.EnvironmentVariables.Remove($entry.Name)
        } else {
            $start.EnvironmentVariables[$entry.Name] = [string]$entry.Value
        }
    }
    $code = [NativeForwarding]::Run($start)
    exit $code
""" + _FAILURE
_CAPTURE = _DECODE + r'''
    Add-Type -AssemblyName System.Drawing
    Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public class WindowCapture {
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h,out RECT r);
 [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr h);
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr h);
 [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h,int command);
 [DllImport("dwmapi.dll")] public static extern int DwmFlush();
 [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h,IntPtr dc,uint f);
}
"@
    [WindowCapture]::SetProcessDPIAware() | Out-Null
    $targets = @(Get-Process | Where-Object {
        $_.ProcessName -ceq $data.process -and $_.MainWindowTitle -ceq $data.title -and
        $_.MainWindowHandle -ne [IntPtr]::Zero
    })
    if ($targets.Count -ne 1) {
        throw "Expected exactly one matching window; found $($targets.Count). Process and full title must match exactly."
    }
    $handle = $targets[0].MainWindowHandle
    $previousForeground = [WindowCapture]::GetForegroundWindow()
    $foregroundBefore = $previousForeground -eq $handle
    $minimizedBefore = [WindowCapture]::IsIconic($handle)
    $previousFocusUsable = [WindowCapture]::IsWindow($previousForeground) -and ![WindowCapture]::IsIconic($previousForeground)
    $previousOwner = @()
    if ($previousFocusUsable -and !$foregroundBefore) {
        $previousOwner = @(Get-Process | Where-Object { $_.MainWindowHandle -eq $previousForeground })
    }
    $previousFocusUsable = $previousFocusUsable -and ($foregroundBefore -or $previousOwner.Count -eq 1)
    $focusReturnError = $null
    $borrowed = $false
    $restoredWithoutFocus = $false
    $foregroundAtCapture = $null
    $release = 'not_borrowed'
    $saved = $false
    $bitmap = $null
    $focusTimer = $null
    try {
        try {
            if ($minimizedBefore -and !$data.restoreMinimized) {
                throw 'Window is minimized; restore it or explicitly authorize --foreground --restore-minimized.'
            }
            if ($data.foreground) {
                $focusTimer = [Diagnostics.Stopwatch]::StartNew()
                if ($minimizedBefore) {
                    if ($foregroundBefore -or $previousFocusUsable) {
                        $borrowed = $true
                        [WindowCapture]::ShowWindow($handle,9) | Out-Null
                    } else {
                        # A null/disappearing foreground means the user may be
                        # switching. Restore without activation, not a takeover.
                        $restoredWithoutFocus = $true
                        [WindowCapture]::ShowWindow($handle,4) | Out-Null
                    }
                }
                # Do not reassert focus if the user switched during this attempt.
                if ($previousFocusUsable -and [WindowCapture]::GetForegroundWindow() -eq $previousForeground -and !$foregroundBefore) {
                    $borrowed = $true
                    [WindowCapture]::SetForegroundWindow($handle) | Out-Null
                    if ([WindowCapture]::GetForegroundWindow() -eq $previousForeground) {
                        $shell = New-Object -ComObject WScript.Shell
                        try { $shell.AppActivate([int]$targets[0].Id) | Out-Null }
                        finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
                    }
                }
                [WindowCapture]::DwmFlush() | Out-Null
                Start-Sleep -Milliseconds 200
            }
            if ([WindowCapture]::IsIconic($handle)) { throw 'Window remains minimized; capture was not attempted.' }
            $rect = New-Object WindowCapture+RECT
            if (![WindowCapture]::GetWindowRect($handle,[ref]$rect)) { throw 'GetWindowRect failed' }
            $width = $rect.Right - $rect.Left
            $height = $rect.Bottom - $rect.Top
            if ($width -le 0 -or $height -le 0) { throw 'Window has no capture area' }
            $bitmap = New-Object System.Drawing.Bitmap($width,$height)
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $dc = $graphics.GetHdc()
                try {
                    $foregroundAtCapture = [WindowCapture]::GetForegroundWindow() -eq $handle
                    if (![WindowCapture]::PrintWindow($handle,$dc,2)) { throw 'PrintWindow failed' }
                } finally { $graphics.ReleaseHdc($dc) }
            } finally { $graphics.Dispose() }
        } finally {
            # Release before PNG encoding. A user focus change wins; no retry.
            if ($borrowed -and [WindowCapture]::GetForegroundWindow() -eq $handle) {
                if ($previousForeground -ne $handle -and [WindowCapture]::IsWindow($previousForeground) -and ![WindowCapture]::IsIconic($previousForeground)) {
                    [WindowCapture]::SetForegroundWindow($previousForeground) | Out-Null
                    if ([WindowCapture]::GetForegroundWindow() -eq $handle -and $previousOwner.Count -eq 1) {
                        try {
                            $previousOwner[0].Refresh()
                            if ($previousOwner[0].MainWindowHandle -eq $previousForeground -and [WindowCapture]::GetForegroundWindow() -eq $handle) {
                                $shell = New-Object -ComObject WScript.Shell
                                try { $shell.AppActivate([int]$previousOwner[0].Id) | Out-Null }
                                finally { [Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) | Out-Null }
                            }
                        } catch { $focusReturnError = $_.Exception.Message }
                    }
                }
                $current = [WindowCapture]::GetForegroundWindow()
                if ($current -eq $previousForeground -and $current -ne $handle) {
                    $release = 'restored'
                    if ($minimizedBefore -and [WindowCapture]::GetForegroundWindow() -ne $handle) {
                        [WindowCapture]::ShowWindow($handle,7) | Out-Null
                        $release = 'restored_and_reminimized'
                    }
                } elseif ($current -ne $handle) {
                    $release = 'focus_changed_during_return'
                } else {
                    [WindowCapture]::ShowWindow($handle,6) | Out-Null
                    $release = 'return_unavailable_target_minimized'
                }
            } elseif ($borrowed) {
                $release = 'focus_changed_no_return'
            } elseif ($restoredWithoutFocus -and [WindowCapture]::GetForegroundWindow() -ne $handle) {
                [WindowCapture]::ShowWindow($handle,7) | Out-Null
                $release = 'reminimized_without_focus'
            }
            if ($focusTimer) { $focusTimer.Stop() }
        }
        $bitmap.Save($data.output,[System.Drawing.Imaging.ImageFormat]::Png)
        $saved = $true
    } finally {
        if ($bitmap) { $bitmap.Dispose() }
        [Console]::Error.WriteLine((@{
            mechanism = 'PrintWindow'; processId = $targets[0].Id; saved = $saved;
            foregroundRequested = [bool]$data.foreground; foregroundBefore = $foregroundBefore;
            foregroundAtCapture = $foregroundAtCapture;
            foregroundAfter = ([WindowCapture]::GetForegroundWindow() -eq $handle);
            minimizedBefore = $minimizedBefore; minimizedAfter = [WindowCapture]::IsIconic($handle);
            previousFocusUsableBefore = $previousFocusUsable; foregroundBorrowed = $borrowed;
            previousMainWindowOwners = $previousOwner.Count;
            previousFocusRestored = ([WindowCapture]::GetForegroundWindow() -eq $previousForeground);
            focusReturnError = $focusReturnError;
            focusRelease = $release; focusScopeMs = $(if ($focusTimer) { $focusTimer.Elapsed.TotalMilliseconds } else { $null })
        } | ConvertTo-Json -Compress))
    }
    exit 0
''' + _FAILURE


def windows_path(path):
    """Resolve a Linux path before asking the installed wslpath for its Windows form."""
    result = subprocess.run(
        ["wslpath", "-w", str(Path(path).resolve())],
        check=True, stdout=subprocess.PIPE, text=True,
    )
    return result.stdout.rstrip("\r\n")


def load_config(config_path=None):
    path = config_path or os.environ.get("WSL_WINDOWS_TOOLS_CONFIG")
    if path is None:
        path = Path(__file__).resolve().parents[4] / "private/windows-tools.json"
    with Path(path).open(encoding="utf-8") as handle:
        config = json.load(handle)
    powershell = config.get("powershell_exe")
    if not isinstance(powershell, str) or not powershell.startswith("/"):
        raise ValueError("powershell_exe must be an absolute WSL path to the existing PowerShell EXE")
    cwd = config.get("cwd")
    if not isinstance(cwd, str) or not ntpath.isabs(cwd):
        raise ValueError("cwd must be an absolute Windows directory")
    environment = config.get("env", {})
    if not isinstance(environment, dict) or any(
        not isinstance(key, str) or not key or "=" in key or "\0" in key
        or (value is not None and (not isinstance(value, str) or "\0" in value))
        for key, value in environment.items()
    ):
        raise ValueError("env must map environment names to strings or null")
    return config


def powershell_call(config, script, payload):
    data = base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")
    encoded = base64.b64encode(script.replace(_PAYLOAD_MARKER, data).encode("utf-16le")).decode("ascii")
    # No timeout, shell, execution-policy override, profile or output text pipe.
    return subprocess.run([
        config["powershell_exe"], "-NoLogo", "-NoProfile", "-NonInteractive",
        "-EncodedCommand", encoded,
    ]).returncode


def run_alias(config, alias, arguments):
    tools = config.get("aliases", {})
    if not isinstance(tools, dict) or alias not in tools:
        raise ValueError(f"Unknown Windows tool alias: {alias}")
    tool = tools[alias]
    if not isinstance(tool, dict):
        raise ValueError(f"Alias {alias} must contain exe and optional prefix_args")
    exe = tool.get("exe")
    prefix = tool.get("prefix_args", [])
    if not isinstance(exe, str) or not ntpath.isabs(exe) or "\0" in exe:
        raise ValueError(f"Alias {alias}: exe must be an absolute Windows executable path")
    if not isinstance(prefix, list) or any(not isinstance(arg, str) or "\0" in arg for arg in prefix):
        raise ValueError(f"Alias {alias}: prefix_args must be an array of strings")
    return powershell_call(config, _RUN, {
        "exe": exe,
        # Windows CRT quoting, not PowerShell native argument-array expansion.
        "arguments": subprocess.list2cmdline(prefix + arguments),
        "cwd": config["cwd"],
        "env": config.get("env", {}),
    })


def capture_window(config, process, title, output, foreground=False, restore_minimized=False):
    if restore_minimized and not foreground:
        raise ValueError("Restoring a minimized capture target requires --foreground")
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    code = powershell_call(config, _CAPTURE, {
        "process": process, "title": title, "output": windows_path(output),
        "foreground": foreground, "restoreMinimized": restore_minimized,
    })
    if code != 0:
        return code
    if not output.is_file() or output.stat().st_size == 0:
        raise ValueError("Windows capture did not produce a nonempty file")
    print(output)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="JSON config; otherwise WSL_WINDOWS_TOOLS_CONFIG or checkout private/windows-tools.json")
    commands = parser.add_subparsers(dest="operation", required=True)
    runner = commands.add_parser("run", help="Run an executable alias with unchanged argument boundaries")
    runner.add_argument("alias")
    runner.add_argument("arguments", nargs=argparse.REMAINDER)
    converter = commands.add_parser("path", help="Convert a relative or absolute Linux path using wslpath")
    converter.add_argument("linux_path")
    capture = commands.add_parser("capture", help="PrintWindow capture of one exact process name and full window title")
    capture.add_argument("--process", required=True, help="Exact case-sensitive process name, without .exe")
    capture.add_argument("--title", required=True, help="Exact case-sensitive full window title (not an AVD substring)")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--foreground", action="store_true",
                         help="Temporarily foreground the authorized target, yielding to user focus changes")
    capture.add_argument("--restore-minimized", action="store_true",
                         help="With --foreground and user authorization, restore only the target during capture")
    args = parser.parse_args(argv)
    if args.operation == "capture" and args.restore_minimized and not args.foreground:
        parser.error("--restore-minimized requires --foreground")
    try:
        if args.operation == "path":
            print(windows_path(args.linux_path))
            return 0
        config = load_config(args.config)
        if args.operation == "run":
            return run_alias(config, args.alias, args.arguments)
        return capture_window(config, args.process, args.title, args.output, args.foreground, args.restore_minimized)
    except subprocess.CalledProcessError as error:
        return error.returncode
    except (OSError, ValueError) as error:
        print(f"windows-interop: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
