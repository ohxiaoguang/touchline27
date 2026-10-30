#!/bin/bash
# Build one unsigned all-in-one IPA: the rewritten modules compiled into the executable, iOS shader libraries at DmIOS.app/msl, and the game files (RomFS) at DmIOS.app/romfs.
# In IPA mode Xcode skips the large resource copy; tools/pack_ipa.py packs the shader libraries, add-on content and RomFS straight from where they are (no Payload/ copy, nothing through the home disk).
# In --prepare-xcode mode the generated project copies those resources before Xcode signs it with the team the user selects. This script never signs or installs anything.
# Prerequisites: the rewriter (patched directory) and the iOS shader build (IOSOUT) have been run as in the README; Xcode and xcodegen are installed.
# Usage: dm/ios/tools/build_ipa.sh [output.ipa | --prepare-xcode]; --prepare-xcode generates the project without building, signing or packing.
#   Environment: GAME=game profile (dm/games/<base game title ID>, or one in DM_GAMES_DIR; required), W=the game's work folder (required: <NSP folder>/<title ID>-work, never the home folder), PATCHED / ROMFS / MSL_IOS can each be overridden
#   AOC=add-on content directory (default $W/data/aoc; when it exists it goes to DmIOS.app/aoc/<index>/; an empty string = none), GFXAPI=nvn / vulkan (default: by the shader libraries in MSL_IOS)
#   The app name is the game name in the base NSP's control data ($W/data/v0/control.nacp, else the one next to the RomFS), the app version is the display version in the packed game's control data (the one next to the RomFS:
#   nx_extract saves the update's there when an update is packed, else the base game's), the bundle ID is org.nxnative.<base game title ID in lowercase> (DM_DISPLAY_NAME / DM_APP_VERSION / DM_BUNDLE_ID override them);
#   DM_SHOW_FPS=1 turns the frame-rate counter on (DMShowFPS in Info.plist; DM_SHOW_FPS in the app's Documents/env.txt overrides it on the phone);
#   DM_LANG=<language code> is the game language (DMLanguage in Info.plist, default en-US; DM_LANG in the app's Documents/env.txt overrides it on the phone);
#   both are also the launcher's defaults (dm/launcher.json from dm/games/settings.py; the player's choice there wins over them, Documents/env.txt over the choice);
#   the IPA name, code modules, RomFS marker and shader tables come from the game profile
set -u
cd "$(dirname "$0")/.." || exit 1
IOS_SOURCE=$PWD; IOS=$PWD; DM=$(cd .. && pwd)
export DM_SHARED_LAUNCHER_DIR="$DM/apple"
t() { echo "[$(date +%T)] $*"; }; die() { t "FAIL: $*"; exit 1; }
[ -n "${GAME:-}" ] || die "GAME is not set: GAME=<base game title ID> $0; profiles: $(python3 "$DM/games/game.py" list | awk -F'\t' '{printf "%s (%s)  ", $1, $3}')"
export DM_RESOURCE_BACKEND=${DM_RESOURCE_BACKEND:-directory}
case "$DM_RESOURCE_BACKEND" in directory|nsp) ;; *) die 'DM_RESOURCE_BACKEND must be directory or nsp';; esac
# No host paths or keys may be embedded in a diagnostic env file.
if [ "$DM_RESOURCE_BACKEND" = nsp ] && [ -n "${DM_ENV_FILE:-}" ]; then
    if grep -Eq '^[[:space:]]*DM_RESOURCE_(NSP|UPDATE|KEYS)=' "$DM_ENV_FILE"; then die 'Set resource paths on the device, never in a bundled DM_ENV_FILE'; fi
fi
export GAME; GD=$(python3 "$DM/games/game.py" dir "$GAME") || die "no game profile $GAME"   # dm/games/<id>, or a profile in DM_GAMES_DIR (the NSP script's provisional one); the make that gen_build.py runs uses the same GAME
gp() { python3 "$DM/games/game.py" "$GAME" "$1" || die "game profile $GD: $1"; }   # read a key of the game profile
[ -f "$GD/game.tsv" ] || die "no game profile $GD/game.tsv"
[ -n "${W:-}" ] || die "W is not set: W=<NSP folder>/$GAME-work (the game's work folder) $0"
PKG=$(gp package)
PATCHED=${PATCHED:-$W/build/patched_$PKG}; ROMFS=${ROMFS:-$W/data/$PKG/RomFS}; MSL_IOS=${MSL_IOS:-$W/build/ios/dmsh_b}; AOC=${AOC-$W/data/aoc}
PREPARE_XCODE=NO; [ "${1:-}" != --prepare-xcode ] || PREPARE_XCODE=YES
OUT_IPA=${1:-$(dirname "$W")/$(gp ipa)}; O=$W/build/ios/pkg; DD=$O/dd
XCODE_DD=${DM_XCODE_DERIVED_DATA:-$W/build/ios/xcode-dd}
MODS=$(gp modules); MARKER=$(gp romfs_marker)
NACP=$W/data/v0/control.nacp; [ -f "$NACP" ] || NACP=$(dirname "$ROMFS")/control.nacp
[ -n "${DM_DISPLAY_NAME:-}" ] || DM_DISPLAY_NAME=$(python3 "$DM/tools/nacp.py" "$NACP") || die "no game name in $NACP (re-extract with nx_extract, or set DM_DISPLAY_NAME)"
VNACP=$(dirname "$ROMFS")/control.nacp; [ -f "$VNACP" ] || VNACP=$W/data/v0/control.nacp
[ -n "${DM_APP_VERSION:-}" ] || DM_APP_VERSION=$(python3 "$DM/tools/nacp.py" --version "$VNACP") || { t "no display version in $VNACP: the app version is 1.0"; DM_APP_VERSION=1.0; }
export LC_ALL=C DM_BUNDLE_ID=${DM_BUNDLE_ID:-org.nxnative.$(echo "$GAME" | tr 'A-Z' 'a-z')} DM_DISPLAY_NAME DM_APP_VERSION DM_APP_CATEGORY=$(gp app_category) DM_TEAM_ID=${DM_TEAM_ID:-0000000000}   # placeholder identity: unsigned, the install tool replaces it
if [ "${DM_SHOW_FPS:-0}" = 1 ]; then export DM_SHOW_FPS=YES; else export DM_SHOW_FPS=NO; fi
export DM_LANG=${DM_LANG:-en-US}
if [ "$PREPARE_XCODE" = YES ]; then
  IOS=${DM_XCODE_PROJECT_DIR:-$W/xcode}
  mkdir -p "$IOS" || die "mkdir $IOS"
  IOS=$(cd "$IOS" && pwd)
  [ "$IOS" != "$IOS_SOURCE" ] || die "the per-game Xcode project must be outside dm/ios"
  # Source links follow repository edits; generated files and build products belong to this game only. Linked again each time: a project prepared from another checkout (a removed worktree) follows this one
  for item in Sources tools; do ln -sfn "$IOS_SOURCE/$item" "$IOS/$item" || die "link $item"; done
  cp "$IOS_SOURCE/project.yml" "$IOS/project.yml" || die "copy project template"
  cd "$IOS" || die "cd $IOS"
  DM_SCHEME_NAME="$(echo "$DM_DISPLAY_NAME" | tr '/:' '__') ($GAME)"   # the scheme file is named after it

elif [ -n "${DM_IOS_BUILD_DIR:-}" ]; then
  # An unsigned build can also keep generated inputs outside the source tree.
  # Require a fresh directory: never replace another build's project or links.
  [ ! -e "$DM_IOS_BUILD_DIR" ] && [ ! -L "$DM_IOS_BUILD_DIR" ] || die 'DM_IOS_BUILD_DIR must be a new directory'
  mkdir -p "$DM_IOS_BUILD_DIR" || die 'mkdir DM_IOS_BUILD_DIR'
  IOS=$(cd "$DM_IOS_BUILD_DIR" && pwd)
  for item in Sources tools; do ln -s "$IOS_SOURCE/$item" "$IOS/$item" || die "link $item"; done
  cp "$IOS_SOURCE/project.yml" "$IOS/project.yml" || die 'copy project template'
  cd "$IOS" || die "cd $IOS"
  DM_SCHEME_NAME=DmIOS
else DM_SCHEME_NAME=DmIOS; fi
export DM_SCHEME_NAME
for f in $MODS; do [ -f "$PATCHED/$f.patched.bin" ] && [ -f "$PATCHED/$f.fixups.tsv" ] || die "no rewritten module $PATCHED/$f (run dm/tools/patch_nso.py first)"; done
if [ "$DM_RESOURCE_BACKEND" = directory ]; then [ -e "$ROMFS/$MARKER" ] || die "no RomFS at $ROMFS (missing $MARKER)"; fi   # nsp mode reads the game from the player's NSP: no RomFS is staged
V=$(sed -n 's/^#define DMSH_CHAIN "\(.*\)"/\1/p' "$DM/gfx/nvn/dmsh_chain.h")   # the chain version the host is compiled with, one for every game
# A Vulkan game (Hades): the shaders are the game's SPIR-V, translated by dm/gfx/tools/vk_shaders.py into $MSL_IOS/vk; an OpenGL game (Digimon Story Cyber Sleuth): its GLSL, translated by
# dm/gfx/tools/gl_shaders.py into $MSL_IOS/gl; neither has NVN chain libraries. GFXAPI=nvn / vulkan / gl says which (the NSP script passes what main imports); without it, the shader
# libraries in $MSL_IOS tell: the chain's b-$V, else vk, else gl
if [ -z "${GFXAPI:-}" ]; then if ls "$MSL_IOS/b-$V" 2> /dev/null | grep -q '_b.metallib$'; then GFXAPI=nvn; elif [ -f "$MSL_IOS/vk/vk_shaders.metallib" ]; then GFXAPI=vulkan;
  elif [ -f "$MSL_IOS/gl/gl_shaders.metallib" ]; then GFXAPI=gl; else GFXAPI=nvn; fi; fi
if [ "$GFXAPI" = vulkan ]; then [ -f "$MSL_IOS/vk/vk_shaders.metallib" ] || die "no iOS Vulkan shader library $MSL_IOS/vk (dm/gfx/tools/vk_shaders.py \"$ROMFS\" <Mac dir> --ios \"$MSL_IOS\")"
elif [ "$GFXAPI" = gl ]; then [ -f "$MSL_IOS/gl/gl_shaders.metallib" ] || die "no iOS GL shader library $MSL_IOS/gl (dm/gfx/tools/gl_shaders.py \"$ROMFS\" <main> <Mac dir> --ios \"$MSL_IOS\")"
else [ -n "$V" ] && ls "$MSL_IOS/b-$V" 2> /dev/null | grep -q '_b.metallib$' || die "no iOS shader libraries $MSL_IOS/b-$V (IOSOUT=$MSL_IOS dmsh_build.py ...)"
  # One chain version serves every game and every state of a profile's tables: the libraries' stamp (b-$V/inputs.tsv, written by a full dmsh_build.py run) must name this game and the
  # digest of its profile's current inputs, and c1_full.tsv (not in the repository: the same build makes it, and cb_extent.tsv, from its Mac outputs) must name that digest, or the host ignores it
  IN=$(DM_GAME="$GAME" python3 "$DM/gfx/tools/dmsh_chain.py" --inputs) || die "dmsh_chain.py --inputs (game profile $GD)"
  grep -qxF "$(printf 'game\t%s' "$GAME")" "$MSL_IOS/b-$V/inputs.tsv" 2> /dev/null && grep -qxF "$(printf 'inputs\t%s' "$IN")" "$MSL_IOS/b-$V/inputs.tsv" ||
    die "the iOS shader libraries $MSL_IOS/b-$V are not a full build from this profile's current tables (inputs $IN; their stamp: $([ -f "$MSL_IOS/b-$V/inputs.tsv" ] && grep -v '^#' "$MSL_IOS/b-$V/inputs.tsv" | tr '\n\t' '  ' || echo none)): build them again (IOSOUT=$MSL_IOS dmsh_build.py ...)"
  head -1 "$GD/c1_full.tsv" 2> /dev/null | grep -q "^# chain b-$V inputs $IN " || die "$GD/c1_full.tsv is missing or not made from these libraries (chain $V, inputs $IN): a full dmsh_build.py run makes it and cb_extent.tsv"; fi

t "app: $DM_DISPLAY_NAME $DM_APP_VERSION ($DM_BUNDLE_ID), language $DM_LANG$([ $DM_SHOW_FPS = YES ] && echo ', frame-rate counter on')"
t "generate Gen/ (host sources, embedded modules, tables)"
rm -rf Gen && mkdir -p Gen/dm || die "mkdir Gen"
python3 tools/gen_build.py "$DM/host" Gen > Gen/dm.xcconfig || die "gen_build"
F=$(python3 tools/gen_embed.py "$PATCHED" Gen/embed.S $MODS) || die "gen_embed"
echo "OTHER_LDFLAGS = \$(inherited) \$(DM_FRAMEWORKS) $F" >> Gen/dm.xcconfig
cp "$PATCHED"/*.fixups.tsv "$PATCHED"/*.gates.tsv "$PATCHED"/*.cuts.tsv "$PATCHED"/*.obs.tsv Gen/dm/ || die "copy rewriter tables"
if [ -f "$PATCHED/nro.tsv" ]; then cp "$PATCHED/nro.tsv" Gen/dm/ || die "copy the NRO table"; fi   # the NRO modules the game loads with nn::ro (hle_ro.c), embedded by gen_embed.py
if [ "$GFXAPI" = vulkan ] || [ "$GFXAPI" = gl ]; then cp "$GD/shader_map.tsv" "$GD/pso_manifest.tsv" Gen/dm/ || die "copy shader tables"   # empty NVN tables: the NVN layer draws nothing
else cp "$GD/shader_map.tsv" "$GD/pso_manifest.tsv" "$GD/c1_full.tsv" Gen/dm/ || die "copy shader tables"
  if [ -f "$GD/cb_extent.tsv" ]; then cp "$GD/cb_extent.tsv" Gen/dm/ || die "copy cb_extent.tsv"; else t "no $GD/cb_extent.tsv: the host copies whole uniform bindings"; fi; fi   # optional
# The launcher's settings for this game (Launcher.swift): dm/games/settings.tsv filtered by the profile, main's rewriter table and the game's languages (dm/games/settings.py)
L=$(python3 "$DM/games/settings.py" "$GAME" "$PATCHED" "$VNACP" Gen/dm/launcher.json) || die "launcher settings (dm/games/settings.py)"; t "launcher: $L"
# Diagnostic build: DM_ENV_FILE=file → dm/env.txt in the bundle (main.m sets one environment variable per line at boot)
if [ -n "${DM_ENV_FILE:-}" ]; then cp "$DM_ENV_FILE" Gen/dm/env.txt || die "copy DM_ENV_FILE"; t "env: $(grep -v '^#' "$DM_ENV_FILE" | tr '\n' ' ')"; fi
# The shader libraries go into the archive as DmIOS.app/msl/<folder> (main.m sets DM_MSL_DIR to it)
if [ "$GFXAPI" = vulkan ]; then MSLDIR=vk; elif [ "$GFXAPI" = gl ]; then MSLDIR=gl; else MSLDIR=b-$V; fi
# Shared-font stand-ins: standard = macOS's Arial Unicode (absent on iOS), Nintendo extension = button icons generated by make_ext_font.py (needs fontTools; FONT_PY names a python that has it)
mkdir -p Gen/dm/font && cp "${STD_FONT:-/System/Library/Fonts/Supplemental/Arial Unicode.ttf}" Gen/dm/font/standard.ttf || die "copy standard font (STD_FONT=a TTF)"
"${FONT_PY:-python3}" "$DM/tools/make_ext_font.py" Gen/dm/font/nintendo_ext.ttf > /dev/null || die "make_ext_font.py (pip install fonttools, or FONT_PY=python with fontTools)"
# App icon: Touchline 27's own icon (assets/app-icon/touchline27.png), not the game's control-data icon.jpg. DM_ICON can point at another image.
# It is scaled to a 1024x1024 PNG in the asset catalog Gen/Assets.xcassets (a single-size app icon; actool generates the other sizes); with no icon file, no icon is set and the home-screen icon is blank.
# The catalog is always created (the project always lists it, see project.yml); without an icon it stays empty and DM_APPICON is not set
ICON=${DM_ICON:-$DM/assets/app-icon/touchline27.png}
mkdir -p Gen/Assets.xcassets && printf '{"info":{"author":"xcode","version":1}}\n' > Gen/Assets.xcassets/Contents.json || die "asset catalog"
if [ -f "$ICON" ]; then
  AI=Gen/Assets.xcassets/AppIcon.appiconset; mkdir -p "$AI" || die "mkdir $AI"
  sips -s format png -z 1024 1024 "$ICON" --out "$AI/icon.png" > /dev/null || die "sips: cannot convert the icon $ICON"
  printf '{"images":[{"filename":"icon.png","idiom":"universal","platform":"ios","size":"1024x1024"}],"info":{"author":"xcode","version":1}}\n' > "$AI/Contents.json"
  echo "DM_APPICON = AppIcon" >> Gen/dm.xcconfig
  t "app icon: $ICON"
else t "no app icon ($ICON not found): the home-screen icon stays blank"; fi
# A guest block over 6 GB cannot be reserved on iOS without the extended-virtual-addressing entitlement: a process
# then has about 7.4 GB of address space in all and the host dies at nnosInitialize (FATAL reserve guest AS, hle_svc.c
# mem_init; a single 6 GB reservation succeeds, 7 GB fails, measured on a real device). The unsigned IPA cannot carry
# entitlements, so this writes the plist the signer must add next to the IPA and warns; a free personal team cannot
# sign that entitlement.
RESERVE_DEC=$((16#$(gp mem_reserve | sed 's/^0[xX]//')))
BIG_VA=0; [ "$RESERVE_DEC" -gt $((0x180000000)) ] && BIG_VA=1
# A prepared Xcode project is signed in Xcode, so it asks for the Increased Memory Limit capability the bigger games need (see the README); DM_ENTITLEMENTS=another plist, or empty for none.
# The unsigned IPA has none: the install tool adds it.
if [ "$PREPARE_XCODE" = YES ] && [ -n "${DM_ENTITLEMENTS-default}" ]; then
  if [ -n "${DM_ENTITLEMENTS:-}" ]; then cp "$DM_ENTITLEMENTS" Gen/DmIOS.entitlements || die "copy DM_ENTITLEMENTS"
  else ENT_KEYS='<key>com.apple.developer.kernel.increased-memory-limit</key><true/>'
    [ "$BIG_VA" = 1 ] && ENT_KEYS="$ENT_KEYS<key>com.apple.developer.kernel.extended-virtual-addressing</key><true/>"
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
      "<plist version=\"1.0\"><dict>$ENT_KEYS</dict></plist>" > Gen/DmIOS.entitlements || die "entitlements"; fi
  echo "CODE_SIGN_ENTITLEMENTS = Gen/DmIOS.entitlements" >> Gen/dm.xcconfig
  t "entitlements: $(plutil -convert json -o - Gen/DmIOS.entitlements)"
fi
if [ "$BIG_VA" = 1 ]; then
  t "WARNING: this game reserves more than 6 GB of guest address space: on iOS the app must be signed with the extended-virtual-addressing entitlement, or it exits right after Play (FATAL reserve guest AS)"
fi
xcodegen generate -q > /dev/null || die "xcodegen"
python3 tools/gen_resources.py "$IOS" "$ROMFS" "$MARKER" "$MSL_IOS/$MSLDIR" "$MSLDIR" "$AOC" "$XCODE_DD" "$DM/gfx/nvn/dmsh_chain.h" || die "generate Xcode resource paths"
if [ "$PREPARE_XCODE" = YES ]; then
  t "Xcode project: $IOS/DmIOS.xcodeproj"
  t "Xcode derived data: $XCODE_DD"
  t "scheme: $DM_SCHEME_NAME"
  t "ready: select your Team in Signing & Capabilities, select a physical device, and Run (Release)"
  exit 0
fi

t "xcodebuild (Release, unsigned, iPhone + iPad)"
mkdir -p "$O"
xcodebuild -project DmIOS.xcodeproj -scheme DmIOS -configuration Release -destination 'generic/platform=iOS' -derivedDataPath "$DD" \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY= DM_COPY_GAME_RESOURCES=NO \
  DM_XCODE_OUTPUT_ROOT="$DD" SYMROOT="$DD/Build/Products" OBJROOT="$DD/Build/Intermediates.noindex" build > "$O/build.log" 2>&1 \
  || { grep -E 'error:' "$O/build.log" | head -20; die "xcodebuild, log $O/build.log"; }
# SYMROOT and OBJROOT above keep the unsigned build separate from the interactive Xcode app.
APP=$DD/Build/Products/Release-iphoneos/DmIOS.app
[ -n "$APP" ] && [ -d "$APP" ] || die "no built app"; t "app: $APP"

# Straight from the sources: the app without its signature, and without the folders an app built before pack_ipa.py still has (DerivedData keeps resources that left the project;
# msl/ is also deleted there, it took 1.5 GB of the home disk), then the shader libraries, the add-on content (the RomFS extracted from the player's DLC NSPs, one folder per index:
# the app sets DM_AOC_DIR at launch, the host reports them as owned and mounts them from it) and the RomFS
rm -rf "$APP/msl" "$O/Payload" "$O/out.ipa"   # (the last two: what the copy-and-zip packing left behind)
P=Payload/DmIOS.app; MAPS=("$P=$APP" "$P/msl/$MSLDIR=$MSL_IOS/$MSLDIR")
if [ "$DM_RESOURCE_BACKEND" = directory ] && [ -n "$AOC" ] && [ -d "$AOC" ]; then MAPS+=("$P/aoc=$AOC"); t "add-on content: $(ls "$AOC" | tr '\n' ' ')"; fi
if [ "$DM_RESOURCE_BACKEND" = directory ]; then MAPS+=("$P/romfs=$ROMFS"); fi
t "pack IPA (already-compressed game files stored, everything else deflated)"
# A scalar, not an array: bash 3.2 (macOS /bin/bash) treats "${array[@]}" of an empty
# array as an unbound variable under set -u, which is the default (directory) path.
PACK_POLICY=; [ "$DM_RESOURCE_BACKEND" = nsp ] && PACK_POLICY=--external-resources
# The other direction of the same assertion: directory mode must ship the RomFS, nsp mode must not. Keys are rejected in both (pack_ipa.py).
ROMFS_POLICY=; [ "$DM_RESOURCE_BACKEND" = directory ] && ROMFS_POLICY=--require-romfs
python3 tools/pack_ipa.py "$OUT_IPA" $PACK_POLICY $ROMFS_POLICY --store "$(gp zip_store)" --skip $P/_CodeSignature --skip $P/embedded.mobileprovision --skip $P/msl --skip $P/aoc --skip $P/romfs "${MAPS[@]}" || die "pack_ipa"
if [ "$BIG_VA" = 1 ]; then
  printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
    '<plist version="1.0"><dict><key>com.apple.developer.kernel.increased-memory-limit</key><true/><key>com.apple.developer.kernel.extended-virtual-addressing</key><true/></dict></plist>' > "$OUT_IPA.entitlements" || die "entitlements file"
  t "wrote $OUT_IPA.entitlements: hand it to the signing tool, or the app exits right after Play (free personal teams cannot sign it)"
fi
t "done: $OUT_IPA ($(du -h "$OUT_IPA" | cut -f1))"
