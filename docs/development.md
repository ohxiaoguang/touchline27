# Development guide

## Environment and entry points

Use the environment in [building](building.md#development-environment). The standalone
product entry points are `scripts/build-mac.sh` and `scripts/build-ios.sh`; they share
`scripts/touchline_build.py`. Generic inherited packagers are implementation utilities,
not an additional supported user workflow or game catalog.

The host is C/Objective-C with assembly entry points, the launchers use Swift/Objective-C,
and the rewriter/pipeline tooling uses Python. The extraction and shader translation tools
are .NET projects. [Architecture](architecture.md) maps these components.

## Generated and private state

Wrappers default to `build/work`, with configurable `--work`/`--out` paths. Use separate
Mac/iOS work directories when preparing platform-specific shader libraries. Generation
also writes local profile tables, and external toolchains can use their own caches.
Do not assume a build writes only to the output App/IPA path.

Prepared modules, runtime NROs, shader dumps/packs, translated libraries, game metadata,
fonts and extracted files are local inputs/outputs. They must not become source fixtures
or a public artifact merely because a converter produced them. Review ignore rules and
tracked files separately. Do not regenerate these items for a documentation-only change.

## Changing the shader chain

The current translator is the locked tool under `dm/gfx/tools/dmsh_xlate_bin/`.
`dmsh_chain.py` hashes translation inputs and checks tool fingerprints; a library also
carries a game/profile input stamp. Changing source, DLLs, the lock or shader profile
inputs can invalidate prepared libraries. Do not patch a binary or edit a lock hash just
to silence an identity mismatch. A source-build replacement must be a separately reviewed
change with its provenance and compatibility consequences recorded.

See [graphics](../dm/gfx/README.md), [dependency material](../dm/third_party/dmsh_xlate_dependencies/README.md)
and [upstream comparison](upstream-provenance.md). This documentation review did not
rebuild the translator, compile shaders or update any chain identifier.

## Validation categories

Report each category separately:

| Category | What it can establish | What it does not establish |
|---|---|---|
| Static review | File identity, command/option existence, references, configuration and notices | Successful compilation or runtime behavior |
| Synthetic tests | The tested parser/host contract on constructed inputs | Retail game provenance or complete gameplay |
| Build | An artifact was produced for stated inputs/toolchain | Signing, installation, startup or gameplay |
| Device installation/startup | A specific signed artifact installs/starts on a named device | Complete matches or sustained performance |
| Gameplay | A stated route, scene or match was played | All modes, DLC, languages or long sessions |
| Performance | Measured scene/settings/duration on a specified machine | Another device or every scene |

### Existing test locations

| Location | Scope / prerequisites |
|---|---|
| `dm/tools/tests/` | Rewriter and build-tool contracts; some use synthetic modules |
| `dm/resource/tests/` | Container/parser/pipeline fixtures; `*_real.py` paths may need private inputs |
| `dm/host/tests/` | Host services, FPS data adapter and VM guards; platform-specific compile/link requirements |
| `dm/gfx/tests/` | Metal/NVN logic; several require a Metal device or a prepared shader library |
| `dm/gfx/tex/tests/` | Layout and pixel format checks |
| `dm/gfx/metal/` | Standalone offscreen example; not the production replay backend |
| `dm/apple/tests/`, `dm/ios/tests/` | Shared launcher settings and iOS workflow/control contracts |

Commands are documented for future development; **none were run in this review**:

```sh
make -C dm/host/tests GAME=0100C49025D3E000 fpslock
make -C dm/gfx/tex/tests run
make -C dm/gfx/metal run
```

The host `fpslock` target builds two executables but does not run them; see its Makefile
and use `build/t_fpslock_fc27` / `build/t_fpslock_vm` from that test directory when a
future task authorizes execution. Broad historical test counts are not current CI results.

## FPS implementation and evidence

`fpslock_fc27.h` contains local typed field/pointer logic. `hle_fpslock.c` supplies safe
host read/write handling, checks the full Build ID and applies the adapter at presentation.
`t_fpslock_fc27.c` has synthetic checks for targets, identity, alignment, bad values and
write failure. Their presence is not a new passing result. Addresses and adjustment research
reference FPSLocker-Warehouse; [provenance](fpslocker-provenance.md) records the reference
relationship, the targeted expression comparison and the fact that no explicit reuse
permission was found — without copying its YAML or assigning it a GPL license.

## Documentation conventions

User/developer guides are English; audit/release decisions are Chinese; original research
can retain its original language. Use Touchline 27 as the product name. Keep module names,
Bundle IDs, file identities, third-party copyrights and meaningful source history intact.
Link archival observations to their date and exact build rather than presenting them as
current support. Use placeholders for personal paths; never publish key values or device IDs.

Before proposing a source release, follow [public release review](public-release-review.md)
and the [final publication report](final-publication-report.md). The published history is a
single clean root commit; the pre-publication history is kept only in the private backup
outside the repository.
