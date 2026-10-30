# Third-party notices

Touchline 27 retains code from nxnative and third-party projects. The root [MIT license](LICENSE)
does not replace a dependency's grant or authorize game-derived material. Original license
texts, source headers and patent/notice files remain authoritative and unchanged.

## Engine origin

The host/HLE, rewriter, graphics infrastructure and substantial packaging/tooling derive
from [seedds/nxnative](https://github.com/seedds/nxnative) and its contributors under MIT.
The root license retains seedds's copyright and the Touchline 27 contributors' notice.
The independent repository history does not erase upstream authorship.

FC 27 bring-up and compatibility work were developed in a research fork before migration.
Attributing that work to this project does not mean the entire shader chain, host or packaging
system was independently authored here. [Source/binary comparisons](docs/upstream-provenance.md)
record the checked upstream revision and the limits of the evidence.

## Vendored source and adaptations

| Component | Origin / retained version record | Terms and material | Use |
|---|---|---|---|
| libvpx | VP9 decoder subset; recorded v1.17.0, `6df3ec3` | [BSD 3-Clause](dm/third_party/libvpx/LICENSE), [PATENTS](dm/third_party/libvpx/PATENTS), [AUTHORS](dm/third_party/libvpx/AUTHORS) | Host movie decoding |
| stb_vorbis | Recorded 1.22, `1ee679c`, **with a retained multichannel residue fix** | [MIT or public domain](dm/third_party/stb_vorbis/LICENSE), source-end notices and [change description](dm/third_party/stb_vorbis/README.md) | Host movie audio |
| Ryujinx / Spv.Generator | Source subset recorded as Ryujinx 1.3.2 with inherited changes; identified by Git tree `eb03ac43…`; bit-reproducible build recipe not recorded | [Ryujinx MIT](dm/third_party/ryujinx/LICENSE.txt), [Spv license](dm/third_party/ryujinx/src/Spv.Generator/LICENSE) and Khronos notice in `spirv.cs` | Offline shader translator |
| MacNativeGames | Adapted widening, in-pass clear and visibility-counter lowering code; source links retained in comments | [MIT](dm/third_party/macnativegames/LICENSE) | `nvn_mtl.m` and translator adaptations |
| deko3d | Layout-size algorithm adapted into `nvn_tex.c`; original import revision unrecorded | [Original zlib notice](dm/third_party/deko3d/LICENSE), [source record](dm/third_party/deko3d/README.md) | Texture storage layout |
| Vulkan-Headers | 15 headers matched to v1.4.363 in the prior audit | `Apache-2.0 OR MIT` in headers; this distribution selects [MIT](dm/third_party/vulkan-headers/LICENSES/MIT.txt) | Retained backend infrastructure; FC 27 uses NVN |
| NVIDIA FLIP | Optional image-metric source; version not recorded | [BSD 3-Clause](dm/third_party/flip/LICENSE); bundled stb_image, stb_image_write and tinyexr keep their in-file notices | Developer tooling, not the game build |
| NVN interface declarations | `nvn.h`, Copyright 2020 h1k421 | Full MIT notice in [the source header](dm/gfx/nvn/include/nvn.h) | Host API declarations |

Version labels above are retained source records, not newly reproduced imports. Third-party
modification history is in the corresponding directory README; use the actual files when
assessing a particular change.

## Precompiled translator dependencies

The [dependency directory](dm/third_party/dmsh_xlate_dependencies/README.md) supplies original
license texts, package metadata, notices and a [per-file hash/source manifest](dm/third_party/dmsh_xlate_dependencies/binary-provenance.json).

- Gommon 2.8.1.2, Humanizer.Core/locale packages 3.0.10, Microsoft.IO.RecyclableMemoryStream
  3.0.1 and System.CodeDom 4.4.0 use their supplied MIT materials; Humanizer and CodeDom
  have additional retained third-party attributions/notices.
- MsgPack.Cli 1.0.1 remains **Apache-2.0**, with the original license text and package copyright
  (FUJIWARA, Yusuke). It is not relicensed under the root MIT grant.
- The native .NET 10.0.13 apphost has its full package LICENSE and THIRD-PARTY-NOTICES;
  the prior audit documented a normalized SDK-template match, not an exact NuGet binary match.
- The prior package audit matched 56 external DLLs byte-for-byte. The three local Ryujinx/Spv
  assemblies are traceable to the original development project's rebuild commit
  `674c2e14…`; the same batches are in the official source line's retained projects and
  carry the MIT/Khronos notices. Their bit-for-bit build recipe was not recorded, and
  they are not described as copies of the current upstream DLLs.
  [Exact comparison and evidence](docs/upstream-provenance.md). No DLL was changed.

## FPS configuration research

FC 27 frame-rate control uses Touchline 27's host-side C execution logic, including Build ID,
pointer/memory checks, parameter writes and presentation-time adjustment. Addresses, parameters
and adjustment research reference FPSLocker-Warehouse's public FC 27 configuration on the
`v4` branch. The project includes neither FPSLocker's runtime nor the original YAML configuration
or Warehouse ARM64 assembly patch. Reading SaltyNX behavior for reference is not a claim that
its runtime was imported.

The data are not described as wholly independent research. No verified explicit reuse license
was found for the referenced configuration; it is **not described as GPLv2 or automatically
licensed under MIT**. Attribution is not permission. A targeted comparison found that the
local C code shares the referenced addresses, numbers and behaviour but does not reproduce
the upstream YAML structure, variable names or MASTER_WRITE instruction block; see
[FPS provenance](docs/fpslocker-provenance.md). No author was contacted.

## Additional source-origin review

The inherited [nvn_builtin.h](dm/gfx/nvn/nvn_builtin.h) holds four hand-written MSL
equivalents of Maxwell counter kernels. The file is present byte-for-byte in
[seedds/nxnative](https://github.com/seedds/nxnative) from commit `d1b1708`
(2026-10-12), unchanged in the research fork and in Touchline 27: it is upstream
inherited code under the upstream MIT grant, written for a different supported title,
not FC 27-specific work. The operations are single load/subtract/store steps with a
bounds check. See [the provenance note](docs/upstream-provenance.md#built-in-msl-helper-kernels-four-functions-in-nvn_builtinh).

## External tools and restored dependencies

Xcode/Apple SDK tools (`xcrun`, clang, swiftc, Metal tools, `sips`, `plutil`), `make`, `xcodegen`,
`spirv-cross`, `zstd`, Python packages and .NET are used as external tools. `nx_extract` restores
LibHac 0.19.0 through NuGet; it is separate from the engine's MIT adapter code. The repository
does not vendor the complete installed SDK/runtime or every package restored during a local
build. A future distribution of those tools/restored binaries needs its own corresponding notices.
The small precompiled apphost and DLLs actually present here are covered separately above.

## Game content and generated artifacts

The intended source file set excludes game containers, updates, DLC, console keys, extracted
assets, saves and the 41 research images listed in the [image inventory](docs/image-publication-inventory.md).
The published history starts from one clean root commit that never contained them; the
pre-public history is kept only in a private backup outside this repository.
Shader-map tables contain identifiers and metadata, not the private captured shader pack.

Locally built Apps/IPAs embed rewritten game code and derived shaders, and can include game
control metadata/icons and copied/derived fonts. Their distribution is a separate decision;
external NSP mode alone does not authorize it. The root MIT grant does not cover another
rightsholder's game content.

EA SPORTS FC and Nintendo Switch names are used to identify the supported game/platform.
Touchline 27 has no official affiliation or endorsement from Electronic Arts, Nintendo or Apple.
