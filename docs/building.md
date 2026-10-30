# Building Touchline 27

Use `scripts/build-mac.sh` and `scripts/build-ios.sh` from this checkout. The commands
below describe the existing standalone pipeline; none were executed in the documentation
review. Read [platform status](support-status.md) and [release review](public-release-review.md)
for validation and distribution limits.

## Development environment

- An Apple silicon Mac running macOS 26 or later.
- Xcode, selected command-line tools, and the Metal toolchain. Xcode 27 is the recorded
  development setup; the lowest usable Xcode version has not been established here.
- .NET 10 SDK/runtime for `nx_extract` and the shader translator.
- Python **3.12 or later is recommended** for the build tools: inherited code uses modern
  f-string syntax unavailable in Apple's older system Python. This is a source-based
  requirement, not a new multi-version compatibility test.
- `xcodegen` for iOS, `spirv-cross` for shader translation, and `zstd` for supporting tooling.
- Python modules `capstone`, `fonttools`, `lz4` and `backports.zstd`.

Example environment setup, not run by this review:

```sh
brew install xcodegen spirv-cross zstd
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install capstone fonttools lz4 backports.zstd
xcodebuild -downloadComponent MetalToolchain
```

Install the .NET 10 SDK separately using your chosen supported distribution. `PYTHON`
selects the Python used by the wrapper; `--font-python` selects the interpreter for the
rewriter/font helpers. Using the same prepared environment for both avoids missing modules.

The scripts locate their code from their own checkout. Supplied relative paths are relative
to the caller's working directory. They can restore NuGet dependencies on first use and
write toolchain caches outside the checkout. Outputs default to `build/`; generated runtime
profile tables are also written beneath `dm/games/0100C49025D3E000/`.

## Private inputs

| Input | Purpose and limit |
|---|---|
| Base NSP/XCI | Uncompressed base for `0100C49025D3E000`; never included in source |
| Matching update NSP | Historical gameplay baseline `1.8c.fd45`, CNMT v327680; optional input does not imply the base build has equal validation |
| `prod.keys` | Supplied privately from your own console; put directly in `--nsp-dir` or pass `--keys` |
| Runtime NRO | Matching `Engine.Render.Core2.PlatformNvn.nro`, or an extracted RomFS from which to collect it |
| Shader pack | Your own runtime-captured `vs_dump.bin`, `ps_dump.bin`, `cs_dump.bin` inputs compatible with the current profile |
| ZBIC decoder | External library exposing `zbic_decompress`, named by `NX_ZBIC_LIBRARY`; not supplied here |

For runtime NRO input use `--nro /path/to/nro`; alternatively `--romfs /path/to/RomFS`
collects registered modules from that extracted tree. Do not omit the render module merely
because the wrapper can finish packaging without it. Reused `--patched` inputs must contain
the runtime module and `nro.tsv` as well as the expected main/SDK modules.

The profile currently has **494 shader-map entries**. This is coverage of captured development
scenes, not a complete title inventory. The tools do not extract this pack from Frostbite
`.toc`/`.cas` archives. Capturing one requires a separate prepared developer host/session;
there is no source-plus-container-only bootstrap promised here. The capture and translation
interfaces are documented in the [graphics reference](../dm/gfx/README.md) and
[research archive](research/README.md), not a separate end-user GUI workflow.

The decoder question is separate from FPSLocker. Project records describe certain external
ZBIC implementations as GPL-2.0; check the exact external implementation and how it is used.
This is not a license assignment to FPSLocker-Warehouse, nor proof that an external decoder
may be redistributed with this MIT project.

## Build macOS

Run at the checkout root after preparing the above inputs:

```sh
export NX_ZBIC_LIBRARY="/path/to/libzbic.dylib"
./scripts/build-mac.sh   --nsp-dir "/path/to/fc27"   --nro "/path/to/nro"   --shader-pack "/path/to/shader-pack"   --work "build/work-mac"
```

Default App: `build/Touchline27.app`. The host is generated under the selected work directory.
The App uses external NSP resources at runtime and asks for separate game/storage folders.

## Build iOS and iPadOS

```sh
export NX_ZBIC_LIBRARY="/path/to/libzbic.dylib"
./scripts/build-ios.sh   --nsp-dir "/path/to/fc27"   --nro "/path/to/nro"   --shader-pack "/path/to/shader-pack"   --work "build/work-ios"
```

Default IPA: `build/Touchline27.ipa`, unsigned and not installed. The project targets iPhone
and iPad; this does not establish either device's runtime compatibility. Sign with your own
setup, preserving Bundle ID `org.nxnative.0100c49025d3e000`. Back up Documents/save data
before replacing an installation.

### Resource modes for the IPA

`scripts/build-ios.sh` always produces the **external NSP** IPA: the App carries the rewritten
modules and shader libraries, while the game containers and `prod.keys` stay on the device
(`DM_RESOURCE_BACKEND=nsp`). It rejects bundled game data.

The **bundled-resource** IPA (game data inside the App) uses the lower-level script, because
the wrapper has no directory-mode option:

```sh
# once: build the extractor (scripts/build-ios.sh also does this) and extract the merged
# RomFS (about 32 GB for FC 27, base + update) outside the checkout
dotnet build dm/tools/nx_extract/nx_extract.csproj -c Release -o build/tools/nx_extract
export DOTNET_ROOT=/path/to/dotnet
./build/tools/nx_extract/nx_extract "/path/to/fc27/prod.keys" \
    "/path/to/fc27/base.nsp" "/path/to/fc27/update.nsp" "/path/to/work-embed/res"

GAME=0100C49025D3E000 W=/path/to/work-embed \
PATCHED="/path/to/patched" ROMFS="/path/to/work-embed/res/RomFS" \
MSL_IOS="/path/to/ios-library" DM_IOS_BUILD_DIR="/path/to/work-embed/proj" \
DM_RESOURCE_BACKEND=directory FONT_PY=/path/to/python-with-fonttools \
bash dm/ios/tools/build_ipa.sh "/path/to/Touchline27-Embedded.ipa"
```

The directory must contain the profile's RomFS marker and the control data next to it
(`nx_extract` writes both). The packer refuses a missing RomFS in this mode and refuses game
containers or console keys in NSP mode. Both modes are unsigned and keep the same bundle ID,
team placeholder and entitlements behaviour; a bundled IPA is several times larger.

## Reuse prepared inputs

Existing options, as defined in `scripts/touchline_build.py`:

| Option | Meaning |
|---|---|
| `--base`, `--update`, `--keys` | Explicit container/key selection instead of folder discovery |
| `--exefs` | Reuse extracted ExeFS; does not itself supply rewritten runtime NROs |
| `--patched` | Reuse rewritten modules and tables |
| `--shaders` | Reuse a complete, compatible platform-specific `b-<chain>` library or a parent containing it |
| `--nacp`, `--icon` | Supply private control metadata/icon where the chosen packaging path uses them |
| `--out`, `--work` | Override artifact/work paths |
| `--font-python` | Interpreter for rewriter/font helpers |
| `--language`, `--show-fps` | Launcher defaults for language/FPS display |

Example reusing your own compatible outputs:

```sh
./scripts/build-mac.sh   --patched "/path/to/patched"   --shaders "/path/to/macos-library"   --nacp "/path/to/control.nacp"   --work "build/work-mac"
```

For iOS use `build-ios.sh` and the iOS library. Reusing modules without `--nacp` still causes
the wrapper to seek control data through the extraction path; supply the needed containers
or metadata. Mac and iOS metallibs are not interchangeable. Library stamps must match the
profile and chain; do not bypass checks by renaming directories or editing hashes.

## Xcode signing

The lower-level `dm/ios/tools/build_ipa.sh --prepare-xcode` mode prepares an Xcode project
but is not a fresh-checkout one-line build. It needs `GAME=0100C49025D3E000`, writable `W`,
`PATCHED`, `ROMFS` (a resource directory whose parent contains prepared control data),
`MSL_IOS`, generated profile tables and the script's font/tool prerequisites. For external
containers set `DM_RESOURCE_BACKEND=nsp` and preserve the compatibility Bundle ID.

The top-level wrapper prepares related resources internally but does **not** accept a
`--prepare-xcode` option. Do not infer the lower-level defaults match the wrapper's layout;
read its checks and pass the prepared paths explicitly. Select a compatible team/signing
setup in Xcode after generation. This review did not prepare, build or sign that project.

## Distribution and troubleshooting

The wrappers exclude containers/keys/RomFS payloads from external-mode bundles, but embed
rewritten game code and derived shaders. iOS packaging can also use extracted icon/control
metadata. Default fonts copy or derive macOS-supplied fonts. These outputs need a separate
distribution review; a successful local build is not permission to publish an App/IPA.

For file recognition, ZBIC/NRO/shader prerequisites, version mismatches, signing and startup
errors, see [FAQ](faq.md). For historical runtime evidence see [platform status](support-status.md).
