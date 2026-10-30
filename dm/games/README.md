# The game profile

The engine reads one game profile, `dm/games/0100C49025D3E000/`, named after the base game's
title ID (EA SPORTS FC 27). Identity and configuration are stored here as data. FC 27 also has build-ID-specific
adaptations in `dm/host/fpslock_fc27.h` and `dm/tools/sdk_patches.py`.

The folder holds:

- **`game.tsv`** — the game's constants, one `key<TAB>value` row each, with comments on their own
  lines.
- **`shader_map.tsv`** (+ `.conflicts.tsv`) — the Shader keys the game asks for, and where each
  one's bytes come from.
- **`shader_facts.tsv`**, **`shader_pairs.tsv`** — hand-written translation facts and known
  vertex/pixel pairs; both empty for this title.
- **`pso_manifest.tsv`** — the pipeline prewarm seed list.
- **`c1_full.tsv`**, **`cb_extent.tsv`** — how much constant/uniform data each Shader may read.
  A full `dmsh_build.py` run writes both from its macOS outputs; they are build products, are
  not committed, and the build regenerates them (`docs/building.md`).

A profile outside this folder can still be read by pointing `DM_GAMES_DIR` at it; there is no
need to for Touchline 27.

## The keys FC 27 uses

| Key | Meaning |
|---|---|
| `title_id`, `program_id` | Identity; `program_id` is what `svcGetInfo(ProgramId)` reports |
| `name`, `app_name` | Labels for messages, the Mac window title and the App name |
| `ipa`, `app_category` | Default artifact name and the App Store category |
| `pad_layout` | Which controller layout the launcher draws (`full`: both sticks, D-pad, four face buttons) |
| `build <ver> <display> <module>=<build ID>…` | One row per version the game was brought up on; the update is the one the shipped profile builds |
| `package` | The version the tables and notes were made on |
| `modules` | The ExeFS modules the host loads (`main sdk`); run-time NRO modules are listed beside the rewritten ones in `nro.tsv` |
| `romfs_marker` | A path that must exist in a RomFS for it to be this game |
| `zip_store` | Suffixes already compressed, stored in the IPA rather than deflated |
| `graphics_api` | `nvn` |
| `fps_target` | Frame rate the host aims for by default (`30`); the launcher offers 60 as experimental |
| `mem_reserve`, `mem_prefix`, `mem_alias`, `mem_stack`, `app_pool`, `mem_used`, `sys_resource` | The guest memory partition (see `docs/architecture.md`) |

Other keys exist for other renderers and other games' tricks (`present_interval`,
`mem_map_limit`, `stdalloc_cap`, …). The host reads them when a profile sets them; FC 27 sets none
of them.

## Reading a profile

The header command writes a generated file; create its parent directory first. These commands
were checked against the script, not executed during the documentation review.

```sh
mkdir -p build
python3 dm/games/game.py list                    # the registered FC 27 profile
python3 dm/games/game.py 0100C49025D3E000 mem_reserve
python3 dm/games/game.py header 0100C49025D3E000 build/game_profile.h
```

`game.py header` is what `make -C dm/host` runs to produce `game_profile.h`, the header the host,
the GPU layer and the iOS sources compile against. Change `game.tsv`, and the host rebuilds.
