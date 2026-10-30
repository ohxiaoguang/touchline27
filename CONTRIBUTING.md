# Contributing to Touchline 27

Touchline 27 is focused on the Nintendo Switch version of EA SPORTS FC 27. Before
contributing, read the [architecture](docs/architecture.md),
[developer guide](docs/development.md) and [publication review](docs/public-release-review.md).
The public repository URL and release tag have not yet been assigned.

## Issues and changes

Describe the source revision, platform, game version, expected behavior and observed
behavior. Separate build errors, installation errors and runtime bugs. For performance
reports include scene, settings, measurement method and duration; an FPS overlay alone
is insufficient. Device results must name the tested device/OS and exact build, with
personal identifiers redacted.

Keep changes focused and explain their effect and evidence. A documentation change can
be checked statically; do not claim a test passed because a test file exists. Code changes
need checks appropriate to the affected subsystem and an honest account of what was not
run. See [validation categories](docs/development.md#validation-categories).

## Inputs that must stay private

Do not submit game containers, console keys, extracted game programs/assets, shader packs,
converted game shaders, save files, signing identities, provisioning profiles or raw logs
with personal data. Prefer small synthetic fixtures for parser/host work. Review screenshots
and diagnostic captures for provenance before proposing them for publication.

A `.gitignore` rule does not remove an already tracked file or an old blob. Report accidental
inclusion before publishing or proposing a history change. Do not attach suspected secrets
to a public issue.

## Attribution and licenses

Retain applicable copyright and license notices, including seedds/nxnative attribution.
Project code remains MIT; each actual third-party component keeps its own license.
Record imported source URL, exact revision, local modifications, applicable notices and
binary provenance. A project name or matching assembly name is not sufficient evidence.

The FPS implementation uses local C logic with addresses/parameters informed by
FPSLocker-Warehouse. Do not describe those data as wholly independent research, copy its
configuration/assembly patch into this repository, or treat acknowledgement as permission.
The [remaining question](docs/fpslocker-provenance.md) must stay visible until resolved.

Do not change the compatibility Bundle ID as a branding cleanup. Do not delete inherited
shared fixes merely because their comments mention other games. The product's support
scope remains FC 27.
