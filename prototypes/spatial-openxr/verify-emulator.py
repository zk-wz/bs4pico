#!/usr/bin/env python3
"""Real debug-APK lifecycle smoke; Windows ADB, no mock runtime or spatial coordinate taps."""
import argparse
from pathlib import Path
import re
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, required=True)
parser.add_argument("--cycles", type=int, default=5)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
bridge = Path(__file__).resolve().with_name("windows-tools.sh")
pkg = "io.github.zkwz.bs4pico.probe"
probe_pid = None

def adb(*parts):
    result = subprocess.run([str(bridge), "adb", "-s", "emulator-5554", *parts],
        text=True, capture_output=True, timeout=45, check=True)
    return result.stdout

def log():
    # Pico tag snapshots are bounded/client-filtered. ADB's device-side filter preserves all probe transitions.
    pid_filter = ["--pid=" + probe_pid] if probe_pid else []
    return adb("logcat", "-d", "-v", "threadtime", *pid_filter, "-s", "BS4PicoProbe:I", "BS4PicoXR:I", "AndroidRuntime:E")

def start(activity, action=None, direct=False):
    cmd = ["shell", "am", "start", "--activity-single-top", "-n", pkg + "/.platform." + activity]
    if action: cmd += ["--es", "probe_action", action]
    if direct: cmd += ["--ez", "direct", "true"]
    adb(*cmd)

def state():
    text = adb("shell", "run-as", pkg, "cat", "files/switch-probe.txt")
    return {key: value for key, value in (line.split("=", 1) for line in text.splitlines())}

def await_log(marker, baseline, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = log()
        if current.count(marker) > baseline: return current
        time.sleep(0.4)
    raise RuntimeError("Missing new runtime evidence: " + marker)

def mark_count(marker): return log().count(marker)

try:
    adb("shell", "am", "force-stop", pkg)
    start("VrActivity", direct=True)
    probe_pid = adb("shell", "pidof", pkg).strip()
    await_log("FIRST_STEREO_FRAME", 0)
    print("direct native cold start: real stereo frame submitted", flush=True)
    # First cycle deliberately relaunches the manager while VR is still alive.
    # PICO can retain both tasks; the app must retire the previous scene itself.
    for cycle in range(args.cycles):
        entered = mark_count("FIRST_STEREO_FRAME")
        stopped = mark_count("destroy session result=0")
        resumed = mark_count("onResume data=")
        start("LaunchActivity", "enter")
        await_log("FIRST_STEREO_FRAME", entered)
        native = state()
        if native["last_writer"] != "native": raise RuntimeError("Native did not update private data")
        activities = adb("shell", "dumpsys", "activity", "activities")
        if re.search(r"\* Hist.*" + re.escape(pkg) + r"/\.platform\.LaunchActivity", activities):
            raise RuntimeError("Manager Activity remained alive during VR")
        args.out.joinpath(f"cycle-{cycle + 1}-native-activities.txt").write_text(activities)
        adb("shell", "input", "keyevent", "KEYCODE_BACK")
        await_log("destroy session result=0", stopped)
        await_log("onResume data=", resumed)
        returned = state()
        if returned != native: raise RuntimeError("Returned manager lost native private data")
        print(f"cycle {cycle + 1}: stereo, manager destroyed, Back cleanup, shared data {returned}", flush=True)

    # Manager recreation retains durable data; debug extras invoke the same Activity.recreate path.
    restored = mark_count("onCreate restored=true")
    manager_state = state()
    start("LaunchActivity", "recreate")
    await_log("onCreate restored=true", restored)
    if state() != manager_state: raise RuntimeError("Manager recreation lost durable data")
    print("manager recreation: durable data preserved", flush=True)

    entered = mark_count("FIRST_STEREO_FRAME")
    start("LaunchActivity", "enter")
    await_log("FIRST_STEREO_FRAME", entered)
    restored = mark_count("onCreate restored=true")
    stopped = mark_count("destroy session result=0")
    entered = mark_count("FIRST_STEREO_FRAME")
    before_recreate = state()
    start("VrActivity", "recreate")
    await_log("onCreate restored=true", restored)
    await_log("destroy session result=0", stopped)
    await_log("FIRST_STEREO_FRAME", entered)
    after_recreate = state()
    if after_recreate["manager_generation"] != before_recreate["manager_generation"]:
        raise RuntimeError("VR recreation lost manager generation")
    if int(after_recreate["native_visits"]) <= int(before_recreate["native_visits"]):
        raise RuntimeError("VR recreation did not persist a successful new session")
    print("native recreation: old session destroyed, new stereo session rendered", flush=True)

    # Delivering a new Intent to the existing Activity produces genuine Android
    # onPause/onResume here. This is separate from PICO's system Home overlay.
    stopped = mark_count("destroy session result=0")
    entered = mark_count("FIRST_STEREO_FRAME")
    start("VrActivity")
    await_log("destroy session result=0", stopped)
    await_log("FIRST_STEREO_FRAME", entered)
    print("native pause/resume via new Intent: teardown and fresh stereo passed", flush=True)

    visible = mark_count("XR session state=VISIBLE(4)")
    unfocused = mark_count("xrSyncActions=XR_SESSION_NOT_FOCUSED state=4")
    adb("shell", "input", "keyevent", "KEYCODE_HOME")
    await_log("XR session state=VISIBLE(4)", visible)
    await_log("xrSyncActions=XR_SESSION_NOT_FOCUSED state=4", unfocused)
    print("Home confirmation overlay: visible session, actions unfocused; confirm/cancel requires manual spatial input", flush=True)
    stopped = mark_count("destroy session result=0")
    resumed = mark_count("onResume data=")
    # Do not drive the user's mouse or pretend a 2D coordinate tap confirms the
    # spatial dialog. The debug return entry exercises the real app cleanup.
    start("VrActivity", "return")
    await_log("destroy session result=0", stopped)
    await_log("onResume data=", resumed)
    final = state()
    print("final private data:", final, flush=True)
finally:
    args.out.joinpath("lifecycle.log").write_text(log())
    args.out.joinpath("private-data.txt").write_text(adb("shell", "run-as", pkg, "cat", "files/switch-probe.txt"))
