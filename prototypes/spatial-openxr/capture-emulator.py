#!/usr/bin/env python3
"""PICO selectors for the reusable exact-window PrintWindow capture helper."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(
    Path(__file__).resolve().parents[2]
    / ".agents/skills/wsl-windows-interop/scripts"
))
import windows_interop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", "--out", dest="output", type=Path, required=True)
    parser.add_argument("--title", default="PICO Emulator - 6.1.0",
                        help="Exact full emulator window title, not an AVD name substring")
    args = parser.parse_args()
    return windows_interop.main([
        "capture", "--process", "qemu-system-x86_64",
        "--title", args.title, "--output", str(args.output),
    ])


if __name__ == "__main__":
    sys.exit(main())
