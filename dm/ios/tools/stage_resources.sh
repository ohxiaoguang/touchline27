#!/bin/bash
# Xcode target phase: copy the active game's resources into the app before CodeSign.
# Paths come from build_ipa.sh, not from a per-game rule or a phone-visible Mac path.
set -eu
[ "${DM_COPY_GAME_RESOURCES:-YES}" != NO ] || exit 0
die() { echo "[RED] $*" >&2; exit 1; }
[ "${PLATFORM_NAME:-}" = iphoneos ] || die 'This game needs a physical iPhone or iPad; choose a device, not a simulator.'
[ -f "${SRCROOT:?}/Gen/resources.env" ] || die 'Missing game resource paths; run build_ipa_from_nsp.py --prepare-xcode first.'
source "$SRCROOT/Gen/resources.env"
APP="${TARGET_BUILD_DIR:?}/${UNLOCALIZED_RESOURCES_FOLDER_PATH:?}"
case "$APP" in /*.app) ;; *) die "Unexpected app resource destination: $APP";; esac
# Validate every source before copying or removing anything (the external drive may be disconnected).
if [ "${DM_RESOURCE_BACKEND:-directory}" != nsp ]; then
    [ -e "$DM_RESOURCE_ROMFS/$DM_RESOURCE_MARKER" ] || die "Game files unavailable: $DM_RESOURCE_ROMFS/$DM_RESOURCE_MARKER"
    [ -z "$DM_RESOURCE_AOC" ] || [ -d "$DM_RESOURCE_AOC" ] || die "Add-on content unavailable: $DM_RESOURCE_AOC"
fi
[ -d "$DM_RESOURCE_SHADERS" ] || die "Shader libraries unavailable: $DM_RESOURCE_SHADERS"
# The host is compiled from the repository's current sources and loads only msl/b-<its chain version>: after a chain change (a pull, dmsh_chain.py --header) the prepared shaders are another chain's
case "$DM_RESOURCE_MSLDIR" in b-*)
    [ -f "$DM_RESOURCE_CHAIN_H" ] || die "No chain version header: $DM_RESOURCE_CHAIN_H (a project prepared before the chain version moved to dm/gfx/nvn: prepare the game again, build_ipa_from_nsp.py --prepare-xcode)"
    V=$(sed -n 's/^#define DMSH_CHAIN "\(.*\)"/\1/p' "$DM_RESOURCE_CHAIN_H")
    [ "$DM_RESOURCE_MSLDIR" = "b-$V" ] || die "The prepared shaders are chain $DM_RESOURCE_MSLDIR, the sources are now at b-$V: prepare the game again (build_ipa_from_nsp.py --prepare-xcode)";;
esac
# External NSP mode deliberately never stages game containers or extracted RomFS.
# Refuse stale bundled resources instead of deleting an existing build's data.
if [ "${DM_RESOURCE_BACKEND:-directory}" = nsp ]; then
    [ ! -e "$APP/romfs" ] && [ ! -e "$APP/aoc" ] || die 'Stale bundled game resources: choose a fresh DerivedData directory for external NSP mode.'
    [ -d "$DM_RESOURCE_SHADERS" ] || die "Shader libraries unavailable: $DM_RESOURCE_SHADERS"
    mkdir -p "$APP/msl/$DM_RESOURCE_MSLDIR"
    /usr/bin/rsync -a -- "$DM_RESOURCE_SHADERS/" "$APP/msl/$DM_RESOURCE_MSLDIR/"
    exit 0
fi
echo 'Copy game resources (the first build copies the complete game; later builds sync changes)'
mkdir -p "$APP/romfs" "$APP/msl/$DM_RESOURCE_MSLDIR"
/usr/bin/rsync -a --delete -- "$DM_RESOURCE_ROMFS/" "$APP/romfs/"
/usr/bin/rsync -a --delete -- "$DM_RESOURCE_SHADERS/" "$APP/msl/$DM_RESOURCE_MSLDIR/"
for old in "$APP/msl/"*; do
    [ "$old" = "$APP/msl/$DM_RESOURCE_MSLDIR" ] || rm -rf "$old"
done
if [ -n "$DM_RESOURCE_AOC" ]; then
    mkdir -p "$APP/aoc"
    /usr/bin/rsync -a --delete -- "$DM_RESOURCE_AOC/" "$APP/aoc/"
else
    rm -rf "$APP/aoc"
fi
