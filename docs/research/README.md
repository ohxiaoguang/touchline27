# FC 27 research archive

These records explain how Touchline 27 reached its current source state. They are not
installation instructions or current test results. Their branch names and commit IDs
refer to the earlier research fork, not the independent repository's single initial commit.
Private logs/images/scripts named in the text are evidence identifiers, not promised downloads.

## Reading order

| Record | Date / stage | Scope and later developments |
|---|---|---|
| [Feasibility survey](fc27-feasibility.md) | 2026-10-27 | Input identity, engine/module comparison and early blockers; no gameplay claim |
| [Input integrity audit](fc27-input-integrity-audit.md) | 2026-10-27 | Decryption/hash evidence with explicit provenance limits; predates the registered profile |
| [Two-area rewrite and host bring-up](fc27-two-areas-and-bringup.md) | 2026-10-28 | Early rewritten modules, menus and then-incomplete shader coverage; early memory estimates were superseded |
| [Match bring-up, sections 1–18](fc27-bringup.md) | 2026-10-28–29 | Rendering investigation and later Mac fixtures; early black-world reports are historical |
| [Match bring-up, section 19](fc27-bringup.md#19-the-first-ios-build-an-unsigned-ipa-and-the-12-gb-reservation-it-needs-2026-10-29) | 2026-10-29 | First unsigned IPA and old reservation hypothesis |
| [Match bring-up, section 20](fc27-bringup.md#20-the-12-gb-reservation-measured-and-cut-to-503-gib-2026-10-30) | 2026-10-30 | Measured 5.03 GiB partition and Mac gameplay on it; not device RAM certification |
| [Match bring-up, section 21](fc27-bringup.md#21-fc-27-3060-fps-control-and-device-evidence-2026-10-30) | 2026-10-30 | Mac 30/60 FPS measurements; user report for an earlier iPhone build, not new device performance testing |

Comparisons with other engines/titles are retained only as technical provenance and ABI/
algorithm evidence. They do not add supported games or user workflows to Touchline 27.
Earlier packaging prototypes and reproduction commands describe historical experiments;
use [building](../building.md), [platform status](../support-status.md) and
[the user guide](../user-guide.md) for current information.

## Publication boundaries

All 41 game-derived images were excluded from the working tree after private backup;
[the image inventory](../image-publication-inventory.md) records each item. Old Git objects
still contain them until a later authorized history step. No private evidence was regenerated
or copied back for this documentation review.

[The FPS provenance review](../fpslocker-provenance.md) and
[upstream comparison](../upstream-provenance.md) are the source/permission records.
The [public release review](../public-release-review.md) is the current publication decision.
Historical claims that an artifact contains no game data must be read as no bundled
container/RomFS/console keys: rewritten game code and derived shaders were still present.
