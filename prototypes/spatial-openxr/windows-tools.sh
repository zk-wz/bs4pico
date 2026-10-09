#!/usr/bin/env bash
set -euo pipefail
[[ $# -ge 1 ]] || { echo "Usage: $0 adb|pico <arguments...>" >&2; exit 2; }
case "$1" in adb|pico) ;; *) echo "Unknown Windows tool: $1" >&2; exit 2;; esac
repo_root="$(dirname -- "$(dirname -- "$(dirname -- "$(realpath -- "${BASH_SOURCE[0]}")")")")"
exec python3 "$repo_root/.agents/skills/wsl-windows-interop/scripts/windows_interop.py" run "$@"
