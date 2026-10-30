# Using Touchline 27

This guide covers an App you have built from your own inputs. It does not announce a
public binary download. See [platform status](support-status.md) and
[release preparation](public-release-review.md) before treating this as a supported release.

## Get the source and build

Use the project's published repository when one is assigned, or an existing local checkout.
Do not substitute an unrelated upstream repository: its game registry and workflows differ.
From the checkout root, follow [building](building.md) using `scripts/build-mac.sh` or
`scripts/build-ios.sh`. The scripts accept paths to your private inputs; do not copy game
containers, keys, dumps or save files into tracked source directories.

A fresh build needs the matching runtime NRO, a previously captured shader pack and a
ZBIC decoder as well as game containers and keys. The source checkout does not supply
these inputs and cannot produce the shader pack from FC 27 containers alone.

## macOS

1. Open your locally built `build/Touchline27.app`.
2. Select the game folder containing the base NSP/XCI, optional matching update NSP and
   `prod.keys`. The runtime scanner searches subfolders and identifies container contents.
3. Select a writable storage folder. It is separate from the game folder.
4. Resolve any conflict/mismatch the launcher reports; choose settings and select Play.

The launcher keeps a folder bookmark for later launches. If an external drive is moved or
access is revoked, choose the folder again and rescan. The runtime reads containers in place;
the separate build process extracts/reworks code and prepares shaders.

## iOS and iPadOS

1. Build `build/Touchline27.ipa`; the script does not sign or install it.
2. Sign and install using your own compatible setup. No specific signing service is endorsed.
3. Place base NSP/XCI, matching update NSP and `prod.keys` anywhere beneath the App's
   Documents folder through Finder, Xcode or a file manager with access to that folder.
4. Open the launcher, rescan if needed, resolve the selected combination and choose Play.

The Bundle ID is `org.nxnative.0100c49025d3e000`. Keep it for compatibility, but back up
saves before reinstalling: signing identity, installation method and removing the App can
all affect data retention. No signing or installation was performed in this documentation pass.

## Controls

| Platform | Input | Mapping / limit |
|---|---|---|
| macOS | Keyboard | WASD: left stick; J/K/U/I: A/B/X/Y; Q/E: L/R; Z/C: ZL/ZR; F/G: stick presses; Return/Tab: +/−; arrows: D-pad |
| macOS | Mouse | Left press/drag/release is a single virtual touch; this does not provide a full mouse-driven football control scheme |
| macOS, iOS, iPadOS | Controller | Apple GameController path: sticks, D-pad, face/shoulder buttons and menu inputs; mapping depends on the controller |
| iOS, iPadOS | Touch | On-screen gamepad with visibility and haptic options; not a claim that every mode is usable with touch alone |

By default the Mac keyboard shares player 1 with the first controller. Additional controller
slots exist in the host; FC 27 local multiplayer has not been exhaustively tested.

## Settings

Changes apply to the next game launch. Restart to change the frame-rate target.

| Setting | Default | Scope |
|---|---|---|
| Frame rate | 30 FPS | 60 is experimental and only applies to the recorded update Build ID |
| Render scale | 100% | 50–100% in 5% steps, only exposed if the prepared modules contain `RENDER_SCALE` |
| Console mode | Docked | Reports docked/handheld mode to the game; not a promise of a particular resolution |
| Game language | `en-US` | Choices come from supplied NACP metadata; hidden when no alternative is available |
| Frame counter / performance HUD | Off | Diagnostic overlays; the counter alone is not a performance validation |
| Touch feedback / rumble | On | Strength is adjustable; hardware support varies |

On iOS/iPadOS, `Documents/env.txt` can override launcher choices. It is an advanced
diagnostic mechanism, not required for ordinary import. Do not put secret key values in
it, and review it before sharing logs. The Mac launcher has its own settings/environment
handling; do not assume the iOS override file has the same behavior on macOS.

The iOS/iPadOS launcher's **About Touchline 27** entry opens the project home and the
issue tracker in the system browser, next to the Chinese/English open-source disclaimer.
It performs no version check and collects nothing.

## Saves and logs

On macOS the chosen storage folder contains `nxnative-0100C49025D3E000/`, with `save/`,
`temp/` and `log.txt`. This internal directory name is retained for compatibility; it is not
the product name. Earlier logs can have generated suffixes.

On iOS/iPadOS saves are in `Documents/save/`, temporary data in `Documents/temp/`, and
runtime logs in `Documents/log.txt` and `Documents/log.prev.txt`. Back up the save folder
before changing builds or installation methods. Game containers are not a save backup.
Logs can expose local paths and user-entered text; redact before attaching them to an issue.

There is no documented cloud-save or official service synchronization. A save failure or
full-storage warning means progress may not have been written. See [FAQ](faq.md).
