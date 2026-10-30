# Touchline 27 architecture

```text
dm/                 the runtime and the tools that prepare a game for it
  host/             the host: loader, kernel/services (hle_*.c), NVN-over-Metal glue
  gfx/              the graphics layer: nvn/ (NVN → Metal), tex/, hle_nvn.c, Shader tools
  apple/            launcher code shared by macOS and iOS
  ios/              the iOS target: SwiftUI launcher, Xcode project template, packagers
  macos/            the macOS launcher and its resource checks
  games/            the game profile (dm/games/0100C49025D3E000/) and its reader
  resource/         the read-only NSP/XCI reader (nxrom), used by the host and the tools
  tools/            the NSO rewriter, NRO collector, SDK patches, small helpers
  third_party/      vendored third-party code, each with its license
scripts/            build-mac.sh, build-ios.sh, and the packagers they drive
tools/nxrom/        Python side of the preparation pipeline (prepare, compile, package)
docs/               this documentation and the FC 27 research record
```

## Runtime flow

1. `dm/host/loader.c` maps the prepared modules (`main`, `sdk`, and the NRO modules the game
   registers at run time) from the tables beside them, applies the rewriter's fixups and resolves
   the imports between them.
2. The guest starts at `nnMain`. Every `svc` and every `mrs`/`msr` of a Horizon system register
   goes through a gate the rewriter installed, into `dm/host/hle_*.c`, which implements the
   kernel and the services on top of macOS/iOS primitives.
3. The game's graphics calls land in `dm/gfx/hle_nvn.c` and `dm/gfx/nvn/nvn_mtl.m`, which
   translate NVN into Metal, using the Shader library built ahead of time.
4. The standalone wrappers select `nsp`: game data is read in place from the user's containers (`dm/resource/nxrom.c`, the
   `nsp` resource backend). The inherited `directory` backend also exists but is not the documented wrapper workflow.
   Mac and iOS share the
   same discovery code in `dm/apple/ResourceDiscovery.swift`.

## The game profile

The profile stores FC 27 identity and configuration as data: `dm/games/0100C49025D3E000/game.tsv` holds the
identity, the registered builds and their main build IDs, the module list, the RomFS marker, the
graphics API, the default frame rate and the guest memory partition. `game.py` turns it into
`game_profile.h`, which the host, the GPU layer and the iOS sources compile against.

The Shader tables (`shader_map.tsv`, `pso_manifest.tsv`, `shader_facts.tsv`, `shader_pairs.tsv`)
live beside it. Two more tables the host reads at run time, `c1_full.tsv` and `cb_extent.tsv`, are
build products of the Shader library and are not committed.

FC 27 also has code-specific adaptations in `dm/host/fpslock_fc27.h` and
`dm/tools/sdk_patches.py`. Only the FC 27 profile is registered. `make -C dm/host` and `dm/games/game.py` use it by default; the FC 27 frame-rate adapter is gated by full main Build ID. Inherited backend and
other build-gated helpers are retained infrastructure, not a supported game catalog.

## Guest memory

FC 27 runs on a 5.03 GiB guest block (`mem_reserve 0x142000000`): 16 MiB of prefix, a 3.75 GiB
alias region, 64 MiB of stacks and a 1.203125 GiB (1,232 MiB) heap region, with the SDK 22.2.0 node area cut to
62 MiB by `dm/tools/sdk_patches.py`. That is measured, not guessed: `docs/research/fc27-bringup.md`
section 20 records the Frostbite reservations behind it, and 3.375 GiB is fatal at boot. The profile is below the packaging script's threshold for requesting extended virtual
addressing. This does not prove installation or physical-memory suitability for any particular
iPhone/iPad; see [platform status](support-status.md).

## Ownership and implementation boundaries

The host, HLE services, rewriting tools and graphics infrastructure derive from
[seedds/nxnative](https://github.com/seedds/nxnative) and its contributors under MIT.
FC 27 adaptation in the research fork includes large-module rewriting work, runtime
compatibility work, the measured memory profile and the FC 27 FPS data adapter. This
is not a claim that every shader-chain or packaging change was authored in this project.

The shader translator references vendored Ryujinx/Spv source and locked local assemblies.
[Upstream comparison](upstream-provenance.md) records exact matches and differences.
The frame-rate adapter uses local C execution logic with external address/parameter
research; see [FPS provenance](fpslocker-provenance.md). Other components retain their
[third-party notices](../THIRD_PARTY_NOTICES.md).

The configured memory partition is not a device compatibility guarantee; synthesized
unit fixtures, historical Mac runs and a prior iPhone report have different evidence scope.
Use [development](development.md) and [platform evidence](support-status.md) for validation.
