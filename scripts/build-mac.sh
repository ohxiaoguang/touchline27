#!/bin/bash
# Build Touchline 27 for macOS: build/Touchline27.app
#
#   ./scripts/build-mac.sh --nsp-dir "/path/to/fc27" --shader-pack "/path/to/pack"
#
# The game files are yours: this script reads the ExeFS and control data out of
# them, rewrites the modules, and packages an App that carries no game data.
# Every path is resolved from this project, never from the caller's directory.
# Run with --help for all options; docs/building.md explains each input.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd) || { echo "[RED] cannot locate the project root" >&2; exit 1; }
PYTHON=${PYTHON:-python3}

fail() { echo "[RED] $*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || fail "Touchline 27 builds only on macOS"
command -v "$PYTHON" > /dev/null 2>&1 || fail "$PYTHON is not installed (set PYTHON=... to choose one)"
for tool in clang make xcrun swiftc sips; do
    command -v "$tool" > /dev/null 2>&1 || fail "$tool is not installed; install Xcode and its command line tools"
done

exec "$PYTHON" "$ROOT/scripts/touchline_build.py" --target mac "$@"
