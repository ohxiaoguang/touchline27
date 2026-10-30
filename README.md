# Touchline 27

Touchline 27 is an unofficial project for running the Nintendo Switch version of
**EA SPORTS FC 27** on Apple silicon Macs, iPhone and iPad. It adapts the game's
ARM64 program to an Apple host and uses Metal for graphics. It requires your own
game files and console keys; it is not an official port or a general-purpose emulator.

The project is under development. Earlier records document Mac gameplay and
user-reported iPhone playability of a previous build. Current device compatibility
and performance are not certified. The source is published at
<https://github.com/ohxiaoguang/touchline27>; the release review and the final
publication report record what was resolved before publication and what remains
limited.

Touchline 27 is independent of and is not affiliated with, endorsed by or supported
by Electronic Arts / EA SPORTS, Nintendo or Apple. Game names and trademarks identify
the supported title only. Its app icon is the project's own artwork
(`assets/app-icon/touchline27.png`); the build uses it for both the iOS bundle and the
macOS `.icns`, and no game logo or control-data icon is shipped as the app icon.

## Features and limits

- Read base-game and matching update NSP/XCI resources in place, with launcher checks
  against the prepared program's Build IDs.
- Render through NVN-to-Metal translation, using shaders prepared ahead of time.
- Host audio output and movie audio decoding; earlier Mac records include audio checks.
- Keyboard and controller input on macOS; mouse-to-single-touch input in the Mac host;
  touch controls, controller input and haptic settings on iOS/iPadOS. Implemented input
  paths do not establish that every controller or game screen works.
- Game-language selection from the supplied control metadata, local save storage,
  and launcher settings for display mode, frame counters and haptics.
- Default **30 FPS** and **experimental 60 FPS** for update `1.8c.fd45` only. The base
  version does not use this adapter. Device performance and sustained 60 FPS are unverified.

Online play is unsupported. DLC discovery/reading exists in the shared resource layer,
but FC 27 commentary and other DLC are **not verified** as playable. Shader coverage
is based on the scenes captured during development, not the whole game.

## Platform status

| Platform | Target | Evidence and limits |
|---|---|---|
| macOS | Apple silicon, macOS 26+ | Historical builds, startup, menus and matches; bounded 30/60 FPS measurements on Apple M1. No current-checkout build or runtime verification in this documentation pass. |
| iOS | iOS 26+ | Historical unsigned IPA; a previous revision was reported playable by a user on iPhone. Current IPA installation, 60 FPS and device performance remain unverified. |
| iPadOS | iPadOS 26+ | The iOS target includes iPad support; no separate iPad startup, gameplay or performance evidence is recorded. |

See [platform evidence](docs/support-status.md) for build/launch/gameplay distinctions,
GPU and memory requirements, and the exact supported update identity.

## Before building

You need an Apple silicon Mac, Xcode with its command-line and Metal tools, .NET 10,
Python 3 and the dependencies in the [build guide](docs/building.md#development-environment).
Xcode 27 is the recorded development environment, not an independently established minimum.

Prepare these privately from your own game and console:

- Base `.nsp` or `.xci`, Title ID `0100C49025D3E000`.
- A matching update `.nsp` if using the update build; historical gameplay used
  `1.8c.fd45` (CNMT v327680).
- `prod.keys`; keep it out of Git, logs and issue attachments.
- The matching runtime NRO module, a captured shader pack, and an external ZBIC decoder,
  or compatible preparation outputs from your own earlier build.

**The containers alone are insufficient for a first build.** The current tools do not
extract FC 27's shader pack from its Frostbite archives. Runtime capture/prepared inputs
are developer prerequisites; no shader pack or decoder is supplied here.

The source distribution excludes the game, updates, DLC, keys, extracted assets,
game-derived images and build artifacts. The published history starts from a single
clean root commit that never contained those files. Nothing here grants permission to
redistribute the game's program or content.

## Build

Clone the repository (<https://github.com/ohxiaoguang/touchline27>) and open a terminal at
its root. After completing the [input preparation](docs/building.md#private-inputs), use
the independent entry points:

```sh
export NX_ZBIC_LIBRARY="/path/to/libzbic.dylib"
./scripts/build-mac.sh   --nsp-dir "/path/to/fc27"   --nro "/path/to/nro"   --shader-pack "/path/to/shader-pack"   --work "build/work-mac"
```

```sh
./scripts/build-ios.sh   --nsp-dir "/path/to/fc27"   --nro "/path/to/nro"   --shader-pack "/path/to/shader-pack"   --work "build/work-ios"
```

Default outputs are `build/Touchline27.app` and `build/Touchline27.ipa`. The IPA is
**unsigned**; sign and install it with your own compatible signing setup. Preserve
Bundle ID `org.nxnative.0100c49025d3e000` for compatibility, and back up saves before
reinstalling. An unchanged Bundle ID alone does not guarantee data preservation.

The [build guide](docs/building.md) covers dependencies, reuse of prepared modules and
platform-specific shader libraries, output paths and the lower-level Xcode signing workflow.
These are documented commands, not commands run during release documentation review.

## First launch

1. On macOS, open your locally built App, choose the folder containing the base,
   matching update and keys, then choose a separate writable storage folder.
2. On iPhone or iPad, sign/install your own IPA and place the containers and `prod.keys`
   under the App's Documents folder through Finder, Xcode or an available file manager.
3. Let the launcher scan and validate the files. Resolve any reported version mismatch
   or ambiguity before selecting Play.
4. Start with 30 FPS. Change settings before launching the game; restart to apply a new target.

See the [user guide](docs/user-guide.md) for controls and saves, and the
[FAQ](docs/faq.md) for file recognition, signing, startup, graphics and performance issues.

## Documentation and contributing

- [Documentation index](docs/README.md)
- [Build guide](docs/building.md) and [platform evidence](docs/support-status.md)
- [Architecture](docs/architecture.md) and [developer guide](docs/development.md)
- [Contributing](CONTRIBUTING.md) and [unreleased change record](CHANGELOG.md)
- [Research archive](docs/research/README.md)

## Acknowledgements

Touchline 27 grew from [seedds/nxnative](https://github.com/seedds/nxnative) and its
contributors. The host, service implementations, rewriting tools and much of the graphics
and packaging infrastructure come from that work. FC 27 adaptation was developed in a
research fork and migrated into this independent project; it does not make the underlying
engine the current maintainers' original work.

FC 27 frame-rate control is implemented in Touchline 27's host-side C code. The memory
addresses, parameters and adjustment research for the relevant game version reference
[FPSLocker-Warehouse's public FC 27 configuration](https://github.com/masagrator/FPSLocker-Warehouse/tree/v4).
This project includes neither the FPSLocker runtime nor its original configuration file
or ARM64 assembly patch. The remaining question, whether any protected expression was
copied, is recorded in [FPS provenance](docs/fpslocker-provenance.md); the targeted
review found only addresses, numbers and adjustment behaviour in common.

Thanks also to the maintainers of the third-party projects listed in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), including Ryujinx, libvpx, stb,
MacNativeGames, deko3d and Khronos. [Upstream comparisons](docs/upstream-provenance.md)
separate verified source relationships from unverified binary build provenance.

## License and distribution

Project code remains under [MIT](LICENSE), retaining seedds and Touchline 27 contributors'
notices. Third-party components retain their own licenses; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

A source release and an App/IPA release are separate decisions. Locally built Apps and
IPAs embed rewritten game code and derived shaders, and can contain game metadata,
icons and fonts. External NSP mode does not make those artifacts freely redistributable.
The [public release review](docs/public-release-review.md) records the remaining blockers.
