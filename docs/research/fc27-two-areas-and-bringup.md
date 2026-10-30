# FC 27: two patch areas, both mains rewritten, host brought to nnMain

> Archive scope: superseded findings are retained in chronological order. Use the
> [research index](README.md) and [current platform status](../support-status.md) to
> distinguish historical experiments from current product instructions.

> Personal absolute paths have been replaced by `/path/to/...` placeholders for publication.

> Historical research record from the earlier fork. Paths, branch names, commit IDs, test
> results and device observations below describe that work at the stated time, not verification
> of this standalone checkout. Missing local evidence was not regenerated in the release audit.
> Use [building](../building.md) for current instructions and [release audit](../release-audit.md)
> for publication risks.

Date: 2026-10-28. Branch `research/fifa27`, based on `31004bb` ("Share NSO decoding and bound code gap scans"). Inputs are the audited decoded NSOs
`run-20261027/{base,update}-fixed-normalized.nso` (SHA-256 `708eb46d…` / `2445a558…`); scratch, outputs and logs are under
`/path/to/private-fc27-research/`. Something is a **fact** here only where a log or a checked artifact is named.

## 1. The rewriter places stubs in two patch areas (task 1)

`dm/tools/patch_nso.py` now emits through `island_layout.Area` objects instead of one global patch buffer. Every site is assigned an area by
`area_for(site)`; the site's `B` into its stub and the stub's `B` back are asserted by `nso_asm.B` exactly as before, so a site no area reaches stops
the rewrite with its own address instead of emitting a wrong branch.

`dm/tools/island_layout.py` gained `two_area()`: the area before the base at `[-pre_size, 0)` and the area after the image at `page_up(image_size)`
(the image includes bss, the key page and the frame-step state page, so the second area sits past all of them). A site below `split` goes to the first
area, everything above to the second, with `split = after_off - REACH + 2 MB` and the requirement `split + pre_size < REACH`. When the two windows do
not overlap the function raises before any output exists. `plan()` — the original conservative model — is untouched and still holds its tests.

The single-area paths are unchanged: for every module that does not need two areas the emitted bytes, gates, sites, cuts and obs files are
byte-identical (checked again for `sdk` and the render NRO against `stage2-sdk-final` / `stage2-nro-final`).

The output contract grew three header lines, only for the two-area case:

```text
# PATCH_LEN     bytes of the first area, which the file stores at FILE_IMAGE_LEN
# PATCH2_OFF    where the second area is mapped (past IMAGE_SIZE)
# PATCH2_LEN    bytes of the second area, which follow the first in the file
```

## 2. Both real mains are rewritten (task 3)

| | Base | Update |
|---|---|---|
| Build ID | `c2a256339b29922415331fab57de2565` | `9636bcd68e2ef2c863194d76f308c98c` |
| Text / image | `0xb9780f0` / `0xde90000` | `0xb99fbc0` / `0xdebc000` |
| First area | `-0x1000000..-0xc90000` (3,604,480 B) | `-0x1000000..-0xc8c000` (3,620,864 B) |
| Second area | `0xde90000..0xe1dc000` (3,457,024 B) | `0xdebc000..0xe208000` (3,457,024 B) |
| Sites / gates | 176,751 / 3,270 | 177,093 / 3,279 |
| Rewrite time | 10:34→10:48 (14 min) | 10:19→10:32 (13 min); peak sampled RSS 2.35 GiB |

`dm/tools/verify_islands.py` (new) checks each result against its input image without using any rewriter state:

* the file is exactly `FILE_IMAGE_LEN + PATCH_LEN + PATCH2_LEN` and the padding is zero;
* every one of the 176,751 / 177,093 changed 4-byte words is a `B` into one of the two areas — no other byte in text, ro or data differs;
* every instruction of both areas decodes (1,760,483 / 1,763,100 words), and every `B` / `BL` / `ADRP` / conditional branch resolves inside the image
  or inside an area (183,374 / 183,196 branches);
* every site in `sites.tsv` (including window entries and spin back-edges) is a branch into an area;
* every gate's return point lies in an area and starts with `ldp x29, x30, [sp], #16`.

Both runs: `main: OK` (`logs/verify-base.log`, `logs/verify-update.log`).

Base and update are independent builds of the same engine (different text, 342 more sites in the update, one more `br x18` jump table). **The update is
the baseline**: it is the version the container ships, its RomFS is the merged one the game reads, and its render NRO is the one already rewritten. The
base run is kept as the control; it reaches the same point in the SDK (section 4) but ships a different render NRO (SHA-256 `7d807709ac4d6ea6…`, 970,752 B)
that has not been rewritten, so it cannot go further without that step.

## 3. The loader maps two executable areas (task 2)

`dm/host/loader.c` reads the three new header lines and maps, for such a module, one reservation of `pre + image_size + PATCH2_LEN`:

* the image at `base`, the first area at `base + PATCH_OFF` (negative) and the second at `base + PATCH2_OFF`, each copied from its place in the file;
* `mprotect` makes text, both areas and the gap between the first area and the base read-only/execute or inaccessible, in the same order as before;
* the file length, the area lengths and the second area's position are validated against the header, and a mismatch stops the load instead of mapping
  something wrong. `module_of()` and the SVC memory report (`hle_svc.c`) know the second area, so crash reports and Horizon's `QueryMemory` layout stay
  correct. `dm/ios/tools/gen_embed.py` emits the fourth piece (`__TEXT,__dm<name>x2`) and `loader.c`'s iOS branch `vm_remap`s it into the same
  reservation, so the Mac and iOS contracts stay one.

The host boots with this layout: `main: gates 3279 patch_off 0xffffffffff000000`, `main: base 0x110000000 size 0xdebc000`, and `sdk` is mapped at
`0x11e208000` — exactly past the second area, so the two areas do not collide with the next module.

## 4. macOS host: what actually runs now

`make -C dm/host GAME=0100C49025D3E000` builds; the run used the NSP resource backend (base NSP + update NSP + keys, no RomFS extraction):
`DM_RESOURCE_BACKEND=nsp DM_RESOURCE_NSP=… DM_RESOURCE_UPDATE=… DM_RESOURCE_KEYS=… dmhost . main sdk`.

Reached, in order (`logs/run12-update.log`):

1. both modules mapped, **1,231,580 RELR + 12,228 ABS/GLOB + 770 JUMP_SLOT** relocations of `main` and 15,883 / 10,230 / 8,085 of `sdk` applied;
2. `nnosInitialize`, `nninitStartup`, a **1.19 GB heap**, `main`'s `DT_INIT` with 3,325 `init_array` entries, `sdk`'s 91;
3. `nnMain`, the alias region grown to +1.52 GB by the engine's own `MapPhysicalMemory` calls;
4. `fs mount rom` from the NSP (BKTR-merged), `eadpsdk_rom`, audio out opened, `ro::RegisterModuleInfo` with the render NRO's hash;
5. the render NRO loaded and relocated (3,120 RELR, 80 JUMP_SLOT), 14 imports bound to `main`;
6. **NVN on Metal**: `device API 55.15 (SDK 22)`, `Metal device Apple M1`, window origin and depth-mode negotiation.

Three host gaps were found and fixed on the way, each one a contract the SDK 22 build relies on:

* `dm/host/thread.c`: the SDK's `InternalCriticalSection` identifies the owner by `*(u32 *)(tpidrro_el0 + 0x110)` (sdk+0x14b4c0 / 0x14b630). The host left
  it zero, so every mutex looked owned by the caller and `main`'s first `StandardAllocator::Allocate` aborted in `pthread_mutex_lock`. The new
  `guest_thread_set_id()` writes the host's thread id there (SDK 8's module never reads the slot; checked on the Link's Awakening `sdk`).
* `dm/host/hle_fs.c`: the NSP backend compared every loaded module against the container's ExeFS, including NROs, which are never in it — the mount
  failed on `render`. NROs are now skipped (their identity is the NRR hash).
* `dm/gfx/hle_nvn.c`: `nvnTextureBuilderGetMemoryOffset` was missing.

**Fixed on the way to a running frame loop** (`logs/run13-update.log` … `logs/run19-update.log`):

* `nn::am::GetSelfController` has no initializer in this build (nothing in `sdk` writes its singleton and `main` imports no
  `nn::am`/`nn::applet` symbol), so the host hands out a stand-in object whose virtual methods report success — enough for
  `vi::CreateLayer` to finish. After that the game initialized its window (3 swap-chain textures, 1920×1080, interval 1), started the
  present thread, registered its controller styles and created its texture pools.
* `nvnTextureBuilderGetMemoryOffset` and `nvnTextureBuilderGetRawStorageClass` were missing from the NVN table.
* The memory partition had to grow: with a 256 MB alias region the engine's first `VirtualAlloc` failed with `0x1803`
  ("Couldn't reserve memory of size: 50331648 for PreAllocatedSb", `VirtualAlloc_Posix.cpp(284)`), and at 2 GB it failed again for
  512 MB while the alias region was 2.90 GB full. The profile is now `mem_reserve 0x300000000`, `mem_alias 0x180000000`,
  `mem_stack 0x10000000` (6 GB of guest address space, 6 GB alias region, the rest heap) — reservations only, physical pages are
  committed when the game touches them.

**The game runs** (`logs/run19-update.log`): 1,800 frames and more, frame time p50 **33.48 ms (30 fps)**, NVN submit+present p50
0.43 ms, GPU p50 1.55 ms, 34 worker threads (`Job0`–`Job2` at 88 ms/s of CPU), render passes with 92 MB of attachment loads and
165 MB of stores per frame, and a graceful SIGTERM exit.

**Shaders, from the running game (2026-10-28, second phase).** The 54 shaders the boot path asked for were taken from the program
itself, not from the archives: with `DM_NVN_SHDUMP=<dir>` the host writes each missing shader's control section, code area and stage
(`.ctl` / `.code` / `.stg`, the game's own bytes). `dm/gfx/tools/shdump_pack.py` (new) checks every dumped key against the host's
own hash (`sha256(control[:0x880] + code)[:8]`), rejects a mismatch, writes `shader_split.py`-style packages (`vs_dump.bin`,
`ps_dump.bin`, `cs_dump.bin`) and the map rows; `dmsh_build.py` then translated all of them (55 of 55, then 75 of 75 after another
dump while walking the menus) and compiled their Metal libraries. Nothing is fabricated: every row points at bytes the game handed
to `nvnProgramSetShaders`.

The map's stage column cannot come from the NVN array index: a program of one compute shader passes it at index 0, which reads as
vertex. The stage is taken from the code area's own header (`0x12345679` = compute, instructions at +0x100; `0x12345678` = graphics
with the 0x50-byte SPH at +0x30, stage in word 0 bits 10..13), which classified the first dump as 27 compute + 11 vertex + 17 pixel.

**The game shows its own screens.** `DM_WINDOW=1` opens the real window (`front_mac.m` creates none without it, so earlier runs had
"no window, fixed 60 Hz" and nothing to look at). Captured from the presented frames (`DM_CTL` `shot`, `logs/`):

* `Accessibility Settings` (the game's first screen, `logs/fc27-win-a.png`),
* the title screen `EA SPORTS FC 27 · THE WORLD'S GAME · Let's Play!` (`logs/shot-2.png`),
* the main menu with FC NEWS / ULTIMATE TEAM / MANAGER CAREER / PLAYER CAREER / KICK OFF / LEARN TO PLAY / SEASONS / TOURNAMENTS /
  CO-OP SEASONS and "Welcome to the Club!" (`logs/shot-8.png`, `logs/menu-a.png`),
* the offline prompt and the EA sign-in notice the offline path produces (`logs/off-b.png`, `logs/off-c.png`),
* the KICK OFF / LEARN TO PLAY menu with the Training Centre panel (`logs/ko-b.png`).

At the menu the run reports **0 shaders missing from the map**, 195 draws and 18,835 translated instructions per draw, frame time
p50 33.35 ms, GPU 8 ms (`logs/run28-menu.log`).

## 5. Reproduce

```text
# rewrite (each ~13 min, 2.4 GiB)
python3 dm/tools/patch_nso.py <normalized>.nso <out dir> main
python3 dm/tools/verify_islands.py <normalized>.nso <out dir> main

# shaders: dump what the game asks for, pack it, translate and compile it
DM_NVN_SHDUMP=<dump dir> ... dmhost <out dir> main sdk          # writes <key>.ctl/.code/.stg per missing shader
python3 dm/gfx/tools/shdump_pack.py <dump dir> <pack dir> --map dm/games/<id>/shader_map.tsv
DM_GAME=<id> DOTNET_ROOT=<dotnet> python3 dm/gfx/tools/dmsh_build.py <pack dir> <DM_ROOT>/build/cache/metal_shader_cache

# host, with the game's window
make -C dm/host GAME=0100C49025D3E000
DM_WINDOW=1 DM_ROOT=<dir with build/cache/metal_shader_cache> \
DM_RESOURCE_BACKEND=nsp DM_RESOURCE_NSP=<base>.nsp DM_RESOURCE_UPDATE=<update>.nsp \
DM_RESOURCE_KEYS=<prod.keys> dm/host/dmhost <out dir with main/sdk/render + nro.tsv> main sdk
# DM_CTL=<file> drives it from a shell: a line "A" presses A, "shot <path>.png" saves the next presented frame
```

## 6. What is not claimed, and what is still missing

The game's own screens render (title, menus, the offline path). **Still missing:**

* The menu's backdrop is black. The UI draws (195 draws a frame) but the hub's background never appears; nothing in the log says a shader is
  missing, so it is a draw that produces nothing rather than a skipped one. `logs/tc-c.png` shows the game's "Press Any Button" attract screen,
  also on black, and the Training Centre does not get past it inside 60 s.
* Four `[RED]` lines remain at the menu: `texture→texture copy case not implemented: 1920x1080x1→1920x1080x1 flags 0 format 260→252`,
  `sampler ID 4096 not registered`, `compute shader lacks threadgroup size reflection`, and the missing `pso_manifest.tsv` prewarm list. The
  empty `shader_facts.tsv` is why compute shaders get default thread group sizes: `shader_split.py` writes those answers from the archives,
  which are still not parsed.
* The shader map has the 75 shaders this boot and menu path asked for; a match or the Training Centre will ask for more, and each new key
  needs the dump → `shdump_pack.py` → `dmsh_build.py` round. `DM_NVN_SHDUMP` and `DM_CTL` make that a scripted loop.
* The map's `source` column points at the runtime dump, not at a file inside the game's archives. Packaging a derived profile
  (`scripts/build_ipa_from_nsp.py`) still runs `shader_split.py`, which cannot read Frostbite's `.toc`/`.cas`; this profile is not a packaged
  artifact, and its `shader_facts.tsv` is empty (translation queries use defaults, listed per build).
* Nothing on iOS was built. The memory partition is a working hypothesis measured against the engine's reservation failures. The base build's
  own render NRO is not rewritten. The `am` stand-in is a stub.
