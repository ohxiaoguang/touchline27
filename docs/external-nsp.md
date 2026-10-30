# External container reader: implementation archive

> Historical implementation and validation reference inherited from the engine work.
> Generic packagers and old preparation examples below are not the supported Touchline 27
> build workflow. Use [building](building.md), [user guide](user-guide.md) and
> [platform evidence](support-status.md). Historical cross-title fixtures are not FC 27 tests.
> No tests or runtime workflows were rerun for the documentation review.

This is an incremental runtime implementation, not a claim that all nxnative games
have been validated with external containers. The inherited lower-level directory mode was preserved; Touchline 27 wrappers select external NSP mode.
No commits, remote changes, device installation, or real-game extraction were
performed during this implementation.

## Architecture and ownership

`dm/resource/nxrom.c` and `nxrom.h` are a standalone MIT C library, shared by macOS
and iOS. The implementation uses Apple SDK CommonCrypto; it contains no Mush8
source, translated GPL code, downloaded library, or runtime .NET dependency.
Mush8 was an architectural reference only. The pre-existing MIT LibHac 0.19 assembly
is an optional test oracle, not linked into the app.

The read graph is:

```text
HLE nn::fs -> normalized guest path -> immutable RomFS file/child index
          -> IVFC verified logical storage
          -> optional BKTR indirect mapping (base or update)
          -> CTR / CTREx subsection decryption
          -> NCA range -> PFS0 member range -> external NSP descriptor + pread
```

Storage nodes use atomic reference counts. Each read specifies an absolute offset;
there is no shared seek cursor. Mounts are immutable and process-lifetime in HLE,
matching existing mount/unmount semantics. Independent library users must quiesce
readers before close. Source files must remain immutable for the mount lifetime.
Open descriptors keep a selected file identity across renames; truncation and I/O
failures are errors. Changed ciphertext/data outside cached blocks fails integrity
checks. This is not a hot-reload facility.

IVFC keeps one verified block per level, with a mutex per cache. ExeFS hierarchical
SHA-256 has the same scheme. Each supported block is at most 1 MiB, so a mount's
verified data caches are at most 8 MiB (six RomFS levels plus two ExeFS levels).
No disk cache or extracted file is created. The parsed index is separate: directory
and file tables total at most 128 MiB, copied full-path text at most 128 MiB, at most
one million entries, and bounded traversal depth 128. Temporary parse/visited
buffers add to opening peak memory; these bounds are safety ceilings, not measured
normal-game usage. Directory children are linked at index construction, avoiding a
whole-index scan for each directory enumeration.

`nxrom_directory()` implements the same independent metadata/read/enumeration API
for tools and parity tests. It snapshots an immutable ordinary directory and rejects
links/special files; it does not implement APFS guest-name xattrs. HLE deliberately
retains its existing directory resolver (case aliases, overlays and save semantics)
instead of replacing it with this narrower test/tool backend.

`hle_fs.c` dispatches only explicitly selected NSP RomFS mounts to this library.
File opens reserve a host fd as a handle ID; size, read, close and mode use the
associated virtual entry. Writes/set-size/path mutations are refused. Directory
handles retain their own cursor and support filtering and position-independent
counts. The original read destination preparation and logging remain in place.
Before publishing a mount, all loaded modules' NSO build IDs must match the selected
ExeFS. An old prepared module without a build ID is rejected in NSP mode.
Saves, temp, audio, rendering and program rewriting are unchanged.

The earlier uncommitted `nxdata.*`, `tools/nxdata/*` and archive HLE experiment were
preserved, not deleted/reset. They are frozen legacy drafts, not the new resource
format or a supported workflow. Their build inclusion and zlib linkage remain to
avoid silently destroying prior work. `gen_build.py` now carries system `-l` flags
into iOS as well as frameworks, fixing linkage of that retained draft.

## Supported subset and explicit limitations

Implemented and tested with synthetic containers:

- PFS0 NSP members, bounded indexes, duplicate/overlap/path checks, no extraction.
- NCA3 encrypted headers; common ticket title keys or derived key-area keys supplied
  by the user; plaintext and AES-CTR data sections.
- Standard six-level NCA IVFC SHA-256, including padded final blocks, FS-header
  hashes, and two-level ExeFS hierarchical SHA-256 with unpadded final blocks.
- Basic retail BKTR single-root bucket tables, strictly ordered relocation maps and
  CTREx subsections; reads split at both map and crypto boundaries. The region the
  subsection table describes may end anywhere up to the start of that table itself:
  a historical reference fixture declares it there, past the relative table, and gives the subsection
  covering both tables the natural counter. Anything further is refused.
- Base Program identity and update identity relationship (same Program ID or base
  plus 0x800), unambiguous Program selection, and loaded-module NSO build matching.
- File size/type, empty directories/files, case-sensitive UTF-8 paths, arbitrary
  offsets, EOF, concurrent reads and immediate-child enumeration.

Explicitly unsupported/rejected: NSZ/NCZ/XCZ, NCA2, XTS data sections, personalized
or unsupported tickets, missing derived keys/tickets, sparse/compressed NCA layers,
alternate hash layouts/block sizes, deeper BKTR trees, ambiguous multi-program NSPs,
and update data sections that are not the supported BKTR form. `DM_ROMFS_OVERLAY`
(RomFS mods) **is** supported on container mounts; see "Mod overlay" below. The
frozen `DM_RESOURCE_ARCHIVE` sandbox still refuses it.
Gamecard images are now read through the same mount: `nxrom_open()` detects the
card header ("HEAD" at 0x100) by content, verifies the root HFS0 header against the
SHA-256 at 0x140, locates the unique "secure" partition, verifies its leading bytes
against the root entry hash (up to 1 MiB) and mounts the secure partition's NCA
members with the same bounded-table/name/range/overlap checks as PFS0. Root-declared
partition sizes stay advisory (a trimmed dump's secure partition can claim bytes
past the file's end); member ranges are bounds-checked against the bytes that exist.
The on-card firmware-update, normal and logo partitions are not game content and are
never read. A gamecard Program NCA with a rights ID is refused: that title key
exists only in the per-console encrypted InitialData region. An XCI base combines
with an NSP update through the same identity checks (same Program ID or base+0x800)
and the same BKTR mapping as an NSP base.
DLC NSP mounting/registration is not implemented; existing directory DLC remains
available through the established configuration. The native reader does not verify
RSA authenticity signatures or CNMT required-application-version relationships.
Identity/build checks must not be described as complete CNMT validation. A corrupt
but coherently re-authored unsigned hash tree is not an authenticity proof.

Filename extensions are only an early rejection; PFS0/NCA/section contents are
validated independently. Opening validates the index and accessed hash paths, not
all payload blocks. Full inspection with `--verify` reads every file.

### Where a second container format plugs in

The reader is separated from everything that consumes it, and the gamecard (XCI)
format has plugged in through exactly these seams:

- `dm/resource/nxrom.c` owns container parsing and `nxrom_open()` is its only entry
  point. The HLE layer never sees a file name or an extension: it asks for a path
  inside a mounted container and gets bytes.
- `tools/nxrom/resourcefs.py` presents one `ResourceFS` interface over either a
  directory or a container. Preparation, Shader scanning and the profile census are
  written against that interface, not against NSP.
- `nsp` stays the backend id for every external container - it is the name the
  runtime, the `Info.plist` key, the `--resource-backend` value and
  `DM_RESOURCE_BACKEND` already use. A new format extends what that mode accepts;
  it does not add a third mode.
- Formats are named in lists, not in branches: the early rejections in
  `nxrom_open()`, and `FORBIDDEN_SUFFIXES` in `scripts/build_mac_app.py` (what must
  never be bundled). A new container adds an entry.

XCI met both requirements: the container opener sits inside `nxrom_open()` with the
same no-temporary-files contract, and game identity, NSO build matching and key-area
decryption all run through the unchanged NCA path. An NSZ/NCZ backend still needs
its own block translation and is not implemented.

## Configuration and use

Default: unset `DM_RESOURCE_BACKEND`, or set it to `directory`. Existing `DM_ROMFS`,
`DM_ROMFS_OVERLAY`, `DM_SAVE`, `DM_TEMP` and shader paths behave as before.

NSP mode (the backend id stays `nsp` for every external container):

```text
DM_RESOURCE_BACKEND=nsp
DM_RESOURCE_NSP=/external/game/base.nsp        # or a gamecard image: base.xci
DM_RESOURCE_UPDATE=/external/game/update.nsp   # optional; unset or empty for base only
DM_RESOURCE_KEYS=/external/game/prod.keys
```

No game or profile is implicit. Use the host built for the matching profile and
program build. Existing shader libraries/tables must also match that preparation.
For example, after separately preparing matching program/shader outputs:

```sh
DM_RESOURCE_BACKEND=nsp \
DM_RESOURCE_NSP=/external/game/base.nsp \
DM_RESOURCE_UPDATE=/external/game/update.nsp \
DM_RESOURCE_KEYS=/external/game/prod.keys \
DM_MSL_DIR=/external/game/shaders \
DM_SAVE=/external/game/save DM_TEMP=/external/game/temp \
DM_WINDOW=1 dm/host/dmhost /external/game/patched
```

`DM_RESOURCE_PICK=1` opts into macOS native selection for missing base/key paths.
The update can be supplied through the same environment. The picker is run before
preload, and resources are checked before guest execution. The prepared code and
shader configuration are still required; this does not make any NSP executable
without the nxnative preparation stage.

The new user-facing script streams inspection/verification without a RomFS tree:

```sh
python3 scripts/inspect_external_nsp.py --base /external/game/base.nsp \
  --keys /external/game/prod.keys --title 01006BB00C6F0000
python3 scripts/inspect_external_nsp.py --base /external/game/base.nsp \
  --update /external/game/update.nsp --keys /external/game/prod.keys --verify
python3 scripts/inspect_external_nsp.py --base /external/game/base.nsp \
  --keys /external/game/prod.keys --read path/in/romfs --offset 4090 --length 100
```

The script builds a small inspector beside the NSP under `<title-or-stem>-work/nxrom`
(or `--work`); it never writes resource copies. `--read` writes binary bytes to stdout.
The settings at the top also support Spyder F5. The existing main build script
requires a modern Python (validated here with the already available Python 3.12);
Apple's Python 3.9 cannot parse its pre-existing modern f-string syntax.

## Mod overlay on an external container

`DM_ROMFS_OVERLAY` works on a container mount exactly as it does on a directory mount:
one RomFS path is served from the mod instead of the game's own file. It is the same
configuration, the same precedence and the same read semantics; only the layer it plugs
into differs. A container's files have no host path, so the overlay resolves a guest path
itself instead of rewriting a directory path.

```sh
DM_ROMFS_OVERLAY=mods/romfs          # relative: see root resolution below
DM_ROMFS_OVERLAY=/abs/a:/abs/b       # ':' separated, first root that has the path wins
```

Root resolution happens once, at mount. An absolute root is used as given; a relative one
is tried against the process directory first (on iOS the App `chdir`s into `Documents`,
on macOS the launcher sets the run directory as the working directory) and then against
`DM_ROOT`, the per-game runtime directory both launchers pass. The resolved absolute
paths are logged, so the answer to "which directory is `mods/romfs`?" is always in the log
rather than implied by the current directory. A root that is missing or not a readable
directory is reported and skipped; the mount itself still succeeds, because the game must
start and read its own resources when a mod folder is absent or partly imported.

Precedence is mod → update → base: the mod shadows the merged base + update view, and a
path the mod does not have keeps coming from the container (including from the update
package). Multiple roots keep the directory backend's rule (the first root with the path
wins), so a mod set that already worked in directory mode behaves the same here.

| Request | Behaviour |
| --- | --- |
| `rom:/a/b` where the mod has `a/b` | the mod's file is opened as an ordinary host file and read with `pread` |
| `rom:/a/b` where the mod has no `a/b` | unchanged container read (IVFC, BKTR, CTR/CTREx, PFS0/XCI range) |
| a path only the mod has (new file or new directory) | readable and enumerable like any other RomFS entry |
| a directory both sides have | enumerated as the merge: the mod's children first, a same-named container child skipped |
| a mod file where the container has a directory | the directory becomes unobtainable: the mod wins |
| size / type queries | answered from the mod (its own size, not the container's) |
| writes, creates, deletes, renames | refused: the mount stays read-only |

No copy, no extraction and no per-file buffering is introduced: a hit is one host file
descriptor (the existing read path does the `pread`), a miss is the existing container
read, and a large mod file is read at the requested offsets only. Saves, temp, cache and
DLC mounts are untouched — the overlay only ever applies to the `rom` mount.

Safety follows the guest path rules already used for containers: the path after `mount:` is
normalized lexically, so `.` and repeated separators are harmless and `..` above the mount
root is an error. Inside the mod, each component is matched case-exactly (as the RomFS does
on a case-insensitive APFS volume) and the resolved file must still be inside its root, so
a symlink that points out of the mod directory is neither read nor listed. A mod file that
exists but cannot be opened (deleted between lookup and open, permissions, a broken link)
is reported and the read falls back to the game's own resource: a broken mod cannot make
the original resource unreadable.

Logging is deliberately quiet and only needs to answer "did the overlay work?":
one line at mount (off / on with the resolved roots / no usable root), one line at the
first hit (`guest path → mod path`), any failure with `[RED]`, and a hit/failure summary
at exit. Per-open lines stay behind the existing `DM_FS` switch.

Nothing about Shader handling changes: a mod that replaces an ordinary RomFS file reuses
the existing Shader libraries, the same chain, the same cache identity and the same
integrity checks, and enabling the overlay never triggers a Shader rebuild. A mod that
replaces Shader resources (`shader/*.bfsha` or similar) is a different problem — it changes
the inputs the Shader chain was built from and is not something the overlay can silently
absorb.

Measured behaviour, the mods used and the comparison runs are recorded in
the mod-overlay notes of the project the reader came from.

## iOS and packaging

`--resource-backend nsp` in `scripts/build_ipa_from_nsp.py`, or
`DM_RESOURCE_BACKEND=nsp` with `build_ipa.sh`, produces an external-resource app:

- `DMResourceBackend` in Info.plist selects the mode without embedding host paths.
- The launcher imports base NSP, optional update NSP and console keys into
  `Documents/resources/{base.nsp,update.nsp,prod.keys}` on a background queue.
- Each row shows missing/required or optional status, an import indicator, then
  the imported filename and size with a checkmark. Existing imports are checked
  when the launcher opens. Play is disabled during import/checking, when required
  inputs are missing, or when container/key validation fails. Exact prepared-module
  build compatibility is still checked by the runtime mount at launch.
- A security-scoped URL is held only while copying. A new temporary file is copied
  first; atomic replacement preserves the prior imported file on copy failure.
- Resources are excluded from device backups. When a complete set exists, invalid imports are rejected before replacing the old
  resource. The launcher validates before Play;
  the HLE subsequently checks the exact prepared module build IDs.
- Device `Documents/env.txt` can override resource paths. An empty
  `DM_RESOURCE_UPDATE=` selects base-only even if an old update file exists.
- RomFS mods are imported the same way as in directory mode: a `mods/romfs` tree placed in
  the App's `Documents` (Files app) and `DM_ROMFS_OVERLAY=mods/romfs` in `Documents/env.txt`.
  Swapping the mod needs no rebuild of the IPA and no game copy; the tree is read in place
  and only the paths it contains shadow the container. Removing the folder (or the setting)
  restores the game's own resources on the next launch.
- Direct open-in-place/bookmark access to third-party/cloud providers is not yet
  implemented. Importing can require one full NSP copy on the device.
- Do not set `DM_LAUNCHER=0` if import UI is needed. Manual Documents import remains
  available. Restart after correcting a launch that already attempted guest mount.

Both IPA mappings and interactive Xcode resource staging omit RomFS and directory
DLC in this mode. Xcode refuses a stale App containing those resources rather than
deleting user data; choose fresh DerivedData. Shader libraries/fonts/small tables
and prepared program code remain bundled. `pack_ipa.py --external-resources` audits
entries before writing and refuses containers, key files and resource trees.
Bundle diagnostic env files must not contain resource/key source paths. Console
key values are never logged or generated into the App; the user must supply them
on each target platform. Directory mode remains the default build mode.

IMPORTANT: the current main preparation pipeline STILL extracts RomFS for Shader
and engine-specific scanners. The new packaging option does not remove that step.
A full unsigned Link's Awakening 1.1.0 validation IPA has now been built and audited
using the isolated validation profile and matching Shader chain. Device execution
is still unverified; see `external-nsp-validation.md` for the artifact and results.

## macOS development App packaging

`scripts/build_mac_app.py --host <dmhost> --patched <prepared modules>
--shaders <b-chain directory> --profile <profile> --font <font directory>
--settings <launcher.json> --output <new path.app> --title-id <base ID>
--name <display name> --version <prepared version>` packages an
already-built NVN host. It checks the host/profile/library chain and refuses an
existing output. It does not build games or support Vulkan/OpenGL packages yet.
Only prepared modules/tables, compiled libraries/JSON metadata and fonts enter the
App; `.metal` sources, compiler caches, game containers, keys and RomFS do not.
The App is a local development artifact, without distribution signing/notarization.

The native SwiftUI launcher has separate base, update and key selectors, file
status/size indicators, a validation-gated Play button and the same game settings
schema/model/controls as iOS (`dm/apple/LauncherSettings.swift`). Its settings JSON
is generated by `dm/games/settings.py`, exactly as for IPA preparation. Containers
are opened in place rather than imported. User-selected security-scoped bookmarks
restore resource paths and the storage directory; inaccessible/stale resources
require selection again. Only bookmark metadata/preferences are saved, never keys.

The storage directory is selected independently in the launcher. Saves/logs/temp
go into its `nxnative-<title ID>` child. This grants access before creating runtime
files; the old shell entry silently exited when macOS denied automatic creation of
a sibling directory. Play also checks all prepared module build IDs through the
native resource core before starting the game. Resource/settings changes are
disabled while the game is running. Sound is explicitly enabled (`DM_AUDIO=1`);
macOS headless test defaults remain silent. Existing source directories, games,
keys and saves are not copied or deleted by resource selection.

## Reproducible verification

All synthetic fixtures use deliberately generated dummy keys and are not game
content. They live under ignored `dm/resource/tests/build/` on the repository drive.
Unit tests use only dummy keys. Subsequent real validation used the user-selected
`/path/to/container-test-inputs` inputs read-only; no key values were copied into
source, documentation, logs or an App.

```sh
# Optional: use the already installed MIT LibHac assembly; network sources cleared.
make -C dm/resource/tests oracle \
  LIBHAC_DLL=/path/to/existing/libhac/0.19.0/lib/net7.0/LibHac.dll
make -C dm/resource/tests GAME=010015100B514000 run platform
make -C dm/host/tests GAME=010015100B514000 \
  build/t_fs build/t_fs_case build/t_fs_commit_list
# Run the last three binaries with TMPDIR on the repository/external test drive.
make -C dm/host GAME=010015100B514000 dmhost
```

Recorded results for this implementation:

- Nine native-reader test groups passed, including base/update byte comparison,
  randomized/concurrent/cross-boundary reads, UTF-8/case/EOF, corruption, and ExeFS
  identity. The existing LibHac assembly independently verified the synthetic base
  and patched view and matched file sizes and complete SHA-256s.
- 24 malformed-container cases ran under AddressSanitizer + UndefinedBehaviorSanitizer
  with no findings. These are deterministic cases, not a comprehensive fuzz audit.
- Native HLE tests passed for base and update, including wrong-build refusal,
  normalized paths, read-only protection, precise EOF, directory filtering/count
  and cursor lifetime. The HLE harness also runs with both sanitizers.
- Existing directory/save tests: 55 filesystem, 51 case, 36 commit-list checks passed.
- Two packaging tests passed: synthetic IPA entry policy, and external Xcode staging
  without a RomFS source, with non-destructive stale-resource refusal.
- macOS host built successfully (existing graphics warnings remain).
- Native core and host resource wrapper cross-compiled for arm64 iOS 26. iOS
  main.m syntax and Launcher.swift type checks passed with the installed Apple SDK.
  SwiftUI's macro checker needed execution outside the restricted nested sandbox.
- Changed shell/Python tools passed syntax checks (main script: Python 3.12).

Real read-only validation additionally passed for the user-selected Link's Awakening
base and update 1.1.0: both complete views matched LibHac across 3,836 files and
4,005 entries (base 6,232,003,695 file bytes; updated 6,232,003,903). 137 offset reads
across 21 selected updated-view files matched the existing extracted directory.
This exposed and fixed a real BKTR boundary: subsection coverage ends at patch data,
not necessarily the subsection table offset; the regression fixture now covers it.

The actual game entered nnMain using the NSP mount, with DM_ROMFS unset and a new
isolated DM_ROOT containing no RomFS tree. A 20-second headless run recorded 1,189
reads; a separate directory run recorded 1,205. All 1,115 shared unique
(path, offset, returned length) requests had identical content hashes. Both were
stopped gracefully at the test deadline with isolated, newly created saves.

Later validation regenerated matching Mac/iOS libraries in an isolated profile
(chain `55287b700f3a`); the repository profile and old libraries were preserved.
Mac play reached the village, acquired the shield, saved and reloaded in independent
NSP/directory runs. The paired reload runs agreed on 1,695 shared unique reads.
Full iOS linking and unsigned packaging passed; archive CRC, resource exclusions,
ARM64/iOS platform, signature absence and matching Shader inventory were checked.
Synthetic storage-loss tests also verify zero returned bytes on failure and that
committed saves remain intact and writable. See the companion validation record
for exact evidence, warning counts, artifact paths and the earlier Shader mismatch.

Gamecard (XCI) read-only validation, on the user-selected inputs Rhythm Heaven
two historical non-FC 27 reference fixtures (3.8 GB and 15 GB cards): both containers
mounted from the original files, and a full `--verify` pass matched the LibHac
oracle exactly — Rhythm 7,902 entries / 7,237 files / 3.17 GB, FIFA 71 entries /
62 files / 13.49 GB, every path, size and SHA-256 identical. 496 random and
block-boundary reads cross-checked between the Python stream and inspector paths.
A wrong-title update NSP, an NSZ update and an `.xcz` name were each refused.
No real XCI + matching NSP update pair existed to test; that combination is
covered by synthetic fixtures only. See `xci-external-reader-report.md`.

Still unverified: physical iOS execution/import, representative performance/power,
later game content, other games, provider bookmarks and actual device-disconnect
recovery. The Mac run recorded recoverable display-link stalls; these are unresolved.
Shader translation source/tables were not changed.

## Disk and maintenance

Native inspection and gameplay create no extracted files. Test fixtures, tool
binaries, caches and logs under `dm/resource/tests/build/` are reproducible. Host
`gen/`, the test binaries and `dmhost` are normal rebuildable outputs. Their actual
sizes for this run are recorded in `external-nsp-validation.md`; they are not
estimates of real-game size savings. Existing game extraction trees, keys, saves,
old `.data` drafts and user build results were not cleaned up.

Future upstream sync: inspect/fetch, verify local main and upstream relationship,
fast-forward main only where safe, then merge main into this feature branch after
review. Do not overwrite custom commits, rewrite history or auto-resolve file-system
conflicts. Expected conflict sites are `hle_fs.c`, startup/launcher files, host test
link rules and resource build scripts. New `dm/resource/` code is independent;
no per-game fixed module addresses or shader-chain changes were introduced.

### Seekable build-tool input

`tools/nxrom/resourcefs.py` now exposes the same C core to Python tools without
an extracted tree. Build its small macOS shared library explicitly into a chosen
work directory before importing assets; opening a mount does not run a compiler.
The wrapper implements metadata, immediate directory enumeration, recursive file
listing and read-only binary streams supporting `seek`, `tell` and `readinto`.
Directory and base/update NSP mounts share the same interface:

```python
from tools.nxrom.resourcefs import ResourceFS, build_library

library = build_library(work / 'nxrom.dylib')
with ResourceFS(library, base=base_nsp, update=update_nsp,
                keys=keys_path, title=title_id) as resources:
    for entry in resources.files():
        if entry.path.endswith('.pak'):
            with resources.open(entry.path) as stream:
                header = stream.read(16)
                stream.seek(-64, 2)
                footer = stream.read(64)
```

Use `ResourceFS(library, directory=romfs_directory)` for the compatibility backend.
Paths remain case-sensitive, relative and subject to the native path validation;
embedded NULs are rejected before crossing the C interface. No keys enter the
library binary. Independent streams have their own cursor locks; native reads
may proceed concurrently. Mount close waits for active calls. Close streams
before their mount; buffered streams can otherwise retain already-read bytes.
Native transfers are limited to 1 MiB per call and buffered streams default to
64 KiB. As with ordinary Python files, unbounded `read()` collects an entire file;
large archive consumers must read bounded ranges. No `fileno`, mmap or write
interface is provided. Existing consumers requiring real paths cannot use this
adapter unchanged. Container mutation while mounted remains unsupported.

The first production consumer is `dm/games/profile_guess.py::romfs_files`:
`facts_of(existing_exefs, resources)` now reads each file's first 32 bytes directly
from the mount, with unbuffered streams to avoid 64 KiB read-ahead. Directory and
manifest arguments retain their existing behavior. The public inspector exposes
this census and the existing profile inference rules:

```sh
python scripts/inspect_external_nsp.py --base /game/base.nsp \
  --update /game/update.nsp --keys /game/prod.keys --title 01006BB00C6F0000 \
  --survey-exefs /game/prepared/ExeFS --work /game/work/nxrom
```

The command prints JSON with resource statistics, module metadata and suggested
profile values. It checks each supplied NSO build ID against the selected logical
ExeFS and fails before emitting a report on mismatch. `--survey-exefs` cannot be
combined with verify/read/range options. It needs already available matching
ExeFS modules; it does not extract program code, generate a profile or run a game.
Spyder F5 can set `SURVEY_EXEFS` in the settings block. Shared libraries use a
source fingerprint in their names so repeated F5 runs do not overwrite an older
library still mapped by that Python process. No key values appear in the report.

This remains an incremental path: the main `build_ipa_from_nsp.py` survey still
uses nx_extract's manifest, and `shader_split.py`, Unity and Unreal readers still
use their existing paths. Migrate those consumers individually, compare their
outputs, and follow the Shader chain procedure whenever the translation chain
changes. This census integration changes no Shader tables or translation output.

### Opt-in Shader stream scanning

`tools/nxrom/shader_scan.py` is the first Shader-resource consumer. It searches
explicitly selected raw files in 1 MiB blocks, including signatures spanning block
boundaries, then seeks to each BNSH candidate and reads only that declared container
for the unchanged `shader_split.bnsh_shaders` decoder. Containers are capped at
64 MiB before allocation. Original offsets and source labels are preserved even
though the decoder sees a rebased slice. No mmap, extraction tree or shared file
cursor is required. Records are available as `(source, stage, control, code)` to
future preparation consumers.

It now also traverses little-endian SARC indexes. A member is a seekable bounded
view of its original stream, preserving nested member names without copying member
bodies to disk. Index/name/member ranges, duplicate/unsafe names and partial
overlaps are rejected; exact shared ranges with distinct names are permitted.
Nested SARC and Yaz0 preserve the original decoder's source labels. Yaz0 checks
back-references and caps compressed and expanded members at 64 MiB, with a 128 MiB
cumulative expansion budget per selected resource and at most eight nested layers.
Big-endian SARC and zstd/Unity/other engine containers remain unsupported here.

```sh
DM_GAME=01006BB00C6F0000 python -m tools.nxrom.shader_scan \
  --library /game/work/nxrom.dylib --base /game/base.nsp \
  --update /game/update.nsp --keys /game/prod.keys --title 01006BB00C6F0000 \
  --suffix .bfsha --suffix .ptcl --suffix .arc \
  --main /game/prepared/ExeFS/main --output /game/work/bnsh-scan.json
```

Run from the repository root. The shared library is explicitly prepared with
`build_library` as above; this command does not compile it implicitly. Use
`--directory /game/RomFS` instead of NSP options for the same stream path over
existing files. Repeated `--path` selects exact relative files instead of suffixes.
Report paths must be new: an existing report is never overwritten.

Optional `--main` scans an existing raw main NSO through the production image and
Shader parsers. Segment/file/image bounds are checked before decompression, with a
256 MiB file/image limit. In NSP mode its build ID must match the selected logical
ExeFS. Directory mode cannot prove container identity and records
`build_checked: false`. Program rewriting still needs this separate NSO; this
option does not extract code or eliminate that preprocessing requirement.

The manifest stores distinct payload variants, their first source, counts, pair
sets and an ordered SHA-256 over every raw record (including all duplicate source
labels). It writes no Shader code/control payloads. The output explicitly says
`complete_game_shader_scan: false`: only the selected BNSH/SARC/Yaz0 and optional
program sources are covered. Recognized zstd, Unity and several engine containers
are refused, rather than quietly treated as raw files. Other shader formats remain outside this scanner's
scope even when a selected file yields no BNSH. The size limit bounds individual
container reads, not total RSS or the number of returned Shader records.

The unchanged production decoder and runtime tables remain in place. This opt-in
scanner has not been wired into `build_ipa_from_nsp.py` and does not publish new
Shader tables or translated libraries. No existing Shader chain input changed.
Before replacing a production scan, validate all sources required by its profile,
compare final packages/tables and follow the repository's Shader chain procedure.

The current Link's Awakening selection covers every key in its existing Profile;
that is a measured key-inventory result, not proof of complete Shader discovery
for other games or byte-identical final package/table generation. The normal
pipeline still supplies global deduplication, source precedence and single-stage
pair coverage when writing its tables.

Next phases: final package/table output comparison and preparation integration,
broader engine stream adapters and BKTR/CNMT/DLC support. Wire validated readers into preparation
so it can stop materializing the complete RomFS. Keep directory compatibility until
each engine path is validated.
NSZ needs a separate block-NCZ backend or explicit conversion policy; solid NCZ
cannot be promised cheap arbitrary access. Do not silently decompress it to disk.

### Isolated final-package verification

`python -m tools.nxrom.shader_package` now exports a single-version selection
through the stream reader into an exclusively created directory. It preserves the
production ordering rules: main precedes resources, repeated main keys take the
last source, repeated resource keys take the first source, files sort by path,
and final keys sort by group/source/key. Payload conflicts are rejected using the
existing compatibility check. All variation pairs and single-stage coverage are
retained, compute facts are generated, and manual facts are merged. Record indices
are record counts within each package, rather than byte offsets.

Its arguments match the scanner (`--library`, NSP or directory, selection and
`--main`), plus required `--reference-package` and a new `--output` directory.
Before writing, selected keys must exactly cover the loaded Profile. After writing,
all package hashes and all bytes of the three tables must match the supplied
reference packages and current Profile. A mismatch returns failure and retains
only the isolated diagnostic output. It never replaces packages, tables or caches.
The real tested call selected `.bfsha`, `.ptcl` and `.arc` with the matching main.

This is an independent experimental serializer, deliberately outside the existing
production chain. Tests execute the production writer's trusted AST as an
independent format oracle; production export does not rewrite or monkeypatch that
writer. Upstream changes to the writer can therefore be detected by those tests.
Before enabling it in normal preparation, consolidate or maintain that format
compatibility explicitly. Multiple input versions, run-time GLSLC capture,
Unreal/Unity/other engine adapters and automatic source selection are not enabled.
The normal NSP build script still follows its directory-based preparation path.

### Public preparation-only entry point

The existing public script now offers an explicit preparation-only path:

```sh
python scripts/build_ipa_from_nsp.py /game -k /game/prod.keys \
  --resource-backend nsp --package v131072 \
  --prepare-nsp-resources stream-prepared
```

The new relative output folder is under the NSP folder; absolute paths are accepted
only inside that folder. Existing output is refused. Spyder F5 can set
`NSP_PREPARE_OUTPUT`. The default extractor is the already built
`<title ID>_build/tools/nx_extract/nx_extract`; `--nsp-extractor` can select another
existing build. It does not install/build that dependency. When a sidecar DLL is
present, the installed dotnet muxer runs it using the script's configured PATH,
avoiding apphost runtime-root discovery problems on Homebrew installations.

This mode requires a registered Profile with exactly one matching Shader version
and matching program build IDs. It rejects DLC inputs, uncompressed-NSP format
violations, provisional/survey/Xcode/IPA-output/damaged-input modes, and requests
to delete extracted inputs. The normal default workflow remains unchanged.

The path uses `nx_extract --manifest` to write only ExeFS, control/icon metadata
and a header manifest. It mounts the original containers, compares every native
header with LibHac's manifest, checks all supplied module IDs, checks renderer and
capture requirements, and scans **all files** through the stream reader. No suffix
selection or per-game path list is used. Unsupported engine archive requirements,
readers or incomplete/mismatching Profile tables stop the preparation without
falling back to full extraction. Vulkan/OpenGL, runtime capture and multiple input
versions are not supported in this path yet.

`tools/nxrom/prepare.py` writes the package and three tables in the fresh output
directory, then publishes `ready.json` only after successful validation. Failure
retains diagnostic output without a ready report. This mode stops before program
rewriting, Shader translation, compilation, game launch or IPA generation. Do not
interpret the ready report as a complete runnable app. The default IPA path still
uses the established extraction workflow. The explicit consumer below uses the
verified inputs without creating RomFS.

### Building an unsigned IPA from prepared NSP inputs

The public script supports an explicit second stage, `--use-nsp-prepared`, for
registered single-version NVN profiles supported by stream preparation. It
requires a schema-2 preparation (older reports must be regenerated into a new
directory), an existing certified iOS Shader context, a new work directory and a
new IPA destination inside that work directory. There is no fallback to full
extraction or Shader compilation. Directory-mode builds retain their old path.

For the current validation artifacts, the command is:

```sh
GAME_ROOT=/path/to/container-test-inputs
CONTEXT="$GAME_ROOT/01006BB00C6F0000-work/shader-current-validation"
DM_GAMES_FIRST=1 DM_GAMES_DIR="$CONTEXT/profiles" \
  "$GAME_ROOT/01006BB00C6F0000_build/tools/venv/bin/python3" \
  scripts/build_ipa_from_nsp.py "$GAME_ROOT" -k "$GAME_ROOT/prod.keys" \
  --resource-backend nsp --package v131072 \
  --use-nsp-prepared "$CONTEXT/nsp-preparation-03" \
  --ios-shader-context "$CONTEXT" \
  --nsp-build-work "$CONTEXT/nsp-build-next" \
  --out "$CONTEXT/nsp-build-next/Links Awakening External NSP.ipa"
```

Run from the repository and choose a **new** work directory for each attempt.
`DM_GAMES_DIR` selects the copied profile whose header matches the already
certified cache; it does not replace the repository profile or tool lock. A context
contains `shader-summary.json`, `ios/b-<chain>/` and a
`toolchain/gfx/tools/dmsh_chain.py` verifier with the source tree and tool lock used
for that cache. This is explicit reuse of a previously compiled context, not a
general Shader compiler entry point.

`tools/nxrom/prepared_build.py` checks the complete program/package inventories
and SHA-256 hashes, profile game/map/facts/pairs hashes, selected title/version,
the current source/tool-lock chain, exact reflection coverage, iOS compile records,
library counts and Metal library headers. It rechecks selected container module
IDs through the current native reader, then runs the existing rewriter and iOS
builder. Cache files are hashed before packaging; every packed reflection/library
must match those bytes. These checks do not prove arbitrary cached binaries have
correct rendering semantics; a device run remains required.

`DM_IOS_BUILD_DIR` gives the shell builder a fresh external staging directory for
the generated project, `Gen/`, source links and assets. The consumer sets it
automatically. Existing `dm/ios/Gen`, game work directories, cache files and
existing IPAs are preserved. The metadata parent supplies NACP/icon data; its
nonexistent `RomFS` path is only a compatibility argument to the old builder and
is never created or copied.

Success writes `build-report.json` and `shader-cache-inventory.json` in the new
work directory. The report includes the preparation and IPA hashes, selected
chain, resource/Shader audit, and `device_run_verified: false`. The final audit
checks ZIP CRCs, the external-resource Info.plist setting, executable presence,
exact cached Shader bytes and absence of RomFS/AOC, containers, keys, provisioning
profiles or signature directories. No signing or installation runs.

Limitations remain explicit: no DLC, provisional/derived profile, damaged-input
mode, diagnostic environment bundle, multi-version Shader union, Vulkan/OpenGL
capture, automatic new cache compilation, NSZ or NCZ. Missing/incompatible caches
stop before rewriting. The generic core is shared, but this complete preparation
and consumer sequence has been exercised on only the registered Link's Awakening
1.1.0 inputs so far. The macOS consumer below shares the input and cache checks.

### Building a Mac App from the same prepared inputs

`scripts/build_mac_app.py --use-nsp-prepared` now accepts the same schema-2
preparation used for an unsigned IPA. It does not use the old extracted RomFS or
rewritten program directory. An explicit profile selects the matching registered
version; its subprocesses use that profile too. A certified **macOS** cache is
required. The shared validator rejects an iOS cache in its place and recomputes
the context's source/tool-lock chain before any rewrite.

```sh
GAME_ROOT=/path/to/container-test-inputs
CONTEXT="$GAME_ROOT/01006BB00C6F0000-work/shader-current-validation"
"$GAME_ROOT/01006BB00C6F0000_build/tools/venv/bin/python3" \
  scripts/build_mac_app.py \
  --use-nsp-prepared "$CONTEXT/nsp-preparation-03" \
  --shader-context "$CONTEXT" \
  --nsp-dir "$GAME_ROOT" --keys "$GAME_ROOT/prod.keys" --package v131072 \
  --profile "$CONTEXT/profiles/01006BB00C6F0000" \
  --work "$CONTEXT/mac-prepared-build-next" \
  --output "$CONTEXT/mac-prepared-build-next/Links Awakening External NSP.app"
```

Choose a new work directory for each attempt. Host/module/Shader/font/settings
arguments belong to the existing asset-only packer mode and cannot be mixed with
this prepared-input mode. The latter extracts nothing: it validates preparation
hashes, checks the selected NSP module IDs with the current reader, runs the
existing rewriter, compiles a new Mac host, generates fonts and shared launcher
settings, then invokes the existing packer with explicit runtime inputs. Host
generation uses the host Makefile's expanded compile command with an isolated
output; the original `dm/host/dmhost` is not replaced. Its ordinary generated
profile headers/libvpx dependency cache are still reused by make.

The resulting App has the same external-file selection/settings launcher. NSPs
and keys remain where the user selected them; save/log/temp state is created in
the launcher's selected workspace. Font bytes, rewritten code, runtime tables
and compiled Shaders are bundled. `_b_build.json` is a compiler summary and is
excluded, along with Metal sources and other compiler scratch files.

`tools/nxrom/mac_build.py` audits the entire bundle for links/private game files,
checks executable/title/backend metadata, matches every program/table byte to the
new rewrite and selected profile, and matches every Shader/reflection byte to the
validated cache. `build-report.json` and `shader-cache-inventory.json` record the
result. A build report deliberately leaves runtime/launcher-interaction flags
false; bounded host runs are recorded separately. No extraction, Shader
translation, signing, notarization, commit or push is part of this mode.

`dm/resource/tests/smoke_real.py` accepts `--patched` and `--fonts` so a registered
Link's Awakening smoke run can use **the new bundle's actual runtime files**
instead of its old extraction/build directory. It still uses a fresh isolated
test save. This real-game harness is title-specific; the new preparation/cache/
packaging interfaces contain no Link's Awakening resource paths or special cases.

### Compiling a new Shader context from preparation

`scripts/compile_nsp_shaders.py` supplies the prepared package directly to the
existing translator and Metal build tools. It does not reopen NSPs, extract
RomFS, require an old library directory, rebuild the translator, or install tools.
Use the existing Python 3.12 environment with the public build script's packages:

```sh
GAME_ROOT=/path/to/container-test-inputs
CONTEXT="$GAME_ROOT/01006BB00C6F0000-work/shader-current-validation"
"$GAME_ROOT/01006BB00C6F0000_build/tools/venv/bin/python3" \
  scripts/compile_nsp_shaders.py --nsp-dir "$GAME_ROOT" \
  --prepared "$CONTEXT/nsp-preparation-03" \
  --profile "$CONTEXT/profiles/01006BB00C6F0000" --package v131072 \
  --output "$CONTEXT/shader-from-prepared-next" --jobs 8
```

The Settings block supports Spyder F5; command-line values override it. Progress
defaults to stage/count lines (`--progress off`, `bar` or `json` are available).

The output must be a new folder under the game drive, separate from preparation
and profile inputs. It contains an independent copy of the current Shader Python
sources, translator binaries and compile conventions, plus a copied profile.
The installed tool fingerprints and chain header are regenerated **only in that
snapshot**. Translator embedded-source verification remains enforced. Homebrew's
runtime location is obtained with `dotnet --list-runtimes`; no runtime is fetched.

The first build starts with an empty local CAS and clears inherited library
prefill settings. Both macOS and iOS are built. The existing compiler's complete
per-key result list, RED/error diagnostics, key coverage, target compile records,
Metal library headers and output hashes are checked. The copied profile's
`c1_full.tsv` and `cb_extent.tsv` are regenerated from the new results. No original
profile/lock/header/cache is overwritten and no RomFS is created.

`shader-summary.json` is published last and enables both prepared-input consumers
to use this new context. `compile-report.json`, `source-inventory.json`, target
inventories and `logs/` record inputs and outcomes. Failure leaves diagnostic work
without that successful-context marker. Normally choose a fresh output to retry.
If compilation completed but final validation was interrupted or failed, the same
command with `--finalize-existing` checks completed results, regenerates only the
copied runtime tables and publishes only after full validation. It never invokes
the translator/Metal compiler or replaces an already published context. Missing
MSL, failed keys, mismatched inputs/sources or escaping output links are rejected.
Recovery reports do not infer missing start-history facts: their cold/prefill/CAS
flags are null, while per-key cache counts are taken from the compiler log.
This is a
cold build and may take substantially longer than the earlier cache-reuse builds.
The OS/compiler can retain its own internal caches; no previous nxnative CAS or
library outputs are used by this entry point.

After compilation, pass the new context root and its `profiles/<title ID>` to the
Mac consumer, or `--ios-shader-context` with `DM_GAMES_DIR=<context>/profiles` to
the IPA consumer. Rebuild hosts with those copied runtime tables, then run the
resulting game. A successful Shader build is not a gameplay compatibility test.
Both consumers also compare the chain's listed translation sources against the
current checkout: a frozen snapshot cannot hide later source changes. Its measured
tool lock can differ from the repository lock, but remains part of the recomputed
context version and must match the compiled outputs. No header is edited to make
an incompatible cache pass.
The original default build path, engine-specific extraction/capture limitations
and single-registered-version requirements are unchanged.

## Unified external NSP build entry point

`scripts/build_external_nsp.py` orchestrates the existing stages in one command.
It uses the Python environment that already runs the extraction/Shader tools
(Python 3.12 or newer), existing `nx_extract`, the installed translator and Apple
build tools. It never installs dependencies or falls back to full extraction.
The Settings block also supports Spyder F5; CLI flags override Settings.

For a fresh preparation and cold Shader build followed by both packages:

```sh
PYTHON=/path/to/game-folder/tools/venv/bin/python3
GAME_ROOT=/path/to/game-folder
"$PYTHON" scripts/build_external_nsp.py \
  --nsp-dir "$GAME_ROOT" --keys "$GAME_ROOT/prod.keys" \
  --profile "$PWD/dm/games/01006BB00C6F0000" --package v131072 \
  --nsp-extractor "$GAME_ROOT/01006BB00C6F0000_build/tools/nx_extract/nx_extract" \
  --work "$GAME_ROOT/01006BB00C6F0000-work/external-build-01" \
  --target both --app-name 'Links Awakening External NSP'
```

Use the actual game's registered Profile/version; there is no default game.
The example title is not hardcoded in the orchestrator. `--target macos` or
`--target ios` limits packaging; the existing cold Shader stage still compiles
both targets. `--jobs` controls Shader workers (1–32). `--progress` selects
`lines`, `bar`, `json` or `off`. The workflow is opt-in; the original directory
build entry point remains available.

The work directory must be new, on the game's drive under its NSP directory.
Default stage outputs are `prepared/`, `shaders/`, `macos/<name>.app` and
`ios/<name>.ipa`. Only explicit runtime inputs are bundled. Program rewrites,
Shader libraries and fonts are retained; RomFS, containers and keys stay outside
App/IPA. iOS output is unsigned. No device installation or gameplay test is
automatically performed.

For an incremental rebuild, add `--prepared /existing/preparation` and/or
`--shader-context /existing/context`, still choosing a new `--work`. These are
explicit reuse requests, not unchecked skip flags: input inventories, registered
version, immutable Profile tables, current translation sources, measured chain,
platform and library coverage are revalidated. Packaging uses the context's
copied Profile/runtime tables, even when the repository's original chain header
has a different tools measurement. Existing caches are never modified to make
them pass. Omitting either reuse flag runs that stage normally; for example,
`--shader-context` alone performs a fresh preparation and reuses only compilation.

Each invocation writes `pipeline-report.json`, with stage status/duration,
preparation/Shader-summary hashes, output paths and hashes of package audit
reports. A failure marks the workflow failed, stops subsequent stages and leaves
all outputs/logs intact. It does not overwrite a partially completed work folder.
To recover, select a new work directory and explicitly reuse only stages with
valid publication markers. An unpublished completed Shader compilation can first
be recovered with the separate `compile_nsp_shaders.py --finalize-existing`
procedure above; the unified entry never guesses that compilation completed.
If an earlier target completed before a later failure, its separate audited
artifact remains recorded and preserved. Commands/key contents are not stored
in the workflow report.

Only the currently supported registered single-version NVN subset is accepted;
engine adapters/runtime Shader capture and DLC NSPs remain unsupported. A folder
with only NSZ/NCZ inputs is rejected. When supported NSPs coexist with original
compressed copies, only NSPs are selected and the ignored compressed file names
are displayed and recorded. No NSZ decompression or deletion occurs. Container
module identities are checked by preparation/consumers, not trusted solely from
filename tags. Full CNMT/content-version association remains future work.

### Historical cross-container validation scope

Earlier generic-reader work also exercised a separate non-FC 27 fixture. Its source-specific
validation record is not distributed here and cannot establish FC 27 behavior. The technical
scanner behavior retained from that work is Zstandard/BAHS support with caller-selected
scratch staging and bounded decoded transfers/expansion. Runtime still reads uncompressed
containers; this is not a claim of runtime NSZ support or another supported product.

The existing `smoke_real.py` runner requires explicit title/package identity and private
inputs. See [development](development.md) for validation categories. No real-input runner
was executed in this review.
