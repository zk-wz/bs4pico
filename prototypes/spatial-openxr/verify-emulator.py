#!/usr/bin/env python3
"""Bounded, identity-scoped E1 emulator regression and manual checkpoints."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import time

PKG = "io.github.zkwz.bs4pico.probe"
DATA_KEYS = {"manager_generation", "native_visits", "last_writer"}
CHECKPOINT_KEYS = {"scenario", "device", "apk_sha256", "prepared_utc", "pid", "starttime_ticks", "worker_id", "session_id", "last_snapshot", "data"}
THREAD_LINE = re.compile(r"^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+(\d+)\s+\d+\s+[VDIWEF]\s+(\S+?)\s*:\s?(.*)$")
XR_PREFIX = re.compile(r"^pid=(\d+) activity=(\d+) epoch=(\d+) worker=(\d+) session=(\d+) seq=(\d+) (.*)$")
ACTIVITY_PREFIX = re.compile(r"^pid=(\d+) activity=(\d+)(?: epoch=(\d+))? (Manager|Native)@\d+ (.*)$")


def utc():
    return datetime.now(timezone.utc).isoformat()


def number(event, key):
    return int(event["fields"][key], 0)


def data_from(event):
    fields = dict(re.findall(r"\b(manager_generation|native_visits|last_writer)=([^\s]+)", event["body"]))
    return fields if fields.keys() == DATA_KEYS else None


def validate_data(data):
    if not isinstance(data, dict) or data.keys() != DATA_KEYS or any(type(v) is not str for v in data.values()):
        raise ValueError("Invalid private-data schema")
    if any(not re.fullmatch(r"\d+", data[key]) for key in ("manager_generation", "native_visits")):
        raise ValueError("Invalid private-data counters")
    if data["last_writer"] not in ("manager", "native"):
        raise ValueError("Invalid private-data writer")
    return data


def parse_stat(raw):
    end = raw.rfind(")")
    if end < 0:
        raise ValueError("Missing /proc stat comm terminator")
    tail = raw[end + 1:].split()
    return {"utime_ticks": int(tail[11]), "stime_ticks": int(tail[12]),
            "threads": int(tail[17]), "starttime_ticks": int(tail[19]), "rss_pages": int(tail[21])}


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--device", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--scenario", choices=("baseline", "stress", "recovery", "home-cancel", "home-confirm", "input", "cost"), default="baseline")
    p.add_argument("--cycles", type=int)
    p.add_argument("--phase", choices=("prepare", "check"))
    p.add_argument("--title", default="PICO Emulator - 6.1.0")
    p.add_argument("--warmup-seconds", type=float)
    p.add_argument("--sample-seconds", type=float)
    p.add_argument("--repeats", type=int)
    a = p.parse_args(argv)
    manual = a.scenario in ("home-cancel", "home-confirm", "input")
    if manual != (a.phase is not None):
        p.error("--phase is required only for Home/input scenarios")
    if a.cycles is not None and a.scenario not in ("baseline", "stress"):
        p.error("--cycles is allowed only for baseline/stress")
    if a.cycles is not None and a.cycles <= 0:
        p.error("--cycles must be positive")
    if a.scenario in ("baseline", "stress") and a.cycles is None:
        a.cycles = 1 if a.scenario == "baseline" else 30
    cost_fields = ("warmup_seconds", "sample_seconds", "repeats")
    if a.scenario != "cost" and any(getattr(a, key) is not None for key in cost_fields):
        p.error("Cost parameters are allowed only for cost")
    for key, default in zip(cost_fields, (10.0, 15.0, 3)):
        value = getattr(a, key)
        if value is not None and (value <= 0 or not math.isfinite(value)):
            p.error("Cost parameters must be finite and positive")
        if a.scenario == "cost" and value is None:
            setattr(a, key, default)
    if not a.device.strip() or not a.title:
        p.error("Device and exact title must not be empty")
    a.out = a.out.resolve()
    return a


def load_checkpoint(args):
    cp = json.loads((args.out / "checkpoint.json").read_text())
    if not isinstance(cp, dict) or cp.keys() != CHECKPOINT_KEYS:
        raise ValueError("Invalid checkpoint keys")
    for key in ("scenario", "device", "apk_sha256", "prepared_utc", "last_snapshot"):
        if type(cp[key]) is not str:
            raise ValueError("Invalid checkpoint string: " + key)
    if cp["scenario"] != args.scenario or cp["device"] != args.device:
        raise ValueError("Checkpoint scenario/device mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", cp["apk_sha256"]):
        raise ValueError("Invalid checkpoint APK hash")
    if datetime.fromisoformat(cp["prepared_utc"]).tzinfo is None:
        raise ValueError("Checkpoint timestamp needs timezone")
    if type(cp["pid"]) is not int or cp["pid"] <= 0:
        raise ValueError("Invalid checkpoint PID")
    for key in ("starttime_ticks", "worker_id", "session_id"):
        if cp[key] is not None and (type(cp[key]) is not int or cp[key] < 0):
            raise ValueError("Invalid checkpoint identity: " + key)
    if args.scenario == "input":
        if cp["worker_id"] is not None or cp["session_id"] is not None:
            raise ValueError("Input checkpoint must still be in Manager")
    elif not cp["worker_id"] or cp["session_id"] != cp["worker_id"]:
        raise ValueError("Home checkpoint requires the live native identity")
    validate_data(cp["data"])
    relative = Path(cp["last_snapshot"])
    snapshot = (args.out / relative).resolve()
    if relative.is_absolute() or not snapshot.is_relative_to(args.out) or not snapshot.is_file():
        raise ValueError("Checkpoint snapshot must be an existing file within out")
    if (args.out / "check").exists():
        raise FileExistsError("Checkpoint already consumed; check directory exists")
    return cp, snapshot


class EvidenceFailure(RuntimeError):
    """Observed runtime or evidence-invariant failure, not acquisition failure."""


class Runner:
    def __init__(self, args):
        self.args = args
        self.root_out = args.out
        self.checkpoint = None
        seed = None
        if args.phase == "check":
            self.checkpoint, seed = load_checkpoint(args)
            self.out = args.out / "check"
        else:
            self.out = args.out
        self.repo = Path(__file__).resolve().parents[2]
        self.bridge = self.repo / "prototypes/spatial-openxr/windows-tools.sh"
        self.interop = self.repo / ".agents/skills/wsl-windows-interop/scripts/windows_interop.py"
        self.step = "preflight"
        self.command_number = 0
        self.file_number = 0
        self.events = []
        self.seen = set()
        self.process_times = {}
        self.seq = {}
        self.live_workers = set()
        self.live_sessions = set()
        self.live_managers = set()
        self.live_containers = set()
        self.resources = {}
        self.frames = {}
        self.max_workers = self.max_sessions = 0
        self.last_snapshot = seed
        self.last_command = None
        self.collect_errors = []
        self.validation_failure = None
        self.package_absent_observed = False
        if self.checkpoint:
            cp = self.checkpoint
            self.process_times[cp["pid"]] = cp["starttime_ticks"]
            self.ingest(seed.read_bytes(), seed=True)
            self.checkpoint_cursor = len(self.events)
            process = (cp["pid"], cp["starttime_ticks"])
            for event in self.events:
                if event["process"] != process:
                    continue
                if event["kind"] == "activity" and event["fields"].get("role") == "Manager":
                    if event["body"].startswith("onCreate"):
                        self.live_managers.add(event["activity"])
                    elif event["body"].startswith("onDestroy"):
                        self.live_managers.discard(event["activity"])
                elif event["kind"] == "container":
                    container = (*process, int(event["fields"]["id"]))
                    if event["fields"]["op"] == "create":
                        self.live_containers.add(container)
                    else:
                        self.live_containers.discard(container)
            if cp["session_id"] is not None:
                key = (cp["pid"], cp["starttime_ticks"], cp["session_id"])
                retained = [e for e in self.events if e["worker"] == key]
                if not retained or [number(e, "seq") for e in retained] != list(range(1, number(retained[-1], "seq") + 1)):
                    raise EvidenceFailure("Checkpoint lost a canonical worker interval")
                if sum(e["body"].startswith("worker started;") for e in retained) != 1:
                    raise EvidenceFailure("Checkpoint lost worker start")
                self.seq.pop(key, None)
                self.frames.pop(key, None)
                for event in retained:
                    self.graph(event)
                if self.live_workers != {key} or self.live_sessions != {key}:
                    raise EvidenceFailure("Checkpoint identity is not actually live")
        else:
            self.checkpoint_cursor = 0
        self.out.mkdir(exist_ok=False, parents=True)

    def save(self, name, value):
        with (self.out / name).open("x", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)

    def execute(self, argv, check=True, timeout=45):
        self.command_number += 1
        stem = f"command-{self.command_number:06d}"
        started = utc()
        tick = time.monotonic()
        try:
            p = subprocess.run([str(v) for v in argv], cwd=self.repo, stdin=subprocess.DEVNULL,
                               capture_output=True, timeout=timeout)
            out, err, code, timed = p.stdout, p.stderr, p.returncode, False
        except subprocess.TimeoutExpired as error:
            out, err, code, timed = error.stdout or b"", error.stderr or b"", None, True
        ended_tick = time.monotonic()
        stdout_path, stderr_path = self.out / (stem + ".stdout.bin"), self.out / (stem + ".stderr.bin")
        stdout_path.write_bytes(out)
        stderr_path.write_bytes(err)
        record = {"argv": [str(v) for v in argv], "device": self.args.device,
                  "scenario": self.args.scenario, "step": self.step, "started_utc": started,
                  "ended_utc": utc(), "monotonic_start": tick, "monotonic_end": ended_tick,
                  "elapsed": ended_tick - tick, "exit": code, "timeout": timed,
                  "stdout": {"path": stdout_path.name, "bytes": len(out)},
                  "stderr": {"path": stderr_path.name, "bytes": len(err)}}
        self.save(stem + ".json", record)
        self.last_command = record
        if check and code != 0:
            raise RuntimeError(f"Command failed ({code}, timeout={timed}): {record['argv']!r}; {err.decode('utf-8', 'replace')!r}")
        return out, err, code

    def adb(self, *parts, check=True):
        out, _, _ = self.execute([self.bridge, "adb", "-s", self.args.device, *parts], check=check)
        return out.decode("utf-8", "replace")

    def read_proc(self, pid, name):
        raw = self.adb("shell", "cat", f"/proc/{pid}/{name}", check=False)
        if self.last_command["exit"] != 0:
            raw = self.adb("shell", "run-as", PKG, "cat", f"/proc/{pid}/{name}", check=False)
        return raw if self.last_command["exit"] == 0 else None

    def identity(self):
        text = self.adb("shell", "pidof", PKG, check=False).strip()
        if self.last_command["exit"] not in (0, 1) or self.last_command["timeout"]:
            raise RuntimeError("Cannot observe package PID")
        if not text:
            self.identity_stat = None
            self.package_absent_observed = True
            return {"pid": None, "starttime_ticks": None}
        if not re.fullmatch(r"\d+(?:\s+\d+)*", text):
            raise EvidenceFailure("Package has invalid PID output: " + text)
        candidates = {int(value) for value in text.split()}
        if len(candidates) == 1:
            pid = next(iter(candidates))
        else:
            # A native diagnostic fork can temporarily inherit app cmdline.
            # Use AMS's package process registry, never the first pidof token.
            processes = self.adb("shell", "dumpsys", "activity", "processes")
            registered = {int(value) for value in re.findall(
                r"ProcessRecord\{[^\s{}]+\s+(\d+):" + re.escape(PKG) + r"/", processes)}
            owners = registered & candidates
            if len(owners) != 1:
                raise EvidenceFailure("Ambiguous registered package PID: " + text)
            pid = owners.pop()
        raw = self.read_proc(pid, "stat")
        self.stat_observed_monotonic = time.monotonic()
        try:
            self.identity_stat = parse_stat(raw) if raw is not None else None
        except (ValueError, IndexError):
            self.identity_stat = None
        observed = self.identity_stat["starttime_ticks"] if self.identity_stat else None
        previous = self.process_times.get(pid)
        if pid not in self.process_times or self.package_absent_observed or (
            observed is not None and previous is not None and observed != previous
        ):
            self.process_times[pid] = observed
        self.package_absent_observed = False
        return {"pid": pid, "starttime_ticks": self.process_times[pid]}

    def installed_hash(self):
        paths = self.adb("shell", "pm", "path", PKG).splitlines()
        base = [v.removeprefix("package:").strip() for v in paths if v.strip().endswith("/base.apk")]
        if len(base) != 1:
            raise RuntimeError("Installed base.apk identity unavailable")
        text = self.adb("shell", "sha256sum", base[0], check=False)
        match = re.match(r"([0-9a-fA-F]{64})\s", text)
        if self.last_command["exit"] == 0 and match:
            return match[1].lower()
        out, _, _ = self.execute([self.bridge, "adb", "-s", self.args.device, "exec-out", "cat", base[0]])
        if not out:
            raise RuntimeError("Installed base.apk binary read is empty")
        return hashlib.sha256(out).hexdigest()

    def connect(self):
        if self.adb("get-state").strip() != "device":
            raise RuntimeError("Explicit device is not online; no force-stop performed")
        self.apk_sha256 = self.installed_hash()
        if self.checkpoint and self.apk_sha256 != self.checkpoint["apk_sha256"]:
            raise RuntimeError("Installed APK does not match checkpoint")
        if not self.checkpoint:
            self.identity()
            self.snapshot(seed=True)

    def process_key(self, pid, seed):
        if not seed and pid not in self.process_times:
            raw = self.read_proc(pid, "stat")
            try:
                self.process_times[pid] = parse_stat(raw)["starttime_ticks"] if raw else None
            except (ValueError, IndexError):
                self.process_times[pid] = None
        return (pid, self.process_times.get(pid))

    def ingest(self, raw, seed=False):
        for line in raw.decode("utf-8", "replace").splitlines():
            match = THREAD_LINE.match(line)
            if not match:
                continue
            pid, tag, msg = int(match[1]), match[2], match[3]
            if line in self.seen:
                continue
            if tag == "LifeCycle" and not re.search(r"dispatch container (create|destroy)", msg):
                continue
            kind, body, fields = None, msg, dict(re.findall(r"(\w+)=([^\s]+)", msg))
            worker = session = activity = None
            process = self.process_key(pid, seed) if tag == "BS4PicoXR" or (
                tag == "BS4PicoProbe" and msg.startswith("pid=")) or (
                tag == "LifeCycle" and f"pkg={PKG}," in msg and "name=ProbeManager" in msg
            ) else (pid, self.process_times.get(pid))
            if tag == "BS4PicoXR":
                prefix = XR_PREFIX.match(msg)
                if not prefix:
                    if seed:
                        self.seen.add(line)
                        continue
                    raise EvidenceFailure("Unscoped canonical XR event: " + line)
                if int(prefix[1]) != pid:
                    raise EvidenceFailure("XR log PID prefix mismatch")
                kind, body = "xr", prefix[7]
                worker = (*process, int(prefix[4]))
                session = (*process, int(prefix[5])) if int(prefix[5]) else None
                activity = (*process, int(prefix[2]))
            elif tag == "BS4PicoProbe":
                prefix = ACTIVITY_PREFIX.match(msg)
                if prefix:
                    kind, body = "activity", prefix[5]
                    activity = (*process, int(prefix[2]))
                    fields["role"] = prefix[4]
                elif re.match(r"^pid=\d+ private read data=", msg):
                    kind = "data"
                else:
                    continue  # XR status forwarding is not canonical evidence.
            elif tag == "LifeCycle" and f"pkg={PKG}," in msg and "name=ProbeManager" in msg:
                op = re.search(r"dispatch container (create|destroy)", msg)
                container = re.search(r"\bInfo\{id=(\d+)", msg)
                if not op or not container:
                    raise EvidenceFailure("Unparseable package container event")
                kind = "container"
                fields.update(op=op[1], id=container[1])
            elif PKG in msg and re.search(r"current full space.*allow start fullscreen|result=100|Permission Denial", msg, re.I):
                kind = "system"
            elif tag in ("AndroidRuntime", "libc") and ("FATAL EXCEPTION" in msg or "Fatal signal" in msg):
                kind = "system"
            else:
                continue
            self.seen.add(line)
            event = {"index": len(self.events), "kind": kind, "body": body, "fields": fields,
                     "pid": pid, "process": process, "worker": worker, "session": session, "activity": activity}
            self.events.append(event)
            if seed:
                if worker:
                    self.seq[worker] = max(self.seq.get(worker, 0), number(event, "seq"))
                if session and body.startswith("FRAME_SAMPLE "):
                    self.frames[session] = (number(event, "frame"), number(event, "predictedDisplayTime"))
                continue
            self.graph(event)

    def graph(self, event):
        kind, body, fields = event["kind"], event["body"], event["fields"]
        if kind == "system":
            if PKG in body or event["pid"] in self.process_times:
                raise EvidenceFailure("Runtime rejection/crash: " + body)
        if kind == "activity" and fields["role"] == "Manager":
            if body.startswith("onCreate"):
                self.live_managers.add(event["activity"])
            elif body.startswith("onDestroy"):
                self.live_managers.discard(event["activity"])
        if kind == "container":
            key = (*event["process"], int(fields["id"]))
            if fields["op"] == "create":
                self.live_containers.add(key)
            else:
                self.live_containers.discard(key)
        if kind != "xr":
            return
        worker, session = event["worker"], event["session"]
        seq = number(event, "seq")
        expected = self.seq.get(worker, 0) + 1
        if seq != expected:
            raise EvidenceFailure(f"Canonical XR sequence gap: {worker} expected {expected}, got {seq}")
        self.seq[worker] = seq
        if body.startswith("ERROR"):
            raise EvidenceFailure("Native worker failure: " + body)
        if body.startswith("worker started;"):
            if self.live_workers:
                raise EvidenceFailure("New worker started before previous join")
            self.live_workers.add(worker)
            self.max_workers = max(self.max_workers, len(self.live_workers))
        elif body == "XR session created":
            if self.live_sessions or worker not in self.live_workers or session != worker:
                raise EvidenceFailure("Invalid or overlapping session creation")
            self.live_sessions.add(session)
            self.resources[session] = {"swapchain": [], "session": [], "instance": [], "joined": False}
            self.max_sessions = max(self.max_sessions, len(self.live_sessions))
        elif body.startswith("destroy "):
            match = re.fullmatch(r"destroy (swapchain|session|instance) result=(-?\d+)", body)
            if match and session in self.resources:
                value = int(match[2])
                self.resources[session][match[1]].append(value)
                if value != 0:
                    raise EvidenceFailure("XR destruction failed: " + body)
                if match[1] == "session":
                    self.live_sessions.discard(session)
        elif body.startswith("nativeStop joined worker"):
            self.live_workers.discard(worker)
            if session in self.resources:
                self.resources[session]["joined"] = True
                self.released(session)
        if body.startswith("FRAME_SAMPLE "):
            frame, predicted = number(event, "frame"), number(event, "predictedDisplayTime")
            previous = self.frames.get(session)
            if previous and (frame <= previous[0] or predicted <= previous[1]):
                raise EvidenceFailure("Frame/prediction time did not advance within session")
            self.frames[session] = (frame, predicted)
            timing = ("waitFrameNs", "inputLocateNs", "imageWaitNs", "renderSubmitFenceNs", "endFrameNs")
            if any(number(event, v) < 0 for v in (*timing, "frameCpuNs")) or sum(number(event, v) for v in timing) > number(event, "frameCpuNs"):
                raise EvidenceFailure("Invalid frame timing")
            if not number(event, "shouldRender") and (number(event, "submitted") or number(event, "imageWaitNs") or number(event, "renderSubmitFenceNs")):
                raise EvidenceFailure("Non-rendering frame performed image rendering/submission")

    def snapshot(self, seed=False):
        if not seed:
            self.identity()
        out, err, code = self.execute([self.bridge, "adb", "-s", self.args.device, "logcat", "-b", "all", "-d", "-v", "threadtime"], check=False)
        path = self.out / self.last_command["stdout"]["path"]
        if code != 0:
            if self.last_command["timeout"] or re.search(rb"offline|device.*not found|disconnected", err, re.I):
                raise RuntimeError("All-buffer log snapshot failed")
            buffers = []
            missing = []
            for buffer in ("main", "system", "crash"):
                raw, _, rc = self.execute([self.bridge, "adb", "-s", self.args.device, "logcat", "-b", buffer, "-d", "-v", "threadtime"], check=False)
                if rc != 0:
                    missing.append(buffer)
                else:
                    buffers.append(raw)
            self.file_number += 1
            path = self.out / f"fallback-snapshot-{self.file_number:06d}.log"
            out = b"\n".join(buffers)
            path.write_bytes(out)
            self.save(f"fallback-{self.file_number:06d}.json", {"missing": missing, "all_exit": code})
            if missing:
                raise RuntimeError("Required log buffers unavailable: " + ",".join(missing))
        self.last_snapshot = path
        self.ingest(out, seed=seed)
        return len(self.events)

    def mark(self, step):
        self.step = step
        return self.snapshot()

    def after(self, cursor, kind=None, body=None, session=None, process=None):
        return [e for e in self.events[cursor:] if (kind is None or e["kind"] == kind)
                and (body is None or body in e["body"]) and (session is None or e["session"] == session)
                and (process is None or e["process"] == process)]

    def wait(self, predicate, description, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            self.snapshot()
            value = predicate()
            if value:
                return value
            if time.monotonic() >= deadline:
                raise RuntimeError("Missing bounded runtime evidence: " + description)
            time.sleep(.4)

    def start(self, activity, action=None, direct=False, haptics=False):
        parts = ["shell", "am", "start", "--activity-single-top", "-n", PKG + "/.platform." + activity]
        if action:
            parts += ["--es", "probe_action", action]
        if direct:
            parts += ["--ez", "direct", "true"]
        parts += ["--ez", "probe_haptics", "true" if haptics else "false"]
        out, err, _ = self.execute([self.bridge, "adb", "-s", self.args.device, *parts])
        if re.search(rb"Error:|Permission Denial|current activity is being kept|result=100", out + err, re.I):
            raise RuntimeError("Android refused launch: " + (out + err).decode("utf-8", "replace"))
        self.snapshot()

    def state(self):
        raw = self.adb("shell", "run-as", PKG, "cat", "files/switch-probe.txt")
        return validate_data(dict(line.split("=", 1) for line in raw.splitlines()))

    def activities(self, label):
        raw = self.adb("shell", "dumpsys", "activity", "activities")
        self.file_number += 1
        (self.out / f"{label}-{self.file_number:06d}.activities.txt").write_text(raw)
        return raw

    def native(self, cursor, previous=None):
        def ready():
            created = {e["session"] for e in self.after(cursor, "xr", "XR session created")}
            for e in self.after(cursor, "xr", "FRAME_SAMPLE "):
                key = e["session"]
                if key in created and key != previous and number(e, "submitted") == 1 and number(e, "viewCount") == 2:
                    if self.after(cursor, "xr", "FIRST_STEREO_FRAME", session=key) and not self.live_managers and not self.live_containers:
                        return key
            return None
        key = self.wait(ready, "fresh stereo session and retired Manager/container")
        if re.search(r"\* Hist.*" + re.escape(PKG) + r"/\.platform\.LaunchActivity", self.activities("native")):
            raise RuntimeError("Manager Activity history remained during Native")
        return key

    def manager(self, cursor):
        self.wait(lambda: self.after(cursor, "activity", "onResume") and any(e["fields"].get("role") == "Manager" for e in self.after(cursor, "activity", "onResume")), "new Manager resume")
        if not re.search(r"\* Hist.*" + re.escape(PKG) + r"/\.platform\.LaunchActivity", self.activities("manager")):
            raise RuntimeError("Manager has no Activity history after resume")
        return self.state()

    def released(self, session):
        values = self.resources.get(session)
        if not values or values != {"swapchain": [0, 0], "session": [0], "instance": [0], "joined": True}:
            raise EvidenceFailure(f"Incomplete normal session release: {session}: {values}")

    def back(self, session):
        before = self.state()
        cursor = self.mark("normal Back")
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        self.wait(lambda: not self.live_workers and not self.live_sessions, "normal Back joins/releases all XR")
        self.released(session)
        after = self.manager(cursor)
        if before != after:
            raise RuntimeError("Normal Back changed committed data")
        return after

    def finish_manager(self):
        if self.live_workers or self.live_sessions:
            raise RuntimeError("Cannot finish Manager with live XR")
        self.mark("normal Manager finish")
        self.start("LaunchActivity", "finish")
        def absent():
            dump = self.activities("finish")
            return not re.search(r"\* Hist.*" + re.escape(PKG), dump) and not self.live_containers and not self.live_managers
        self.wait(absent, "normal Manager finish and nonforeground package")
        return self.identity()

    def cold_condition(self):
        if self.adb("get-state").strip() != "device":
            raise RuntimeError("Target offline before controlled cold condition")
        self.mark("explicit force-stop cold setup")
        aborted = list(self.live_workers)
        self.adb("shell", "am", "force-stop", PKG)
        # This is explicit process termination, not evidence of normal XR cleanup.
        self.live_workers.clear()
        self.live_sessions.clear()
        self.live_managers.clear()
        self.live_containers.clear()
        def absent():
            identity = self.identity()
            dump = self.activities("cold")
            return identity["pid"] is None and not re.search(r"\* Hist.*" + re.escape(PKG), dump)
        self.wait(absent, "absent process and Activity cold condition")
        self.file_number += 1
        self.save(f"cold-condition-{self.file_number:06d}.json", {"aborted_workers": aborted, "normal_cleanup_claimed": False})

    def no_regression(self, before, after):
        validate_data(before)
        validate_data(after)
        if any(int(after[k]) < int(before[k]) for k in ("manager_generation", "native_visits")):
            raise RuntimeError("Committed private counters regressed")

    def first_read(self, cursor, expected, process=None):
        event = self.wait(lambda: next(iter(self.after(cursor, "data", "private read data=", process=process)), None), "first private read after reopen")
        if data_from(event) != expected:
            raise RuntimeError(f"First private read differs from committed snapshot: {data_from(event)} != {expected}")
        return event

    def unfocused(self, cursor, session):
        def ready():
            hands = {number(e, "frame") for e in self.after(cursor, "xr", "HAND_SAMPLE ", session=session)
                     if number(e, "syncAttempted") == 1 and number(e, "syncResult") == 8}
            return next((e for e in self.after(cursor, "xr", "FRAME_SAMPLE ", session=session)
                         if number(e, "state") == 4 and number(e, "frame") in hands), None)
        return self.wait(ready, "same-frame VISIBLE and actual NOT_FOCUSED sync")

    def metrics(self, label):
        before = time.monotonic()
        identity = self.identity()
        stat = self.identity_stat
        observed = self.stat_observed_monotonic if identity["pid"] else None
        status_raw = self.read_proc(identity["pid"], "status") if identity["pid"] else None
        status = {}
        if status_raw:
            for key, value in re.findall(r"^(Threads|VmRSS):\s+(\d+)", status_raw, re.M):
                status[key] = int(value)
        result = {**identity, "stat": stat, "status": status, "read_started_monotonic": before,
                  "stat_observed_monotonic": observed, "read_ended_monotonic": time.monotonic(), "observed_utc": utc()}
        result["starttime_ticks"] = stat["starttime_ticks"] if stat else None
        self.file_number += 1
        self.save(f"{label}-{self.file_number:06d}.metrics.json", result)
        return result

    def capture(self, label):
        self.file_number += 1
        cli_path = self.out / f"{label}-{self.file_number:06d}.cli.png"
        win = self.execute([sys.executable, self.interop, "path", cli_path])[0].decode().strip()
        self.execute([self.bridge, "pico", "capture", "screenshot", "--device", self.args.device, "--out", win], check=False)
        window_path = self.out / f"{label}-{self.file_number:06d}.window.png"
        self.execute([sys.executable, self.repo / "prototypes/spatial-openxr/capture-emulator.py", "--title", self.args.title, "--output", window_path])
        return {"cli": cli_path.name if cli_path.is_file() else None, "window": window_path.name, "visual_check_required": True}

    def collect(self):
        for label, action in (
            ("logs", self.snapshot),
            ("crash", lambda: self.adb("logcat", "-b", "crash", "-d", "-v", "threadtime")),
            ("activities", lambda: self.activities("final")),
            ("processes", lambda: self.adb("shell", "dumpsys", "activity", "processes")),
            ("metrics", lambda: self.metrics("final")),
            ("private", self.state),
            ("capture", lambda: self.capture("final")),
        ):
            try:
                action()
            except Exception as error:
                self.collect_errors.append({"item": label, "error": repr(error)})
                if isinstance(error, EvidenceFailure) and self.validation_failure is None:
                    self.validation_failure = repr(error)
        self.save("collection-errors.json", self.collect_errors)


def run_cost(r):
    units = {}
    for key in ("CLK_TCK", "PAGESIZE"):
        text = r.adb("shell", "getconf", key, check=False).strip()
        units[key] = int(text) if r.last_command["exit"] == 0 and text.isdigit() and int(text) > 0 else None
    rows = []
    for repeat in range(1, r.args.repeats + 1):
        for path in ("direct", "spatial"):
            r.cold_condition()
            cursor = r.mark(f"cost {path}{repeat} enter")
            r.start("VrActivity" if path == "direct" else "LaunchActivity", None if path == "direct" else "enter", direct=path == "direct")
            session = r.native(cursor)
            entry_cursor = cursor
            r.capture(f"cost-{path}-{repeat}")
            warm_start = time.monotonic()
            while time.monotonic() - warm_start < r.args.warmup_seconds:
                r.snapshot()
                time.sleep(.4)
            cursor = r.mark(f"cost {path}{repeat} sample")
            begin = r.metrics(f"cost-{path}-{repeat}-begin")
            sample_start = time.monotonic()
            while time.monotonic() - sample_start < r.args.sample_seconds:
                r.snapshot()
                time.sleep(.4)
            end = r.metrics(f"cost-{path}-{repeat}-end")
            r.snapshot()
            valid = bool(begin["stat"] and end["stat"] and begin["pid"] == end["pid"] and begin["starttime_ticks"] == end["starttime_ticks"])
            row = {"path": path, "repeat": repeat, "session": session, "apk_sha256": r.apk_sha256,
                   "warmup_elapsed": sample_start - warm_start, "requested_sample_seconds": r.args.sample_seconds,
                   "begin": begin, "end": end, "valid": valid, "units": units,
                   "frame_samples": [e["fields"] for e in r.after(cursor, "xr", "FRAME_SAMPLE ", session=session)],
                   "unmeasured": ["GPU time", "display FPS", "input latency", "device sustained performance"],
                   "conditions": "Requires external pose/window/host-load record; CLI does not verify these conditions",
                   "validity_scope": "PID/starttime and CPU observations only; external condition changes invalidate the sample"}
            if valid:
                ticks = (end["stat"]["utime_ticks"] + end["stat"]["stime_ticks"] - begin["stat"]["utime_ticks"] - begin["stat"]["stime_ticks"])
                elapsed = end["stat_observed_monotonic"] - begin["stat_observed_monotonic"]
                row.update(cpu_ticks_delta=ticks, elapsed=elapsed)
                if ticks < 0 or elapsed <= 0:
                    row["valid"] = False
                    row["invalid_reason"] = "negative ticks or nonpositive observed interval"
                else:
                    row["ticks_per_second"] = ticks / elapsed
                    row["cpu_seconds"] = ticks / units["CLK_TCK"] if units["CLK_TCK"] else None
                    row["rss_bytes"] = [v["stat"]["rss_pages"] * units["PAGESIZE"] for v in (begin, end)] if units["PAGESIZE"] else None
            else:
                row["invalid_reason"] = "PID/starttime changed or stat unreadable"
            starts = [e for e in r.after(entry_cursor, "xr", "worker started;") if e["worker"] == session]
            if len(starts) != 1 or number(starts[0], "hapticProbe") != 0 or r.after(entry_cursor, "xr", "HAPTIC_API ", session=session):
                raise EvidenceFailure("Cost path unexpectedly enabled haptic")
            row["haptic_probe_enabled"] = False
            r.save(f"cost-{path}-{repeat}.json", row)
            rows.append(row)
            r.back(session)
            r.finish_manager()
    return {"samples": rows, "direct_still_initializes_spatial_application": True,
            "no_device_performance_ranking": True}


def _auto_resource_trends(cycles):
    trends = {}
    for role, stage in (('native', 'entry'), ('manager', 'back')):
        observations = [(record['cycle'], record[stage]['stable']['metrics']) for record in cycles]
        role_trends = {}
        for source, key, unit in (('stat', 'threads', 'threads'), ('stat', 'rss_pages', 'pages'),
                                  ('status', 'Threads', 'threads'), ('status', 'VmRSS', 'KiB')):
            series = [{'cycle': cycle, 'pid': metrics['pid'],
                       'starttime_ticks': metrics['starttime_ticks'],
                       'value': (metrics.get(source) or {}).get(key)}
                      for cycle, metrics in observations]
            values = [row['value'] for row in series]
            identities = {(row['pid'], row['starttime_ticks']) for row in series}
            same_process = (len(identities) == 1
                            and all(row['pid'] is not None and row['starttime_ticks'] is not None
                                    for row in series))
            result = {'series': series, 'unit': unit, 'same_process_proved': same_process}
            if not all(type(value) is int for value in values):
                result['classification'] = 'partially_or_entirely_unmeasured'
            elif not same_process:
                result['classification'] = 'process_identity_not_comparable'
            elif len(values) < 2:
                result['classification'] = 'insufficient_observations_for_trend'
            else:
                nondecreasing = all(right >= left for left, right in zip(values, values[1:]))
                growing = values[-1] > values[0]
                result.update({'last_minus_first': values[-1] - values[0],
                               'nondecreasing': nondecreasing,
                               'strictly_increasing': all(right > left for left, right in zip(values, values[1:])),
                               'classification': ('sustained_nondecreasing_growth_pending_investigation'
                                                  if nondecreasing and growing
                                                  else 'no_sustained_monotonic_growth_observed_not_leak_exclusion')})
            role_trends[source + '.' + key] = result
        trends[role] = role_trends
    return trends


def _auto_indexes(r, cursor):
    return [event['index'] for event in r.after(cursor)
            if event['kind'] in ('xr', 'activity', 'data', 'container')]


def _auto_process(identity):
    return (identity['pid'], identity['starttime_ticks'])


def _auto_activity(r, cursor, role, marker, activity=None, process=None):
    def found():
        return next((event for event in r.after(cursor, kind='activity', body=marker)
                     if event['fields'].get('role') == role
                     and (activity is None or event['activity'] == activity)
                     and (process is None or event['process'] == process)), None)
    return r.wait(found, f'{role} {marker} after action')


def _auto_session_activity(r, session):
    events = r.after(0, kind='xr', session=session)
    if not events:
        raise RuntimeError(f'No XR events identify session {session!r}')
    return (*session[:2], number(events[0], 'activity'))


def _auto_stable(r, label):
    cursor = r.mark(label + '-stable')
    data = r.state()
    r.activities(label)
    metrics = r.metrics(label)
    r.snapshot()
    record = {'label': label, 'data': data, 'metrics': metrics,
              'activity_dump_label': label, 'event_indexes': _auto_indexes(r, cursor)}
    r.save(label + '-stable.json', record)
    return record


def _auto_native_data(r, before, after, manager_entry=False):
    r.no_regression(before, after)
    if after['last_writer'] != 'native':
        raise RuntimeError('Fresh Native session did not commit native private data')
    if int(after['native_visits']) <= int(before['native_visits']):
        raise RuntimeError('Fresh successful Native session did not increase native_visits')
    if manager_entry:
        if int(after['manager_generation']) <= int(before['manager_generation']):
            raise RuntimeError('Manager enter did not advance manager_generation')
    elif after['manager_generation'] != before['manager_generation']:
        raise RuntimeError('Native-only lifecycle changed manager_generation')


def _auto_enter(r, label, previous=None):
    before = r.state()
    cursor = r.mark(label + '-enter')
    r.start('LaunchActivity', 'enter')
    session = r.native(cursor, previous=previous)
    after = r.state()
    _auto_native_data(r, before, after, manager_entry=True)
    if previous is not None:
        r.released(previous)
    return session, {'cursor': cursor, 'session': session, 'before': before,
                     'after': after, 'event_indexes': _auto_indexes(r, cursor)}


def _auto_recreate_manager(r, label):
    before = r.state()
    cursor = r.mark(label + '-recreate-manager')
    r.start('LaunchActivity', 'recreate')
    created = _auto_activity(r, cursor, 'Manager', 'onCreate restored=true')
    restored = r.manager(created['index'])
    read = r.first_read(created['index'], before, process=created['process'])
    if restored != before or r.state() != before:
        raise RuntimeError('Manager recreation changed durable private data')
    return {'cursor': cursor, 'created_event': created['index'],
            'first_read_event': read['index'], 'activity': created['activity'],
            'before': before, 'after': restored,
            'stable': _auto_stable(r, label + '-recreated-manager'),
            'event_indexes': _auto_indexes(r, cursor)}


def _auto_recreate_native(r, session, label):
    before = r.state()
    old_activity = _auto_session_activity(r, session)
    cursor = r.mark(label + '-recreate-native')
    r.start('VrActivity', 'recreate')
    created = _auto_activity(r, cursor, 'Native', 'onCreate restored=true')
    if created['activity'] == old_activity:
        raise RuntimeError('Native recreation reused the old Activity identity')
    # am start may first pause/resume the old Activity. Only the restored
    # Activity's worker is the recreation result, not that transient worker.
    replacement = r.native(created['index'], previous=session)
    r.released(session)
    destroyed = _auto_activity(r, cursor, 'Native', 'onDestroy', activity=old_activity)
    after = r.state()
    _auto_native_data(r, before, after)
    return replacement, {'cursor': cursor, 'old_session': session,
                         'session': replacement, 'created_event': created['index'],
                         'destroyed_event': destroyed['index'],
                         'before': before, 'after': after,
                         'stable': _auto_stable(r, label + '-recreated-native'),
                         'event_indexes': _auto_indexes(r, cursor)}


def _auto_retired_manager(r, session, cursor, before, label, allow_native_restart=False):
    joined = r.wait(lambda: r.after(cursor, kind='xr', session=session,
                                    body='nativeStop joined'),
                    'old Native worker join before stable manager')
    r.released(session)
    destroyed = _auto_activity(r, cursor, 'Native', 'onDestroy',
                               activity=_auto_session_activity(r, session))
    after = r.manager(cursor)
    retired_sessions = [session]
    if allow_native_restart:
        r.no_regression(before, after)
        if (after['manager_generation'] != before['manager_generation']
                or after['last_writer'] != 'native'):
            raise RuntimeError('Debug return changed manager generation or lost native commit')
        for event in r.after(cursor, kind='xr', body='XR session created'):
            if event['session'] not in retired_sessions:
                r.released(event['session'])
                retired_sessions.append(event['session'])
    elif after != before:
        raise RuntimeError('Native retirement changed committed private data')
    if r.state() != after:
        raise RuntimeError('Stable manager does not retain final Native commit')
    read = r.first_read(cursor, after, process=session[:2])
    dump = r.activities(label + '-retirement')
    if re.search(r'\* Hist.*' + re.escape(PKG) + r'/[^\s}]*VrActivity', dump):
        raise RuntimeError('Retired Native Activity remains in Activity history')
    return {'cursor': cursor, 'session': session, 'data': after,
            'joined_events': [event['index'] for event in joined],
            'destroyed_event': destroyed['index'],
            'before': before, 'first_read_event': read['index'],
            'retired_sessions': retired_sessions,
            'event_indexes': _auto_indexes(r, cursor)}


def _auto_back(r, session, label):
    cursor = r.mark(label + '-before-back')
    before = r.state()
    returned = r.back(session)
    if returned != before:
        raise RuntimeError('Back did not preserve the complete Native data snapshot')
    r.released(session)
    read = r.first_read(cursor, before, process=session[:2])
    return {'cursor': cursor, 'session': session, 'before': before,
            'first_read_event': read['index'],
            'after': returned, 'stable': _auto_stable(r, label + '-manager'),
            'event_indexes': _auto_indexes(r, cursor)}


def _auto_close(r, session, label):
    returned = _auto_back(r, session, label)
    before_finish = r.identity()
    cursor = r.mark(label + '-before-finish')
    after_finish = r.finish_manager()
    if r.state() != returned['after']:
        raise RuntimeError('Normal manager finish changed committed private data')
    return {'back': returned, 'data': returned['after'],
            'identity_before_finish': before_finish,
            'identity_after_finish': after_finish, 'finish_cursor': cursor,
            'nonforeground_dump': label + '-nonforeground',
            'activity_dump': r.activities(label + '-nonforeground'),
            'event_indexes': _auto_indexes(r, cursor)}


def _auto_relation(before, after):
    old_pid, new_pid = before['pid'], after['pid']
    old_ticks, new_ticks = before['starttime_ticks'], after['starttime_ticks']
    if old_pid is None:
        return {'kind': 'old_process_already_absent', 'new_process_proved': False}
    if new_pid is None:
        return {'kind': 'process_absent', 'new_process_proved': False}
    if old_pid != new_pid:
        return {'kind': 'different_pid', 'new_process_proved': True}
    if old_ticks is None or new_ticks is None:
        return {'kind': 'same_pid_starttime_unreadable_identity_insufficient',
                'new_process_proved': False}
    if old_ticks != new_ticks:
        return {'kind': 'pid_reused_different_starttime', 'new_process_proved': True}
    return {'kind': 'same_process', 'new_process_proved': False}


def _auto_reopen(r, expected, previous_identity, label):
    cursor = r.mark(label + '-reopen')
    r.start('LaunchActivity')
    # Select the first package read after the action; a later matching read
    # must never hide an incorrect initial restoration.
    read = r.first_read(cursor, expected)
    restored = r.manager(cursor)
    current = r.identity()
    if current['pid'] != read['pid']:
        raise RuntimeError('Manager process changed between first read and stable restoration')
    if (read['process'][1] is not None and current['starttime_ticks'] is not None
            and read['process'][1] != current['starttime_ticks']):
        raise RuntimeError('Manager PID was reused during restoration')
    if restored != expected or r.state() != expected:
        raise RuntimeError('Reopened manager changed committed data before enter')
    return {'cursor': cursor, 'first_read_event': read['index'],
            'first_read_process': read['process'], 'expected': expected,
            'data': restored, 'before_identity': previous_identity,
            'identity': current, 'process_relation': _auto_relation(previous_identity, current),
            'stable': _auto_stable(r, label + '-manager'),
            'event_indexes': _auto_indexes(r, cursor)}


def _auto_disappearance(r, identity, label):
    observations = []
    started = time.monotonic()
    deadline = started + 20

    def observed():
        current = r.identity()
        observations.append({'elapsed_seconds': time.monotonic() - started,
                             'identity': current})
        relation = _auto_relation(identity, current)
        if identity['pid'] is None:
            return {'kind': 'no_background_process_at_kill', 'disappearance_proved': False,
                    'identity': current}
        if current['pid'] is None:
            return {'kind': 'old_process_observed_absent', 'disappearance_proved': True,
                    'identity': current}
        if relation['new_process_proved']:
            return {'kind': relation['kind'], 'disappearance_proved': True,
                    'identity': current}
        if time.monotonic() >= deadline:
            return {'kind': 'background_termination_not_covered',
                    'disappearance_proved': False, 'identity': current,
                    'identity_relation': relation}
        return None

    result = r.wait(observed, 'single am kill actual process-identity disappearance', timeout=25)
    result['elapsed_seconds'] = time.monotonic() - started
    result['observations'] = observations
    r.save(label + '-disappearance.json', result)
    return result


def run_baseline(r):
    start_cursor = r.mark('baseline-cold-condition')
    r.cold_condition()
    cursor = r.mark('baseline-direct-native')
    r.start('VrActivity', direct=True)
    session = r.native(cursor)
    direct = {'cursor': cursor, 'session': session,
              'stable': _auto_stable(r, 'baseline-direct-native'),
              'event_indexes': _auto_indexes(r, cursor)}
    r.capture('baseline-direct-native')
    cycles = []
    for cycle in range(1, r.args.cycles + 1):
        label = f'baseline-cycle-{cycle:02d}'
        session, entry = _auto_enter(r, label, previous=session if cycle == 1 else None)
        entry['stable'] = _auto_stable(r, label + '-native')
        if cycle == 1:
            r.capture(label + '-native')
        returned = _auto_back(r, session, label)
        if cycle == 1:
            r.capture(label + '-manager')
        cycles.append({'cycle': cycle, 'entry': entry, 'back': returned})
    manager_recreation = _auto_recreate_manager(r, 'baseline')
    session, after_manager = _auto_enter(r, 'baseline-after-manager-recreate')
    session, native_recreation = _auto_recreate_native(r, session, 'baseline')
    before = r.state()
    old_session = session
    activity = _auto_session_activity(r, session)
    cursor = r.mark('baseline-native-new-intent-pause-resume')
    r.start('VrActivity')
    paused = _auto_activity(r, cursor, 'Native', 'onPause', activity=activity)
    resumed = _auto_activity(r, paused['index'] + 1, 'Native', 'onResume', activity=activity)
    session = r.native(cursor, previous=old_session)
    r.released(old_session)
    after = r.state()
    _auto_native_data(r, before, after)
    pause_resume = {'cursor': cursor, 'old_session': old_session, 'session': session,
                    'pause_event': paused['index'], 'resume_event': resumed['index'],
                    'before': before, 'after': after,
                    'stable': _auto_stable(r, 'baseline-pause-resume-native'),
                    'event_indexes': _auto_indexes(r, cursor)}
    r.capture('baseline-pause-resume-native')
    cursor = r.mark('baseline-home-overlay')
    r.adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    unfocused = r.unfocused(cursor, session)
    hands = [event for event in r.after(cursor, kind='xr', body='HAND_SAMPLE', session=session)
             if number(event, 'frame') == number(unfocused, 'frame')
             and number(event, 'syncAttempted') == 1 and number(event, 'syncResult') == 8]
    if not hands:
        raise RuntimeError('Home overlay lacks actual same-frame numeric NOT_FOCUSED sync evidence')
    r.capture('baseline-home-overlay')
    overlay = {'cursor': cursor, 'session': session,
               'unfocused_event': unfocused['index'],
               'frame_state': number(unfocused, 'state'),
               'frame': number(unfocused, 'frame'),
               'hand_samples': [{'event_index': event['index'],
                                 'hand': event['fields']['hand'],
                                 'syncAttempted': number(event, 'syncAttempted'),
                                 'syncResult': number(event, 'syncResult')} for event in hands],
               'classification': 'overlay_only_not_home_cancel_or_confirm',
               'event_indexes': _auto_indexes(r, cursor)}
    before_return = r.state()
    cursor = r.mark('baseline-overlay-debug-return')
    r.start('VrActivity', 'return')
    debug_return = _auto_retired_manager(r, session, cursor, before_return, 'baseline-debug-return',
                                        allow_native_restart=True)
    debug_return['stable'] = _auto_stable(r, 'baseline-final-manager')
    r.capture('baseline-final-manager')
    finish_cursor = r.mark('baseline-finish-manager')
    finish_identity = r.finish_manager()
    if r.state() != debug_return['data']:
        raise RuntimeError('Baseline normal finish changed private data')
    return {'scenario': 'baseline', 'cycles_completed': len(cycles),
            'direct': direct, 'cycles': cycles, 'manager_recreation': manager_recreation,
            'entry_after_manager_recreation': after_manager, 'native_recreation': native_recreation,
            'new_intent_pause_resume': pause_resume, 'home_overlay': overlay,
            'overlay_debug_return': debug_return, 'final_data': debug_return['data'],
            'finish_identity': finish_identity,
            'finish_event_indexes': _auto_indexes(r, finish_cursor),
            'event_indexes': _auto_indexes(r, start_cursor)}


def run_stress(r):
    start_cursor = r.mark('stress-cold-condition')
    r.cold_condition()
    cursor = r.mark('stress-direct-native')
    r.start('VrActivity', direct=True)
    session = r.native(cursor)
    direct = {'cursor': cursor, 'session': session,
              'stable': _auto_stable(r, 'stress-direct-native'),
              'event_indexes': _auto_indexes(r, cursor)}
    last_data = direct['stable']['data']
    cycles = []
    for cycle in range(1, r.args.cycles + 1):
        label = f'stress-cycle-{cycle:02d}'
        record = {'cycle': cycle}
        if cycle % 5 == 0:
            record['manager_recreation'] = _auto_recreate_manager(r, label)
            if record['manager_recreation']['after'] != last_data:
                raise RuntimeError('Stress manager recreation changed the prior Back snapshot')
        session, entry = _auto_enter(r, label, previous=session if cycle == 1 else None)
        entry['stable'] = _auto_stable(r, label + '-native')
        r.no_regression(last_data, entry['after'])
        record['entry'] = entry
        if cycle % 5 == 0:
            session, recreation = _auto_recreate_native(r, session, label)
            record['native_recreation'] = recreation
            before = r.state()
            retire_cursor = r.mark(label + '-ordinary-manager-no-enter')
            r.start('LaunchActivity')
            retirement = _auto_retired_manager(r, session, retire_cursor, before, label)
            retirement['stable'] = _auto_stable(r, label + '-ordinary-manager')
            record['ordinary_manager_retirement'] = retirement
            session, reentry = _auto_enter(r, label + '-reenter', previous=session)
            reentry['stable'] = _auto_stable(r, label + '-reentered-native')
            record['reentry'] = reentry
        record['back'] = _auto_back(r, session, label)
        last_data = record['back']['after']
        cycles.append(record)
        r.save(label + '-result.json', record)
    finish_cursor = r.mark('stress-finish-manager')
    identity = r.finish_manager()
    if r.state() != last_data:
        raise RuntimeError('Stress finish changed the final Back data snapshot')
    metrics = [direct['stable']['metrics']]
    for record in cycles:
        if 'manager_recreation' in record:
            metrics.append(record['manager_recreation']['stable']['metrics'])
        metrics.append(record['entry']['stable']['metrics'])
        for key in ('native_recreation', 'ordinary_manager_retirement', 'reentry'):
            if key in record:
                metrics.append(record[key]['stable']['metrics'])
        metrics.append(record['back']['stable']['metrics'])
    return {'scenario': 'stress', 'cycles_requested': r.args.cycles,
            'cycles_completed': len(cycles), 'direct': direct, 'cycles': cycles,
            'final_data': last_data, 'finish_identity': identity,
            'finish_event_indexes': _auto_indexes(r, finish_cursor),
            'resource_observations': metrics,
            'resource_trends': _auto_resource_trends(cycles),
            'resource_interpretation': 'raw ordered thread/RSS observations; no arbitrary leak threshold; resource accumulation not excluded',
            'event_indexes': _auto_indexes(r, start_cursor)}


def run_recovery(r):
    start_cursor = r.mark('recovery-direct-native')
    r.start('VrActivity', direct=True)
    session = r.native(start_cursor)
    initial = {'cursor': start_cursor, 'session': session,
               'stable': _auto_stable(r, 'recovery-initial-native'),
               'event_indexes': _auto_indexes(r, start_cursor)}
    normal_exit = _auto_close(r, session, 'recovery-normal-exit')
    snapshot = normal_exit['data']
    old_identity = normal_exit['identity_before_finish']
    reopen = _auto_reopen(r, snapshot, old_identity, 'recovery-normal-reopen')
    naturally_gone = (normal_exit['identity_after_finish']['pid'] is None
                      or _auto_relation(old_identity, normal_exit['identity_after_finish'])['new_process_proved'])
    if reopen['process_relation']['new_process_proved']:
        classification = 'natural_cold_process_recovery'
    elif reopen['process_relation']['kind'] == 'same_process' and not naturally_gone:
        classification = 'normal_exit_warm_reopen'
    else:
        classification = 'normal_exit_reopen_process_identity_insufficient'
    reopen['classification'] = classification
    reopen['old_disappearance_observed_at_finish'] = naturally_gone
    r.capture('recovery-normal-reopened-manager')
    session, normal_entry = _auto_enter(r, 'recovery-normal-reopen')
    normal_entry['stable'] = _auto_stable(r, 'recovery-normal-reopened-native')
    normal_closed = _auto_close(r, session, 'recovery-normal-reopened-exit')
    controlled_cold = None
    if classification != 'natural_cold_process_recovery':
        cold_cursor = r.mark('recovery-normal-exit-controlled-cold-condition')
        previous = normal_closed['identity_before_finish']
        expected = normal_closed['data']
        r.cold_condition()
        cold_reopen = _auto_reopen(r, expected, previous, 'recovery-controlled-cold')
        cold_reopen['classification'] = ('controlled_force_stop_after_normal_exit'
                                         if cold_reopen['process_relation']['new_process_proved']
                                         else 'controlled_cold_process_identity_insufficient')
        session, cold_entry = _auto_enter(r, 'recovery-controlled-cold')
        cold_entry['stable'] = _auto_stable(r, 'recovery-controlled-cold-native')
        cold_closed = _auto_close(r, session, 'recovery-controlled-cold-exit')
        controlled_cold = {'cursor': cold_cursor, 'reopen': cold_reopen,
                           'entry': cold_entry, 'normal_exit': cold_closed,
                           'event_indexes': _auto_indexes(r, cold_cursor)}
    expected = r.state()
    cursor = r.mark('recovery-background-kill-native')
    r.start('VrActivity', direct=True)
    first_read = r.first_read(cursor, expected)
    session = r.native(cursor)
    _auto_native_data(r, expected, r.state())
    kill_setup = {'cursor': cursor, 'session': session,
                  'first_read_event': first_read['index'],
                  'stable': _auto_stable(r, 'recovery-background-kill-native'),
                  'event_indexes': _auto_indexes(r, cursor)}
    background = _auto_close(r, session, 'recovery-background-before-kill')
    expected = background['data']
    cursor = r.mark('recovery-single-background-am-kill')
    target = r.identity()
    background['identity_before_kill'] = target
    # Exactly one cooperative background kill; no kill -9 or retry.
    r.adb('shell', 'am', 'kill', PKG)
    disappearance = _auto_disappearance(r, target, 'recovery-background-am-kill')
    kill = {'cursor': cursor, 'target_identity': target,
            'disappearance': disappearance, 'event_indexes': _auto_indexes(r, cursor)}
    fallback = None
    if disappearance['disappearance_proved']:
        kill_reopen = _auto_reopen(r, expected, target, 'recovery-after-am-kill')
        kill_reopen['classification'] = ('background_am_kill_new_process_data_recovery'
                                         if kill_reopen['process_relation']['new_process_proved']
                                         else 'background_disappeared_reopen_identity_insufficient')
        session, kill_entry = _auto_enter(r, 'recovery-after-am-kill')
        kill_entry['stable'] = _auto_stable(r, 'recovery-after-am-kill-native')
        r.capture('recovery-after-am-kill-native')
        kill_exit = _auto_close(r, session, 'recovery-after-am-kill-exit')
        kill.update({'reopen': kill_reopen, 'entry': kill_entry, 'normal_exit': kill_exit})
    else:
        kill['classification'] = 'background_am_kill_termination_not_covered'
        fallback_cursor = r.mark('recovery-am-kill-ineffective-force-stop-fallback')
        r.cold_condition()
        fallback_reopen = _auto_reopen(r, expected, target, 'recovery-kill-force-stop-fallback')
        fallback_reopen['classification'] = ('force_stop_data_recovery_not_background_kill_or_LMK'
                                             if fallback_reopen['process_relation']['new_process_proved']
                                             else 'force_stop_recovery_process_identity_insufficient')
        session, fallback_entry = _auto_enter(r, 'recovery-kill-force-stop-fallback')
        fallback_entry['stable'] = _auto_stable(r, 'recovery-kill-force-stop-fallback-native')
        r.capture('recovery-kill-force-stop-fallback-native')
        fallback_exit = _auto_close(r, session, 'recovery-kill-force-stop-fallback-exit')
        fallback = {'cursor': fallback_cursor, 'reopen': fallback_reopen,
                    'entry': fallback_entry, 'normal_exit': fallback_exit,
                    'event_indexes': _auto_indexes(r, fallback_cursor)}
    return {'scenario': 'recovery', 'initial_native': initial,
            'normal_exit': normal_exit, 'normal_reopen': reopen,
            'normal_reopen_entry': normal_entry, 'normal_reopen_exit': normal_closed,
            'controlled_cold_after_normal_exit': controlled_cold,
            'background_kill_setup': kill_setup, 'background_normal_exit': background,
            'background_am_kill': kill, 'separate_force_stop_fallback': fallback,
            'final_data': r.state(), 'final_identity': r.identity(),
            'event_indexes': _auto_indexes(r, start_cursor)}


def _manual_require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _manual_indexes(events):
    return [event['index'] for event in events]


def _manual_int(event, key):
    return number(event, key)


def _manual_pose(event, key, size):
    text = event['fields'].get(key, 'unavailable').rstrip(';')
    if text == 'unavailable':
        return None
    _manual_require(text.startswith('(') and text.endswith(')'), 'Malformed pose: ' + text)
    values = tuple(float(part) for part in text[1:-1].split(','))
    _manual_require(len(values) == size and all(value == value and abs(value) != float('inf') for value in values),
                    'Nonfinite or malformed pose: ' + text)
    return values


def _manual_checkpoint_process(r):
    checkpoint = r.checkpoint
    return (checkpoint['pid'], checkpoint['starttime_ticks'])


def _manual_same_process(expected, actual):
    return actual[0] == expected[0] and (expected[1] is None or actual[1] == expected[1])


def _manual_check_process(r):
    identity = r.identity()
    expected = _manual_checkpoint_process(r)
    actual = (identity['pid'], identity['starttime_ticks'])
    _manual_require(_manual_same_process(expected, actual),
                    'Unexplained process restart since manual prepare: %r -> %r' % (expected, actual))
    if expected[1] is None:
        # Same numeric PID alone cannot rule out reuse. Native/Manager instance
        # continuity is checked by each branch, rather than claiming cold recovery.
        return {'identity': identity, 'starttime_unavailable': True,
                'limitation': 'PID reuse cannot be excluded by /proc; lifecycle instance continuity required'}
    return {'identity': identity, 'starttime_unavailable': False}


def _manual_checkpoint(r, session):
    identity = r.identity()
    _manual_require(isinstance(identity['pid'], int), 'Prepared application has no readable PID')
    if session is not None:
        _manual_require(_manual_same_process((identity['pid'], identity['starttime_ticks']), session[:2]),
                        'Prepared session does not belong to current process')
    data = r.state()
    r.mark('manual-prepare-checkpoint')
    return {
        'scenario': r.args.scenario,
        'device': r.args.device,
        'apk_sha256': r.apk_sha256,
        'prepared_utc': utc(),
        'pid': identity['pid'],
        'starttime_ticks': identity['starttime_ticks'],
        'worker_id': session[2] if session is not None else None,
        'session_id': session[2] if session is not None else None,
        'last_snapshot': str(r.last_snapshot.relative_to(r.root_out)),
        'data': data,
    }


def _manual_submitted(events, focused=False):
    return [event for event in events if 'FRAME_SAMPLE ' in event['body']
            and _manual_int(event, 'submitted') == 1 and _manual_int(event, 'viewCount') == 2
            and (not focused or _manual_int(event, 'state') == 5)]


def _manual_sync_samples(events):
    return [event for event in events if 'HAND_SAMPLE ' in event['body']
            and _manual_int(event, 'syncAttempted') == 1 and _manual_int(event, 'syncResult') == 0]


def _manual_focused_frame(r, cursor, session):
    def ready():
        events = r.after(cursor, kind='xr', session=session)
        hands = _manual_sync_samples(events)
        for frame in _manual_submitted(events, focused=True):
            matching = [hand for hand in hands
                        if _manual_int(hand, 'frame') == _manual_int(frame, 'frame')
                        and _manual_int(hand, 'displayTime') == _manual_int(frame, 'predictedDisplayTime')]
            if matching:
                return {'frame': frame, 'hands': matching}
        return None
    return r.wait(ready, 'new focused stereo frame and same-frame exact XR_SUCCESS action sync')


def _manual_activity_events(r, cursor, process, activity=None):
    return [event for event in r.after(cursor, kind='activity')
            if event['fields'].get('role') == 'Native'
            and _manual_same_process(process, event['process'])
            and (activity is None or event.get('activity') == activity)]


def _manual_cancel_session(r, cursor, old):
    process = old[:2]
    def ready():
        events = [event for event in r.after(cursor, kind='xr')
                  if event.get('session') and _manual_same_process(process, event['process'])]
        frames = _manual_submitted(events, focused=True)
        return frames[-1]['session'] if frames else None
    session = r.wait(ready, 'Home cancel restores a new focused submitted frame')
    old_events = r.after(0, kind='xr', session=old)
    _manual_require(bool(old_events), 'Prepared session identity is missing from seed snapshot')
    old_activity = old_events[0].get('activity')
    _manual_require(old_activity is not None, 'Prepared session has no Activity identity')
    lifecycle = _manual_activity_events(r, cursor, process, old_activity)
    transitions = []
    creates = [event for event in r.after(cursor, kind='xr', body='XR session created')
               if _manual_same_process(process, event['process'])]
    previous = old
    for created in creates:
        replacement = created['session']
        _manual_require(replacement is not None and replacement != previous,
                        'Home cancel contains duplicate session creation')
        prior = r.after(0, kind='xr', session=previous)
        prior_activity = prior[0].get('activity') if prior else None
        prior_lifecycle = _manual_activity_events(r, cursor, process, prior_activity)
        causes = [event for event in prior_lifecycle if event['index'] < created['index']
                  and ('surfaceDestroyed' in event['body'] or 'onPause' in event['body'])]
        _manual_require(causes, 'Replacement session lacks real prior pause/Surface-destruction cause')
        r.released(previous)
        replacement_activity = created.get('activity')
        if replacement_activity != prior_activity:
            destroyed = [event for event in prior_lifecycle if 'onDestroy' in event['body']
                         and event['index'] < created['index']]
            _manual_require(destroyed, 'Replacement Activity lacks old Activity destruction')
        new_lifecycle = _manual_activity_events(r, cursor, process, replacement_activity)
        activation = [event for event in new_lifecycle if event['index'] < created['index']
                      and ('onResume' in event['body'] or 'surfaceCreated' in event['body'])]
        _manual_require(activation, 'Replacement lacks actual resume/Surface-create activation')
        first = r.after(cursor, kind='xr', body='FIRST_STEREO_FRAME', session=replacement)
        stereo = _manual_submitted(r.after(cursor, kind='xr', session=replacement))
        _manual_require(first and stereo, 'Replacement session has no real new stereo evidence')
        transitions.append({'old': previous, 'new': replacement,
                            'cause_indexes': _manual_indexes(causes),
                            'activation_indexes': _manual_indexes(activation),
                            'first_stereo_indexes': _manual_indexes(first)})
        previous = replacement
    _manual_require(previous == session, 'Focused session is not the causally reconstructed current session')
    if session == old:
        _manual_require(not any('onDestroy' in event['body'] for event in lifecycle),
                        'Prepared Native Activity was destroyed despite claimed same-session continuation')
    return session, transitions


def _manual_trigger(samples, full_cycle):
    active = []
    changes = []
    cycle = None
    low = high = previous = None
    for current in samples:
        if _manual_int(current, 'triggerActive') != 1:
            low = high = previous = None
            continue
        active.append(current)
        if previous and current['fields'].get('profile') != previous['fields'].get('profile'):
            low = high = previous = None
        value = float(current['fields']['value'])
        _manual_require(value == value and 0 <= value <= 1, 'Invalid trigger value')
        changed = bool(previous and _manual_int(current, 'changedSinceLastSync') == 1
                       and _manual_int(current, 'lastChangeTime') > _manual_int(previous, 'lastChangeTime')
                       and value != float(previous['fields']['value']))
        if changed:
            changes.append(current)
        if value <= 0.1:
            if low is not None and high is not None and changed:
                held = _manual_int(current, 'lastChangeTime') - _manual_int(high, 'lastChangeTime')
                observed = {'indexes': [low['index'], high['index'], current['index']],
                            'hold_ns': held,
                            'profile': current['fields'].get('profile')}
                if cycle is None or held > cycle['hold_ns']:
                    cycle = observed
            low, high = current, None
        elif value >= 0.9 and low is not None and high is None and changed:
            high = current
        previous = current
    covered = bool(cycle) if full_cycle else bool(changes)
    return {'status': 'not_covered_inactive' if not active else
            'observed' if covered else 'missing_interaction',
            'active_indexes': _manual_indexes(active), 'change_indexes': _manual_indexes(changes),
            'low_high_low': cycle}


def _manual_pose_observation(samples, prefix='', active_key=None):
    position_key = prefix + 'Position' if prefix else 'position'
    orientation_key = prefix + 'Orientation' if prefix else 'orientation'
    valid = []
    zero_quaternions = []
    for event in samples:
        if active_key and _manual_int(event, active_key) != 1:
            continue
        p = _manual_pose(event, position_key, 3)
        q = _manual_pose(event, orientation_key, 4)
        if q is not None and not any(q):
            zero_quaternions.append(event['index'])
        if p is not None and q is not None and any(q):
            valid.append((event, p, q))
    return {'sample_indexes': _manual_indexes(samples),
            'valid_pose_indexes': [event['index'] for event, _, _ in valid],
            'position_changed': len({p for _, p, _ in valid}) > 1,
            'orientation_changed': len({q for _, _, q in valid}) > 1,
            'zero_quaternion_indexes': zero_quaternions,
            'flags': sorted({event['fields'].get(prefix + 'Flags' if prefix else 'flags', 'unavailable')
                             for event in samples}),
            'tracking_claim': 'none; raw valid/tracked flags are observations, not proof of independent 6DoF'}


def _manual_haptics(events, hand):
    api = [event for event in events if 'HAPTIC_API ' in event['body']
           and event['fields'].get('hand') == hand]
    bounds = [event for event in events if 'HAPTIC_BOUND ' in event['body']
              and event['fields'].get('hand') == hand]
    applies = [event for event in api if event['fields'].get('op') == 'apply']
    _manual_require(len(applies) <= 1, 'Haptic preflight repeated for one worker/side')
    details = {'api_indexes': _manual_indexes(api), 'bound_indexes': _manual_indexes(bounds),
               'physical_vibration': 'not_verified', 'bound_sources_scope': 'opaque action-wide; not per-side binding proof'}
    samples = [event for event in _manual_sync_samples(events)
               if event['fields'].get('hand') == hand]
    suggestions = {event['fields'].get('profile') for event in events
                   if 'suggest profile=' in event['body'] and _manual_int(event, 'result') == 0}
    eligible = [event for event in samples if event['fields'].get('profile') in suggestions
                and (_manual_int(event, 'gripActive') == 1 or _manual_int(event, 'aimActive') == 1)]
    _manual_require(not eligible or bounds, 'Eligible haptic side lacks actual bound-source preflight')
    details['eligible_sample_indexes'] = _manual_indexes(eligible)
    for bound in bounds:
        if _manual_int(bound, 'result') != 0:
            name = bound['fields'].get('resultName', '')
            classification = bound['fields'].get('classification', '')
            _manual_require(classification in ('unsupported', 'no_output_expected', 'loss_pending'),
                            'Haptic bound-source API failure result=%s %s' % (bound['fields']['result'], name))
            details.update(status=classification, first_bound_result=_manual_int(bound, 'result'))
    if not applies:
        _manual_require(not any(_manual_int(bound, 'result') == 0 and _manual_int(bound, 'count') > 0
                                for bound in bounds), 'Bound eligible haptic side lacks real apply/stop calls')
        if bounds and _manual_int(bounds[0], 'result') == 0 and _manual_int(bounds[0], 'count') == 0:
            details['status'] = 'unbound'
        else:
            details.setdefault('status', 'not_covered')
        return details
    apply = applies[0]
    fields = apply['fields']
    _manual_require(fields.get('subactionPath') == '/user/hand/' + hand and _manual_int(apply, 'subaction') > 0,
                    'Haptic apply side/subaction mismatch')
    _manual_require(_manual_int(apply, 'duration') == 100_000_000
                    and float(fields['amplitude']) == 0.25 and float(fields['frequency']) == 0.0,
                    'Haptic apply parameters differ from approved preflight')
    _manual_require(any(_manual_int(bound, 'result') == 0 and _manual_int(bound, 'count') > 0
                        and bound['index'] < apply['index'] and bound['fields'].get('profile') == fields.get('profile')
                        for bound in bounds), 'Haptic apply lacks successful nonempty bound-source evidence')
    same_frame = [event for event in eligible if _manual_int(event, 'frame') == _manual_int(apply, 'frame')
                  and _manual_int(event, 'displayTime') == _manual_int(apply, 'displayTime')
                  and event['fields'].get('profile') == fields.get('profile')]
    state_evidence = []
    for event in events:
        if 'FRAME_SAMPLE ' in event['body']:
            if event['index'] < apply['index'] or _manual_int(event, 'frame') == _manual_int(apply, 'frame'):
                state_evidence.append((event['index'], _manual_int(event, 'state')))
        elif 'XR session state=' in event['body'] and event['index'] < apply['index']:
            match = re.search(r'state=(?:[A-Z_]+\()?(\d+)\)?', event['body'])
            if match:
                state_evidence.append((event['index'], int(match.group(1))))
    _manual_require(same_frame and state_evidence and max(state_evidence)[1] == 5,
                    'Haptic apply lacks focused state and synced/active same-frame eligibility')
    stops = [event for event in api if event['fields'].get('op') == 'stop' and event['index'] > apply['index']]
    _manual_require(stops, 'Haptic apply lacks immediate stop result')
    stop = stops[0]
    _manual_require(stop['fields'].get('reason') == 'immediate'
                    and stop['worker'] == apply['worker'] and stop['session'] == apply['session']
                    and _manual_int(stop, 'seq') == _manual_int(apply, 'seq') + 1
                    and _manual_int(stop, 'frame') == _manual_int(apply, 'frame')
                    and _manual_int(stop, 'displayTime') == _manual_int(apply, 'displayTime')
                    and stop['fields'].get('profile') == fields.get('profile')
                    and stop['fields'].get('subactionPath') == fields.get('subactionPath')
                    and _manual_int(stop, 'subaction') == _manual_int(apply, 'subaction'),
                    'Haptic stop was not immediate same-worker/frame/subaction API call')
    results = []
    for event in (apply, stop):
        result = _manual_int(event, 'result')
        name = event['fields'].get('resultName')
        if result == 0:
            classification = 'api_success'
            _manual_require(name == 'XR_SUCCESS', 'Haptic numeric success/name mismatch')
        elif name == 'XR_SESSION_NOT_FOCUSED':
            _manual_require(result == 8, 'Haptic NOT_FOCUSED numeric mismatch')
            classification = 'no_output_expected'
        elif name == 'XR_ERROR_PATH_UNSUPPORTED':
            classification = 'unsupported'
        elif name in ('XR_SESSION_LOSS_PENDING', 'XR_ERROR_SESSION_LOST', 'XR_ERROR_INSTANCE_LOST'):
            classification = 'loss_pending'
        else:
            raise RuntimeError('Haptic probe failure: first %s result=%d %s' % (event['fields']['op'], result, name))
        results.append({'index': event['index'], 'op': event['fields']['op'],
                        'result': result, 'result_name': name, 'classification': classification})
    details.update(first_results=results, parameters={'duration_ns': _manual_int(apply, 'duration'),
                   'amplitude': float(fields['amplitude']), 'frequency': float(fields['frequency']),
                   'subaction': _manual_int(apply, 'subaction'), 'subaction_path': fields['subactionPath']},
                   status='api_preflight_success' if all(item['result'] == 0 for item in results)
                   else next(item['classification'] for item in results if item['result'] != 0))
    return details


def _manual_reference_changes(events):
    changes = [event for event in events if event['body'].startswith('reference space change type=')]
    observations = []
    for change in changes:
        valid = _manual_int(change, 'poseValid') == 1
        if valid:
            _manual_require(_manual_pose(change, 'position', 3) is not None
                            and _manual_pose(change, 'orientation', 4) is not None,
                            'Valid reference-space change lacks actual transform')
        else:
            _manual_require(change['fields'].get('transform', '').rstrip(';') == 'unavailable',
                            'Invalid reference-space change was not marked unavailable')
        crossed = [event for event in events if event['index'] > change['index']
                   and 'FRAME_SAMPLE ' in event['body']
                   and _manual_int(event, 'predictedDisplayTime') >= _manual_int(change, 'changeTime')]
        if crossed:
            frame = crossed[0]
            frame_number = _manual_int(frame, 'frame')
            head = [event for event in events if 'HEAD_SAMPLE ' in event['body']
                    and _manual_int(event, 'frame') == frame_number]
            eyes = [event for event in events if 'EYE_SAMPLE ' in event['body']
                    and _manual_int(event, 'frame') == frame_number]
            hands = [event for event in events if 'HAND_SAMPLE ' in event['body']
                     and _manual_int(event, 'frame') == frame_number]
            _manual_require(head and {event['fields'].get('eye') for event in eyes} == {'left', 'right'}
                            and {event['fields'].get('hand') for event in hands} == {'left', 'right'},
                            'Reference-space crossing lacks actual head/eyes/hands sampling')
            crossing_indexes = _manual_indexes([frame] + head + eyes + hands)
        else:
            crossing_indexes = []
        observations.append({'index': change['index'], 'type': _manual_int(change, 'type'),
                             'change_time': _manual_int(change, 'changeTime'),
                             'world_type': _manual_int(change, 'worldType'), 'pose_valid': valid,
                             'position': change['fields'].get('position'),
                             'orientation': change['fields'].get('orientation'),
                             'crossing_indexes': crossing_indexes,
                             'crossing_status': 'sampled' if crossing_indexes else 'not_covered_pending'})
    return {'status': 'observed_runtime_event' if changes else 'not_covered', 'events': observations,
            'recenter_claim': 'no synthetic event; runtime reference remains anchored'}


def _manual_homepage(r):
    resolved = r.adb('shell', 'cmd', 'package', 'resolve-activity', '--brief',
                     '-a', 'android.intent.action.MAIN', '-c', 'android.intent.category.HOME')
    components = re.findall(r'\b([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)\b', resolved)
    _manual_require(components, 'System HOME activity could not be resolved')
    def normalized(component):
        package, activity = component.split('/', 1)
        return package + '/' + (package + activity if activity.startswith('.') else activity)
    homes = {normalized(component) for component in components if component.split('/', 1)[0] != PKG}
    _manual_require(homes, 'Resolved HOME is not a separate system homepage')
    dump = r.activities('manual-confirm-homepage')
    resumed = [line for line in dump.splitlines()
               if 'mResumedActivity' in line or 'topResumedActivity' in line or 'mTopResumedActivity' in line]
    top = {normalized(component) for line in resumed
           for component in re.findall(r'\b([A-Za-z0-9_.]+/[A-Za-z0-9_.$]+)\b', line)}
    _manual_require(top.intersection(homes) and not any(component.split('/', 1)[0] == PKG for component in top),
                    'Real system HOME is not the resumed foreground activity before reopen')
    return {'resolved_home_components': sorted(homes), 'resumed_components': sorted(top),
            'evidence': 'Activity dump matched resolved HOME component, before any reopen'}


def run_manual_prepare(r):
    scenario = r.args.scenario
    cursor = r.mark('manual-prepare-start')
    if scenario == 'input':
        r.start('LaunchActivity', haptics=True)
        data = r.manager(cursor)
        _manual_require(not r.after(cursor, kind='xr', body='XR session created'),
                        'Input prepare unexpectedly entered Native')
        r.activities('manual-input-manager-prepared')
        r.capture('manual-input-manager-prepared')
        checkpoint = _manual_checkpoint(r, None)
        _manual_require(checkpoint['data'] == data, 'Manager data changed during input prepare')
        return {'checkpoint': checkpoint, 'position': 'Manager; no automatic enter',
                'haptic_requested': True,
                'manual_instruction': 'Click the real enter-VR button, inspect cubes/axes/floor; move/rotate head and supported aim/grip, hold each available trigger five seconds then release, recenter only if actually available; stop in Native.',
                'event_indexes': _manual_indexes(r.after(cursor))}
    _manual_require(scenario in ('home-cancel', 'home-confirm'), 'Unknown manual prepare scenario')
    r.start('VrActivity', direct=True)
    session = r.native(cursor)
    r.capture('manual-home-native-before')
    home_cursor = r.mark('manual-prepare-home-overlay')
    r.adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
    unfocused = r.unfocused(home_cursor, session)
    r.capture('manual-home-overlay-prepared')
    checkpoint = _manual_checkpoint(r, session)
    return {'checkpoint': checkpoint, 'session': session,
            'position': 'Real Home overlay; Native remains untouched after VISIBLE/NOT_FOCUSED evidence',
            'unfocused_event_index': unfocused['index'],
            'manual_instruction': 'Cancel Home, press and release a supported trigger once, allowing a sampled high state, and stop in Native.'
            if scenario == 'home-cancel' else 'Confirm Home and stop on the system homepage.',
            'event_indexes': _manual_indexes(r.after(cursor))}


def _manual_run_cancel(r):
    cursor = r.checkpoint_cursor
    process_evidence = _manual_check_process(r)
    old = (_manual_checkpoint_process(r) + (r.checkpoint['session_id'],))
    session, transitions = _manual_cancel_session(r, cursor, old)
    focused = _manual_focused_frame(r, cursor, session)
    events = r.after(cursor, kind='xr', session=session)
    hands = _manual_sync_samples(events)
    sides = {}
    for side in ('left', 'right'):
        samples = [event for event in hands if event['fields'].get('hand') == side]
        _manual_require(samples, 'Home cancel lacks real per-side sync diagnostics for ' + side)
        sides[side] = _manual_trigger(samples, False)
        sides[side]['profiles'] = sorted({event['fields'].get('profile', 'unavailable') for event in samples})
        sides[side]['sample_indexes'] = _manual_indexes(samples)
    active = [side for side in sides.values() if side['active_indexes']]
    _manual_require(not active or any(side['status'] == 'observed' for side in active),
                    'Focused controller is active but no actual post-cancel trigger change was recorded')
    current_data = r.state()
    r.no_regression(r.checkpoint['data'], current_data)
    r.activities('manual-home-cancel-restored')
    r.capture('manual-home-cancel-restored')
    evidence_end = len(r.events)
    returned = r.back(session)
    finished = r.finish_manager()
    return {'scenario': 'home-cancel', 'session': session, 'checkpoint_session': old,
            'process': process_evidence, 'causal_rebuilds': transitions,
            'focus_and_stereo': 'observed', 'focused_frame_index': focused['frame']['index'],
            'same_frame_sync_indexes': _manual_indexes(focused['hands']), 'input': sides,
            'input_recovery': 'observed' if active else 'not_covered_no_active_controller',
            'data_before': r.checkpoint['data'], 'data_restored': current_data, 'data_after_back': returned,
            'finished_identity': finished, 'event_indexes': _manual_indexes(r.after(cursor)),
            'manual_evidence_end_index': evidence_end,
            'visual_confirmation': 'requires actual screenshot/user review; runtime evidence alone does not prove appearance'}


def _manual_run_confirm(r):
    cursor = r.checkpoint_cursor
    process = _manual_checkpoint_process(r)
    session = process + (r.checkpoint['session_id'],)
    seeded = r.after(0, kind='xr', session=session)
    _manual_require(seeded, 'Prepared Home session missing from seed snapshot')
    activity = seeded[0].get('activity')
    _manual_require(activity is not None, 'Prepared Native Activity identity missing')
    def retired():
        lifecycle = _manual_activity_events(r, cursor, process, activity)
        required = ('surfaceDestroyed', 'onPause', 'onStop')
        return lifecycle if all(any(marker in event['body'] for event in lifecycle) for marker in required) else None
    lifecycle = r.wait(retired, 'real Home-confirm Native Surface destruction, onPause and onStop')
    r.released(session)
    created = [event for event in r.after(cursor, kind='xr', body='XR session created')]
    _manual_require(not created, 'Home confirm unexpectedly created a new Native session before reopen')
    homepage = _manual_homepage(r)
    committed = r.state()
    r.no_regression(r.checkpoint['data'], committed)
    r.capture('manual-home-confirm-homepage')
    reopen_cursor = r.mark('manual-home-confirm-reopen-manager')
    r.start('LaunchActivity')
    identity = r.identity()
    read = r.first_read(reopen_cursor, committed, process=(identity['pid'], identity['starttime_ticks']))
    manager_data = r.manager(reopen_cursor)
    _manual_require(manager_data == committed, 'Home-confirm manager data changed before debug enter')
    r.capture('manual-home-confirm-reopened-manager')
    enter_cursor = r.mark('manual-home-confirm-enter')
    r.start('LaunchActivity', action='enter')
    new_session = r.native(enter_cursor, previous=session)
    r.no_regression(committed, r.state())
    r.capture('manual-home-confirm-reopened-native')
    returned = r.back(new_session)
    finished = r.finish_manager()
    return {'scenario': 'home-confirm', 'retired_session': session,
            'lifecycle_indexes': _manual_indexes(lifecycle), 'homepage': homepage,
            'committed_data': committed, 'first_read_index': read['index'],
            'reopened_identity': identity, 'new_session': new_session, 'data_after_back': returned,
            'finished_identity': finished, 'event_indexes': _manual_indexes(r.after(cursor)),
            'visual_confirmation': 'requires manager/native screenshot review; no synthetic Home confirmation'}


def _manual_run_input(r):
    cursor = r.checkpoint_cursor
    process_evidence = _manual_check_process(r)
    process = _manual_checkpoint_process(r)
    button = [event for event in r.after(cursor, kind='activity', body='switch manager -> native')
              if event['fields'].get('role') == 'Manager' and _manual_same_process(process, event['process'])]
    _manual_require(button, 'No real prepared Manager enter-button transition after checkpoint')
    prepared_managers = [event['activity'] for event in r.events[:cursor]
                         if event['kind'] == 'activity' and event['fields'].get('role') == 'Manager'
                         and _manual_same_process(process, event['process']) and 'onResume' in event['body']]
    _manual_require(prepared_managers and button[0]['activity'] == prepared_managers[-1],
                    'Real enter transition is not from the prepared Manager instance')
    session = r.native(cursor)
    created = r.after(cursor, kind='xr', body='XR session created', session=session)
    _manual_require(created and button[0]['index'] < created[0]['index'],
                    'Native session was not created after actual Manager button entry')
    _manual_focused_frame(r, cursor, session)
    events = r.after(cursor, kind='xr', session=session)
    worker_started = [event for event in r.after(cursor, kind='xr', body='worker started')
                      if event.get('worker') == created[0]['worker']]
    _manual_require(len(worker_started) == 1 and _manual_int(worker_started[0], 'hapticProbe') == 1,
                    'Real Manager button did not pass explicit debug haptic configuration to Native')
    submitted = _manual_submitted(events)
    head_samples = [event for event in events if 'HEAD_SAMPLE ' in event['body']]
    head = _manual_pose_observation(head_samples)
    _manual_require(head['position_changed'] and head['orientation_changed'],
                    'Real head translation and rotation changes were not recorded')
    eyes = {}
    for side in ('left', 'right'):
        samples = [event for event in events if 'EYE_SAMPLE ' in event['body']
                   and event['fields'].get('eye') == side]
        eyes[side] = _manual_pose_observation(samples)
        _manual_require(eyes[side]['position_changed'] and eyes[side]['orientation_changed'],
                        'Eye %s pose did not follow actual head translation/rotation' % side)
    hands = {}
    synced = _manual_sync_samples(events)
    for side in ('left', 'right'):
        samples = [event for event in synced if event['fields'].get('hand') == side]
        _manual_require(samples, 'No actual hand diagnostics for ' + side)
        trigger = _manual_trigger(samples, True)
        _manual_require(trigger['status'] != 'missing_interaction',
                        'Active %s trigger lacks real low-high-low cycle' % side)
        grip = _manual_pose_observation(samples, 'grip', 'gripActive')
        aim = _manual_pose_observation(samples, 'aim', 'aimActive')
        active_aim = [event for event in samples if _manual_int(event, 'aimActive') == 1]
        if aim['valid_pose_indexes']:
            _manual_require(aim['position_changed'] or aim['orientation_changed'],
                            'Supported %s aim pose did not change during manual input' % side)
        head_positions = {event['fields'].get('position') for event in head_samples}
        grip_head_indexes = [event['index'] for event in samples
                             if event['fields'].get('gripPosition') in head_positions
                             and _manual_int(event, 'gripPositionValid') == 1]
        limitations = []
        if grip['zero_quaternion_indexes']:
            limitations.append('Runtime reports a valid grip orientation with zero quaternion; not a useful grip pose or independent 6DoF')
        if grip_head_indexes:
            limitations.append('Reported grip position matches sampled head position; no independent controller position claim')
        if not grip['position_changed'] and not grip['orientation_changed']:
            limitations.append('Grip motion not covered/fixed in observed mode')
        hands[side] = {'status': 'observed_supported_input' if trigger['active_indexes'] else 'not_covered_inactive_trigger',
                       'profiles': sorted({event['fields'].get('profile', 'unavailable') for event in samples}),
                       'sample_indexes': _manual_indexes(samples), 'trigger': trigger, 'grip': grip, 'aim': aim,
                       'aim_status': 'observed_motion' if aim['position_changed'] or aim['orientation_changed']
                       else 'not_covered_invalid_pose' if active_aim else 'not_covered_inactive',
                       'grip_matches_head_indexes': grip_head_indexes,
                       'flags_and_active': [dict(index=event['index'], **{key: value for key, value in event['fields'].items()
                                                if key.endswith(('Valid', 'Tracked', 'Active', 'Flags'))}) for event in samples],
                       'haptic': _manual_haptics(events, side), 'limitations': limitations}
    reference = _manual_reference_changes(events)
    current_data = r.state()
    r.no_regression(r.checkpoint['data'], current_data)
    r.activities('manual-input-native-observed')
    r.capture('manual-input-native-observed')
    evidence_end = len(r.events)
    returned = r.back(session)
    finished = r.finish_manager()
    summaries = r.after(cursor, kind='xr', body='HAPTIC_SUMMARY', session=session)
    for side in ('left', 'right'):
        hands[side]['haptic']['summary_indexes'] = _manual_indexes(
            [event for event in summaries if event['fields'].get('hand') == side])
    return {'scenario': 'input', 'session': session, 'process': process_evidence,
            'real_button_indexes': _manual_indexes(button), 'submitted_frame_indexes': _manual_indexes(submitted),
            'head': head, 'eyes': eyes, 'hands': hands, 'reference_space': reference,
            'data_before': r.checkpoint['data'], 'data_observed': current_data, 'data_after_back': returned,
            'finished_identity': finished, 'manual_evidence_end_index': evidence_end,
            'event_indexes': _manual_indexes(r.after(cursor)),
            'visual_confirmation': 'Cube/grid/axis/hand pose consistency requires actual screenshot and user review; not inferred from numeric logs',
            'haptic_claim': 'API preflight only; physical vibration not verified',
            'tracking_claim': 'No blanket two-hand 6DoF claim; supported mode and raw flags reported per side'}


def run_manual_check(r):
    r.snapshot()
    if r.args.scenario == 'home-cancel':
        return _manual_run_cancel(r)
    if r.args.scenario == 'home-confirm':
        return _manual_run_confirm(r)
    if r.args.scenario == 'input':
        return _manual_run_input(r)
    raise RuntimeError('Unknown manual check scenario: ' + r.args.scenario)


def main(argv=None):
    args = arguments(argv)
    r = None
    result = {"scenario": args.scenario, "phase": args.phase, "device": args.device, "started_utc": utc()}
    try:
        r = Runner(args)
        r.connect()
        if args.phase == "prepare":
            detail = run_manual_prepare(r)
            r.save("checkpoint.json", detail.pop("checkpoint"))
        elif args.phase == "check":
            detail = run_manual_check(r)
        else:
            detail = {"baseline": run_baseline, "stress": run_stress, "recovery": run_recovery, "cost": run_cost}[args.scenario](r)
        result.update(status="passed" if args.phase != "prepare" else "prepared", detail=detail,
                      apk_sha256=r.apk_sha256, max_live_workers=r.max_workers, max_live_sessions=r.max_sessions)
    except Exception as error:
        result.update(status="failed", primary_error=repr(error))
    finally:
        if r:
            r.collect()
            if result["status"] != "failed" and r.validation_failure is not None:
                result.update(status="failed", primary_error=r.validation_failure)
            result.update(ended_utc=utc(), collection_errors=r.collect_errors,
                          live_workers=list(r.live_workers), live_sessions=list(r.live_sessions))
            r.save("result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in ("passed", "prepared") else 1


if __name__ == "__main__":
    sys.exit(main())
