#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
export JAVA_HOME="${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v javac)")")")}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$HOME/.gradle}"
export PATH="$JAVA_HOME/bin:$PATH"
[[ -x "$JAVA_HOME/bin/javac" ]] || { echo "JDK 17-23 required: set JAVA_HOME" >&2; exit 1; }
[[ -f "$ANDROID_HOME/platforms/android-35/android.jar" ]] || { echo "Missing Android platform 35 in $ANDROID_HOME" >&2; exit 1; }
cmake_bin="$(command -v cmake)"
ninja_bin="$(command -v ninja)"
cd "$root/prototypes/spatial-openxr"
# Explicit existing host binaries prevent AGP from downloading a redundant SDK CMake.
exec ./gradlew --console=plain -Dorg.gradle.java.home="$JAVA_HOME" \
  -Pcmake.dir="$(dirname "$(dirname "$cmake_bin")")" \
  -Pandroid.injected.cmake.ninja.path="$ninja_bin" assembleDebug "$@"
