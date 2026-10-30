# FC 27 historical bring-up: rendering, memory and frame-rate evidence

> Archive scope: superseded findings are retained in chronological order. Use the
> [research index](README.md) and [current platform status](../support-status.md) to
> distinguish historical experiments from current product instructions.

> Personal absolute paths have been replaced by `/path/to/...` placeholders for publication.

> Historical research record from the earlier fork. Paths, branch names, commit IDs, test
> results and device observations below describe that work at the stated time, not verification
> of this standalone checkout. Missing local evidence was not regenerated in the release audit.
> Use [building](../building.md) for current instructions and [release audit](../release-audit.md)
> for publication risks.
> Image names below identify private historical evidence, not files shipped with this source
> repository. See [the image inventory](../image-publication-inventory.md) for exclusions.

> Migrated from the earlier research fork. Technical observations and their chronology are
> retained; publication edits normalize paths, evidence labels and superseded instructions.
> Sections 19–21 contain the later iOS build, memory and FPS work. Current support is in
> [platform evidence](../support-status.md), not the earliest failure report below.
> Additional background and superseded stages are indexed in [the research archive](README.md).

Date: 2026-10-28, branch `research/fifa27`, continuing `ad6082d`. Scratch, logs and screenshots are under
`/path/to/private-fc27-research/` (`logs/run3x-*.log`, `logs/m5-*.png`). A claim is a fact here only where the run or the artifact
is named.

## 1. What ran at the initial stage

The title screen, the EA online notices, the main menu, KICK OFF, the Kick Off hub and Match Preview all render, and **Start Match loads the match**:
the pre-match presentation (team lineup with the real squad portraits), the difficulty dialog the first match shows, and then the match itself, with its
HUD running (score banner, clock, player names and stamina, `LIVE`), at **30 fps** (frame time p50 33.30 ms, footprint 3343 MiB, 368–374 draws a
frame, 25 k translated instructions per draw). Evidence: `logs/m5-08.png` (lineup, `fifa27-match-lineup.png`), `logs/m5-10.png` (match HUD,
`fifa27-match-hud.png`), `logs/run41-m5.log`.

The 3D view of the pitch is **not** there yet: the area the world is drawn into stays black while the HUD is composited over it. Section 4 is the
evidence, section 5 the next step.

## 2. Shaders: 357, all taken from the running game

The shader map grew from 75 (menus) to **357** entries across the recorded capture rounds; every key is a shader the game handed to `nvnProgramSetShaders`, dumped with
`DM_NVN_SHDUMP` and checked by `dm/gfx/tools/shdump_pack.py` against `sha256(control[:0x880] + code)[:8]` (nothing is fabricated):

| round | dumped | total | where the game asked for them |
|---|---|---|---|
| 1 | 75 | 75 | boot, accessibility settings, title, main menu |
| 2 | 68 | 143 | KICK OFF, Classic Match, Match Preview, Start Match |
| 3 | 68 | 337 | the match load (lineup, presentation, first scene frames) |
| 4 | 20 | 357 | the running match |

The historical round labels/totals above are preserved as recorded; the per-round counts
do not fully reconstruct the cumulative totals. Use the later 494-entry source inventory
for current profile size, not this early table as an independent coverage proof.

`dmsh_build.py` translated and compiled all of them (`shaders 357: ok 357`, `Metal cache: mac 0 reused, 405 compiled`) into a fresh library
directory; the build is 4 minutes on this Mac. At the menu the run reports **0 shaders missing from the map**; in the match, 4 new keys appeared
(`0a22ce80f832f078`, `9992e002d1474029`, `1c3f40dc32db5cf6`, `d093bbb6a7639349`), all dumped; one pixel shader (`cc26086f56a50927`) fails to *load* at
run time — `reflection conversion failed: B binding fp_t2d_cb196610_10570000 has no resolved slot number` — so its draws are dropped (section 4).

`shader_facts.tsv` is still empty: the translator answers every query with its default. The round-3 build's `c1_full.tsv` / `cb_extent.tsv` are
stamped for the current library (`inputs 8c7a068a98a9`).

## 3. Two defects fixed on the way (both were fatal or dropped draws)

**A buffer copy whose end is in no memory pool is no longer fatal.** Start Match used to die at `mtl_sub_copy` on `dst=0` (`FATAL buffer copy address
is in no memory pool`), and after that one was skipped, on `dst=0x82c800`. A copy the host cannot express is now reported and skipped:
`[RED] buffer copy with a null end skipped` / `[RED] buffer copy in no memory pool skipped (n so far)`, with the operation history of the submission
printed once (`ophist_dump`). Dying there ended the match before its first frame; skipping it let the whole match load and run.

**A multi-target pipeline whose fragment shader writes fewer outputs than the pass has attachments.** FC 27 has four match pipelines Metal refuses
with `Fragment shader does not write to render target color(0), index(1) that is required for blending`. `pso_desc` already turns blending off on an
output the reflection says the shader does not write (`fs->rf.color_mask`), but the build could not answer that query for these shaders. The error names
the index, so `pso_get_` now retries the descriptor once with blending and the write mask cleared on that attachment and logs
`colour target N is not written by the shader, blending turned off there`. All four pipelines build now.

## 4. Where the world view stops

The passes and targets are right: the frame has 1920×1080 passes for colour (RGBA16F), depth (D32F) and depth-stencil (D32S8), the resolve chain
(`224239`…`224243`) draws into one RGBA16F target, and the HUD composites over it. The world's own target is nearly empty: `texraw` of it (1920×1080
RGBA16F, `logs/run39-m3.log`) has **4.4 % of its components non-zero** — three tall magenta bands and a band of noise at the very top.

3D rendering itself works — a stadium crowd pass draws ~4,600 seats with their textures into a target of its own (`fifa27-crowd-pass.png`,
`logs/hd-894400.png`), so geometry, texturing, pipelines and the Metal path are sound. What is missing is the *world* view.

The strongest lead is a group of three buffer copies the engine records **every frame** that the host cannot place:

```text
copy_b2b src=0x73e8155400 dst=0x7e9000   bytes=170496
copy_b2b src=0x741b243800 dst=0x82c800   bytes=256512
copy_b2b src=0x73d854a500 dst=0x335400   bytes=112128
```

The source is always in a pool; the destination is a small number (0, 0x335400, 0x7e9000, 0x82c800) that lies in no pool and in no guest address
(every pool is around 0x70–0x74 xxxxxxxx, the guest image starts at 0x7265400000). Where it comes from (disassembly of the rewritten render NRO at the
record site, `render+0x8ea00`, md5 of the result checked by `dm/tools/verify_islands.py`):

```text
0x8e9b8  ldr  w10, [x22, #4]      ; the destination block's GPU base, a 32-bit field
0x8e9e4  add  x11, x24, x26       ; a pointer into the block
0x8e9e8  sub  x11, x11, x0        ; minus the block's own base -> offset in the block
0x8e9f4  add  x2,  x11, x10       ; destination = offset + GPU base
```

A `[RED] CopyBufferToBuffer with an address below the pools` line prints the caller's frame, which gives `x24 = 0x73908469cc` (a guest pointer),
`x26 = 0x1064`, `x21 = 0x738f65d998` (the constant base of the source heap) — i.e. the offset is 0 and the whole destination is the block's GPU base,
which reads **0**. None of the host's address getters returns 0 (`nvnBufferGetAddress`, `nvnMemoryPoolGetBufferAddress`, `nvnMemoryPoolMap`,
`nvnTextureGetTextureAddress` are all instrumented and never fired in these runs), and no memory pool is ever created with a null address except three
512 MB virtual pools, one of which (`0x724b3d4c00`) is created and then never mapped or queried at all. So the engine is copying into a block whose GPU
address it never filled in, and the destination of those 0.5 MB of per-frame uploads is lost.

## 5. What is not claimed, and the next step

**Not claimed:** that the game plays a match. The match *simulates* (clock, players, HUD, commentary threads) and its presentation screens render, but
the pitch, the players and the stadium in the match view are missing, so this is not "FC 27 runs".

Next, in this order:

1. Find who leaves that 32-bit GPU base at 0 (the destination block at `[x22+4]`): break on the record site with the frame's registers (the two
   getters at `render+0x8e94c` / `render+0x8e998` return the block's mapped pointer) and follow which object fills `+4`. If it is a virtual pool that
   the engine maps later, the pool needs an address range at `Initialize` rather than at its first `MapVirtual` (`hle_nvn.c` `vpool_reserve` skips
   pools no larger than the application pool) — that is the change to try first, with `DM_NVN_VLOG` to see the pool's state.
2. Fill `shader_facts.tsv` for the compute shader whose thread group size the build could not answer (`compute shader lacks threadgroup size
   reflection`, once at boot): its own control section carries the size, `dmsh_facts.py` reads the table instead.
3. The dropped pixel shader `cc26086f56a50927`: the translator emits a binding (`fp_t2d_cb196610_10570000`, a handle taken from a constant buffer)
   whose slot `dmsh_slots.py` cannot resolve; until it does, every draw that uses it is skipped.
4. The depth copy `D32S8 → D32F` (`texture→texture copy case not implemented ... format 260→252`, once a frame at the menu) has no path in
   `copy_t2t_draw`: the depth branch requires equal formats, and the destination has no render-target usage to upgrade.
5. `sampler ID 4096 not registered` and the empty `pso_manifest.tsv` prewarm list are still open; neither has been shown to affect the world view.

## 6. Reproduce this state

```text
# shaders: dump what the game asks for, pack it, translate and compile it (fresh library directory: an incremental run into a used one deletes
# stale outputs, which the workspace's bulk-delete guard stops)
DM_NVN_SHDUMP=<dump dir> ... dmhost <out dir> main sdk          # writes <key>.ctl/.code/.stg per missing shader
python3 dm/gfx/tools/shdump_pack.py <dump dir> <pack dir> --map dm/games/0100C49025D3E000/shader_map.tsv
DM_GAME=0100C49025D3E000 DOTNET_ROOT=<dotnet> python3 dm/gfx/tools/dmsh_build.py <pack dir> <new cache dir>

# host: NSP backend (base + update NSP + keys), the game's window, a save directory, and DM_CTL to drive it
make -C dm/host GAME=0100C49025D3E000
DM_WINDOW=1 DM_ROOT=<dir> DM_MSL_DIR=<new cache dir> DM_SAVE=<save dir> \
DM_RESOURCE_BACKEND=nsp DM_RESOURCE_NSP=<base>.nsp DM_RESOURCE_UPDATE=<update>.nsp DM_RESOURCE_KEYS=<prod.keys> \
DM_CTL=<ctl file> dm/host/dmhost <out dir> main sdk
```

Driving it (the sequence the screenshots were taken with, `drive2.sh` in the scratch directory): A (title), A (main menu), Up ×9 then Down ×4 (KICK
OFF, the selection saturates at the top so the count does not depend on where it starts), A, A, Down + A (the offline prompt's *Play Offline*, the
default is *Reconnect*), then A (Classic Match), A (Start Match), Down + A (the difficulty dialog's *No Thanks*). `shot <path>` saves the next
presented frame, `passdump <n>`, `texdump <path with %d>`, `texraw <serial> <path>`, `texlist <target>` and `peek <address> <n>` are the diagnostics
used above.

## 7. Follow-up (same day): the copy record decoded, and the world pass rasterizes nothing

Two things were measured since section 4; both narrow the fault, neither fixes the picture yet.

**The copy record, read out of the guest.** `render+0x8e020` is the worker for one copy command; `render+0xb4448` is the thunk that calls it and chains to the
next command with `ldrb w8,[x19+0x50]`. Its argument (the record) is left in `x19` by the thunk, and the worker's prologue saves that `x19`, so the saved slot
(`[frame+0x58]`) is the record pointer even though the worker overwrites its own `x19` (a first attempt read `[frame+0x40]` and got the *thunk's* `x22`, which is
0 — the saved slots hold the caller's registers, not the worker's). Dumping the record gives the layout:

```text
+00  (gpuBase << 32) | 0x00500012      ← +4 is what render+0x8e9b8 loads:  ldr w10,[x22,#4]
+10  resource record A   +18  resource record B
+20  region A            +28  region B
```

and the base really is the engine's own field: the observed copies carry `0`, `0x43800`, `0x7e9000`, `0x82c800` with sizes `0x29a00`, `0x1b600`,
`0x3ea00`. The destination is a ring inside an **8.8 MB buffer**: `0x82c800 + 0x3ea00 = 0x86b200`, exactly the size field (`+0x0C`) of the resource record
dumped beside it, whose own mapping record reads `{cpu 0x71f61ab800, mapped 0x72e5602200, offset 0x202200, size 0x3ea00}` — i.e. the buffer is mapped and
addressable, while the ring's GPU base in the copy record is 0.

**A virtual pool address at `Initialize` does not change it.** Giving every virtual pool a reserved address range at `Initialize` (`vpool_reserve` without
the "no larger than the application pool" shortcut, so FC 27's never-mapped 512 MB pool gets one) was tried and reverted: the copy destinations stayed
`0`/`0x43800`/`0x82c800` (`logs/run45-a3.log`), so the base is not read back from a pool through any host getter — it is the engine's own bookkeeping, which
never receives the heap's address. The change was reverted because it alters the virtual-pool path for every game and fixed nothing here.

**The world pass submits geometry and produces no fragments.** In the running match (`logs/run46-a4.log`), pass `199405` draws `vc=15132` into the 1920×1080
depth target `ser=8561` with `dt=1 dw=1` (depth test and write on) and its vertex stream is a valid buffer (`0x70d1750200`, 64800 bytes, stride 12). The depth
target read back with `texraw` is **entirely at its clear value** (`max 0.000042`, 0 of 2,073,600 pixels above 1e-4): not one fragment was rasterized. So the
black world is neither "no draws" nor "black shading" — the vertices are rejected or clipped before rasterization. Everything the vertex stage reads is
addressable (constant buffers and storage buffers bind from real pools, e.g. `sbufp reg0 0x7221e00000 size=11392000`), which leaves the vertex program's
output (the matrices it builds its clip positions from, or the attribute conversion) as the next thing to measure.

`[pass]` dumps now also print the first vertex stream of each pass (`D <pass> vertex stream <n> buffer=… size=… stride=…`, `nvn_mtl.m`), which is what the
paragraph above rests on.

**Correction to the paragraph above, from the colour target of the same pass.** `texraw` of the colour target `ser=8570` (the 1920×1080 RGBA16F the same
passes draw into, `logs/run46-a4.log`) is **not** empty: 14.5 % of its pixels are above 0.001 and it reads as four saturated magenta bars over dark bands,
with patches of colour noise between them (`logs/col8570.png`). So geometry *does* reach the rasterizer — what it draws is the engine's **missing-resource
placeholder** (magenta) plus uninitialised texture noise, which is the same picture the HUD-free area shows on screen once the frame is composited. The depth
target of that pass (`ser=8561`, D32F, `dt=1 dw=1`) reads back at its clear value while its colour target fills, and that contradiction is unresolved: either
`texraw` of a depth texture does not show what the pass wrote, or depth writes do not land. It is the next thing to check, because the passes after the world
test depth.

That makes the lost ring uploads the leading explanation once more: the world's geometry is submitted and rasterised, and the materials it needs are the
resource data those copies carry. A magenta placeholder for a resource whose upload went to `0x82c800` in a heap whose base is 0 is exactly this picture.

## 8. The ring field is a cursor, and the copies now complete (world still black)

### 8.1 What `[record+4]` is

The command the worker at `render+0x8e020` executes is a 0x50-byte record: `u16 op = 0x12`, `u16 size = 0x50`, then

```text
+00  (u32 op|size)          +04  destination cursor        +08  (0)
+10  destination resource   +18  source resource           +20  region A   +28  region B
+30  source cursor          +38/+3C  (0, size)             +40  (1, 1)     +48  flag
```

`[record+4]` and `[record+0x30]` are **byte offsets inside their resource's buffer**, not addresses, and they are not uninitialised: the
destination cursor of the three uploads advances over the frame and the last one ends exactly at the ring size (`0x82c800 + 0x3ea00 = 0x86b200`,
which is the `+0x0C` size field of the destination resource). The ring itself is an **8.8 MB NVNbuffer at offset 0 of a 12 MB pool**.

The worker turns the two offsets into addresses as

```text
src = GetAddress(srcRes) - Map(srcRes) + regionOut(srcRes) + rec[0x30]
dst = GetAddress(dstRes) - Map(dstRes) + regionOut(dstRes) + rec[4]
```

(`render+0x8e93c`/`0x8e94c` call the two getters on `res+0x1f0`, `render+0x6b620` fills `regionOut` into the frame at `x29-0x28` / `x29-0x50`,
`render+0x8e9ec`/`0x8e9f4` add the record's two offsets). A thread-local trace of the address getters shows the calls in exactly that order and
in that order only:

```text
BufferGetAddress(0x70823fc7b0) -> 0x7117f53600   the source resource's buffer
BufferGetAddress(0x70823fde30) -> 0x7149200000   the destination resource's buffer
MemoryPoolMap(0x705cda9200)    -> 0x7117e00000   the source buffer's pool
BufferMap(0x70823fc7b0)        -> 0x7117f53600   == the source's address
BufferMap(0x70823fde30)        -> 0x7149200000   == the destination's address
```

The helper's outputs for the same command: destination `{0, 0x86b200, 0x86b200}`, source `{0x7117f53600, …, 0x43800}` — the source's
`regionOut` is a **CPU address** (its staging buffer is CPU-authored), the destination's is 0 (it is only addressed by the cursor).

### 8.2 Why the destination collapsed to the bare cursor

`GetAddress - Map` is the engine's space conversion: it expects the GPU address and the CPU mapping of a buffer to be different values, so the
difference carries the pool's base. This host returns **the same pointer from both** (`pool->mem + off`), so the term is 0 for every buffer.
For the source that is harmless — its `regionOut` is already a full host pointer, which is a valid GPU address here. For the destination there
is nothing left but the cursor, so `dst` arrived as `0` / `0x82c800` and the replay skipped it ("address is in no memory pool").

The same identity explains why the values looked "too small to be addresses": they were offsets all along. Nothing was truncated, and no host
getter returned 0 (`nvnBufferGetAddress`, `nvnBufferMap`, `nvnMemoryPoolMap`, `nvnMemoryPoolGetBufferAddress`, `nvnTextureGetTextureAddress`
were all traced; every one returned the pool pointer).

### 8.3 The fix

`rec_cursor_base` in `hle_nvn.c`: when `nvnCommandBufferCopyBufferToBuffer` receives a destination below every pool, the command's own
destination resource (`record+0x10`) names the buffer that must receive the bytes — the sdk wrapper keeps the NVNbuffer inline at
`resource+0x1f0` (magic `BUF\0`, then pool, offset, size). The cursor is resolved to `pool->mem + bufferOffset + cursor` only if every step
checks out: the record is a copy command (op `0x12`, size `0x50`), the buffer and pool magics match, the buffer lies inside its pool, the
record's own size field equals `n`, and `n` fits the buffer. Everything else is passed through unchanged. `DM_NVN_RINGREL=0` disables it.

This is not a base chosen by the host: it is the destination the command names, and the offset it carries. The deeper mismatch remains — a real
NVN gives a buffer two different addresses (GPU and CPU) and this host gives it one — but reconstructing the address at the only layer that
still knows the destination is what restores the transfer.

### 8.4 Verification

* Before: three copies per frame recorded with `dst = 0 / 0x7e9000 / 0x82c800`, replay "address is in no memory pool", transfer dropped.
* After (`logs/run56-d1.log`): `0x7147000000 + 0 -> 0x7147000000` (170496 bytes) and `0x7147000000 + 0x82c800 -> 0x714782c800` (256512 bytes);
  no "address below the pools" report is left at all (the diagnostic only fires when a destination could not be resolved).
* The bytes really move: reading back both ends of the 256,512-byte copy shows identical content (`src`/`dst` dumps of `0x735cd26400` and
  `0x735d82c800`, first 64 bytes equal — constant-buffer matrices of 1.0f).
* `make GAME=… t_nvn` still passes (124 checks, 0 failed).

### 8.5 The world is still black

The match runs (HUD, clock, 410 draws/frame, ~30 fps) but the 3D area stays black (`fifa27-match-after-ring-fix.png`). The ring
content is now correct, and yet the picture did not come back, so the copies were necessary but not sufficient. Two observations for the next
pass:

1. The world pass's vertex stream is **not** the upload ring: run 46's world draw bound `buffer=0x70d1750200`, while this ring is
   `0x7147000000`. So these three uploads feed something else (constant buffers / a data ring), and the geometry path needs the same treatment.
2. A pass dump taken during the match contained only fullscreen quads (`vc=3/6/1122`) while the frame counter reports 410 draws — the dump is
   catching a UI-only submission. The next step is to dump the pass list of a frame that contains the world pass (the one with `vc≈15132` seen
   in section 7) and read its depth and colour targets, to tell "nothing rasterized" from "rasterized black".

## 9. The world pass renders a stadium; the tonemap after it outputs black

**Evidence correction (2026-10-28):** the original LUT read-back covered only slice zero, not the whole volume.
The original format decoder also mislabeled Metal format 92 as RGBA16F; it is RG11B10Float.
The all-volume and causality claims below were preliminary and are superseded by section 10.

### 9.1 The read-back tool was lying

`dm_gfx_texraw` copies a texture into a buffer with a **16-byte texel row** (`row = w * 16`) but the blit packs texels
of the source format tightly inside each row. Decoding a D32F dump at 16 bytes a texel reads padding, not depth, so every
depth target "read back at its clear value" in sections 7 and 8, and the RGBA16F world target looked squeezed into a
quarter of the frame. Both were artefacts of the decoder, not of the renderer:

* `dm/tools/texraw2png.py` now decodes by the dump's own header and the format's texel size.
* `depthprobe` (DM_CTL) writes a 8x8 D32F texture through a blit and reads it back the same way: `0 of 64 texels differ
  -> the depth read-back path works`.

With the correct stride the world pass's depth target holds **117,029 of 2,073,600** non-zero texels (5.6 %) and a shadow
pass at 960x540 holds 61,065 of 518,400 — depth writes land, and no depth defect is involved.

### 9.2 Capturing the real world pass

`passdump` by frame number kept landing on UI submissions. New DM_CTL command **`vcdump <min vertices>`** arms a capture
on geometry size instead: the first draw at or above the threshold makes its own frame the dumped one and prints that
pass's attachments (`[pass] CAP F<frame> pass=… vc=… vs=… fs=… c0=<serial>/f<fmt>/<w>x<h> d=<serial>/f<fmt> vbs=…`).
FC 27's world draw is then unambiguous:

```text
[pass] CAP F8981 pass=260778 prim=4 vc=21714 inst=1 vs=85afca03d2be28de_b fs=515c5461353d5258_b
       c0=7845/f92/1920x1080 d=7846/f252 vbs=0/0x70d0c1e190/859808/12
[pass] D 260778 ... dt=1 dw=1 df=7 sc=0,0,1920,1080 vp=0,0,1920,1080
```

(The 15,132-vertex draw of section 7 is the same pass in an earlier frame; the count varies per frame, so the threshold
is only a trigger, not an identifier.)

### 9.3 The world is drawn correctly

`fifa27-world-target-stadium.png` is that pass's colour target (serial 9119 in a later frame, 49 % of texels
non-zero): **stands with a crowd, the roof structures, the pitch with its line markings, and the players on it**. The
camera, the vertex stream (stride 12, 860 KB), the textures and the shaders of the world pass are all working. Nothing
is missing from the 3D scene itself.

### 9.4 The first broken stage: the tonemap pass

The frame chain (F14763, serials stable across frames):

```text
world 9119 (RGBA16F, has the stadium) + depth 9110
   → 414068 tonemap: reads 9119 at reg128 and the 32x32x32 LUT 735 at reg129, writes c0=9132, c1=672
   → 414069/70/71 960x540 bloom (9135/9134/9133)
   → 414072 back into 9132 → 414073 9147 (RGBA8) → 414074 7859 → 414077 9147 → 414078 28 (final)
```

Every target from 9132 on is **empty** (`fifa27-composite-empty.png`), and so are 9133/9134/9135/9147. The
tonemap pass draws its fullscreen quad (`D 414068 vc=6`, no depth, blend off, writes all channels) and does not report a
pipeline failure, yet both of its attachments stay at zero. Its inputs are bound correctly — 9119 at reg128 with the
world's content, the LUT 735 at reg129 — so the pass is the first place the picture disappears.

The checked slice of texture 735 was zero. This did not establish that every slice was zero, or that the LUT alone
caused the black final image. The early instrumentation observed no layered render pass and no buffer upload into this
LUT; neither observation excluded a skipped compute producer. See section 10 for the confirmed producer.

### 9.5 What to fix next (smallest step)

Find out how FC 27 fills its 32x32x32 LUT and make that path land, then re-run `vcdump 14000` + `texdump`:

1. If it is built with instanced draws into a layered 3D attachment, `g_rp_layered` never became true for it: the pass
   has to be recognised from the shader writing `render_target_array_index` (as in the Z-A case).
2. If it is built by a compute dispatch writing an image (`BindImage` + `Dispatch`), that pipeline is the one that logs
   `[RED] compute shader lacks threadgroup size reflection` at startup, and the dispatch is skipped.
3. If it is uploaded from the resource, the copy is not reaching us at all (no B2T targets it).

Instrumentation added for that step: a log line for every `CopyBufferToTexture` into a texture with depth > 1, and one
for every layered pass that renders into a colour attachment (both always on, capped).

## 10. Compute launch reflection restored; final acceptance still fails

Starting revision: `7e715b43567e581c678de7933c2c65a2aaec79e2`, branch `research/fifa27`.
The initial worktree already contained compute-control reflection and volume-readback changes; these were retained and tested.
No game files were modified and no identity LUT, bypass, or replacement texture was used.

### 10.1 Confirmed producers and descriptors

Run logs: `/path/to/private-fc27-research/logs/lut-investigate.log` and `lut-trace.log`.
The shader cache used is `msl3/b-3722236a52d2` in the same scratch directory.

* `432e6fc529e9d96c_b` writes image0, tid 1412, serial 734 in the trace run: 32x32x32,
  NVN target 2 (3D), format 0x3d (Metal 90, RGB10A2Unorm), flags 4; one mip, one sample,
  Metal texture type 7, array length 1, usage 7, private storage. Its pipeline is ready;
  dispatch groups 1x16x32 with local size 32x2x1 cover the entire volume.
* `b2f4bfe07ec9b7c2_b` writes the display conversion LUTs 150/152: the same launch dimensions,
  NVN format 0x3f / Metal 92 (RG11B10Float).
* `8a5473b6fa07d8cd_b` and `3daf0df0303a4f87_b` instead write 32x64x32 lighting volumes,
  groups 8x16x8, local size 4x4x4. They are not the tonemap LUT producer.

Local sizes and shared memory come from captured control +0x748 and +0x754, already decoded by shader_split.py.
Previously job_for returned without these answers when the shader had no profile facts row. It now carries the captured
answers into translation and the generated reflection. Explicit profile answers still override them.
The missing-threadgroup diagnostic is absent in the new run. Four regression tests cover missing/partial/explicit
profile facts and zero dimensions (which remain unguessed).

`texraw3d 734 <private-scratch>/fc27-lut734.raw` waits for GPU completion and reads all 32 planes. Correctly decoded as 4-byte
RGB10A2, **each plane contains 1024 nonzero texels**. This proves the reconstructed compute path produces a full volume;
it does not alone prove the color transform is correct. The blit diagnostic now initializes padding and checks command-buffer errors.
The opt-in `DM_NVN_LUT_TRACE=1` logs the shader, reflected image slots, descriptor, launch size and pipeline state before
the missing-reflection gate. It does not change rendering.

### 10.2 What now reaches the screen, and what still fails

In F7384 the world pass 221284 uses VS `85afca03d2be28de_b`, FS `515c5461353d5258_b`, c0=7164.
Tonemap 221292 uses VS `42904d74b0c37c1d_b`, FS `24e97a5519ada39d_b`, input 7164 / LUT 734,
output 7169. Display conversion 221294 uses FS `f987d8cd60809431_b`, input 7169 / LUT 150, output 7178.
All these outputs contain world geometry. However, the later HUD composite 7177 reads back black except for HUD.
7177 and 7178 are distinct storage (0x7100a00000 and 0x7105200000); this is not merely two names of one attachment.
The final pass samples 7177. The conclusion that the world must propagate into the HUD target was incorrect: section 11 shows that the final shader independently samples the world and HUD. Final visual acceptance still fails on color/lighting.
The intro showed stadium structures after the reflection rebuild; live gameplay still loses the world at composition.

The HDR world read-back also needs more analysis: at pixel (960,700) the packed HDR value decodes to
(17.25,14.25,9.25), tonemap to (26,19.25,8.75). A gain-one preview clips this to white; it cannot establish correct grass
color or lighting. Do not reuse the old half-float preview as evidence of correct world colors.

Read-backs are taken after queue completion on the running match, not atomic before/after snapshots of one submission.
Such a capture and the exact missing propagation from 7178 to 7177 remain necessary before claiming the final fix.
No layered-rendering or shared resource alias behavior has been changed speculatively.

### 10.3 Artifacts and validation

Diagnostic artifacts in `/tmp`: `fc27-lut734.raw`, `fc27-live-lut150.raw`, `fc27-live-world.raw`,
`fc27-live-tonemap.raw`, `fc27-prehud.raw`, `fc27-live-composite.raw`, and corresponding PNG previews.
Historical previews were saved as `fifa27-lut-*`.
The trace run reports 13.5–14.1 fps around frames 6900–8100 with diagnostics enabled; this is not a clean performance run.
Mac host build succeeds (existing warnings); compute-control tests 4/4, packed-format decoder tests 4/4,
shader chain tests 12/12 pass. Ring changes and prior diagnostic commands remain intact.

## 11. Final composition: HUD-only 7177 is intentional (category E)

Baseline `4a798c6`, clean worktree, branch unchanged. No production graphics behavior was changed.

### 11.1 Correct resource graph

The final fragment shader `58282b58a593ede0_b` reads **three** resources:
reg128 = HDR tonemap world, reg129 = transparent HUD, reg130 = 3D display conversion LUT.
It applies the display transform to the HDR world, then blends HUD over it. Its generated Metal computes
`worldConverted * (1 - hudAlpha * cb[4].z) + hudRGB * cb[4].y`, after scaling HDR by cb[4].x.
The separate display-conversion target (old 7178) is a parallel output, not a required input to the HUD target.
No missing copy from 7178 to 7177 has been demonstrated; inserting one would incorrectly change the game.

Old F7384 pass 221299 already bound 7169 at reg128, 7177 at reg129, 150 at reg130. Section 10 omitted
reg128 and reg130 when drawing its final-path conclusion. This was the first erroneous investigation inference,
not evidence of an erroneous GPU command.

New run `logs/composite.log` under the established external scratch directory reproduces the same graph in F6104:

| Pass | Operation | Output / inputs |
| --- | --- | --- |
| 160058 | Tonemap FS 24e97a5519ada39d_b | HDR world 7143 |
| 160059 | First HUD write: clear zero | HUD 7151 |
| 160060 | Display conversion FS f987d8cd60809431_b | 7152, reads 7143 and LUT 150 |
| 160062 | Overlay FS e99a575065baa5c1_b | HUD 7151, loads preceding clear |
| 160064 | HUD FS a5eae74de232e0d1_b | HUD 7151, loads preceding overlay |
| 160065 | Final FS 58282b58a593ede0_b | window texture 30, reads world 7143 + HUD 7151 + LUT 150 |

7151/7152 are both NVN target 1, format 0x25; Metal 2D RGBA8Unorm, 1920x1080, one mip, one layer,
one sample, private storage. Their storage addresses are 0x7100600000 / 0x7104e00000; flags 8 / 12,
Metal usage 5 / 7. The different storage is intentional, not itself an alias failure.
The pass log shows no texture copy between them. Separate HUD/world are sampled together in the final draw.
No evidence supports A/B/C/D as the reason the HUD target has no world.

### 11.2 GPU-ordered evidence

Existing `DM_NVN_TEXSNAP=0,...,39`, `DM_NVN_SNAPRAW=1`, `texdump` and `vcdump 21000` were sufficient;
no new capture mechanism was needed. Each selected pass's attachments are copied into immutable textures by
`ts_after` in the **same Metal replay stream**, after ending that render encoder; CPU readback occurs after completion.
These are not post-frame reads of the reused original texture. Both snapshots and pass log identify F6104.

Saved `fifa27-composition-*.png` correspond to in-frame indices:
15 HUD just cleared; 16 display conversion complete; 18 HUD after overlay; 20 HUD complete; 21 final output.
The raw HUD-clear snapshot has alpha=0 at all 2,073,600 pixels. After HUD, 2,013,520 pixels still have alpha=0;
the transparent background is preserved. Final output contains players, stadium silhouettes and HUD simultaneously.
Thus the requested world-to-HUD copy is not the path taken by this game.
A second ordered capture in F3487 shows the same final shader and stadium + HUD output.
CPU uniform diagnostics for that frame report cb[4]=(0.5, approximately 1,1,1), cb[15]=(1,0,1,0);
these CPU bytes are supplementary, not GPU snapshot proof.

The filtered command evidence is `fifa27-composition-evidence.txt`. External raw snapshots remain `<private-scratch>/fc27-livechain-*`.
The snapshots verify attachment results, not independent readback of every sampled mip or all cross-submit lifetimes.

### 11.3 Acceptance and remaining problem

**Normal visual acceptance is not achieved.** Live-match final output contains a near-white pitch and dark player
silhouettes with normal HUD. The world is present in the final render target, but grass color and lighting are wrong.
No placeholder, forced copy, HUD bypass, or changes to Ring/LUT/compute were made.
The next failure to isolate is color/lighting in the HDR world / display-transform chain, rather than missing world
propagation into the HUD layer. The world VS/FS remain 85afca03d2be28de_b / 515c5461353d5258_b;
the final FS is 58282b58a593ede0_b. Existing data do not justify assigning the color fault to one of them yet.

Actual-window `shot` requests remained pending while replay continued; final attachment snapshots must not be called
an actual presented-window screenshot. This presentation behavior needs separate verification before final acceptance.
Detailed captures were disabled after collection. A formal performance result is intentionally not claimed because
normal image acceptance has not passed. No shared graphics code change was retained, so no new compatibility fix or
cross-game compatibility claim is made. The host compiled successfully during investigation; its source was restored
to baseline when the existing capture tooling proved sufficient.

## 12. Color investigation and verified rendering repairs (2026-10-28–29)

Baseline `56efd35581f0fa910962cef98bb1b36870c30961`, clean worktree, same branch.
**Acceptance remains incomplete.** None of the repairs below is claimed to restore correct grass/lighting.
Ring, compute launch parameters, LUT data and the HUD/world composition formula were retained.

### 12.1 Numerical baseline, not PNG inference

`fifa27-color-metrics.json` records original bytes, decoded RGBA and 5x5 means at six fixed candidate regions of the
F6104 ordered snapshots: pitch center (960,700), candidate shadow (200,450), jersey (350,240), head (350,225),
stadium (1000,100), and HUD (130,70). Player/shadow labels are approximate silhouette locations, not validated face
or shadow masks; these samples must not be represented as a complete material validation.
The JSON also records stride-8 global sampled ranges, percentiles, nonfinite/negative counts and values above one.
Alpha is implicit 1 for RG11B10Float. Original raw files remain outside the repository.

| Stage | Metal format | Center RGB | Sampled range | Sampled RGB components > 1 |
| --- | --- | --- | --- | --- |
| World, snapshot 10 | 92, RG11B10Float | 4.0625, 3.34375, 2.1875 | 0–5.5625 | 85.27% |
| Tonemap, snapshot 14 | 92, RG11B10Float | 9.375, 6.4375, 2.6875 | 0.0000381–14.125 | 85.27% |
| Display conversion, snapshot 16 | 70, RGBA8Unorm | 0.988235, 0.913725, 0.776471 | 0–1 | 0% |
| Final, snapshot 21 | 70, RGBA8Unorm | 0.988235, 0.913725, 0.776471 | 0–1 | 0% |

The center first changes from zero at snapshot 6 to approximately (4.08,3.34,2.19) at snapshot 7,
corresponding to pass 160051, FS `6744b3d298e56dcf_b`. This identifies the first observed color contribution there,
not proof that HDR >1 or that shader's instruction translation is wrong. The final HUD composite does not cause
this center color: display and final values agree. A complete semantic validation of the tonemap/LUT formulas and
GPU uniform values is still outstanding.

### 12.2 Concrete defects repaired

1. **Dropped dual-source draws.** Runtime rejected FS `ca79f10492b64b8c_b` and `49966011dcbc8318_b` because Source1
   blend factors require Metal `color(0), index(1)`, while the ordinary entry declared `color(1)`.
   `dmsh_dual.py` adds an alternate signature; the host selects it only for actual Source1 blend state.
   The original MRT entry is retained. The failures disappear in the new runs.
2. **Missing captured shaders.** 76 shaders already in `shdump_run` were absent from the old profile. The union of
   existing captured directories has 435 shader keys, all packed from the game's unchanged bytes. The profile map
   now references that union. All 435 compile; the repeated missing-map errors disappear on the tested route.
   This restores coverage, not proof of correct colors. No extracted code or shader bytes were committed.
3. **Indexed separate texture table.** Newly available `cc26086f56a50927_b` failed reflection. It addresses c2 at
   byte 0x170 (index 46), but translation emitted a 32-entry array clamped to 31, with an unresolved texture slot.
   Its encoded handle identifies c2 plus an independent fixed sampler. `dmsh_driver_array.py` expands that binding
   through the full combined/separate-texture extent (0x568/8 = 173), updates only its index clamp and argument IDs,
   and retains a scalar fixed sampler. Reflection names the c2 table rather than inventing a texture slot.
   The host already fills the entire c2 bank from current bindings; a full-table binding contract now permits that
   dynamic read. Dynamic c0, unbound dynamic c2 and static reads outside implemented ranges remain rejected.
   `color-driver.log` confirms this shader loads and binds the 173-entry driver table in the actual game.
4. **Rejected depth-plane copy.** The log consistently reported D32S8 (260) → D32F (252), 1920x1080, unsupported.
   The depth-copy draw already supports depth sampling/writing but required identical formats. It now accepts
   extracting D32F from D32S8, discarding the absent destination stencil plane. No depth scaling or compensation
   was added. A GPU test preserves every depth value, and `color-depth.log` confirms the real copy executes.

No fixed exposure, color coefficients, replacement LUT, post-process bypass or texture recoloring was used.
Final chain version is `32e83615bd74`; full Mac shader library: external `msl-color-driver/b-32e83615bd74`.
Host-only depth-copy support does not alter this translation chain stamp.

### 12.3 Window verification and remaining visual failure

The supported `DM_PRESENT_LINK=0` direct drawable path completes `shot` requests, unlike the previous display-link
run. It was used explicitly; the global default was not changed. This is a working verification path, not a diagnosis
or repair of every display-link stall.
For independent native-window observation, a scratch-only `FC27Research.app` wraps the built host, with an explicit
`DM_NVN_SHMAP` because moving the executable changes its relative default map path. The first bundle attempt aborted
on that missing path; it was corrected, not treated as a graphics failure. CUA identified window `EA SPORTS FC 27`
and captured actual native window pixels on multiple occasions, showing changing menus, match views and HUD.
These native captures are visible in the investigation conversation; the repo PNGs below are presented-source `shot`
artifacts and must not be mislabeled as OS window captures.

`fifa27-color-driver-live.png` shows that correct colors are still absent after the shader coverage/indexing repairs:
the field and players remain too dark. `fifa27-color-depth-intro.png` is the later run with depth conversion enabled;
it still has visibly incorrect scene illumination. The team-management screenshot confirms UI portraits/colors remain
readable, not that the 3D player's skin is correct. These are not acceptance screenshots.

During the next native-window check CUA reported: “The Mac is locked and automatic unlock could not unlock it.”
Manual unlock was requested. Further native-window acceptance is blocked on unlocking; no alternate UI mechanism
was used to bypass the lock. The lighting defect remains independently unresolved.

### 12.4 Validation and reproducible run inputs

External root: `/path/to/private-fc27-research/`.
Runs/logs: `color-fix`, `color-complete`, `color-window`, `color-driver`, `color-depth`; shader builds are
`color-*-shader-build.log`. The research app uses the normal NSP backend/save and `drive2.sh` route, with explicit
shader map, `DM_MSL_DIR=.../msl-color-driver`, `DM_WINDOW=1`, `DM_PRESENT_LINK=0`.

* Full Mac shader build: 435/435, shadow-input variants compile; host builds successfully (existing warnings).
* Dual-source tests: 3 passed, including actual GPU 0.25 × Source1(0.5) = 0.125 and unchanged two-MRT values;
  generated entry compiles for macOS and iOS.
* Driver-table tests: 3 passed, covering index 46, fixed sampler, preserved unrelated clamps, binding ID shifts,
  ordinary arrays unchanged, dynamic-driver rejection controls.
* Reflection test: complete 173-entry c2 table added beside existing 32-entry uniform-array controls.
  Older Super Mario Bros. Wonder cache samples are unavailable for this chain and are explicitly skipped.
* Readback GPU tests: 8/8, including D32S8→D32F acceptance and all 32 literal depth values preserved.
  An initial test omitted the explicit submit and failed; adding the production-equivalent submit boundary made
  the readback valid. This was a test synchronization error, not evidence of a failed game copy.
* Shader chain tests: 12 passed. Existing shader-slot tests: 10 run, one skipped.

Other games were not launched; no cross-game gameplay claim is made. No formal FPS, p50/p95 or optimization result
is claimed because visual acceptance has not passed. Remaining diagnostics include the absent prewarm seed and a
sampler-ID-4096 warning; current tested log no longer reports the repaired copy/pipeline/reflection failures.
The next investigation must isolate the first incorrect material/light contribution, verify LUT representative points
and GPU-consumed uniforms numerically, and finish the unlocked actual-window acceptance.

### 12.5 Unlocked native-window follow-up (2026-10-29)

At HEAD `4954ce6`, with a clean worktree, the user manually unlocked the Mac. Native CUA reattached to
`FC27Research.app`, raised and enlarged window `EA SPORTS FC 27`, and independently captured its pixels.
The window showed the halftime statistics, then the pause menu, then the resumed match after DM_CTL input.
The OS window and presented-source `shot` agree: the scene and HUD are actually presented, but the field/player
lighting remains incorrect. The lock is no longer a blocker. This establishes a working real-window path under
`DM_PRESENT_LINK=0`, not complete visual acceptance or a fix to the default display-link path.

New presented-source evidence: `<private-scratch>/fc27-unlocked-state.png`, `<private-scratch>/fc27-unlocked-half.png`,
`<private-scratch>/fc27-unlocked-play.png`. Native screenshots are also recorded inline in the investigation conversation.
The final CPU uniform block in F885805, pass 31690127 (FS 58282b58a593ede0_b), was saved by the existing diagnostic
at `<private-scratch>/fc27-unlocked-cb/F885805_p31690127_st1_cb0_710b120300.bin`; this is still CPU evidence, not GPU uniform proof.
The shader's C1 starts with (0.0000305185386, 0.00313080009, 1.0549999475): the expected half-float LUT indexing scale
and sRGB threshold/coefficient. Display FS f987d8cd60809431_b has the same constants in its expected order.
No C1 extraction offset error was found in these entries. This does not validate every instruction or the LUT itself.
No brightness/color adjustment was introduced, and formal performance testing remains deferred.

## 13. First contribution is not an established grass-material baseline (2026-10-29)

Baseline `46b859e`, clean worktree, same branch. This step changes no rendering code.
Existing Ring/compute/LUT/dual-source/indexing/depth-copy fixes remain in place.

### 13.1 What 160051 actually demonstrates

The generated entry of `6744b3d298e56dcf_b` has only `gl_FragCoord` plus resource arguments: no interpolated UV,
normal, tangent, material ID or vertex color input. It reconstructs a vector from screen coordinates and cb0 vectors
4–7, normalizes it with rsqrt(dot(v,v)), and uses its normalized Y component to address a 512x1 lookup texture.
It also samples a 32x64x32 volume and a 512x512 texture. This is a screen-space ray/volume calculation, not a direct
albedo material evaluation. Its structure is consistent with an atmospheric/sky contribution; that specific engine
label is an inference, not a recovered symbol or a proven original resource name.

F6104 pass 160051 is a six-vertex draw, 1920x1080 viewport, blend disabled, depth testing enabled,
depth writes disabled (df=7). Input bindings logged at that draw include:

| Slot | Serial | Metal format | Dimensions |
| --- | --- | --- | --- |
| 128 | 459 | 115, RGBA16Float | 32x64x32 |
| 129 | 38 | 70, RGBA8Unorm | 1x1 |
| 130/131 | 40 | 70, RGBA8Unorm | 1x1 |
| 132 | 384 | 20, R16Unorm | 512x1 |
| 133 | 9305 | 153, BC7 sRGB | 512x512, ten levels |

The logged cb0 begins (5.8e-6, 1.35e-5, 3.31e-5, 4e-6); this is not evidence of a sampled green albedo.
The exact command/binding extract is `fifa27-first-contribution-evidence.txt`.
The runtime explicitly selects near=0 and the main0_z vertex entry; the unused GL-depth remapping in main0 is
not evidence of a depth-mode bug. No depth-mode change was made.

The old (960,700) region was zero after snapshot 6 and acquired its tan/HDR contribution at snapshot 7. Combined
with the shader evidence above, this proves only that this screen-space pass first colors those pixels in that
capture. It does **not** establish that its inputs are grass, that HDR 4 is an error, or that its arithmetic should
be changed. A world snapshot needs object/material/depth attribution before the previous region can be called
an actual grass material sample. No new counterclaim about all field geometry being absent is made either.

### 13.2 Player and current-run evidence limits

The previous jersey/head coordinate labels remain unverified silhouette candidates; they cannot establish a skin
shader or a normal-transform defect. They are not used to justify a lighting fix. The captured stage inputs and
current pipeline coverage do not yet identify the first incorrect player material/light value.

The existing color-depth run was still alive after overnight execution. Native-window observation showed halftime
statistics, then the pause menu and resumed match after input. New diagnostics under `<private-scratch>/fc27-unlocked-cb` identify
F885804/885805 and their resources; they are a different camera/time from F6104, so no before/after pixel equality
or color improvement is claimed across them. This run must not be described as a controlled A/B experiment.

### 13.3 Outcome classification

* **Previously proven fixes retained:** the fixes recorded in section 12; no new compatibility modification here.
* **Located but not shown erroneous:** the first nonzero contribution at 160051/6744b3d298e56dcf_b is a screen-space
  ray/volume pass. Its interpretation as direct grass material was not supported by the capture.
* **Unproven hypotheses:** atmosphere/depth coverage explaining the field appearance; missing/incorrect grass
  material contribution; player normal/shadow defects; incorrect LUT math. None is promoted to a root cause.

No new build is necessary for these source/log findings, and no new GPU regression test or cross-game claim is made.
Normal color acceptance remains **failed**. Formal performance remains deferred. Next useful evidence is a matched
color/depth/material attribution before this screen-space contribution, and identification of an actual player draw
with its albedo/normal inputs. Changing exposure, LUT data or this pass's output would not yet be justified.

## 14. Draw attribution: field geometry and separate player candidates (2026-10-29)

Baseline `e359687`, `research/fifa27`, initially clean. No color, exposure, LUT, game asset or compatibility
implementation is changed in this step. Visual acceptance still **fails**. The new evidence establishes a field
geometry/material shader family and narrows several player geometry families; it does not establish a first
incorrect lighting instruction or a complete player material chain.

### 14.1 Reproduction and bounded ordered readback

Three new app runs used the existing offline Kick Off route, `DM_WINDOW=1 DM_PRESENT_LINK=0`, the complete 435-entry
shader map and existing `msl-color-driver/b-32e83615bd74` library. All temporary logs, raw bytes and generated shaders
remain under `/path/to/private-fc27-research/` (abbreviated `R` below). Each isolated process was stopped
after capture, restoring the ordinary shader behavior for subsequent runs.

The new opt-in `DM_NVN_DRAWROI=960,700,8,8,<existing-directory>` diagnostic copies color attachment 0 and supported
depth attachments immediately before/after replayed direct/indexed draws. Arm one frame with existing `vcdump` or
`passdump`. Copies use the replay GPU queue, not a separate queue-completion texture inspection. Shared buffers are
published only after their submission fence has completed. JSON pairs identify frame, global draw, diagnostic pass,
submission, actual VS/FS, texture serial/storage and ROI format/stride. The accompanying forced existing pass log
records resources, samplers, uniform/storage buffers, pipeline/depth/blend and vertex stream details. Texture serials
are capture identities, not hardcoded game constants.

The switch is absent by default. It captures one frame per process, caps the range at 4096 replay draw-counter steps,
and limits each region to 16x16. These runs used an earlier 512-step cap, sufficient to reach final composition.
It deliberately splits render encoders to order copies, so its pass IDs and timing are diagnostic, not ordinary-run
pass numbering/performance. Unsupported formats, multisample, non-2D and nondefault mip/slice/format views are skipped;
combined D32S8 is skipped. It is not a complete MRT/indirect-draw debugger. Index-buffer bytes/addresses and GPU-consumed
uniform bytes are not exported by this addition. Unchanged bytes can also equal a prior frame's contents: lack of a
difference is not proof that a later draw did not execute or contribute.

| Run | Evidence | Captured frame / color-post draw range | Experiment |
| --- | --- | --- | --- |
| Ordinary material | `R/logs/drawroi.log`, `R/drawroi/` | F7056, 3231143–3231577 | Ordered 8x8 field ROI, no highlight |
| Field coverage | `R/logs/drawmask.log`, `R/drawroi-mask/` | F6269, 2804575–2805000 | Only FS `6b160f91c5a5e26a` highlighted |
| Player candidates | `R/logs/playermask.log` | Separate live run; no ROI capture | Existing six-key shader highlight |

The ordinary and field runs produced 1454 and 1418 ROI metadata files respectively. They are separate runs, not a
same-frame quantitative A/B pair. Presented-source `DM_CTL shot` images were retained privately as
`fifa27-drawroi-baseline.png`, `fifa27-drawroi-field-mask.png`, and `fifa27-drawroi-player-mask.png`.
These files are **not OS screenshots**. Native CUA separately inspected/captured the actual `FC27Research.app` window
in the player experiment: it showed the moving match at 23:27 with the same field/limb/head/shorts highlight separation
and normal HUD. That native-window screenshot is recorded inline in the investigation conversation, not represented
by one of these source-image files. No new window-system change was needed.

### 14.2 Established field draw and its real bindings

Highlighting only FS `6b160f91c5a5e26a_b` makes the playing surface magenta while player geometry remains independently
visible. In ordinary F7056, draw **3231295**, diagnostic pass **201816**, VS `0a139b0b8568dd4d_b`, FS
`6b160f91c5a5e26a_b`, changes the chosen region's color and depth together. This is positive field-geometry attribution,
not an inference from the atmospheric pass in section 13. Exactly one draw with this FS occurs in the captured
world-color range; this does not prove that every grass detail/marking/shadow uses that one draw.

The draw logs primitive 4, count 2727, instance count 1, blend off, write mask `0xffffffff`, depth test/write on,
comparison 7, 1920x1080 viewport/scissor. Vertex stream 0 is `0x7b592f3100`, size 33056, stride 12. The count is evidence
for this capture, not an object-selection rule. Color target 7515 is RG11B10Float (Metal 92), depth 7516 D32Float
(Metal 252). Color first pixel changes from zero to packed bytes `49 7a 92 48`, decoded RGB
`(0.017822265625, 0.019287109375, 0.0166015625)`; depth changes from zero to `41 9f 23 3f`, float
`0.6391487717628479`. The highlighted run's corresponding draw 2804721/pass 177561 writes `(1,0,1)` and the same
representative depth, supporting surface coverage rather than a full-screen color-only coincidence.

Representative **actual FS** bindings at 201816 (all texture serials local to this run):

| Register | Serial | Metal format / dimensions | Established use or limit |
| --- | --- | --- | --- |
| 139 | 4051 | RGBA8Unorm, 512x1024, 8 levels | Four channels sampled at base UV |
| 141 | 5617 | BC7Unorm, 512x512, 10 levels | xyw sampled with UV multiplied by 40x60 |
| 142 | 5735 | BC1_RGBA_sRGB, 512x1024, 11 levels | RGB control inputs to palette/math; not established literal albedo |
| 130 | 660 | RG8Unorm, 512x512 | xy sampled; precise material semantic still unproven |
| 140 | 4127 | BC4_RUnorm, 512x1024, 11 levels | Bound material input |
| 136/137 | 4226/10041 | BC4_RUnorm, 1920x2048 / 512x512 | Bound inputs; do not label shadows without dataflow proof |
| 138 | 9985 | BC5_RGUnorm, 512x512 | Bound input |
| 135 | 4065 | BC7Unorm, 760x820 | Bound input |
| 134 | 4177 | RGB9E5Float, 760x820 | Bound input |
| 128/129 | 508/413 | RG11B10Float 128x128 (type 6, six levels) / RGBA16Float 128x128 | Lighting-related candidates; no correctness conclusion |

The generated FS samples reg142 into `_190/_192/_194`; `_192` interpolates palette components from c4, `_190`
multiplies the interpolated colors, and `_194` participates in a 0.75 scale. Thus a decoded RGB image of this texture
alone would not establish the field's intended albedo. The logged reg1 block is 64 bytes at `0x7be1502600`, beginning
`(0.0528629,0.121756,0.0305035,0)`; reg2 is 32 bytes at `0x7b59004600`, beginning `(0.3,0.2,0.025,1)`; reg3 is 5184
bytes at `0x7be14f6900`. These are CPU binding diagnostics, not proof of all GPU-consumed constants or correct lighting.
Storage-buffer and sampler records are preserved in `fifa27-draw-attribution-evidence.txt`.

### 14.3 Player geometry families: positive coverage, incomplete material attribution

The existing `DM_NVN_HILITE` shader-list experiment used, in order:
`6b160f91c5a5e26a,e3c47e6f8f6fed2f,6b0ad5ede3c4a22f,0086439a1761070d,172c93379d73e93d,ff1a047a44a86c58`.
Its colors are magenta/green/cyan/yellow/blue/white. Arms/body portions become green, head regions yellow, and shorts
white; jersey torsos remain dark and **unidentified**. Cyan also covers stadium roof geometry in the intro, so this
candidate must not be classified as exclusively a player shader.

| Visible coverage | FS / ordinary-run VS | F7056 captured draw count | Representative draw/pass and geometry |
| --- | --- | --- | --- |
| Arms/body candidate, green | `e3c47e6f8f6fed2f_b` / `2fb835888cf23cb5_b` | 26 | 3231334 / 201855; count 4080, inst 6; stream `0x7ba8946d00`, size 30816, stride 12 |
| Head-region candidate, yellow | `0086439a1761070d_b` / `e5b2c5a35c1e2587_b` | 17 | 3231360 / 201881; count 1023, inst 1; stream `0x7c2b766400`, size 8496, stride 12 |
| Shorts candidate, white | `ff1a047a44a86c58_b` / `27c550834a1c2632_b` | 16 | 3231154 / 201675; count 1062, inst 1; stream `0x7ba7e15100`, size 8208, stride 12 |

These draws use primitive 4, blend off, depth test/write on with comparison 7. The first two original fragments may
discard; replacing them with a constant fragment loses that discard. Their coverage establishes candidate geometry
families, **not exact original surviving-fragment masks**, recovered material names, or all skin/hair draws. Shorts
FS has no recorded discard, but its material inputs still need numeric validation. Instancing is observed; skinning,
normal/tangent transforms and the torso's actual FS are not yet demonstrated.

The representative arm-family FS binds reg137 serial6854 BC1 sRGB 512x512; reg138 serial315 BC1 linear 256x256;
reg135 serial7961 BC5 512x512; reg136 serial6602 BC2 linear 512x512; reg134 serial6949 BC4 128x128. These are actual
resources, not yet assigned albedo/normal/roughness labels. Its depth input reg128 serial83 is D32Float, reg129/130
serial508/413 match shared field inputs. The shorts family binds numerous BC1/2/4/5/7 and array textures, including
reg136 serial9839 BC1 sRGB 512x256, reg135 serial9983 BC7 512x256, reg138 serial2311 BC5 512x256 array length3, and
reg134 serial12443 BC5 128x128 array length4. Exact head-family bindings and all representative resource records are
in the evidence extract. A texture's existence/format is not evidence its values or selection are correct.

`fifa27-draw-attribution.json` preserves every captured draw identity in these four families, rather than guessing a
single player draw by count. The field ROI does not intersect a positively isolated player body pixel, so its color
values cannot be repurposed as player material values.

### 14.4 Same-frame field-to-display numeric chain

The 64 pixels at x960–967/y700–707 are associated with field geometry by the experiment above. The following are
ordered **post-draw** copies from ordinary F7056; metadata/raw files retain resource/storage and submission identity.
No values from section 12's different camera/run are mixed into this chain.

| Stage | Draw / FS | Resource, format | First pixel RGB (alpha where stored) |
| --- | --- | --- | --- |
| Field geometry contribution | 3231295 / `6b160f91c5a5e26a_b` | 7515, RG11B10Float | (0.0178223, 0.0192871, 0.0166016), no alpha channel |
| Last captured world output | 3231436 / `172c93379d73e93d_b` | 7515, RG11B10Float | (0.0178223, 0.0192871, 0.0166016) |
| Tonemap | 3231439 / `24e97a5519ada39d_b` | 7520, RG11B10Float | (0.00323486, 0.00289917, 0.00155640) |
| Display conversion | 3231440 / `f987d8cd60809431_b` | 7529, RGBA8Unorm | (5,5,3,255)/255 |
| HUD at this field coordinate | 3231576 / `a5eae74de232e0d1_b` | 7528, RGBA8Unorm | (0,0,0,0) |
| Final composite | 3231577 / `58282b58a593ede0_b` | 28, RGBA8Unorm | (5,5,3,255)/255 |

World-region mean is `(0.0176277161,0.0191764832,0.0166015625)`, min
`(0.017578125,0.01904296875,0.0166015625)`, max equal to the first pixel. Tonemap mean is
`(0.00320005417,0.00287151337,0.00155639648)`; final 64 pixels are all `(5,5,3,255)`. All these float samples are finite,
nonnegative and below 1; none is an HDR-clipping observation. Final RGB has no 0/255 endpoint clipping in this region.
Alpha 255 is opaque output, not a color saturation diagnosis. The JSON includes min/max/mean for each stage.

In the separate field-highlight run, the same screen region follows `(1,0,1)` world →
`(1.3125,0.00817871,0.984375)` Tonemap → `(202,46,178,255)/255` display/final. This proves that the isolated field
geometry's replacement output reaches the actual composite; it does not validate the original lighting or LUT formula.
The final copy agreeing with display conversion here is consistent with zero HUD alpha at this coordinate, not a
missing-HUD defect. The live HUD remains visible elsewhere.

### 14.5 Outcome, validation and next minimal evidence

* **Proven new result:** field geometry attribution, actual material/control resource bindings, same-frame field
  color/depth and downstream color chain; separate player candidate geometry groups and actual runtime bindings.
* **Proven new fix:** none. The first incorrect color/light value is **not established**. A dark output and its
  palette-based implementation are observations, not enough to change shader arithmetic or texture color space.
* **Still unresolved:** torso attribution, player-specific original material/light values, GPU-consumed palette/light
  constants, source texture/control values, and whether field/player defects share a cause. The old tan/high-HDR
  sample is not the new attributed field baseline.

The diagnostic host builds successfully (existing Metal encoder-type warnings remain). `t_readback` on Apple M1
passes **14/14**, including existing clear/queue/readback and D32S8→D32F literal-depth cases plus explicit ROI arming,
pending-until-submit, completed-fence publication, stride and all literal texels. The sandbox-only attempt had no
Metal device; the real GPU run succeeded outside that restriction. No production shader, Ring, compute reflection,
dual-source, c2 table or depth-copy implementation changed; their old test results are not claimed as newly rerun.
Other games were not launched. Visual acceptance is not passed, so no formal performance or optimization run is made.

Next smallest actions are: (1) isolate the still-dark jersey family with the existing shader filter, preserving original
discard when interpreting masks; (2) place a new ordered ROI on a positively attributed player fragment; (3) capture
GPU-visible field palette/light uniform bytes and sample the **actual** control textures/UVs for 3231295, then evaluate
that material's original instruction dataflow. Only after an input or operation is shown incorrect should a one-factor
A/B and compatibility fix be attempted. No fixed RGB/exposure, LUT substitution, shadow disable or pass bypass is justified.

## 15. Field material inputs, the jersey torso draw, and a texture-content defect (2026-10-29)

Baseline `872c392`, `research/fifa27`, clean worktree. One host diagnostic was corrected and one added; no rendering
behaviour, shader, exposure, LUT or game asset is changed. Visual acceptance still **fails**.

### 15.1 Instruments, and one measurement that had to be corrected first

Six app runs used the same route (offline Kick Off, `DM_WINDOW=1 DM_PRESENT_LINK=0`, the 435-key shader map and
`msl-color-driver/b-32e83615bd74`). All logs, raw bytes and dumps stay under `/path/to/private-fc27-research/`.

| Run | Purpose | Result |
| --- | --- | --- |
| `field1` | first attempt at uniform capture | showed that `DM_NVN_CBDUMP` only fires when per-binding logging is on (`DM_NVN_PASSDUMP` armed **and** `DM_NVN_PASSDUMP_ALL`, because `bl` is set for the first draw of a pass only) and that the key is the full `_b` key |
| `field2` | field material: uniforms + textures | F6863 / pass 201990 (see 15.2) |
| `field3` | `DM_NVN_HILITE` on six candidate shaders | jersey torso identified (15.4), kit uniforms dumped |
| `field4` | A/B: allow `COMPRESSIBLE` textures into `tex_init_fill` | no change in the match frame, reverted |
| `field5` | `DM_NVN_TEXFILL` diagnostic | refusal reasons classified (15.5) |
| `field6` | A/B: fill a non-flushed CPU-visible range when its storage is non-zero | refusals 14 → 2, the field's own textures unchanged, reverted |

`texraw` was **wrong for block-compressed textures** before this section. It copied level 0 with `destinationBytesPerRow
= w * 16`, which is not a legal row stride for a block format; Metal did not write the copy, the command buffer's status
was never checked, and the fresh buffer then read back as all zeros. That is why "every BC1/BC4/BC5/BC7 texture is
black" looked true in the earlier runs of this session. It now uses the same row bytes the upload uses (blocks per row ×
bytes per block), clears the buffer first and logs a failed copy. The size change is visible in the dumps themselves:
BC1 512×1024 went from 4,194,321 to 1,048,593 bytes.

### 15.2 The field draw, live, with the uniform bytes it is given

F6863, draw/pass **201990**, VS `0a139b0b8568dd4d_b`, FS `6b160f91c5a5e26a_b`, colour target RG11B10Float, depth
D32Float. `DM_NVN_CBDUMP` wrote the four blocks the shader can read (`cb_extent.tsv` agrees with the MSL: `0:16 1:64
2:32 3:5008`), so these are the bytes the GPU is handed, not a CPU-side guess:

| Alias | Bytes | Content that matters |
| --- | --- | --- |
| c3 | 16 | zero |
| c4 (palette) | 64 | `c4[0] = (0.052863, 0.121756, 0.030504)` grass green, `c4[2] = (0.204, 0.167, 0.111)` dry/tan, `c4[3] = (0.610702, 0.746821, 0.761740)` paint white; `c4[0].w` holds an integer (the base index of this draw's 20-dword material records, read as `as_type<int>`) |
| c5 | 32 | `(0.3, 0.2, 0.025, 1)`, `(0.15, 0, 1, 0.9)` |
| c6 | 5008 | `c6[0]=(8,32,0,0)`, `c6[1]=(9.6,100,0,0)`, `c6[200]=(1920,1080,1/1920,1/1080)`, `c6[213]=(0,0,10,1)`, `c6[233]=(13697.3,8532.81,2617.68,1)`, `c6[298]=(-52.5,1,35,0)`, `c6[300]=(-0.619029,0.330739,0.712330,0.1041667)`, `c6[308]=(same xyz, 1)`, `c6[312]=(0.999987,0.00506143,0,0)` |
| c1 | 256 (from the shader package, not a binding) | `(0.5, 1.0, 0.013720, 0.008800)`, `(0.6, 0.886228, 1.023328, -1.023328)`, `(0.858085, -0.858085, 0.247708, 0.429043)`, `(0, 2.246717, 0.226744, 0.044721)`, `(0.002, 2.2, 73.2, 24.5)`, `(8.9, -4.7951, 2.7552, 2.0404)`, `(-0.3324, 0, 0, 0)` |

Fragment texture bindings of that draw (serials are per-run identities, not game constants):

| MSL | reg | Metal format | Size / levels | Role read out of the original instructions |
| --- | --- | --- | --- | --- |
| `fp_t_tcb_60` | 131 | 53 (R16F), NVN target 9 = buffer texture | 129×1 | the painted-line record list; fetched as a wrapped 1D read, its first texel is the segment count |
| `10588070` | 139 | 70 RGBA8 | 512×1024, 8 | `.rgb` mixes the two normal-map layers, `.a` is a wetness/reflection weight |
| `10568074` | 141 | 152 BC7 | 512×512, 10 | two-layer normal, sampled at UV×40×60 |
| `101D815A` | 142 | 131 BC1_sRGB | 512×1024, 11 | `.r` scales the albedo, `.g/.z` are the palette interpolants |
| `1059005E` | 130 | 30 RG8 | 512×512 | screen-space terms (`.xy`) |
| `10598072` | 140 | 140 BC4 | 512×1024, 11 | a single-channel mask sampled at the base UV |
| `101A815A` | 136 | 140 BC4 | 1920×2048, 4 | AO/occlusion at the base UV |
| `1056806C` | 137 | 140 BC4 | 512×512 | 4×4 and 24×24 lookup atlases |
| `1057006E` | 138 | 142 BC5 | 512×512 | tangent-space detail normal |
| `101A0164` | 135 | 152 BC7 | 760×820 | stadium light map, `.w` = visibility |
| `10198164` | 134 | 93 RGB9E5 | 760×820 | stadium HDR irradiance (measured 0…3648, mean 62) |
| `1057805C` | 129 | 115 RGBA16F | 128×128 | BRDF LUT (`.x` = 0.31…1.00) |
| `1058005A` | 128 | 92 RG11B10 cube | 128×128, 6 | reflection probe (measured 10.9…44.5) |

### 15.3 The arithmetic, checked against the MSL and the uniform values

* **The whole material is scaled by `c6[300].w`.** The MSL's last three assignments are
  `out = c6[300].w * (lit * (1 - in.m_81.w) + in.m_81.rgb)`, where `in.m_81` is the vertex shader's light-map blend
  weight and `lit` (`_2190`) already contains the palette albedo, the direct sun term, the light-map term and the probe.
* **That scale is the engine's own exposure, and it is self-consistent.** In this frame `c6[300].w = 0.1041667` and
  `c6[1].x = 9.6 = 1 / 0.1041667`; in the section 14 session's frame the same pair was `0.00920712` and `108.61`. Both
  are stored together and agree to the last digit, so a mis-bound or mis-offset constant is **not** what makes the field
  dark. The value changes by 11× between frames, i.e. it is an auto-exposure the engine recomputes, not a material
  constant — which is also why the section 14 ROI value (0.0178, from another frame) must not be multiplied by this
  frame's constants.
* **The albedo is a two-entry palette, and its scale comes from a texture.** `_386/_390/_378 = lerp(c4[2], c4[0],
  reg142.g)` builds the colour, `_396/_404/_406 = reg142.r * that`, so **with `reg142` = 0 the albedo is exactly 0** and
  every diffuse and specular term of the surface goes with it. `c4[2] → c4[0]` (tan → green) and the two BC7/BC1 detail
  layers mean the visible grass pattern is entirely carried by reg141 and reg142, not by the palette constant.
* **The light arrives from the 760×820 pair plus the probe**: `lightmap.rgb * c6[308].w (=1)` gated by
  `clamp(min(AO, lightmap.w) * …)`, the sun term `c6[233].xyz * NdotL * visibility / d²` with the occlusion quantised
  to even 8-bit steps by the shader itself, and the probe scaled by `c6[1].y = 100` at mip `log2(1 + roughness²·c6[0].y)`.
  None of these constants is zero or out of range in the captured frame.
* **The display end is not a double/missing sRGB step.** `f987d8cd60809431_b` samples the graded image, converts each
  channel to a half-float **code**, indexes a 32³ 3D LUT with `code * c1[0].x + 1/64` (`c1[0].x = 1/32768`, half a texel
  of 1/32), then applies a textbook sRGB encode (`x^(5/12)·1.055 − 0.055`, with `12.92·x` under `c1[0].z = 0.0031308`).
  Its constants are exactly the expected ones. Verifying the 3D LUT's *content* is still open.

### 15.4 The jersey torso: FS `6956f7b5b6219c0a_b`

`DM_NVN_HILITE` on six candidate keys (magenta/green/cyan/yellow/blue/white) resolved the player materials that
section 14 left open, in the "player to watch" close-up and again in the match (`fifa27-hilite-kit-and-field.png`):

| Visible coverage | FS | Colour |
| --- | --- | --- |
| **jersey torso** (every player, both views) | **`6956f7b5b6219c0a_b`** | yellow |
| head / face | `c2cb026208599228_b` | cyan |
| shorts / boots (small parts under the torso) | `d4238c4b59c49bc7_b` | blue |
| stands, stadium backdrop behind the players | `edc9d98901d582df_b` | magenta |
| (not seen in these two views) | `7bfd1324324e96c9_b`, `6b0ad5ede3c4a22f_b` | white, green |

The torso draw in the match frame carries 59 bindings (16 such draws in that frame, one per player), blend off, depth test/write on:
`cb reg3` 5184 B, `cb reg2` 240 B, `cb reg1` **320 B**, `cb reg0` 96 B; albedo `reg136` BC1 1024×1024 / 11 levels,
normal `reg138` BC5 512×512 ×3 layers, masks `reg151/152` BC4 256×256, a four-slot BC3 128×256 set (`reg141/142/149/150`),
`reg147` BC3 1024×1024, `reg131` RG11B10 1024×1024, `reg129` probe, `reg130` BRDF LUT, `reg128` D32F 1×1.

Its palette is **bright**: `c4[3] = c4[4] = (0.576, 0.541, 0.243)`, `c4[5] = c4[7] = (0.604, 0.537, 0.259)` (the gold
away kit), `c4[0] = (-0.108, 0.0837, 0.0657)` as a signed detail term. So "the players are dark" is **not** a dark
palette: with this albedo and this exposure the torso would be clearly visible if its textures and light were the ones
the shader expects.

### 15.5 The first input that is provably wrong: the material textures are not in the GPU's textures

Measured with the corrected `texraw` (level 0), against the guest storage the same texture is registered to
(`texinfo` → `memdump`):

| Texture | Metal format | Guest storage | Host (GPU) texture |
| --- | --- | --- | --- |
| field `reg142` BC1 512×1024 | 131 | valid BC1 blocks (`efffeeff aaaaaaaa …` at `0x709872cc00`) | **all zero** |
| field `reg141` BC7 512×512 | 152 | not dumped | **all zero** |
| field `reg140` BC4 512×1024 | 140 | not dumped | **all zero** |
| field `reg139` RGBA8 512×1024 | 70 | zeros in the first 16 KB | **(0,0,0,255) everywhere** |
| kit `reg136` BC1 1024×1024 | 131 | valid blocks (`0331e418 ffffffff …` at `0x7a42230000`) | **all zero** |
| kit `reg138` BC5 512×512×3 | 142 | not dumped | **all zero** |
| kit `reg137` BC7 256×256, `reg151/152` BC4 | 152/140 | not dumped | **all zero** |
| control: `reg147` BC3 1024×1024 | 135 | not dumped | content (458,771 non-zero bytes) |
| control: `reg131` RG11B10 1024×1024 | 92 | not dumped | content (1,669,033) |

So the read-back is not the explanation (two textures of the same material read with content, and the corrected stride
made the compressed dumps legal), and the GPU is sampling **zero** where the game's data holds a texture: the pitch's
albedo scale/normal/palette/mask and the kit's albedo/normal. With `reg142 = 0` the field's albedo is 0 (15.3) and it
renders as a flat near-black surface whatever the lighting does — which is what the frame shows. The kit is the same
class of failure, so **field and players do share a root cause at the resourcing level**, not in exposure, tone mapping
or the shader arithmetic.

### 15.6 Why the content never arrives: classified, not yet fixed

`tex_init_fill` is the only path that fills a new texture from its storage. `DM_NVN_TEXFILL=1` (added here) logs every
texture it declines *while its storage is not zero*, with the guard that stopped it:

* `multisample, COMPRESSIBLE or depth` — the swap chain and some render targets (expected).
* `CPU-visible pool, storage not flushed before first use` — e.g. 256×256 BC1 9 levels and 512×512 BC7 sRGB 10 levels:
  FC 27 writes texture data into the pool without a flush record covering it.

Two one-factor fixes were tried and **both reverted**, because neither was shown to change the defect:

1. dropping `NVN_TEXTURE_FLAGS_COMPRESSIBLE` from the guard (run `field4`): the field/kit textures carry `flags 0`, and
   the match frame was unchanged; the exclusion is back with a comment.
2. filling a non-flushed CPU-visible range whenever its storage is non-zero (run `field6`): refusals fell 14 → 2 and the
   crowd/stand textures visibly gained detail, but the **field's own** textures stayed zero (`reg142` still 18 non-zero
   bytes = the header only), so the change was reverted rather than shipped as an unverified behaviour change.

The pitch and kit textures were declined by the **first** guard (`!t->mem || !t->pool || VIRTUAL || has_layout`), which
the earlier version of the diagnostic did not report. It now names `virtual (sparse) pool` and `the texture has a
layout`, so one run of `DM_NVN_TEXFILL=1` answers it. That, or an unregistered texture object for these draws, is the
remaining gap between "the data is in the pool" and "the GPU samples zeros".

### 15.7 Outcome classification

* **Proven, dynamic:** the field draw's identity and its real textures (15.2); the uniform bytes the GPU is given and
  their self-consistent exposure pair; the palette/light/probe magnitudes; the jersey torso's FS and its bright palette;
  the zero content of the field's and the kit's albedo/normal/mask textures against non-zero guest storage; the two
  control textures that read correctly; the two `tex_init_fill` refusal classes.
* **Static inference:** that a zero `reg142` forces the field's albedo to zero and therefore its `lit` to the ambient
  and specular residual only; that the 760×820 pair is a light map (name not recovered); that the two `tex_init_fill`
  refusals are the mechanism for *the* textures I measured (measured for other textures, not for these).
* **Guess:** that the engine streams texture data into a pool the host fills before the data is written; that a sparse
  pool or an unregistered texture object explains why these particular textures are declined by the first guard.
* **Not claimed:** that exposure, the tonemap, the grading 3D LUT, the sRGB handling or the field shader's translation
  are wrong. Nothing in this section shows an error in the shader arithmetic; the error that is shown is upstream, in
  what the shader is handed.
* **Colour problem solved?** No. **Match picture accepted?** No — the pitch is still essentially black and the players
  are silhouettes.

### 15.8 Validation

`make GAME=0100C49025D3E000 check_t_readback` on Apple M1: **14/14 PASS** (re-run after the final edit, including the
D32S8→D32F literal-depth and draw-ROI cases). The host builds with the existing encoder-type warnings only. Other games
were not launched, so the `texraw` stride change is claimed only for the diagnostic path it belongs to. No production
rendering, shader, LUT, exposure or asset was changed; the only committed host changes are `dm_gfx_texraw`'s row stride
and failure check, and the opt-in `DM_NVN_TEXFILL` diagnostic. Formal performance work stays deferred.

### 15.9 Next three actions, in order

1. `DM_NVN_TEXFILL=1` on a run to the match and read the guard for the field's `reg142`/`reg141` and the kit's `reg136`:
   if it says `virtual (sparse) pool`, fill through `nvn_sparse_copy` at creation (the sparse path `pkg_upload_` already
   has); if it says nothing at all, the texture object is not reaching `tex_init_fill` and that call site is the target.
2. Re-measure the same ordered ROI right after that one change: with a real albedo the field's world value should move
   from ~0.018 toward ~0.1–0.3. One factor only, before/after on the same frame.
3. Only then evaluate the tonemap/3D-LUT numerically (it is the last unverified stage, and it is not implicated by any
   measurement so far).

## 16. The fill declined FC 27's textures because their pool is virtual, not because their data was missing (2026-10-29)

Baseline `0fc68ba`, `research/fifa27`. One **production guard** in `tex_init_fill` is narrowed, one opt-in diagnostic
(`DM_NVN_TEXWATCH`) and one readback test case are added, and one comment on the `COMPRESSIBLE` guard is corrected. No
shader, exposure, tonemap, LUT, asset or profile constant is touched. The pitch and the kits now sample the textures the
game wrote into its own memory: the match picture takes real colour (16.7), and the material defect of section 15 is
**closed**, while full colour acceptance of the match is **not yet signed off** (16.9).

### 16.1 The four runs this section rests on

| Run | Host | Purpose |
| --- | --- | --- |
| `field7` | pre-fix | the match as it was: the pitch near-black, the players silhouettes (`logs/field7-11.png`) |
| `field8` | pre-fix | `DM_NVN_TEXWATCH` on the pitch's and the kit's material descriptions: every decision and every guard, per texture |
| `field9` | **fixed** | the same watch, the kit's BC1 read back from the GPU, the pitch and the bench cutscene on screen |
| `field10` | **fixed** | the match in play (kick-off, 30:39), and `texraw` + `memdump` of one BC1, one BC4, one BC5 and one BC7 material texture against their storage in the same frame |

`DM_NVN_TEXWATCH=WxH[:format],…` (new, `nvn_mtl.m`) follows the textures that match a description through their whole
life on the resolving thread: at the first resolution it logs the memory pool it belongs to (address, size, flags), the
texture's own storage address and size, whether that storage holds any non-zero byte, whether it has a packaged layout,
whether the storage was flushed, **which path the host texture took** (packaged, filled, zeroed, linear, texture buffer,
shared storage) and, when the fill was declined, the guard that declined it; while its storage is still empty it logs the
first moment that storage turns non-zero, and it notes a buffer→texture copy into the same texture. It is off unless the
variable is set, and it prints for the descriptions it is given only. `tex_init_fill` now records the declining guard in
`g_tif_why` for that line; `[texfill]` keeps its 200-line cap, which is what hid the case in section 15: the pitch's and
the kit's serials fell past line 200 of the refusal list.

Two `[RED]` lines of `field10` belong to the harness, not to the host: nine screenshots were requested with relative paths
from a working directory without them. The run's own evidence was captured with absolute paths.

### 16.2 How a material texture is created, and where its bytes live

The pitch draw (F6863, pass 201990, VS `0a139b0b8568dd4d_b`, FS `6b160f91c5a5e26a_b`) and the jersey torso
(FS `6956f7b5b6219c0a_b`) bind their material set from **one memory pool**, and every texture of that set is described
the same way in `field8` and `field9`. One watched line, verbatim (field8, the pitch's 512×1024 BC1 sRGB):

```text
[texwatch] ser=3244 512x1024x1 format 0x46 flags 0 target 1 levels 11: private texture, ZEROED — tex_init_fill
  declined: nothing recorded; mem=0x7914841800 off=0x4c41800 pool=0x78e83d4a00(mem 0x790fc00000 size 0x20000000
  flags 0x221) sparse=0 has_layout=0 flushed=0, storage 352256 bytes, 329418 non-zero
```

Read field by field:

* **The pool is `0x221`** = `VIRTUAL (0x200) | GPU_CACHED (0x20) | CPU_NO_ACCESS (0x1)`, `0x20000000` bytes (512 MB).
* **It has an address**, `0x790fc00000`. `hle_nvn.c` logs the two steps: `MemoryPool …: a virtual pool of 0x20000000
  bytes starts with no address (0 until its first MapVirtual)` and then `MapVirtual: the storage of virtual pool …
  points at physical pool … + 0`. The host keeps a page table only for a virtual pool **larger than the application
  pool** (`vpool_reserve` returns NULL for `size <= DM_GAME_APP_POOL`); a 512 MB pool is then aliased in place, i.e.
  `pool->mem` **is** the physical pool's host memory, contiguous and directly readable.
* **`sparse=0`** therefore: `nvn_sparse_pool(pool)` is false, there is no page table, and no `nvn_sparse_copy` is needed
  to read the texture's bytes — `t->mem` is an ordinary host pointer into the pool.
* **`mem=0x7914841800`** is `pool->mem + 0x4c41800`: the texture's storage sits about 76 MB into that pool, and both the
  pool base and the offset are 4 KB-aligned.
* **`storage 352256 bytes, 329418 non-zero`**: the game had already put the whole texture, mip chain included, into that
  storage — 93 % of the bytes are non-zero. `flushed=0` only means no `nvnFlush` record covers it, which is expected in a
  `CPU_NO_ACCESS` pool: the guest's CPU cannot write it, so there is nothing to flush.
* **`flags 0`, `has_layout=0`**: no `COMPRESSIBLE`/`IMAGE`/`LINEAR` bit and no packaged layout, so the texture is an
  ordinary sampled block-compressed texture that the host must create as a private Metal texture and fill.

The kit's albedo is the same picture one size up: `ser=2426 1024x1024x1 format 0x46 … storage 701440 bytes, 691925
non-zero`, same pool, same flags. In `field9` the same class appears with `mem=0x7c05dbe200 off=0x45be200
pool=0x7bd9fd4a00(mem 0x7c01800000 size 0x20000000 flags 0x221)`.

### 16.3 The guard that declined the fill

`tex_init_fill` is the only path that gives a new private texture its initial content from guest memory. Before this
section its third guard read

```c
if (t->pool->flags & NVN_MEMORY_POOL_FLAGS_VIRTUAL) TF_RET("virtual (sparse) pool");
```

which treats **every** virtual pool as a page-table pool. Two different things share the `VIRTUAL` flag in NVN, and only
the larger one is a page table in this host (16.2). For FC 27's aliased pool the guard was wrong, and the consequence is
exactly the section 15 symptom: the texture is created as a private Metal texture, `tex_init_fill` returns 0 before it
reads a byte, `tex_zero_fill` clears it, and the GPU samples zeros for the whole material set — while the game's own data
sits in the pool the shader's texture is registered to.

The refusal classes in the two runs (`DM_NVN_TEXFILL=1`, `[texfill]` lines, storage non-zero):

| Guard | `field8` (pre-fix) | `field9` (fixed) |
| --- | --- | --- |
| `virtual (sparse) pool` | **72** | **0** |
| `CPU-visible pool, storage not flushed before first use` | 126 | 95 |
| `multisample, COMPRESSIBLE or depth` | 2 | 2 |
| (list cap) | 200 lines | — |

The 200-line cap is why section 15 saw the virtual class only for small, early textures: the pitch's and the kit's
serials resolved after it had been reached.

### 16.4 What is now known about the guest-storage ↔ Metal-texture relationship

Five separate facts, each measured separately, because "the guest storage is non-zero" alone proves none of them:

| Fact | How it is established here |
| --- | --- |
| the pool has a virtual address | `MapVirtual` line + `pool->mem` non-null in the watch line |
| that address resolves to physical memory the host can read | the alias model (`sparse=0`, `pool->mem` = physical pool base); `mem_count` over `t->mem` reads 329 418 non-zero bytes |
| the physical memory holds the texture's bytes at first use | the same count, taken at the texture's first resolution; no watched texture needed a "turned non-zero after creation" line in `field9` (0 such lines) |
| the upload runs with the right layout | the readback decodes (16.6); the storage is **not** byte-identical to the Metal texture, so a byte comparison would be the wrong test — see below |
| the data is still valid when sampled | the on-screen pitch and kits (16.7) and the fact that `flushed=0` is inherent to a `CPU_NO_ACCESS` pool |

Textures whose storage is genuinely empty at creation are a different case and stay on the other path: in `field9` some
watched textures were zeroed correctly and then written by a **buffer→texture copy** (`[texwatch] ser=4508: a
buffer→texture copy writes this host texture directly (frame 9637), so its content does not come from guest storage`),
which the host already implements and which this section does not change.

**The Metal texture is deliberately not a copy of the storage's bytes.** Level 0 of the guest storage is NVN
block-linear (the list line says `block height log2 4`, i.e. 16-pixel-tall tiles, interleaved in 64-byte groups), while
the Metal texture is row-linear. For that reason a straight `memcmp` of a GPU dump against a `memdump` of the storage
differs from byte 16–20 on (measured for all four formats in `field10`), and it would differ even for a **correct**
upload. The layout is verified by decoding instead, which is also the check a reader can repeat: a wrong de-tiling shears
the image every 16 rows, and these decodes are not sheared (16.6).

### 16.5 The fix

One guard, in `dm/gfx/nvn/nvn_mtl.m`, `tex_init_fill`:

```c
if ((t->pool->flags & NVN_MEMORY_POOL_FLAGS_VIRTUAL) && nvn_sparse_pool(t->pool))
    TF_RET("virtual pool kept as a page table (read through it, not copied)");
```

A virtual pool that the host keeps as a page table is still excluded, and for a real reason: its own storage range has
holes the CPU cannot touch, and its textures are read **through** the table by the packaged path (`tex_mtl_`'s
`packaged` condition and `pkg_upload`'s `nvn_sparse_copy`), so filling them from the flat range would be wrong. A virtual
pool the host aliases in place has no such property: its bytes are exactly the bytes the GPU would sample, so its
texture's content is its storage like any other pool's, and the same reasoning that already lets a `CPU_NO_ACCESS`
physical pool be filled applies unchanged.

What this matches:

* **NVN's own contract.** The content of a texture after `nvnTextureInitialize` is not defined by the API; the host's
  rule everywhere else is "a new texture starts with what its storage holds" (`tex_init_fill`'s other callers, the
  packaged path, `tex_linear`). Excluding one *host-side* storage model from that rule was an artefact of the host, not a
  property of the console.
* **Metal's side.** The destination is a private `MTLTexture` the host creates, so nothing about residency or caching
  changes: `res_add` registers it, `pkg_upload` de-tiles through the same blit it uses for every packaged texture, and
  the sample is a normal sample of a private texture.
* **The other guards stay**: `multisample / COMPRESSIBLE / depth`, `has_layout`, the flush rule for a CPU-visible pool,
  the zero-storage short-circuit, the submit-thread rule and the upload-failure return are untouched, so nothing that was
  correct before changes behaviour.

A/B, on the test rather than on the picture: with the old unconditional `VIRTUAL` guard the new readback case reports
`virtual (aliased) pool texture -> its storage's content, 256 literal pixels expected 0 -> got 256 FAIL`; with the guard
as above, `READBACK cases=21 failed=0`.

### 16.6 The texture data, before and after

Read back with the corrected `texraw` (block row bytes, cleared buffer, command-buffer status checked) and compared with
`memdump` of the same texture's storage in the same frame:

| Texture (slot) | Metal | Guest storage | GPU before | GPU after |
| --- | --- | --- | --- | --- |
| pitch `reg142` BC1 sRGB 512×1024, 11 lv | 131 | 352 256 B, 329 418 (kit set) / 346 718 (pitch set) non-zero | **all zero** (`tex7/ser8155.raw`, 18 non-zero bytes of a 1 048 594-byte dump) | filled from storage at creation in `field9`; a texture of the same description dumped in `field10` (`ser9491`) reads 246 592 non-zero bytes of its 262 144-byte level 0, first 8 bytes `ef ff ee ff aa aa aa aa` = its storage |
| pitch `reg140` BC4 512×1024, 11 lv | 140 | 352 256 B, 71 474 non-zero | **all zero** (`tex7/ser10136.raw`, 18 non-zero) | `ser9863`: 47 093 non-zero of 262 144; decodes to the pitch's line plan (below) |
| pitch `reg141` BC7 512×512, 10 lv | 152 | 351 744 B, 232 315 non-zero | **all zero** (`tex7/ser6183.raw`, 18 non-zero) | `ser2397`: 172 690 non-zero of 262 144, first 8 bytes `c0 01 c0 ec 3e 14 00 00` = storage |
| kit `reg136` BC1 sRGB 1024×1024, 11 lv | 131 | 701 440 B, 691 925 non-zero | **all zero** (`tex2/ser10418.raw`) | `tex9/ser2520`: 519 923 non-zero of 524 288, first 8 bytes `03 31 e4 18 ff ff ff ff` = storage |
| kit `reg138` BC5 512×512, 10 lv | 142 | 351 744 B, 345 038 non-zero | **all zero** | `ser9472`: 259 936 non-zero of 262 144, first 8 bytes `7e 7d 42 26 71 e3 b8 6d` = storage |
| control: `reg147` BC3 1024×1024 | 135 | — | content (458 771 non-zero) | content, unchanged |

Counts of the new path in `field9`, over the descriptions that were watched: **58 textures filled from their storage —
15 BC1 sRGB, 9 BC4, 34 BC7** (and the BC5 above from `field10`). So BC1, BC4, BC5 and BC7 do **not** have four problems:
they shared one, and they were all declined by the same guard.

Two decodes, both from the GPU texture, not from guest memory:

* `fifa27-pitch-line-mask.png` — the 512×1024 BC4 above, decoded as a single channel. It is the pitch's
  marking plan: touchlines, both penalty areas, the centre circle and the spots. Lines are continuous across 16-row
  boundaries, which is the de-tiling check.
* `fifa27-kit-albedo-decoded.png` — the kit's 1024×1024 BC1, decoded as sRGB. It is the Atlanta United jersey
  UV layout with its lettering readable (`AMERICAN FAMILY INSURANCE`, `EMORY HEALTHCARE`, `CAPTAIN`, the MLS crest), so
  both the colour blocks and their arrangement are the game's.

### 16.7 The match, in the real window

`DM_WINDOW=1 DM_PRESENT_LINK=0`, offline Kick Off, Atlanta United (home) against Orlando City, the same route as section
15 (`drive2.sh`), 1 920×1 080.

| | Before (`field7`) | After (`field9`, `field10`) |
| --- | --- | --- |
| pitch | near-black, a faint mowing pattern; no markings | green with mowing stripes, white touchlines, penalty areas and centre circle, specular sheen (`fifa27-pitch-before-fill.png` → `fifa27-pitch-after-fill.png`) |
| players | black silhouettes | real kits: dark red/black Atlanta with numbers and crest, yellow Orlando, skin tones, hair, shorts, socks, boots, contact shadows (`fifa27-match-in-play.png`) |
| the walk-out cutscene | brown flat panels, a bench that is one dark shape | dugout seats, crest board, warm-up bibs, coach, crowd (`fifa27-bench-untextured.png` → `fifa27-bench-textured.png`) |
| close-up materials | — | `fifa27-kickoff-materials.png`: the pre-match handshake, kits, faces, crowd and the `MAJOR LEAGUE SOCCER` boards |
| HUD, stadium, crowd | already correct | unchanged (score banner, clock, `LIVE`, minimap, player bars) |
| continuous update | — | clock runs (00:00 → 30:39), players and ball move, mip levels change as the camera pulls out, no stale texture |

Acceptance, item by item: pitch colour, texture and shading **pass**; white line markings **pass** (they come from the
BC4 mask above, so their presence is itself evidence that the fill ran); kit colour and detail **pass**; skin, shorts,
boots and shadows **pass**; stadium, crowd and HUD **pass**; continuous updates **pass**; the other screens (menus,
team management, Match Preview) are **unaffected** — they were correct before this change, and their textures are not
among the zeroed ones (section 15's two control textures, in this same material set, already had content).

Not signed off: the **balance** between the pitch and the players. The pitch is now bright and the players read dark
against it, which is what section 15's numbers predict for this material set (the pitch's albedo is a palette the shader
scales, the players' is a photographic texture) — but with the material data correct for the first time, this is a
question about the engine's own exposure and lighting, not about missing textures, and it must be answered by
measurement on this frame, not by a colour patch. None was applied.

### 16.8 Validation

* `make -C dm/gfx/tests GAME=0100C49025D3E000 check_t_readback` — **21 cases, 0 failed** (the 14 of section 15 plus 7
  new: an aliased virtual pool whose texture must reproduce 256 literal texels, an aliased virtual pool with no address
  that must give zeros and not crash, and the residency/commit/error checks around them). The new case fails with the old
  guard and passes with the new one (16.5).
* Unchanged suites, re-run after the edit: `t_nvn` 124/0, `t_texture_views`, `t_view_levels` 34/0, `t_view_swizzle`
  203/0, `t_mip_extent` 303/0, `t_upgrade_alias` 10/0, `t_linear_readback` 17/0, `t_deswz_gpu` 15 cases pass.
* No other game was launched. The change only *permits* a fill that was refused, only for a virtual pool the host
  aliases in place, and the page-table model that Monster Hunter Rise and the other sparse-pool games depend on is
  untouched (`nvn_sparse_pool` gating, `tex_mtl_`'s `packaged` condition, `pkg_upload`'s sparse copy).
* Frame time: `field10`'s in-match windows are p50 46.05 / 50.31 ms (GPU p50 44.7 / 49.6); `field9`'s are 39.4 / 50.5;
  `field8`'s last windows were 36.0–38.1 but at frames 8400–9600, a different part of the match. These are **not** a
  like-for-like A/B, and the fill itself adds no per-frame work (it runs once per texture when the texture is created:
  58 watched textures, about 20 MB in all). Sampling real BC data instead of a zeroed texture can change cache and
  bandwidth behaviour, so a proper A/B on the same scene is still owed before any claim about performance.

### 16.9 Open issues

1. **95 textures still refused as "CPU-visible pool, storage not flushed before first use"** (126 before). They are a
   different class: a pool the guest CPU writes, with no flush record covering the texture's range at its first use. The
   section 15 experiment that filled them (14 → 2 refusals, some stand detail gained, the field unchanged) is still not
   shipped, and doing it correctly means deciding what "the storage is valid" means for such a pool rather than relaxing
   the check.
2. **Two shaders of the deeper match are not in the map**: `d09b9396bbcfd6ef` and `44e0d294a2b0c5a6`, first hit at frame
   14784 of `field10` (598 s), after which the program they belong to cannot be built and its draw is skipped. They need
   capturing before the next visual pass; they are unrelated to this section's change (they appear at a game state the
   earlier runs never reached).
3. **The pitch/player brightness balance** (16.7) — to be measured on the corrected material, not patched.
4. `texraw` allocates its dump buffer as `rowBytes × height` even for a block-compressed format, where Metal writes
   `rowBytes × ceil(height / blockHeight)`; the file is therefore up to 4× the data with the tail zeroed. Harmless for
   content (the counts above are taken over the level-0 region, not the file), but worth tidying before a script starts
   depending on the file size.
5. No performance A/B (16.8).

### 16.10 Outcome classification

* **Proven, dynamic:** the pool of the pitch's and the kit's material textures (virtual, 512 MB, `0x221`, aliased in
  place, no page table); that the game's data is in that pool's storage at the texture's first use (329 418 / 691 925
  non-zero bytes); that the old guard declined exactly those textures and the host zeroed them; that the new guard fills
  58 of them, in four block-compressed formats; that the GPU texture's level 0 then matches the storage's first bytes and
  decodes to the pitch's line plan and to the jersey with readable lettering; that the pitch and the kits take their real
  colour in the window.
* **Static inference:** that no other game's aliased virtual pool depends on its textures *not* being filled (none was
  launched); that the remaining darkness of the players is the engine's exposure and lighting rather than material data.
* **Not claimed:** that exposure, the tonemap, the grading LUT, the sRGB handling or the field shader are wrong; that the
  performance is unchanged; that full colour acceptance passes.
* **Colour problem solved?** The **material** defect is: the pitch and the players sample the textures the game wrote.
  Match picture accepted? Not yet — the remaining question is brightness balance (16.7), not missing data.
* **Committed:** the guard, the `DM_NVN_TEXWATCH` diagnostic and its one-line report hooks, the corrected
  `COMPRESSIBLE` comment, the `t_readback` case, this section and the four new images.

## 17. The deep match's missing shaders, the CPU-uncached pool's textures, and the brightness measured on them (2026-10-29)

Baseline `ced7638`, `research/fifa27`. Four shaders are added to the profile's map and library, one production guard in
`tex_init_fill` is narrowed (a pool's CPU cache attribute decides whether a flush is needed), `DM_NVN_KEYDUMP` takes a
list of keys, and one `t_readback` family pins the new rule in both directions. No shader source, exposure, tonemap, LUT,
kit palette, grass palette or asset is touched. The two shaders that skipped a draw in the deep match build and draw; the
textures the fill used to decline in a CPU-uncached pool are filled (6 of one run's 40 are textures the match binds and
reads every frame, and the stands' crowd is the visible difference); the pitch's and the players' brightness is measured
through the material stage and needs no change.

### 17.1 The runs this section rests on

All eight used the same route (offline Kick Off, Atlanta United against Orlando City, `DM_WINDOW=1 DM_PRESENT_LINK=0`,
1920×1080), the 439-key shader map and `msl-color-driver2/b-32e83615bd74`. Logs, raw targets and dumps stay under
`/path/to/private-fc27-research/`.

| Run | Guard in `tex_init_fill` | Diagnostics | Reached | Purpose |
| --- | --- | --- | --- | --- |
| `field10` | virtual-pool fix only | `SHDUMP`, `TEXFILL` | F27 000 | the run that asked for the missing shaders (14 784, 19 950) |
| `field11` | before 17.4 | `TEXFILL`, a 20-frame pass dump | F31 500 | the class of 17.3 in the match, with its bindings |
| `field12` | as 17.4 | `TEXFILL` | F13 000 | first run of the new rule |
| `field13` | as 17.4 | `TEXFILL` | F27 300 | the class's fills over a long match |
| `field14` | as 17.4 | `TEXFILL`, `KEYDUMP` (pitch + kit), same-frame target dump | F27 345 | the pitch's and the kit's uniforms in one frame; the frame of 17.6 |
| `field15` | as 17.4 | none | F17 000 | the A/B "with the fix" side, and the window pass of 17.7 |
| `field16` | the guard before 17.4 | none | F17 000 | the A/B "without the fix" side (one build, one line) |
| `field17` | the guard before 17.4 | `TEXFILL`, a 40-frame pass dump with every binding (`PASSDUMP_ALL`) | F9 000 | the census of 17.3: which refused textures the match binds and reads |

### 17.2 The four shaders the deep match asked for and did not get

Section 16.9 left two keys open. `DM_NVN_SHDUMP` on `field10` had already written their `.ctl` / `.code` / `.stg` at the
frames that asked for them, and the same dump held two more keys that the same frame reported:

| Key | Stage | Code | First asked | Role |
| --- | --- | --- | --- | --- |
| `d09b9396bbcfd6ef` | vertex | 768 B | F14 784 | a geometry-capture vertex stage (`main0_gs` with `dm_geometry_capture`, buffer 13) |
| `44e0d294a2b0c5a6` | pixel | 1 536 B | F14 784 | the fragment stage that pairs with it |
| `3e9a7bcf756123f0` | pixel | 1 536 B | F19 950 | a second pixel stage of the same game state |
| `944c27a55049d95d` | pixel | 1 024 B | F19 950 | a third |

Each capture was verified before packing, from its own bytes and not from its name: the control block is 2 176 bytes with
the `0x98761234` magic, the code length it states at `+0x704` equals the `.code` file's length, the stage comes from the
code header (graphics magic `0x12345678`, stage bits 10..13 of the SPH word), and `sha256(control[:length] + code)`'s
first 8 bytes equal the key. `shdump_pack.py` then wrote the four records into the pack the 435 keys already used and
appended four rows to `shader_map.tsv`; the pack's key set and the map's key set are equal at **439**.

`dmsh_build.py` translated the pack with the chain of `dmsh_chain.h` (`32e83615bd74`) and its locked translator:
`shaders 439: ok 439, shader cache: hit 435, rebuilt 4`, `Metal cache: mac 67 reused, 4 compiled`; the four new
`_b.json` / `_b.metal` / `_b.metallib` exist and their MSL is full shader code (8.6 KB / 6.1 KB / 10.9 KB / 6.2 KB), not a
stub. Every run above then reported `shader route B ..., shader map 439 entries`, and from `field11` to `field16` the log
holds **no** `is not in the shader map` and **no** `program has no vertex shader` through F27 345 — both frames that
skipped a draw in `field10` are passed, and the draws of that program build a pipeline and execute. That is
completeness for this route and not for the title: section 18 finds 55 more keys the same map lacks in another
fixture.

One artifact of the rebuild is worth naming, because it is a build-input gap and not a shader error: the readable-tile
variant (`<key>_bf.metallib`) of `d04bd72a626b3a62` is produced only for keys in the profile's `bf_want.tsv`, which this
profile does not have; the library built before this section still had that file from an earlier tree state. It is
unrelated to the four keys (which built their `_b` outputs), and no run of this section took the readable-tile path — the
host logs `not provable: no readable-tile version` when it does, and none appears. The file must be regenerated from the
planner's list before this profile's libraries are shipped.

### 17.3 The refused textures: what they are, and whether the match samples them

`field9`'s `DM_NVN_TEXFILL` refused **95 distinct textures** with one reason, `CPU-visible pool, storage not flushed
before first use`, and every one of them was in a pool of flags `0x22` = `CPU_UNCACHED | GPU_CACHED`. Two more were
refused as `COMPRESSIBLE` (`0xa2`, a 1920×1080 RGB9E5 and a 1920×1080 RGBA8), which is correct: a compression-tagged
texture's bytes have no meaning without their tags.

| Shape | Count | Format |
| --- | --- | --- |
| 68×80, 1 level | 66 | BC3 (`0x44`) |
| 384×32, 1 level | 7 | BC3 |
| 256×32, 1 level | 6 | BC3 |
| 256×256, 4 levels | 4 | BGRA8 (`0x9a`) |
| 512×128, 6 levels | 2 | BC3 sRGB (`0x48`) |
| 512×512, 10 levels | 1 | BC7 sRGB (`0x4e`) |
| 2400×1080 / 3840×1080 / 1028×1028, 1 level | 3 | BGRA8 / RGBA8 |
| 308×224, 128×128 (`0x48`, 3 levels), 32×40, 32×32 | 4 | BC3 |
| 128×128, 8 levels (`0x2c` → Metal 113) and 128×32, 6 levels (`0x2f` → Metal 123) | 2 | integer / R-format leaves |
| 1920×2048 BC4 4 levels, 1024×1024 BC1 sRGB 11 levels | 2 | measured **empty at this resolution** (`DM_NVN_TEXWATCH`: 0 non-zero bytes), so declining them was right |

Are they sampled by the match? Yes, and it is measurable. `field11` (a match run with the refusal log and a 20-frame pass dump)
gave one: serial 4717, a 512×512 BC7 sRGB with 10 levels in a `0x22` pool, bound at fragment slot 131
(`T ... bind st1 slot131 ... ser=4717`) and read by that frame's draws (`R ... st1 ser=4717`). `field17` repeats the census
over a wider window on the pre-fix build — 40 consecutive in-play frames (F8 957–8 996) with `DM_NVN_PASSDUMP_ALL`, so
every draw's bindings are recorded, not only each pass's first: **6 of the run's 40 refusals are bound and read** by the
match's draws, and every one of them is read (`R`) and not merely bound:

| Serial | Shape | Format | Bound | Read | Where |
| --- | --- | --- | --- | --- | --- |
| 4948 | 512×512, 10 levels | BC7 sRGB (`0x4e`) | 320× | 160× | fragment slot 131 |
| 6022 | 512×128, 6 levels | BC3 sRGB (`0x48`) | 80× | 40× | fragment slot 148 |
| 6073 | 512×128, 6 levels | BC3 sRGB (`0x48`) | 80× | 40× | fragment slot 148 |
| 6141 | 512×128, 6 levels | BC3 sRGB (`0x48`) | 80× | 40× | fragment slot 148 |
| 6158 | 512×128, 6 levels | BC3 sRGB (`0x48`) | 80× | 40× | fragment slot 148 |
| 6175 | 512×128, 6 levels | BC3 sRGB (`0x48`) | 80× | 40× | fragment slot 148 |

The pass that binds them is the one whose stages are `852a68aa29eda480_b` (vertex) and `6744b3d298e56dcf_b` (fragment),
and 320 = 8 bindings a frame × 40 frames for the atlas, 80 = 2 a frame for each board. One line's own `pool flushed=1`
(serial 6022) is the whole-pool answer, not the guard's: the guard asks whether a flush covers the *texture's* range, and
that pool had a flush record elsewhere.

So the class is not dead weight: textures the match binds every frame were GPU textures of zeros while the guest's storage
held their blocks. How many in total is a per-run figure, not a constant: `field9` refused 95, `field17` 40 and filled 85
others of the same pool class through flush records that did cover them, because the guard's answer depends on whether a
flush record covers a given range at that texture's first use. The floor is the two windows above: 1 proven in 20 frames,
6 in 40.

The remaining two refusals (`COMPRESSIBLE`) are not sampled: in `field13` and `field14` the intersection of refused and
bound serials is **0** over 666 and 383 distinct bound serials. Those are render targets and swap-chain-like surfaces,
not material textures.

### 17.4 The defect: a flush is how a *cached* pool publishes writes, not how an uncached one does

`nvnMemoryPoolFlushMappedRange` (hle_nvn.c:229) is the operation that publishes a **CPU_CACHED** pool's writes to the
GPU. A **CPU_UNCACHED** pool's stores are in memory when they retire — that is what the attribute means — and NVN offers
no flush for it. The guard asked every CPU-visible pool for a flush record:

```c
if (!no_cpu && !nvn_flushed(t->mem, t->L.size)) TF_RET("CPU-visible pool, storage not flushed before first use");
```

so every texture of an uncached pool was declined even though its bytes were exactly where the GPU reads them. That is a
host-side visibility-semantics error, not an omission by the game: the game does call `MemoryPoolFlushMappedRange` (it
appears in the per-frame NVN call counts), and its cached pools still take the flush path. The guard now asks by the
pool's cache attribute:

```c
int cpu_cached = (t->pool->flags & NVN_MEMORY_POOL_FLAGS_CPU_CACHED) != 0;
if (!no_cpu && cpu_cached && !nvn_flushed(t->mem, t->L.size)) TF_RET("CPU-cached pool, storage not flushed before first use");
```

`t_readback` pins the rule in both directions with three cases, each in a pool of its own (the host shares textures by
pool object, offset and description, so a shared stack slot would hand back the previous case's texture): a `0x22`
(uncached) pool with no flush must reproduce its storage's 256 literal texels; a `0x24` (cached) pool with no flush must
give 256 zero texels; the same cached pool with a flush covering the range must reproduce the texels. **24 cases, 0
failed** on Apple M1. The experiment switch section 16 left to turn the fill off (`DM_NVN_FLUSH_FILL=0`) goes with the old
rule; `docs/research/fc27-bringup.md` now states the pool-attribute rule and lists `DM_NVN_TEXFILL=1` as the way to see what
is still declined.

What the fix does at runtime, in counts (`[nvn] texture first content from storage`, cumulative):

| Run | from a `CPU_NO_ACCESS` pool | flushed by the CPU | from a `CPU_UNCACHED` pool | refusals |
| --- | --- | --- | --- | --- |
| `field17` (guard before 17.4) | 5 580 | 0 | 85 | 40 (that guard) + 5 (`COMPRESSIBLE`) |
| `field13` | 5 057 | 0 | 106 | 7 (all `COMPRESSIBLE`) |
| `field14` | 5 273 | 0 | 125 | 6 (all `COMPRESSIBLE`) |

The refusals of `field9` (95) and of `field17` (40) are gone; what remains is the class the guard is right to decline. The
pre-fix run's 85 uncached fills are the same class of texture as the refused ones, taken through a flush record that did
cover them — the guard's answer is per range and per moment, which is why a run's refusal count is not a constant.

### 17.5 The texture data, before and after

For the virtual-pool materials the before/after bytes are section 16.6's table (pitch BC1/BC4/BC7 and kit BC1/BC5: all
zero → the storage's own first blocks, and decodes that are recognisably the pitch's line plan and the jersey). This
section's class adds the texel-level case to the suite (17.4) and six in-match bindings (17.3). Two of the 95 were empty
in the guest's storage at their resolution, and they stay zero — correctly, since there is nothing to copy.

### 17.6 Pitch and player brightness, measured on the material the shaders are actually given

The two shaders are the ones sections 15 and 16 identified: pitch `6b160f91c5a5e26a_b` (VS `0a139b0b8568dd4d_b`), jersey
torso `6956f7b5b6219c0a_b` (VS `5654c0be919633a5_b`). Both fragment programs end with the same three assignments: a
`lit` value scaled by `fp_c6._m0[300].w`, mixed with an emissive term by the vertex stage's light-map weight. So the
engine's exposure is a single number per draw, and the question "are the players darker than the pitch because of a
wrong computation" reduces to three measurable things: whether the two materials get the same exposure, whether the
material inputs are the game's, and whether one display transform is applied to every surface.

**The exposure is one value for both materials.** `DM_NVN_KEYDUMP` with both keys captured the pitch and the jersey in
the same window of the same run (`field14`); `c6[1].x` is the reciprocal of `c6[300].w` (section 15.3), and the two draws
agree to 0.5 %:

| Frame | Draw | `c6[1].x` | implied `c6[300].w` |
| --- | --- | --- | --- |
| F4 270 | pitch FS | 48.9344 | 0.020436 |
| F4 323 | jersey FS | 48.6922 | 0.020537 |

53 frames apart in one cutscene, and 24 % apart from the pair at F3 970 / F4 023 (175.486 / 138.116), which is the auto
exposure following the camera. The buffers are separate objects (different addresses) whose exposure field the engine
writes with the same value, so no material can be exposed differently by construction.

**The material inputs are the game's own.** The home kit's albedo (BC1 sRGB 1024×1024, read back from the GPU texture)
has a mean of sRGB (0.179, 0.128, 0.128) = linear Y 0.0175: it is a black shirt with dark red trim, which is what the
picture shows, with its gold number and the crest readable. The away kit's palette in its own draw is
`(0.576, 0.541, 0.243)` (linear Y 0.527, gold), and the picture shows a bright yellow shirt with `ORLANDO HEALTH`
lettering. So the two kits differ by ~30× in albedo, and that is the order of the difference on the screen.

**One display transform, measured.** A same-frame capture of the world colour target (RG11B10F) and of the final
composited target (RGBA8, ser 30) in `field14` (frame 8 867, in play at 07:17) gives, per surface class, the world
luminance and the display luminance at the very same pixels:

| Class | pixels | world Y (p50 / p90) | display linear Y (p50) | world / display |
| --- | --- | --- | --- | --- |
| away kit shirt (yellow) | 960 | 0.2487 / 1.1742 | 0.1239 | 2.01 |
| home kit shirt (black) | 520 | 0.0082 / 0.1612 | 0.0041 | 1.98 |
| home kit shorts | 160 | 0.0032 / 0.1225 | 0.0017 | 1.90 |
| grass, sunlit stripe | 29 900 | 0.3724 / 0.4105 | 0.1866 | 2.00 |
| grass, second stripe | 1 600 | 0.2174 / 0.2407 | 0.1081 | 2.01 |
| painted line | 9 | 0.2582 / 0.2762 | 0.1289 | 2.00 |

The ratio is 2.0 ± 0.1 across three and a half orders of magnitude of world luminance, so the tonemap, the grading LUT
and the sRGB encode treat the pitch, the yellow kit and the black kit identically — there is no per-material branch to
get wrong, and the earlier ROI tables of section 14 that suggested otherwise were mixing pixels of different frames.

**What that means for the two materials.** In the same frame, the brightest part of the yellow shirt (p90 1.174) is
2.9× the brightest sunlit grass (0.411): a gold kit under this sun is brighter than the pitch, and it is. The black
shirt's median is 45× below the sunlit grass, of which ~30× is its albedo (0.0175 against the pitch's palette
Y ≈ 0.10 scaled by its mask) and the rest is the shirt facing away from the sun while the pitch faces it. The players are
therefore **not** over-darkened by a missing term: they are a black kit, a gold kit and a white line, each landing where
its own albedo and orientation put it, under one exposure and one display transform. Nothing was changed to make them
brighter or darker.

### 17.7 The match in the real window

`field15` (no diagnostics), `DM_WINDOW=1`, 1920×1080, the same route, screenshots of the OS window (`shot`, the frame the
display presents) — not exports of a render target:

| Screen | Result |
| --- | --- |
| Kick Off hub | text, tiles, gradients and the `HD` badge correct (`fifa27-fix2-kickoff-hub.png`, `logs/field15-10.png`) |
| entrance / TIFO cutscene | the banner, the crowd with its red cards, the ad boards, the commentators' lower third with their portraits (`fifa27-fix2-entrance-tifo.png`, `logs/field15-11.png`) |
| player close-up | the yellow away shirt with `ORLANDO HEALTH`, the crest, sleeve trim and the fabric's own pattern; skin, hair and stubble (`fifa27-fix2-away-kit-closeup.png`, `logs/field15-12.png`) |
| in play | pitch with mowing stripes, both penalty areas, the centre circle, white lines; both kits; contact shadows; stands, ad boards, HUD, minimap; no black block and no Metal error (`fifa27-fix2-in-play.png`, `logs/field15-13.png`, `-14.png`) |
| pause / bench menu | goal net, dugout, camera operator, the crowd behind, `RESUME MATCH` (`logs/field14-13.png`) |
| half-time summary | the overlay over a blurred pitch, all its numbers and the two crests (`fifa27-fix2-halftime.png`, `logs/field14-12.png`) |
| continuous update | the clock runs (00:00 → 45:31 and on), players and ball move, mip levels change as the camera pulls out, no stale texture |

The same route's in-play frame before the fix is `fifa27-fix2-before-fix-in-play.png` (`logs/field16-13.png`,
24:46; `logs/field17-21.png` at 05:26 is a second one). The camera differs from the frame above, so this is a visual
comparison and not a pixel A/B: there the crowd in the stands reads as a near-black unlit mass with no seat colour, and
the same frame of section 16 (`fifa27-match-in-play.png`, whose build had the virtual-pool fix but not this
one) reads it the same way, while here the crowd shows its seat colours, red shirts and the cards held up. The pitch
keeps its mowing stripes and the kits, the HUD, the lines and the shadows look the same in all of them. The ad boards'
content also differs between the frames, but the game rotates its boards, so that is not evidence by itself. The crowd is
the class's visible contribution, and 17.3's 512×512 BC7 sRGB atlas — bound 8 times a frame and read 4 — is the shape of
it.

The half-time summary and the pause menu are the game's own stops in this route (it reached 45:31 of a simulated clock in
about 16 minutes of wall time); both draw correctly and `A` / `B` return to play.

### 17.8 Performance and regression

`field15` (the fix, no diagnostics) and `field16` (the same build with the single guard line of 17.4 put back) ran the
same route, and their steady in-match windows at the same frames are the like-for-like A/B:

| Window (p50 / p95) | `field15` with the fix | `field16` without it |
| --- | --- | --- |
| F14 700 | 33.33 / 34.12 ms, GPU 12.37 / 15.70, submit+present 1.96 | 33.28 / 34.45, GPU 11.80 / 15.47, 2.80 |
| F15 000 | 33.32 / 34.11, GPU 12.55 / 15.50, 1.95 | 33.33 / 34.51, 11.93 / 15.15, 2.81 |
| F16 200 | 33.30 / 34.94, GPU 12.48 / 16.24, 2.16 | 33.52 / 34.30, 11.99 / 15.25, 2.75 |
| footprint | 3 445 MiB | 3 265 MiB |

The frame time is the 33.3 ms the display asks for in both runs, with p95 within 1.7 ms of it; the GPU work is 12.5 ms
with the fix and 12.0 ms without it, inside the run-to-run spread of the same build over its own windows (11.7–12.6 ms).
The fix adds no per-frame work by construction — it fills a texture once, when the texture is created, and adds three
counters — so the A/B ties, and the table's differences (the pre-fix run's submit+present is 0.6–0.9 ms higher and its
resident footprint 180 MiB lower) are the sessions', not the change's: the pre-fix run uploads only the textures a flush
record covered (85 in `field17`'s pre-fix session), the post-fix one uploads all 106–125 and pays their storage once, at
creation.

Diagnostics cost much more than this section's change and must not be mixed into a comparison: `field14`, the same build
and the same match with `TEXFILL` and `KEYDUMP` on, sat at p50 34.0–34.6 / p95 43–46 ms with GPU 33.4–34.3 ms in the same
frames. Every earlier "frame time" figure of this document that was taken with those switches on is one of those, not a
rendering cost.

Regression (re-run on the committed tree, `GAME=0100C49025D3E000`): `check_t_readback` **24 cases, 0 failed** (the 21
of section 16 plus 3); `t_nvn` 124 / 0; `t_texture_views` exits 0 (its single 2D-array → 2D view case),
`t_view_levels` 34 / 0, `t_view_swizzle` 203 / 0, `t_mip_extent` 303 / 0, `t_upgrade_alias` 10 / 0, `t_deswz_gpu` 15 / 15,
and the shader-chain check (`test_nsp_chain.py`) 12 / 0 against the unchanged `dmsh_chain.h`. No other game was launched; the
guard change only *permits* a fill that was refused, only for a pool the guest CPU can write and did write, and the
sparse/page-table pool model that Monster Hunter Rise and the other page-table games depend on is untouched
(`nvn_sparse_pool` gating unchanged, `t_readback`'s sparse cases pass).

### 17.9 Open issues

1. `d04bd72a626b3a62_bf.metallib` was missing from this profile's rebuilt library. The reason given here (no
   `bf_want.tsv`) was wrong, and 18.9.1 replaces it: the build plans that variant itself, and it fails to compile
   because the readable-tile rewrite drops a dual-output shader's second entry point. No run of this section
   needed it.
2. The 66 68×80 BC3 masks of 17.3 are still unidentified by name. They are filled now, and the picture shows no
   difference that can be attributed to them alone (the pitch and the kits come from the virtual pool), so identifying
   them is only worth doing if a mask-shaped artefact appears.
3. The remaining `COMPRESSIBLE` refusals are correct but the guard's message reads like a defect; a wording change would
   make a future log clearer.
4. The half-time and pause stops are the game's design, so a long run needs `A` / `B`; a scripted acceptance sweep
   should drive them.
5. The A/B of 17.8 is one build pair on one machine; it says the fix is free, not that the game's frame time is optimal.
6. The census of 17.3 covers 40 in-play frames of one run and finds 6 of that run's 40 refusals bound and read. A dump over
   a whole half, on a pre-fix build, would say how many the match samples in total; the count of refusals itself varies
   per run (95 in `field9`, 40 in `field17`), so the figure to carry is the census window, not a constant.

### 17.10 Outcome classification

* **Proven, dynamic:** the four shaders' capture bytes verify against their keys, and the rebuilt library's 439 keys
  equal the map's; the deep match passes F14 784 and F19 950 with no missing key and no skipped program; the refused
  textures are all `CPU_UNCACHED | GPU_CACHED` pools, 6 of a run's 40 are bound and read by the match's draws over 40
  in-play frames (a 512×512 BC7 sRGB atlas at fragment slot 131 and five 512×128 BC3 sRGB boards at slot 148; 1 was
  already proven in a 20-frame window); the new guard fills 106–125 of them per session and refuses only `COMPRESSIBLE`
  ones; the pitch and the jersey get the same exposure value to 0.5 % in one frame; the world-to-display ratio is
  2.0 ± 0.1 for six surface classes including
  both kits; the window shows the pitch, both kits, the crowd and the HUD correctly, and two pre-fix frames of that route
  and section 16's read the crowd as a near-black mass (17.7 — a visual comparison at other cameras, not a pixel A/B);
  frame time holds 33.3 ms with the fix and without it.
* **Static inference:** that the black shirt's remaining darkness is its albedo and its orientation (measured albedo and
  orientation, not an independent light probe); that the 66 masks belong to crowd or badge materials (shape only).
* **Not claimed:** that the whole title is colour-accepted on a device; that the missing `_bf` variant is harmless beyond
  the runs of this section; that the frame time is optimal.
* **Colour problem solved?** The material and the visibility problems are: the pitch, the kits, the crowd and the UI
  sample the data the game wrote, through one exposure and one display transform, and the brightness difference between
  the pitch and the players is the difference of their own materials. **Match picture accepted?** Yes for the Mac window
  at 1920×1080 through a first half, a half-time stop, a pause menu and the second half's opening.
* **FC 27 playable?** On the Mac host, yes: Kick Off to the second half at a locked 30 fps with no missing shader, no
  skipped draw and no black material. On a device it is not verified by this section.
* **Committed:** the guard, the `KEYDUMP` list, the `t_readback` cases, the four map rows, `docs/research/fc27-bringup.md`
  (the rule and its diagnostics) and this section with its window images.

## 18. The packaged App's black match: 55 programs the shipped map lacked (2026-10-29)

Baseline `4eb2b93`, `research/fifa27`. One profile input changes and nothing else: `shader_map.tsv` goes from this
document's 439 keys to 494 (3 compute, 28 pixel, 24 vertex added), and the library is rebuilt from a dump of all
494. No shader source, no fill guard, no profile key, no host code. The App this tree packages draws its menus, its
team sheets and its whole pre-match presentation correctly and its match black; the match's programs are the ones
the map did not hold, so every draw of them was skipped. With the 55 keys in, the same route, the same save and the
same payload draw the pitch, both kits, the stadium and the crowd.

### 18.1 The App's three reports, and what each turned out to be

| Report | Symptom | Cause | Fixed in |
| --- | --- | --- | --- |
| first launch | the App quit after 0.7 s | the game loads its `render` NRO with `nn::ro::LoadModule`; the packaging had dropped `nro.tsv` and the module, so no image matched the game's SHA-256, the export resolved to 0 and the game jumped through it | `4eb2b93` |
| second launch | the launcher refused every container ("game not found") | the same `render` was listed in `prepared_builds.tsv` and in `render.fixups.tsv`; the launcher compares those Build IDs against the container's ExeFS, where a module the game loads from its own data cannot appear | `4eb2b93` |
| third launch | menus, team sheets, presentation and HUD correct, the match black | the match's programs are not in the packaged map | this section |

The third report's screen is `fifa27-bm-black-before.png`: in play at 02:59, BOU 0-0 BHA, the window at
2326×1440. The scoreboard, the two crests, the player names, the stamina bars, the `MINUTE 11` tag and the minimap
are drawn; the 3D image behind them is black. The host's own overlay reads 29.88 fps, 12.78 ms of GPU time and a
33.47 ms frame interval, so the frame is composed and presented — what is missing is not the backbuffer but the
draws that would fill it. The two that came first were packaging defects of the same module; this one is a
completeness defect of the map, and the map is a run-time capture (18.5).

### 18.2 The runs

`user1`, `kd1` and `app1` each ran the App's own payload (`Contents/MacOS/dmhost`, `Contents/Resources/program`,
the App's map and library — `user1` the App packed before this section, the other two the App packed with it);
`bm1` ran the same rewritten modules against `msl-bm2/b-32e83615bd74` and the rebuilt map. Every run used the
user's save and walked the same route (Kick Off → Premier League, Bournemouth against Brighton,
`DM_WINDOW=1 DM_PRESENT_LINK=0`, 1920×1080), which is the fixture of the user's screenshot. Logs, dumps and
screenshots stay under `/path/to/private-fc27-research/`.

| Run | Map | Library | Diagnostics | Reached | Result |
| --- | --- | --- | --- | --- | --- |
| `user1` | the App's, 439 | the App's, 439 | `SHDUMP` | F25 585 (859 s) | the match is black for the whole session; **83** `is not in the shader map` lines, **55** distinct keys |
| `kd1` | the App's, 494 | the App's, 494 | `KEYDUMP` (pitch + jersey) | F6 900 | in play; both materials' uniforms at F3 804 and F3 831 |
| `bm1` | 494 | `msl-bm2`, 494 | `SHDUMP` | F13 500 | in play; 0 missing |
| `app1` | the App's, 494 | the App's, 494 | none | F13 200 | the packaged App in play; 0 missing |

### 18.3 The 55 keys

`user1` was run with `DM_NVN_SHDUMP`, so every program the map lacked saved its control section, its code area and
its stage — 55 keys, 167 files:

| Stage | In the 494-key map | Added here | Largest new MSL | Smallest new MSL |
| --- | --- | --- | --- | --- |
| compute | 73 | 3 | 36 022 B | 2 895 B |
| pixel | 245 | 28 | 302 823 B | 677 B |
| vertex | 176 | 24 | 312 728 B | 29 354 B |

These are not variations of a few programs: 49 of the 55 translate to more than 30 KB of Metal source and the
largest to 302 KB, where the four shaders of 17.2 came to 6–11 KB each. One of the pixel stages is 677 bytes and
writes zero to colour 0. Each capture was verified from its own bytes before packing, by the same four checks as
17.2 (`0x98761234` control magic, the code length at `+0x704` equal to the `.code` file, the stage from the code
header, `sha256(control[:0x880] + code)[:8]` equal to the key), and `shdump_pack.py` re-checks all four itself.

Nothing is asked for them before the match: the first `is not in the shader map` line comes between frames 5 512
and 5 530 (185.9–186.4 s), which is where the presentation ends and the whistle goes. The 5 400 frames before it
— menus, the two team sheets, the league ident, the handshake, the walk-out, the cutscene around the goal — ask for
nothing the map lacks, which is why the menus looked right in the same session that the match did not. Each key is
requested once to six times (83 lines over 55 keys; `9a58c5b802a71656` six times).

### 18.4 Why section 17 did not see them

Section 17's route was a different fixture — offline Kick Off, Atlanta United against Orlando City — and its runs
were complete *for that route*: from `field11` to `field16` the log held no missing key through F27 345. This
fixture is a Premier League match in a Premier League stadium, and it builds programs the 439 never held.

The difference is in which programs are used, not in a kind of stage that was never captured. The pitch's fragment
stage is `6b160f91c5a5e26a_b` in both routes, but here it is paired with vertex stage `5193e4875978bf21_b` where
section 17 recorded `0a139b0b8568dd4d_b`; both vertex stages were already in the 439. A profile whose shaders come
only from run-time captures is therefore complete exactly up to the content that was played, and section 17's
"no missing key" was a statement about its own half of one fixture.

### 18.5 The map and the pack

The 439 keys and the 55 new ones were packed as one dump of 494 (`shdump_pack.py`), which writes three packages —
`cs_dump.bin` 73 records, `ps_dump.bin` 245, `vs_dump.bin` 176 — and the map rows that point at them. Re-running
the packer on the same dump reproduces both byte-for-byte: the three packages `cmp` identical and the map `diff`
identical, so the map's row order *is* the pack's record order. Adding 55 keys therefore renumbers the rows that
sort after them (461 added and 406 removed lines, not 55), and a pack built before this section no longer pairs
with the committed map; anyone holding one must repack from a dump of all 494 keys.

`dmsh_build.py` built the library from that pack: `shaders 494: ok 494`, `shader keys not in the shader map 0`,
library stamp `inputs 0897d92d6220`. Re-running the build today against the same cache prints
`shader cache: hit 494, rebuilt 0`, which is the check that `msl-bm2/b-32e83615bd74` on disk is exactly what this
map and pack produce — the same 494 keys, 494 `_b.metallib`, no stub.

### 18.6 The picture

`app1` is the shipped App — its own payload, its own map and library, no diagnostics — driven to kick-off and into
play. `bm1` is the same route against the standalone library. Both logs hold **no** `is not in the shader map` and
**no** `program has no vertex shader` line; the only `[RED]` lines left are the ones `user1` also has, a
`CopyBufferToBuffer` the game issues with `src=0` and sampler ID 4096, both present in every run of this document.

| Screen | Result |
| --- | --- |
| team sheets, ident, handshake | the crowd pan, the camera beside the goal, the two team sheets over a live blurred pitch, and the handshake cutscene with both squads, the dugouts and the ad boards (`logs/app1-09.png`, `-20.png`, `-22.png`, `logs/bm1-21.png`, `-22.png`) |
| in play | pitch with mowing stripes and the stadium's shadow pattern, both penalty areas, the centre circle and lines, both kits, contact shadows, the stands, the crowd, the ad boards, the HUD and minimap (`fifa27-bm-match-after.jpg`, `logs/app1-25.png` at 03:32; `logs/app1-24.png` at 01:58 wide) |
| player close-up | the away shirt with its chevron pattern, `AMERICAN EXPRESS`, the crest, the sleeve badge, skin, hair and stubble, the goal net and the crowd behind (`fifa27-bm-closeup-after.jpg`, `logs/bm1-23.png`) |

The before picture of the same fixture is `user1`'s (`logs/user1-22.png` — HUD and minimap only) and the user's own
window (`fifa27-bm-black-before.png`). Between them and the frames above, one input changed: the map,
from 439 keys to 494.

### 18.7 The materials are section 17's, unchanged

`kd1` ran with `DM_NVN_KEYDUMP` on the two materials of 17.6 in the new library. Both still build and draw — the
pitch at F3 804, 3 805 and 3 806 (`[kd]` and `[pass] d` lines with the same program), the jersey at F3 831 — and
their exposure is the quantity section 17 measured, in its range: `c6[1].x` = 175.49 for the pitch and 206.252 for
the jersey, against 175.486 at section 17's F3 970 and 48.93 / 48.69 for the pitch and the jersey at its F4 270 /
F4 323. Nothing in this section touches an exposure, a tonemap, the LUT, a kit palette or a grass palette, and the
world-to-display ratio of 17.6 was measured on the same two shaders, so the brightness of what is now visible is
17.6's result rather than a new one.

### 18.8 Performance

| Run | Frame time p50 / p95 | GPU p50 / p95 | Draws a frame |
| --- | --- | --- | --- |
| `user1`, match skipped | 33.34 / 33.90 ms | 12.39 / 15.30 ms | 1 303 draws |
| `bm1`, match drawn | 33.41 / 35.21 | 12.65 / 16.94 | 549 |
| `app1`, match drawn | 33.34 / 34.22 | 10.52 / 17.71 | 579 |

All three hold the 33.3 ms the display asks for. They are not a like-for-like A/B — the black session is 14
minutes of a different game state and translates more than twice the draws of the other two, which is why its GPU
figure sits between them — so this section claims no frame-time difference, only that the cost of the 55 programs
disappears into the session-to-session spread of this title. Nothing was added to the per-frame path: the map is a
lookup.

### 18.9 Open issues

1. **The readable-tile library is 31 of 33, not 33 of 33** — this replaces 17.9's item 1, whose explanation was
   wrong. `bf_want.tsv` is not needed: the build plans 33 readable-tile (`_bf`) variants of this profile by
   itself. Two of them do not compile, and the reason is visible in the generated source: the readable-tile
   rewrite does not carry a shader's second (integer-output) entry point, so `ca79f10492b64b8c_bf.metal` and
   `d04bd72a626b3a62_bf.metal` name `fb0`–`fb7`, `spv_o_m_76`, `spv_o_m_78` and `main0_out_dual`'s members before
   they exist (20 errors, `logs/build-bm2.log`). No run of this document took the readable-tile path (0
   `readable-tile` lines in `user1`, `bm1`, `app1`), so nothing needs them today; the App on hand carries all 33
   from the library it was packed with. **Corrected in 19.6:** the cold-cache build of section 19, this same
   profile on this same cache disk, made all 33 — the run that made 31 is the exception, not the rule.
2. **The map is complete for what was played.** A competition, stadium or kit nobody played can ask for programs
   nobody captured; the fix is a capture run with `DM_NVN_SHDUMP` on over the modes meant to be shipped, not a
   larger guess. `docs/research/fc27-bringup.md` now says this where it says how to validate coverage.
3. The 55 keys were captured in one session and used in `bm1`/`app1`; a second fixture has not been checked, so
   how much of the title's program set 494 covers is unknown — 55 new keys in one new fixture is the only rate
   measured.
4. `app1` is a Mac run. The iOS side is not verified by this section.

### 18.10 Outcome classification

* **Proven, dynamic:** the shipped App's menus and presentation draw and its match does not; the session asks for
  55 programs the 439-key map lacks (83 lines, first between F5 512 and F5 530, none in the 5 400 frames before);
  with the 494-key map and its library the same route draws the pitch, both kits, the stadium and the crowd with
  0 missing keys and 0 skipped programs, in the standalone library and in the repacked App; the pack and map are
  reproducible byte-for-byte from the 494-key dump, and a rebuild of the library is 494 hits and 0 rebuilds; both
  materials' exposure is the quantity section 17 measured, in its range; frame time holds 33.3 ms in all three
  sessions.
* **Static inference:** that the 55 belong to the world passes and not the UI (from the picture plus the fact that
  adding exactly them, with nothing else changed, brings the world back); that the fixture is why section 17's
  route did not ask for them (two routes' pitch programs pair the same fragment stage with different vertex
  stages, both already mapped).
* **Not claimed:** that 494 keys cover the title (18.9.2, 18.9.3); that the App behaves on a device; that the
  readable-tile gap is harmless beyond the runs of this document.
* **Match picture accepted?** Yes for the packaged Mac App at 1920×1080: the user's fixture from the team sheets
  through the presentation to in play, with the picture sections 16 and 17 accepted.
* **FC 27 playable?** On the Mac host from the App, yes for this fixture; the coverage caveat of 18.9.2 stands.
* **Committed:** `shader_map.tsv` (494 keys), this section and its three images; the packaging and launcher fixes
  of the first two reports are `4eb2b93`.

## 19. The first iOS build: an unsigned IPA, and the 12 GB reservation it needs (2026-10-29)

Baseline `a49c681` on `research/fifa27`, pushed before any of this section's work. This section adds no host code
and no shader source: it builds the iPhone/iPad side out of the artifacts section 18 verified (the 494-key map,
its rewritten modules) and records what the result is, what it needs from the device, and what remains unproven.

### 19.1 Historical baseline

This stage used research revision `a49c681` after section 18. Old remote-transport
administration details are omitted from the public record; they are not part of the
standalone build or proof of binary/permission provenance.

### 19.2 The iOS shader libraries

One `dmsh_build.py` run, both targets, the 494-key pack of 18.5 and the same per-shader cache:

```text
IOSOUT=$R/ios/msl DM_GAME=0100C49025D3E000 DM_GAMES_DIR=$R/profile-bm DM_GAMES_FIRST=1 \
  DMSH_CAS=$R/msl-bm/cas dmsh_build.py $R/packs-bm $R/msl-bm2
```

The Mac half was cache hits; the iPhone half went through `dm/ios/tools/ios_metal.py`
(`xcrun -sdk iphoneos metal -c -mios-version-min=18.0 -fmetal-math-mode=relaxed -fpreserve-invariance`, then
`metallib`), which is the chain's single iOS compile standard, and finished with 0 compiler errors.

| Check | Result |
| --- | --- |
| keys | 494 `_b.metallib` + 494 `_b.json`; the map's 494 keys and the library's are the same set, no extra, no duplicate |
| stages | `ps` 245, `vs` 176, `cs` 73 — exactly the map's own stage split (18.3) |
| iOS, not Mac | every reflection records `chain_metal` = the `iphoneos` command; the same key's metallib differs in size from the Mac library's (12 555 vs 12 859 B for `005e041ea107f03e_b`) |
| loadable | a sampled compute metallib names `main0` as a defined symbol (`metal-nm`), and its reflection says `stage cs`, `msl_entry_kind kernel` |
| variants | 33 readable-tile (`_bf`) and 80 `_bv` metallibs beside the 494 — the variant sets section 18's library also holds |
| stamp | `game 0100C49025D3E000`, `inputs 0897d92d6220`, the digest the profile's `c1_full.tsv` names, so `build_ipa.sh` accepts it |

### 19.3 The build

`dm/ios/tools/build_ipa.sh` unchanged, driven from `$R/ios/build-ipa.sh` (kept beside the work, not in the
repository) with: `GAME=0100C49025D3E000`, `PATCHED` = the three rewritten modules and their tables used by the
verified Mac App, `MSL_IOS=$R/ios/msl`, `DM_RESOURCE_BACKEND=nsp`, `DM_IOS_BUILD_DIR=$R/ios/proj`,
`DM_DISPLAY_NAME="EA SPORTS FC 27"`, `DM_APP_VERSION=1.0.0`, `DM_BUNDLE_ID=org.nxnative.0100c49025d3e000`.

External resources, not directory mode: the only thing a directory-mode IPA would add is the RomFS, and this
game's is 20 GB of Frostbite `.toc`/`.cas` data. `build_ipa.sh` then packs no containers or RomFS payload (rewritten game code and derived shaders are still included) and the launcher
reads the player's own containers (section 19.5).

Two profile inputs had to be added for the packaging path — the research profile was written for host bring-up,
not for making an App, and `build_ipa.sh` stops without them:

* `zip_store .metallib` — the packer asks every profile for the suffixes it should store rather than deflate.
* `pso_manifest.tsv` — the warm-up seed list, which must exist even when empty. It is empty here: the Mac runs
  recorded 1 286 pipeline states in `pso_user.tsv` beside the save, and prewarming that many on a phone is a
  first-session cost nothing has measured yet; the App that section 18 accepted was also packed with an empty
  seed, so this keeps the iOS build equal to the verified one.

`gen_embed.py` put the game's three modules into the executable (`main` 228 392 960 B, `sdk` 13 892 480 B and the
`render` NRO 1 066 764 B the game loads with `nn::ro`, as one entry of `__DATA,__dm_nro_tab`), and
`xcodebuild -destination 'generic/platform=iOS'` Release, unsigned, finished with `** BUILD SUCCEEDED **`, 0
`error:` lines, in 53 s. `pack_ipa.py` wrote `Payload/DmIOS.app` plus `msl/` in 9 s.

### 19.4 The artifact

| | |
| --- | --- |
| path | `/path/to/private-fc27-research/ios/FC27-iOS-Test.ipa` |
| size | 139 805 500 B (133.3 MiB); 1 134 entries, 300 204 994 B uncompressed |
| SHA-256 | `b3dafcf8b5ef7b6bb0408d1688ef7ca4f74c97bfcd34e47858d1e851acfd2c8e` |
| bundle | `org.nxnative.0100c49025d3e000`, display name `EA SPORTS FC 27`, version 1.0.0 (1.0.0) |
| platform | arm64 only, `LC_BUILD_VERSION` platform IOS, minos 26.0, `UIDeviceFamily` 1,2 (iPhone and iPad) |
| mode | `DMResourceBackend = nsp` — no RomFS and no containers in the bundle |
| signature | **none**: no `_CodeSignature`, no `embedded.mobileprovision`, unsigned build |

Checks on the extracted bundle: `unzip -t` reports no error; the executable is `Mach-O 64-bit executable arm64`
with 64 sections; its only dynamic dependencies are system frameworks and `/usr/lib/swift` (no bundled dylib or
framework is referenced, and none is shipped); `dm/` holds `shader_map.tsv` (494 rows), `c1_full.tsv`,
`cb_extent.tsv`, `pso_manifest.tsv`, `nro.tsv` and the four rewriter tables of each module, and
`msl/b-32e83615bd74/` holds the 607 metallibs and 494 reflections of 19.2. There is no RomFS, no NSP, no key
file and no provisioning profile in the archive.

### 19.5 What the device needs

**Game files.** With `DMResourceBackend = nsp` the launcher scans the App's `Documents` (and its subfolders) for
the containers and the keys and reads them where they are:

* base `EA SPORTS FC 27 v1.0.0[0100C49025D3E000][v0][APP].nsp` (12.7 GB as the user holds it, `.nsz` must be
  unpacked first — the reader takes `.nsp`/`.xci`, not `.nsz`);
* update `v-ea_sports_fc_27_v327680.nsp` (20.3 GB); the prepared build is the update's `main`
  (`9636bcd6…`), so the base alone is not enough;
* `prod.keys` beside them;
* optionally the commentary DLC `0100C49025D3F002` — it is read the same way, nothing is bundled.

Import is a file copy through the Files app (`UIFileSharingEnabled`), and this build reads the containers in
place, so the files are not duplicated inside the App's sandbox.

**An entitlement.** The profile reserves `mem_reserve 0x300000000` (12 GB of guest address space: 1 GB, then a
6 GB alias region, 256 MB of stack and the rest heap), and the host `mmap`s that block `PROT_NONE` at boot
(`hle_svc.c` `mem_init`). Without `com.apple.developer.kernel.extended-virtual-addressing` an iOS process has
about 7.4 GB of address space in all, so that `mmap` fails and the host stops at `FATAL reserve guest AS` the
moment the game starts — the launcher and its import screen still work, the game does not. This is not a
profile setting that can be trimmed for the phone: the 6 GB alias region is the Frostbite engine's own
reservation (it failed at 2 GB with 2.90 GB in use, `fifa27-two-areas-and-bringup.md`), and heap + alias + stack + 1 GB is
about 10.7 GB however the block is cut. `build_ipa.sh` therefore wrote
`FC27-iOS-Test.ipa.entitlements` beside the IPA (increased-memory-limit + extended-virtual-addressing): the
signing tool must sign with it, which a free personal team cannot do and a paid team can only do with a
provisioning profile Apple has granted that capability to.

**Physical memory.** `app_pool 0xCD500000` (3.2 GB) is what the game hands its own allocator, beside a 243 MB
image, which is at the edge of what an 8 GB phone gives an app even with the increased-memory limit.

### 19.6 Mac regression, and the readable-tile correction

Nothing in this section changed host code, a tool or a shader source; the only repository changes are the two
profile inputs of 19.3. To show the Mac side is unaffected, the Mac App was packed again from the current
profile (`scripts/build_mac_app.py`, the same host, modules, library and settings as the App of 18.6, output
`$R/ios/mac-regress`): 3 prepared modules, 1 101 Shader files, and its `shader_map.tsv` is byte-identical to the
shipped App's. All 494 `_b.metallib` are byte-identical too; only the reflections' key order and a recompile of
the 33 `_bf` variants differ. The 494-shader resource chain is intact.

That recompile also settles 18.9.1: this cold-cache build — the same profile, pack and cache disk — produced all
33 readable-tile variants, where a Mac-only rebuild the same evening logged 2 failing (`ca79f10492b64b8c`
among them, undeclared `fb0`–`fb7` and `main0_out_dual` members, 20 errors). Both the shipped Mac App and this
IPA carry 33. So the readable-tile rewrite's failure is what one run did, not what the profile does; 18.9.1's
"a fresh build of this profile will carry 31" is wrong. Nothing shipped here asks for a `_bf` variant anyway (0
`readable-tile` lines in every run of this document).

### 19.7 Tests run

| Test | Result |
| --- | --- |
| `python3 -m unittest discover -s dm/ios/tests` | 4 tests, OK |
| `python3 -m unittest discover -s dm/resource/tests -p 'test_*build*.py'` | 49 tests, OK |
| map ↔ library key sets, stage split, reflection convention | 19.2, all equal |
| `unzip -t`, Mach-O arch, `LC_BUILD_VERSION`, `otool -L`, Info.plist | 19.4, all as expected |
| Mac App repacked from the current profile | 19.6, map and metallibs byte-identical |

`xcodebuild` itself is the iOS compile test: every host source, `front_ios.m`, `main.m`, `DmGamepad.m` and the
Swift launcher compiled for `iphoneos` arm64 in this run, and `gen_build.py` took the source list from
`dm/host/Makefile`, so nothing was hand-picked for this game.

### 19.8 Open issues

1. **Nothing ran on a device.** The IPA is built, structurally checked and unsigned; it was not signed, not
   installed and not started on the user's iPad or iPhone (project rule: builds are unsigned and the user
   sideloads them). No frame rate, no launch time, no memory figure and no Metal runtime error is claimed for
   iOS — the Mac's 30 fps says nothing about a phone.
2. **The entitlement of 19.5 blocks the game on any normally signed build.** Until it is signed with
   `extended-virtual-addressing`, the App opens its launcher and stops at `FATAL reserve guest AS`.
3. **The 494-key map is section 18's capture.** The same caveat applies on the phone: a competition, stadium or
   kit nobody played may ask for programs nobody captured. The first iOS session should run with
   `DM_NVN_SHDUMP` in `Documents/env.txt` so a black scene can be diagnosed the way 18.2 did.
4. **Import cost.** 33 GB of containers have to be copied into `Documents`; nothing measured how long iOS takes
   to scan and mount them.

### 19.9 Outcome classification

* **Proven, static:** the iOS library is a full build of this profile's 494 keys for the iPhone target (key sets,
  stage split, reflections, stamp), and the IPA is a well-formed arm64 iOS bundle that carries that library, the
  map, the three rewritten modules and no bundled containers/RomFS, console key or signature.
* **Proven, dynamic (Mac only):** the Mac App repacked from the current profile is the App section 18 accepted —
  same map bytes, same 494 metallibs.
* **Not claimed:** that the IPA installs, launches or plays; that the entitlement can be signed by the user's
  account; that 494 keys cover the title (18.9.2); any iOS performance figure.
* **IPA delivered?** Yes, as an unsigned artifact for sideloading with re-signing — build and structure only.
* **Committed:** the two profile inputs (`zip_store`, `pso_manifest.tsv`) and this section.

## 20. The 12 GB reservation, measured and cut to 5.03 GiB (2026-10-30)

Section 19 ended on a sentence that was an estimate: the App needs the extended-virtual-addressing
entitlement "because the 6 GB alias region is the Frostbite engine's own reservation". This section measures
that instead of estimating it. It adds the instrumentation upstream has for exactly this question, sizes the
block from the game's own reservations, cuts the SDK's node area on this build, and regresses a full match on
the Mac — first half, half-time and second half — on a block of 5.03 GiB.

### 20.1 What this branch lacked, and what was taken from upstream

Read first: `github.com/seedds/nxnative` commits `d8b8d642`, `75f63ab0`, `f4a24b879`, `4f151c76`, `db9edadb`
and `docs/reference/memory.md`. Nothing was merged and nothing was cherry-picked: the pieces below were written
for this branch in its own terms (a live table of regions, not upstream's patch of its own host).

| Question | Upstream | This branch before | Now |
| --- | --- | --- | --- |
| boot with a Switch-sized alias region | `DM_ALIAS_SIZE` | — | `hle_svc.c` `mem_init` takes `DM_ALIAS_SIZE` (whole pages, at least 256 MB) and grows the block by the difference; the rest of the partition is unchanged |
| who reserves what in the alias region | gates at `VammManager::AllocateAddressRegion` (entry, and the one store through the out pointer) and `FreeAddressRegion`, a host table, `DM_REGIONS=<file>` every 2 s | — | the same three gates, found by the module's own MOD0 symbols (`patch_nso.py` "Address regions", `nso_syms.defined`, `nso_code.out_store`); the host table keeps the caller's return address, the SDK offset it came through, the mapped bytes and the part ever opened |
| a game that hands `StandardAllocator` a Switch-sized size | gates on both `Initialize` overloads, the size lowered to what the alias region has room for; profile key `stdalloc_cap` | — | the same gates and key; the automatic 32 MB search is not ported (a game that needs the key gets a row) |
| the SDK's node area | `0x3fe00000` cut to `0x3e00000` in `sdk_patches.py` | documented for other builds, none for SDK 22.2.0 | `CUTS` row for `fed212d6…`: `sdk+0x14df00`, `sdk+0x14df6c` |
| per-window residency | `DM_ALIAS_WINDOWS` | present | present, unchanged |
| a provisional profile's region check | `profile_guess.py` boots 15 s and checks regions against the alias region | — | not ported: this audit drove the runs by hand (20.5) |

The host changes are five small ones: the observation-gate registry (`dm.h`: ids 22–25, a parameter and
writable registers in the callback), its dispatch (`hle.c`), and in `hle_svc.c` the alias override, the region
table and the `StandardAllocator` cap. Everything else is the profile, the rewriter and one `sdk_patches.py`
row.

### 20.2 What the game asks for when it has room

`DM_ALIAS_SIZE=0x1000000000` (64 GiB), `DM_REGIONS` on, a played match — before any cut to the node area, so
the SDK still takes its ~1 GB:

| | |
| --- | --- |
| address regions live at the end of the run | 638 |
| address space they reserve | 3.03 GiB |
| of it mapped (4 KB page bitmap) | 1.28 GiB |
| highest region end | 5.23 GiB |

The regions are not few and not large: in this run the three 512 MB requests (1.5 GiB between them) map 0,
20 and 250 MB, and in the final table of 20.6, 336 of the 661 regions are 64 KB or less. That table is the
same distribution with the node area cut:

| size class | regions | reserved | mapped |
| --- | --- | --- | --- |
| 64 KB | 336 | 18.5 MB | 17.8 MB |
| 64 KB – 1 MB | 169 | 34.3 MB | 32.4 MB |
| 1 – 16 MB | 137 | 792.8 MB | 706.2 MB |
| 16 – 64 MB | 13 | 448.5 MB | 184.5 MB |
| 64 MB and more | 6 | 1809.0 MB | 385.5 MB |
| **all** | **661** | **3103 MB (3.03 GiB)** | **1327 MB (1.30 GiB)** |

So the engine reserves 2.3 times what it maps, and the waste is concentrated: the six regions of 64 MB and
more hold 1.77 GiB of the reservation and map 0.38 GiB of it.

### 20.3 Which layer asks

* **One layer takes the alias region: the SDK's `VammManager`.** 644 of the 661 regions — 2.98 GiB of the
  3.03 GiB — return to a single address, `main+0x17f9884`, which is Frostbite's virtual-address allocator
  (its `VirtualAlloc_Posix`): the engine keeps its own reservoirs and asks the SDK for the address space
  under them. The other callers are noise: 48 MB at `main+0x1cefc84`, 2.5 MB in 10 regions at
  `main+0x1809bf0`, and four regions of a few MB elsewhere.
* **`StandardAllocator`'s virtual-address path never runs.** The gate on both `Initialize` overloads was in
  place in every run of this section and never printed `[mem] StandardAllocator::Initialize` — this engine
  does not hand its arena to the SDK allocator, so `stdalloc_cap` stays 0 in the profile.
* **NVN's 512 MB virtual pool is not a second layer.** `[nvn] MemoryPool 0x7016fd4a00: a virtual pool of
  0x20000000 bytes` takes its buffer address `0x7032800000` — inside the alias region — because the game
  hands NVN memory it obtained from `VammManager`. The pool is a client of the 3.03 GiB, not a neighbour.
* **The heap is elsewhere.** `SetHeapSize` asks 1.1875 GB, which the host opens in the heap region at the
  end of the block (`[mem] heap 1.19 GB`). That is the game's own memory, not address space.

### 20.4 The partition, part by part

| part | size | what it holds | measured need | can it shrink |
| --- | --- | --- | --- | --- |
| prefix | 16 MB | dead address space before the alias region | nothing measurable (this work's own margin: the host's default is 256 MB) | to 0 if wanted; 0.3% of the block |
| alias | 3.75 GiB | VammManager's regions, the 62 MB node area, and the holes between regions | 3.5 GiB boots and plays; 3.375 GiB is fatal (20.5) | not below 3.5 GiB; 3.75 keeps 0.25 GiB over the high-water |
| stack | 64 MiB | 43 guest thread stacks | 5 MiB | to 16–32 MB; not worth the risk |
| heap | 1.203 GiB | the guest application memory pool | `SetHeapSize` 1.1875 GB | no — the request is the request |
| **block** | **5.03 GiB** | | | |

The 62 MB node area is what the cut buys: without it the SDK takes 1 GB at the start of the alias region
before it hands anything out, i.e. 0.94 GiB of the block for bookkeeping. It is not free even after the cut —
the smallest node area this build accepts has not been probed; 62 MB is the value upstream uses for every
other build.

### 20.5 Shrinking it: six runs

Each run is the same route (`Kick Off`, offline, a Premier League match, player side left alone), the same
save and the same rewritten modules; only `DM_ALIAS_SIZE` (and so the block) changes.

| alias region | block | what happened |
| --- | --- | --- |
| 64 GiB | 65.3 GiB | boots, plays to a match; 638 regions, 3.03 GiB, top 5.23 GiB (20.2) |
| 4.50 GiB | 5.78 GiB | boots, plays to 328 s; 584 regions, top 4.50 GiB |
| **3.75 GiB** | **5.03 GiB** | **boots, a full match incl. half-time and the second half (20.6); 661 regions, top 3.750 GiB** |
| 3.50 GiB | 4.78 GiB | boots, plays to 212 s (stopped there); 625 regions, and the top region ends at exactly 3.500 GiB — the engine fills the tail it is given |
| 3.375 GiB | 4.66 GiB | **fatal 4.06 s after boot** (frame 83): after the three 512 MB regions and 3.25 GB of mappings, a reservation fails and the engine writes through the null it got — `CRASH sig=11 addr=0 pc=main+0x17f98c4` |
| 3.20 GiB | 4.48 GiB | the same fatal write, earlier |

Two things follow. The floor is a **reservation** the engine makes at boot, not a mapping it grows into: at
3.375 GiB everything asked for until then had succeeded (3.25 GB mapped), and the request that failed is one
that no longer fitted in the ~0.12 GiB left. And the engine's own allocator packs small regions right
up to whatever ceiling it is given (`top` equals the alias size at 3.50 and at 3.75), so a ceiling that is
merely "enough" leaves the tail full of reservations and no room for the mapping high-water, which reaches
3.50 GB on its own. 3.75 GiB is the smallest size this work measured with room for both.

### 20.6 The profile, and a full match on it

```text
mem_reserve	0x142000000      # 5.03 GiB
mem_prefix	0x1000000        # 16 MB
mem_alias	0xF0000000       # 3.75 GiB
mem_stack	0x4000000        # 64 MiB
```

plus the `sdk_patches.py` node-area cut, which the rewritten `sdk` must carry (the Mac run of 20.5 used it;
so does the IPA of 20.7). The old rows were `mem_reserve 0x300000000` (12 GiB), `mem_alias 0x180000000`
(6 GiB), `mem_stack 0x10000000` (256 MB) and a 5.5 GiB heap region — a `mem_prefix` row did not exist and the
host's default of 256 MB applied.

One Mac run of the final profile, driven through `DM_CTL`, 18.5 minutes; it ended at 47:29 of the second
half with the front end's `application termination requested` (no failure before it, and the log's last
frame is 33142):

| | |
| --- | --- |
| host line | `guest AS 0x7000000000 +0x142000000  heap 0x70f5000000 alias 0x7001000000 stack 0x70f1000000` |
| heap | `[mem] heap 1.19 GB (heap region 1.20 GB)` — 16 MiB of slack, by construction |
| alias regions | 661 live, 3.03 GiB reserved, 1.30 GiB mapped, top 3.750 GiB |
| alias high-water | `mapped up to +3.50 GB` reached at 2.9 s (frame 44) and unchanged for the rest of the run: this engine takes all its address space at boot, in menus and the match alike |
| frames | 33 142, `frame time p50 33.34 / p95 34.96 ms`; of the last 300 frames 1 was dropped (`on-screen … dropped 1`) |
| footprint | 3436 MiB at its peak |
| crash | none (`CRASH` count 0) |
| route | title → menus → team sheet → kick-off → 15:28 first half (0−1) → 27:24 → half-time → second half 47:29 (0−3), pitch, players, HUD, minimap and shadows as in sections 15–18 |

Screenshots of that run are `small-h2.png` (15:28), `small-r1.png` (27:24) and `small2-h3.png` (47:29, the
in-game menu over the second half) in the work folder's `memory-audit/shots/`. The 494-key shader map, the
rewritten `main` and `render` and every draw of the match are the ones sections 18 and 19 verified: `main`
and `render` are byte-identical between this work's rewrite and the packed Mac App (`d00cc493…`,
`7f35dd08…`), only `sdk` differs, by the two-word node cut and the five observation gates.

### 20.7 The iOS side

`dm/ios/tools/build_ipa.sh` decides the entitlement from the profile: `BIG_VA=1` (and so
`com.apple.developer.kernel.extended-virtual-addressing` in the plist it writes, plus a warning) only when
`mem_reserve` exceeds `0x180000000` (6 GiB). At 5.03 GiB that branch is not taken, and a rebuild of the IPA
from the current profile prints neither the warning nor an entitlement line:

| | |
| --- | --- |
| path | `/path/to/private-fc27-research/ios/FC27-iOS-Test-5g.ipa` |
| size / SHA-256 | 139 808 097 B / `cfe5c109a8a26a96c5290be8403cba7b9501543d2ef5ee9ac14cce44fcd414e4` |
| build | `xcodebuild` Release, unsigned, generic/platform=iOS, 19 s; `pack_ipa.py` 7 s |
| modules | `main` and `render` byte-identical to section 19's IPA; `sdk` = the rewritten one with the node cut (`087ca052` at `+0x14df00`, where section 19's IPA has `08fca752`) |
| entitlement | none requested, none written |

The executable therefore carries the new host (region table, alias override, the same 5.03 GiB constant the
Mac run used) and an `sdk` that matches the profile's assumption. That is a build check, not a run.

### 20.8 Tests

| Test | Result |
| --- | --- |
| `python3 -m unittest discover -s dm/tools/tests` | 92 tests, OK (1 skipped); 12 of them new |
| `dm/tools/tests/test_region_sites.py` | 6: `defined()` reads offsets and sizes from a hand-built MOD0 symbol table and returns `{}` without one; `out_store()` finds the one store through the out pointer, and refuses two stores, a prologue without the copy, and a prologue with two |
| `dm/tools/tests/test_mem_profile.py` | 6: every profile's `mem_prefix + mem_alias + mem_stack` leaves the heap room and is page-aligned; the header carries the values; `mem_prefix` defaults to 256 MB and `stdalloc_cap` to 0; a profile that fills its block exactly, or one page short of it, is refused where it is read; one page of heap is accepted |
| `make -C dm/host GAME=0100C49025D3E000` | relinks; the generated header is unchanged by the new validation |
| `make -C dm/host/tests GAME=0100C49025D3E000 run` | all targets pass except `t_condvar` / `t_condvar_old` (`guest_thread_set_id` missing from the stub) and `t_hid` (links `hle_haptics.c` only); both fail to link on `84bda12` as well — this work touches neither file |
| Mac match | 20.6 |

`game.py header` now refuses a partition that leaves the heap no room, which is the failure the host used to
report at start as `guest address-space profile has invalid native boundaries`.

### 20.9 Rollback

The change is four profile rows, one `sdk_patches.py` row, and host code that is inert when its gates are not
in a module: without the gates the region table stays empty and `DM_ALIAS_SIZE` unset keeps the profile's
sizes. To return to section 19's state, restore `mem_reserve 0x300000000`, `mem_alias 0x180000000`,
`mem_stack 0x10000000`, drop `mem_prefix`, drop the SDK 22.2.0 `CUTS` row, and rewrite `sdk` again — the
12 GiB block then needs the entitlement as before. No shader was rebuilt and no shader input changed in this
section.

### 20.10 The questions this section was asked, answered

1. **Are upstream's mechanisms usable here?** Yes, three of them, and they were the whole toolset: the
   alias-size override (measure with a Switch-sized region), the region table (what is reserved, by whom,
   how much of it is used) and the node-area cut (0.94 GiB of bookkeeping). `stdalloc_cap` was ported but
   never needed; `profile_guess.py`'s automatic region check was not ported.
2. **What is in the 12 GiB?** 256 MB of dead prefix + a 6 GiB alias region (3.03 GiB of regions reserved,
   1.30 GiB mapped, 62 MB of node area, ~0.66 GiB of alignment holes) + 256 MB of stacks (5 MiB used) +
   a 5.5 GiB heap region (the game asks 1.19 GB). Only the alias region and the two 256 MB spacers were
   ever candidates.
3. **How much of a 6 GiB alias is really used?** 1.30 GiB mapped (22%), 3.03 GiB reserved (50%), 0.06 GiB
   node area, 0.66 GiB holes; nothing is reserved but untouched at 3.75 GiB beyond the 1.7 GiB of
   reservoirs the engine keeps for its own streaming.
4. **Can it shrink to a normal iOS process size?** Yes: 5.03 GiB, from 12 GiB, with a full match passing on
   the Mac.
5. **What is the minimal verified configuration?** `mem_reserve 0x142000000`, `mem_prefix 0x1000000`,
   `mem_alias 0xF0000000`, `mem_stack 0x4000000`, plus the SDK 22.2.0 node cut in the rewritten `sdk` — and
   a full Mac match (first half, half-time, second half) on it. 3.5 GiB of alias also boots and plays but
   leaves the mapping high-water at the ceiling; 3.375 GiB is fatal at boot.
6. **If it could not shrink, which region would block it?** It is not a region but a reservation the engine
   makes at boot through `VammManager` (644 of 661 regions return to `main+0x17f9884`), and the mapping
   high-water of 3.50 GB that lands inside it. The evidence that 3.375 GiB is short is the fatal write at
   `main+0x17f98c4` 4 s after boot, with 3.25 GB already mapped.
7. **Can the current IPA start without extended virtual addressing, and what still needs a device?** The
   build no longer asks for it, and the host now logs why if the `mmap` fails. What is still unproven is
   everything a device would show: whether a 5.03 GiB reservation plus Metal's own allocations fit the ~7.4
   GB an unsigned app gets; whether the engine's 1.7 GiB of unmapped reservations and 3.3 GiB footprint run
   under the increased-memory limit; whether the node cut changes any behaviour on the phone; and any
   performance figure.

### 20.11 What is not claimed

* Nothing ran on a device: no launch, no match, no memory figure for iOS. The IPA is unsigned and unrun.
* 5.03 GiB is what this Mac measurement needed; a competition, stadium or kit that reserves more than the
  ones played here would hit the same fatal write, and the profile's 0.25 GiB of margin is the only slack.
* The 3.5 GiB floor is the smallest alias that booted; it was not played through a second half.
* The node area is cut to the 62 MB upstream uses; no attempt was made to find this build's true minimum.
* The heap region has 16 MiB of slack over `SetHeapSize`'s 1.1875 GB request by construction; a profile with
  a different `app_pool` or `mem_used` moves that request.
* The profile change is a research configuration: it was verified on the Mac with `DM_ALIAS_SIZE` unset (the
  profile's own sizes) and in one iOS build, not in the packaged Mac App section 18 accepted.
* **Committed:** the host's gate registry and region table, `game.py`'s partition check, the profile's memory
  rows, the rewriter's region gates and symbol helpers, the SDK 22.2.0 cut, the two new tests and this
  section. `memory-audit/` stays outside the repository.



## 21. FC 27 30/60 FPS control and device evidence (2026-10-30)

### 21.1 Scope and the upstream patch

The user reports that section 20's 5 GiB IPA actually plays on their iPhone. That is user-provided device
verification of the previous build; the measurements in this section are Mac measurements of the new FPS
adapter. The branch is still `research/fifa27`; no upstream merge, push or phone installation is involved.

Sources read, rather than inferred from the offsets in the task:

* [FC 27 1.8c.fd45 YAML](https://github.com/masagrator/FPSLocker-Warehouse/blob/v4/SaltySD/plugins/FPSLocker/patches/0100C49025D3E000/9636BCD68E2EF2C8.yaml).
* [SaltyNX's expression evaluator and block opcode](https://github.com/masagrator/SaltyNX/blob/master/saltysd_core/source/lock.cpp),
  `evaluateExpression`, `execBlock` and `applyPatch`.
* [SaltyNX's frame hooks](https://github.com/masagrator/SaltyNX/blob/master/saltysd_core/source/NX-FPS-Common.hpp),
  `NX_FPS_Math::PreFrame` / `PostFrame`, and the NVN `PresentTexture` / `SetPresentInterval` hooks.

`FPS_TARGET` is the selected FPS itself, **not** a clock multiplier and **not** the separate
`FPS_LOCK_TARGET` expression (which can add 2). `FRAMETIME_TARGET` is `1000 / FPS_TARGET` in milliseconds:
33.333333 at 30, 16.666667 at 60. The patch is reapplied from the presentation hook. Its `block timing`
sets `m_blockDelayFPS`, suppressing SaltyNX's additional PreFrame delay loop. It does not disable the
game's clock, OS ticks, GPU timestamps, audio scheduling or synchronization. nxnative has no SaltyNX delay
loop to remove: its clock implementations and GPU/CPU fences are unchanged.

### 21.2 Addresses, original code and the implementation choice

The decoded update NSO identifies itself as `9636bcd68e2ef2c863194d76f308c98c`; the YAML's 64-bit BID is its
prefix. The base game's `c2a256339b29922415331fab57de2565` is explicitly unsupported. Its offsets are not
borrowed from the update. The adapter checks both profile Title ID `0100C49025D3E000` and the full 128-bit
main Build ID before doing anything, including the present override.

The original main layout is text `[0, 0xb99fbc0)`, rodata at `0xb9a0000`, data at `0xc41b000`, BSS starting
at `0xd30d570` and ending at `0xdeb7a90`. All three pointer globals below are in BSS, not executable code.
The objects they refer to are created at runtime in the guest address space:

| Expression | Type and purpose |
| --- | --- |
| `*(main + 0xda1ee38) + 8` | double FPS target; the frame limiter reads it at `main+0x99e8a7c`, computes `1 / target`, and compares elapsed time against that period |
| `*(*(main + 0xde81da0) + 0x14c8) + 0xc`, then `+0x10` | two adjacent float regulator frame-time budgets, in ms |
| `*(main + 0xde82020) + 0xf8`, then `+0x144` | float RenderSettings budgets loaded into s8/s9 by the original regulator code |

The 64 original bytes replaced by FPSLocker's MASTER_WRITE, `[0x97f21d8, 0x97f2218)`, have SHA-256
`7b114e615469c66bb787320d21e913718451b6b62eaf514acd7707dd2bff53b2`. They load s8 from +f8, s9 from +144,
s10 from +184, s12 from +1d8, w20 (byte) from +240 and s0 from +a4, reloading the pointer `[x21+0x20]` and
checking it for null between reads. `x21 = main+0xde82000` (set at `main+0x97f204c`). After that block,
the function stores s12, w20 and s0 too; those are necessary side effects. It stores s8 at regulator +c,
and `min(s8,s9)` at +10. FPSLocker's replacement retains the six loads but compresses the pointer checks,
then substitutes its declared `dr_target` for s8/s9 when `hasStarted` is set.

The native adapter **does not overwrite that code**. It updates the two source settings as well as the
live budgets at each game present. The untouched code then reads the selected budgets itself and keeps
all its null checks and other fields. Runtime reads confirmed that +144's original value is 0: a zero
DR budget is accepted and replaced in 60 mode, while NaN/Inf or implausible values are skipped. In 30 mode
the adapter leaves both source settings and live DR budgets entirely alone. The FPS double is set to 30.
No runtime executable-page write, new entitlement, JIT, shader regeneration or rewritten NSO is needed.

This is a data adaptation of the upstream patch, not a byte-for-byte transplant. Source-setting writes
also affect any other consumer of these same DR settings; no other settings or rendering stages are
changed. A game-side settings rewrite between a present and its next regulator call can take effect for
that frame; the next present restores the selected values. This timing difference from an inline load
override must be kept visible when evaluating further scenes or device behaviour.

### 21.3 Host pacing, safety and launcher

`hle_fpslock.c` remains the sole engine-FPS adapter. `fpslock_fc27.h` factors its FC 27 pointer/typed-field
operations for tests. It follows the pointers anew on each present, retries objects not created yet and
restores plausible values when the game rewrites them. Corrections are logged with a field mask (FPS 1,
source budgets 2/4, live budgets 8/16); refused writes and unsupported builds are logged separately.
The source and live budgets were all read back as 16.666666, and the FPS double as 60, in the Mac match.
Corrections recurred on scene transitions, rather than being assumed to persist from boot.

Reads use `vm_read_overwrite`. Writes must lie inside `svc_guest_range`, fit a currently writable,
non-executable Mach region, and use `vm_write` after the existing `dm_guest_write_prepare` path.
A stale/unmapped or read-only destination fails without a userspace store or a permission change.
Pointers and fields have 8-/4-byte alignment checks and overflow/range checks. Writes are only the exact
4-/8-byte fields. There is no attempt to make read-only configuration or signed text writable.

`game.tsv` sets `fps_target 30`. The shared settings generator exposes the existing `DM_FPS_TARGET`
choice; only FC 27's label marks 60 as experimental and says to restart. Other games retain their
labels/defaults. `0` leaves original behaviour, invalid strings safely disable the adapter. v0 and
unrecognised main builds retain their original present semantics even if 60 was selected.

FC 27 requests NVN interval 2 in the match. Its validated adapter tells `hle_nvn.c` to pace with
`60 / target` vsyncs and returns the target to `nvn_game_fps`; there is no global `present_interval display`
profile change. The existing `CAMetalDisplayLink` in `nvn_mtl.m` then selects a 30/30/30 or 60/60/60
`preferredFrameRateRange` on iOS. Its queue/fence/GPU completion behaviour is unchanged. The Mac tests
use the existing classic present path (`DM_PRESENT_LINK=0`), actual presented-time feedback and the
fixed 60 Hz pacing clock, not uncapped `DM_PRESENT_HZ=0` or a fake FPS overlay value.

### 21.4 Mac experiments and evidence

The paired runs use the same update,
NSP inputs, 494-key map, shader libraries, rewritten modules and separate copies of the same user save;
Bournemouth versus Brighton, default match/camera. There is no pass/texture/shader capture during the
performance windows. `DM_NVN_TSV` records existing per-frame timings with call-count rows disabled.
Screenshots and bounded image-readback frames are excluded from performance windows. The existing
`DM_NVN_REGLUM` diagnostic gained an optional `DM_NVN_REGLUM_RANGE=first,last` so pixel evidence can be
bounded without readback in the quiet measurement windows.


On this **Apple M1**, the following are bounded match windows (frame numbers are in each run's TSV).
They describe actual runs, not a deterministic same-frame GPU benchmark: AI outcomes, camera position,
stoppages and Frostbite's dynamic resolution can differ. The existing game graphics are retained.

| Metric | Default 30, frames 13400–14100 | 60, frames 13500–14500 | 60, heavier goal-area view, frames 40800–41600 |
| --- | ---: | ---: | ---: |
| generated presents / s | 29.732 | 59.768 | 48.525 |
| actual on-screen new presents / s | 29.725 | 59.766 | 48.537 |
| frame time mean / p50 (ms) | 33.634 / 33.298 | 16.731 / 16.697 | 20.608 / 20.393 |
| frame time p95 / p99 (ms) | 35.500 / 38.299 | 18.390 / 19.145 | 29.024 / 36.722 |
| GPU mean / p95 / p99 (ms) | 12.239 / 16.372 / 20.530 | 8.276 / 9.462 / 10.334 | 19.160 / 23.327 / 24.601 |
| acquire wait mean (ms) | 10.000 | 0.000 | 0.000 |
| present-queue wait mean (ms) | 12.578 | 11.864 | 1.386 |
| translation submit CPU mean (ms) | 4.229 | 2.068 | 4.195 |
| frames discarded by presentation | 0 | 0 | 0 |
| on-screen intervals >1.5× target period | 6 | 3 | 185 |
| extra target-period holds, estimated from displayed intervals | 6 | 4 | 189 |

Actual on-screen rates use the Metal presented-time callbacks, not the overlay. A long on-screen interval
keeps the previous frame visible; it is distinct from a frame discarded before presentation. The extra-hold
count rounds displayed duration to target periods, so it is an estimate of repeated holds, not a separate
pixel measurement. CPU waits are separately measured and overlap other work; they must not be summed into
an exclusive frame-time breakdown. The heavy 60 view is substantially GPU-bound: ~19.2 ms GPU per frame
against a 16.7 ms budget, with little acquire wait. This Mac therefore does **not** hold 60 everywhere.

Both runs booted, displayed the menus, loaded the same match and passed the first half, half-time and
second-half transition. The 60 run reached second-half 47:51, with the pause menu then verified at 48:43;
the 30 run was visually verified at second-half 63:12. Pitch, kit materials, HUD, minimap, shadows,
player movement, passes/shots and close-up/replay rendering remained present. No crash or refused FPS
write was logged in either run. Peak logged footprint was **3474 MiB at 30, 3483 MiB at 60**. The runs
were stopped by the test operator, not by a game fault. Existing `buffer copy with a null end skipped`
diagnostics occur in both modes; they were not fixed or suppressed by this work.

**Clock / simulation check.** Count only uninterrupted live play, not tutorials, dead balls, paused menus
or replay shots (all of which legitimately hold the match clock). At 30, screenshots
`30-clock2-00.png` → `30-clock2-10.png` show **35:49 → 37:06 in 10.232954 s**, 7.5247 game s / real s.
At 60, `60-sample-02.png` → `60-sample-03.png` show **02:00 → 05:45 in 30.005825 s**, 7.4985 game s /
real s. Both agree with the default six-minute-half scale, 7.5, within HUD quantisation / screenshot
sampling uncertainty; they do not show a factor-of-two speed change. No host/game clock multiplier was
changed. Running, ball flight and animations were also inspected in the sequences, but no claim is made
of a quantitative per-player trajectory/physics equivalence test. The paired games stayed 0–0 in the
captured first halves: a specifically **goal-scored** replay and end-of-match flow are not proven here.
Commentary pitch / audio-video sync was not independently recorded or scored; those clocks and renderer
paths are unchanged, but device listening remains a useful regression check.

**Independent-frame proof, separate diagnostic run.** `60-image` records the centre of the football
picture, normalized ROI `(0.35,0.35)–(0.65,0.65)`, through the existing asynchronous REGLUM readback. This
excludes the FPS counter and HUD. In game presents **20600–20899**, all **300 grayscale thumbnails differ**,
with **zero adjacent duplicates**, at **59.9546 sampled images/s**. In that same span the game submitted
59.9078 frames/s and Metal reported **60.0021 new presentations/s**, with no discarded frames or long
holds. That is evidence of new football pictures near 60 Hz, not a 60 Hz display repeating a 30 Hz image.
It is a short proof span, not a promise about the whole match. Its readback and the iOS build that ran
during the diagnostic session are why it is separated from the performance windows above.

Machine-readable values, clock pairs, input/build identities and artifact hashes are in
`fifa27-fps-evidence.json` (local evidence, not included). Full local timing logs, screenshots, bounded original
ROI rows, the 300-image SHA-256 manifest and verification scripts are preserved under
`/path/to/historical-checkout/.iosdd_fc27_fps_evidence/` (ignored generated evidence).
For example, `python3 .iosdd_fc27_fps_evidence/report.py <run.tsv> <first> <last>` reproduces the frame
summaries. No keys or NSPs are copied into that evidence directory.

### 21.5 Tests and the iOS artifact

| Check | Result |
| --- | --- |
| `make -C dm/host/tests GAME=0100C49025D3E000 fpslock` | two native tests pass: default/original 30, 60, ms units, both identity guards including v0, invalid values, alignment, overflow, unreadable and unwritable memory, restoration after game writes, precise field width, DR consistency and other-title isolation; production Mach bounds/read-only/unmapped refusal and v0 present fallback |
| tools tests, using the existing fifa23 Python venv | 95 pass (1 skipped), including three new profile/launcher/isolation checks; the system Xcode Python lacks capstone and is not the supported dependency environment |
| NVN `t_nvn` | 124 checks, 0 failed |
| presentation `t_pace` / `t_fstep` | 10 / 47 checks, 0 failed |
| Mac host build | succeeds; existing Metal encoder-type warnings remain |
| iOS Release build | succeeds, arm64 iOS, minimum iOS 26.0 / SDK 27.1, unsigned |
| IPA zip and identity checks | valid archive, original Bundle ID and version, 30 default / experimental 60 choice; no bundled NSP, key file, code signature or entitlement file |
| embedded code / shader check | all 10 embedded NSO chunks equal their source rewritten files; SDK node-cut bytes `087ca052` retained; 494-key map identical; all 1102 MSL resources identical to the available earlier IPA |

The new tests run through the normal host test `run` target too. The rewriter and shader translation
were not modified, and no shader chain was regenerated. The small REGLUM range addition only bounds
existing diagnostic readback; it is inert unless that diagnostic is enabled.

| iOS artifact | Value |
| --- | --- |
| path | `/path/to/historical-checkout/.iosdd_fc27_fps_project/FC27-iOS-30-60-5g.ipa` |
| size | **139808823 bytes** (133.33 MiB) |
| SHA-256 | `040ce15e9432d51f91cf0db5a508cc82b05260737c432975186aad9c53d7ebf4` |
| Bundle ID / version | `org.nxnative.0100c49025d3e000` / `1.0.0`, unchanged |
| guest block | `mem_reserve 0x142000000`, same prefix / alias / stack and SDK 22.2.0 node cut |
| resources | external NSP mode; existing Documents resource discovery and save locations unchanged |
| build | independent `.iosdd_fc27_fps_work` / `.iosdd_fc27_fps_project` directories; existing previous build directories not reused |
| signing / installation | unsigned; **not installed**, no phone App replaced, no Documents or save data touched |

The launcher selection applies at next game launch. Keep 30 for the established mode; choose experimental
60 and restart to exercise the adapter. Existing Documents/env.txt overrides still take precedence.
The display link already supports the required 60 Hz range; this is a code/build verification of that
path, **not an iPhone frame-rate measurement**. No extended-virtual-addressing entitlement is requested,
and there is no new entitlement or runtime executable modification.

### 21.6 Remaining limits

The unlock, data budgets, new near-60-Hz render frames and match-clock rate are demonstrated on the Mac.
The data-only regulator adaptation preserves the original code but differs from FPSLocker's inline
substitution in the timing of settings restoration (21.2); full closed-loop resolution response under
sustained device GPU overload is not measured. The independent-frame proof is a bounded active-picture
span, not an every-frame guarantee through all movies or cutscenes. Other games' adaptation/default paths
are unchanged and shared regression tests pass, but inherited cross-title coverage was not exhaustive and is not part of Touchline 27 support.

iPhone 60-mode launch, actual generated/presented rates, RAM pressure, power, heat, throttling, audio sync
and behaviour below 60 still need the user's device test. There is no basis to infer their numbers from
this M1. The user-confirmed previous 5 GiB IPA remains the device baseline; this new artifact keeps its
identity, resources, memory partition and rewritten modules, with 30 as the default. There was no push,
installation, upstream merge, NSP repack, key re-import, save-code change or removal of rendering features.
