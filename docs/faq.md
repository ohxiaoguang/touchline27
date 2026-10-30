# Troubleshooting and FAQ

Use the independent [build guide](building.md) and [user guide](user-guide.md).
The findings here come from current code paths and historical research, not new runtime tests.

## Why are my game files not recognized?

Use an uncompressed base NSP/XCI and, if needed, the matching update NSP. NSZ/NCZ/XCZ
are not supported runtime inputs; renaming the extension does not decompress a file.
The launcher checks content and Title IDs, not just filenames. Ensure files are readable
and beneath the selected game folder (macOS) or Documents (iOS/iPadOS). Symbolic links
are skipped by resource discovery. Rescan after adding files.

The build wrapper and runtime scanner have different key-discovery rules: for `--nsp-dir`,
put `prod.keys` directly in that input folder or provide `--keys`; the runtime launcher can
search within its selected tree. Keep build inputs unambiguous, or use explicit `--base`,
`--update` and `--keys` options.

## Why does it reject an update or offer several combinations?

The prepared program's Build IDs must match the selected container pair. The recorded
update is `1.8c.fd45`, CNMT v327680; newer is not necessarily compatible. Use the inputs
your local build was prepared from. When several valid combinations exist, select one
explicitly. Do not bypass identity checks or combine modules from unrelated versions.

## Where do I get prod.keys?

Supply keys from your own console. This project does not distribute or provide download
links for keys. A missing or unusable key name may be reported by the launcher; never
paste the key values into an issue. A decryption failure is not proof that the game version
or extracted module is wrong. Share only a redacted error and relevant version information.

## Why is a source checkout plus NSP insufficient?

The current Frostbite `.toc`/`.cas` extraction path does not produce FC 27's shader pack.
A build needs compatible captured/prepared shader inputs and the runtime render NRO.
The game's main NSO also needs external ZBIC decoding unless you reuse your own rewritten
modules. These are private developer inputs; [building](building.md#private-inputs)
explains their roles. The repository does not supply a game-derived pack.

## Why will the IPA not install?

The default output is unsigned. Use a compatible signing and installation setup; check
its certificate/profile, device and OS requirements with that tool's documentation.
An unsigned archive being structurally valid is not installation evidence. The preserved
Bundle ID does not guarantee that a new signature can replace an existing App with its
Documents intact. Back up saves first.

## Does the 5.03 GiB reservation mean I need that much RAM?

No. It is the configured guest virtual address reservation, not a measured physical-RAM
minimum. Metal allocations and process memory limits add separate constraints. The profile
avoids requesting extended virtual addressing in the current packaging logic, but that does
not prove every signing setup or iPhone/iPad will run it. No complete model matrix exists.
Do not reduce profile memory values as an end-user workaround; earlier research records
fatal failures with insufficient alias space.

## Why does startup fail or a match render black?

Check the launcher message, selected versions, runtime NRO preparation and shader-library
identity/coverage. Use macOS shaders for the Mac and iOS shaders for iPhone/iPad. A library
with the right folder name can still have the wrong target or input stamp. A scene not
captured during development can request additional shaders. BC texture support and device
memory also matter. Do not apply the earliest research record's temporary patches as
current instructions; use the latest platform status and a redacted log.

## Why does 60 FPS not work, or drop below 60?

Keep 30 FPS as the default. The FC 27 adapter only accepts the recorded update Build ID;
base or unknown builds are left unchanged. Restart after selecting a target. 60 FPS is
experimental, not a doubled simulation clock. Bounded M1 observations include heavier
views below 60 FPS; no iPhone/iPad sustained-rate, thermal or battery measurements exist.
Changing `DM_PRESENT_HZ` or a displayed counter is not equivalent to enabling the adapter.

## Are DLC commentary, online modes and every language supported?

The shared resource layer implements add-on discovery and reading, but FC 27 DLC gameplay
and commentary have not been verified. The standalone wrappers do not bundle DLC. Online
play and official EA/Nintendo services are unsupported. Game-language choices come from
control metadata; their presence does not prove the required voice content is installed
or that every translation was exercised.

## Where are my saves, and what if saving fails?

See [save locations](user-guide.md#saves-and-logs). Check free space and write permission
on the chosen storage location. A save-write failure can leave progress unsaved. Back up
saves before replacing an App; do not upload them as routine bug-report attachments.
No cross-version save migration or cloud service is promised.

## What should I include in a bug report?

Platform/model, OS, source revision, base/update identity, local build options, selected
settings, steps and a small redacted log excerpt. State whether it is a build, installation,
startup, gameplay or performance issue. Do not attach containers, keys, extracted code,
shader dumps, certificates, saves or unreviewed diagnostic captures. See
[CONTRIBUTING](../CONTRIBUTING.md).
