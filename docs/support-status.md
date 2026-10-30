# Platform support and evidence

Status date: 2026-10-30. This page distinguishes implemented code from historical
runtime observations. No build, game, test, shader compiler or packaging workflow was
run during the documentation review. No public release tag is assigned.

## Evidence by platform

| Check | macOS | iOS / iPhone | iPadOS / iPad |
|---|---|---|---|
| Target configured | arm64, minimum macOS 26.0 | iOS 26.0 | iPad device family in the iOS target |
| Build evidence | Historical host/App and migration records | Historical generic unsigned IPA | Same generic target; no separate iPad build validation |
| Startup and menus | Recorded in Mac research | User report for a previous revision | Not recorded |
| Match gameplay | Recorded Mac fixtures, including first/second-half transitions | Previous build reported playable; exact device/build evidence not independently reproduced | Not recorded |
| Performance | Bounded Apple M1 30/60 FPS windows | No measured device result | No measured device result |
| Current checkout | Not rebuilt or run in this review | Not installed or run in this review | Not installed or run in this review |

Evidence: [bring-up archive, sections 18–21](research/fc27-bringup.md), especially
sections 20 (memory) and 21 (Mac frame-rate measurements and the prior iPhone report).
Early sections describe failures subsequently addressed; they are not the current
user-facing issue list. Raw logs and images referenced there are private evidence,
not artifacts distributed by this source tree.

## Game versions

| Role | Recorded identity | Scope |
|---|---|---|
| Base application | `0100C49025D3E000`, NACP `1.0.0`; main BID `c2a256339b29922415331fab57de2565` | Registered comparison build; do not infer the update's gameplay/FPS evidence applies to it |
| Update | CNMT v327680, NACP literal `1.8c.fd45`; main BID `9636bcd68e2ef2c863194d76f308c98c` | Historical gameplay baseline and the only FC 27 30/60 FPS adapter target |
| SDK | BID `fed212d6e0963706f9f4b16ea5d65879` | Registered SDK 22.2.0 adaptation |

The display string is recorded as supplied by control metadata. Do not replace it with
an assumed conventional release version. Prepared modules must match the selected
containers. A newly downloaded update is not automatically compatible with an old build.

## Hardware and memory limits

The configured guest reservation is `0x142000000` bytes (5.03125 GiB), including prefix,
alias, stacks and heap regions. This is virtual address space, not a minimum physical
RAM specification and not a guarantee that the App fits every device's memory limit.
The current packaging logic does not request the extended-virtual-addressing entitlement
for that profile. Signing, Metal allocations and operating-system memory pressure still matter.

The texture path maps BC-compressed formats to Metal formats without a general BC
software decompressor. Device support for those formats must be checked separately;
an OS version alone is not a compatibility list. No complete supported iPhone/iPad
model list has been established. See [texture notes](../dm/gfx/tex/README.md).

## Feature boundaries

| Area | Implemented behavior | Evidence boundary |
|---|---|---|
| Graphics | NVN calls replayed through Metal, prepared shader libraries and identity stamps | Captured scenes do not prove complete game shader coverage |
| Audio | Host audio output and movie decoding paths | Mac observations exist; device audio sync/long-session behavior is unmeasured |
| Input | Mac keyboard, mouse as single touch, Apple GameController, iOS touch overlay and haptics | No exhaustive controller, local multiplayer or touch-only gameplay matrix |
| Saves | Local host filesystem saves, separate from read-only game containers | No cloud sync, cross-version migration or loss-free reinstall guarantee |
| Frame rate | 30 default; experimental update-only 60 with Build ID checks | M1 measurements are bounded and include heavier views below 60; no device 60 FPS measurements |
| Language | Launcher offers supported NACP languages when available | No claim that every translation/voice pack has been checked |
| DLC | Shared discovery, verification and AOC reader code | FC 27 commentary and other DLC gameplay not verified |
| Online | Offline host paths | EA/Nintendo online services and online play unsupported |

For release permission/provenance status, use [public release review](public-release-review.md).
