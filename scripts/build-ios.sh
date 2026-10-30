#!/bin/bash
# Build Touchline 27 for iOS: build/Touchline27.ipa (unsigned, not installed)
#
#   ./scripts/build-ios.sh --nsp-dir "/path/to/fc27" --shader-pack "/path/to/pack"
#
# The IPA keeps the bundle ID org.nxnative.0100c49025d3e000, so a re-signed
# build upgrades the App already on the device and keeps its Documents: the
# imported NSPs, prod.keys and saves stay where they are. Nothing is signed or
# installed here: sign the IPA with your own tool, or run dm/ios/tools/build_ipa.sh
# --prepare-xcode and let Xcode sign the generated project with your team.
# Run with --help for all options; docs/building.md explains each input.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd) || { echo "[RED] cannot locate the project root" >&2; exit 1; }
PYTHON=${PYTHON:-python3}

fail() { echo "[RED] $*" >&2; exit 1; }

[ "$(uname -s)" = Darwin ] || fail "Touchline 27 builds only on macOS"
command -v "$PYTHON" > /dev/null 2>&1 || fail "$PYTHON is not installed (set PYTHON=... to choose one)"
for tool in xcodebuild xcodegen make xcrun; do
    command -v "$tool" > /dev/null 2>&1 || fail "$tool is not installed; Xcode and 'brew install xcodegen' are required"
done
xcodebuild -version > /dev/null 2>&1 || fail "xcodebuild cannot run: select Xcode with xcode-select -s /Applications/Xcode.app"

exec "$PYTHON" "$ROOT/scripts/touchline_build.py" --target ios "$@"
