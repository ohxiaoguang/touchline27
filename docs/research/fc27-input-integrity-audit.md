# EA SPORTS FC 27 input integrity audit

> Archive scope: superseded findings are retained in chronological order. Use the
> [research index](README.md) and [current platform status](../support-status.md) to
> distinguish historical experiments from current product instructions.

> Personal absolute paths have been replaced by `/path/to/...` placeholders for publication.

> Historical research record from the earlier fork. Paths, branch names, commit IDs, test
> results and device observations below describe that work at the stated time, not verification
> of this standalone checkout. Missing local evidence was not regenerated in the release audit.
> Use [building](../building.md) for current instructions and [release audit](../release-audit.md)
> for publication risks.

Audit date: 2026-10-27, Asia/Shanghai. Initial repository: `/path/to/historical-checkout`, branch `research/fifa27`, HEAD `f084aa5fadcde2202edc7eec8d0a9331111d994f`, clean worktree, three commits ahead of the locally recorded `origin/main`. The process inventory at the start found no active process matching the FC27 scratch directory, extractor or rewriter. This is a point-in-time observation, not a guarantee that no unrelated task exists. New artifacts were written only under `/path/to/private-fc27-research/input-audit-20261027/` (called `AUDIT` below); older files were not cleaned or overwritten. Approximately 587 GiB was free on the external volume at the start.

## Findings

**No key or input-mixing failure was observed for the audited code path.** Both selected Program NCAs were fully hashed as stored and matched the Program records in their integrity-checked CNMTs. Using one existing key file, LibHac opened their encrypted code filesystems and read every ExeFS file with integrity checks enabled. Both freshly extracted main NSOs have bounded, non-overlapping segments; all six decoded ZBIC segment sizes and header SHA-256 values matched, and both new normalized files are byte-identical to the corresponding previous normalized outputs. These results concern the supplied files and accessed code/control blocks. They do not establish provenance from a particular console, validate every RomFS block, certify every key in the file, or establish that either main can be rewritten or executed.

The earlier feasibility report's statement in its initial module section that base ZBIC was not independently decoded is stale: its later Stage 2 section and `logs/zbic-base.log` document that it was. This audit repeats the base and update checks separately.

## Input chain and fingerprints

`W = /path/to/private-fc27-research`, `AUDIT = W/input-audit-20261027`. SHA-256 values below are of the complete specified file or specified container member; no key-file digest or key value is recorded.

| Step | Actual path / member | Bytes | SHA-256 |
|---|---|---:|---|
| Base original | `/path/to/fc27-inputs/EA SPORTS FC 27 v1.0.0[0100C49025D3E000][v0][APP].nsz` | 12712442035 | `99951475e1aa2349e81b7a1e52151167adb45b7f7f57d232685d38946ed59a3f` |
| Base converted | `W/nsp/EA SPORTS FC 27 v1.0.0[0100C49025D3E000][v0][APP].nsp` | 14049497676 | `151c4f7e163c87413ac5443695464f55dd566007c591d9df4651555d1dec59a2` |
| Base Program NCA, inside converted NSP | `e3e2e8704a5c812035b6477ee3db0578.nca` | 14049099776 | `e3e2e8704a5c812035b6477ee3db0578e0b50ea8b0ef6899c292bd77b8ffe955` |
| Update original | `/path/to/fc27-inputs/v-ea_sports_fc_27_v327680.nsp` | 20280760397 | `dba47ae217e2179d4a8aad1131082dd511a628e6a90cf92829f736d0f1c7ebbb` |
| Update Program NCA, inside NSP | `9b25b2f405b6570c7040bc5441f56f0c.nca` | 20280392704 | `9b25b2f405b6570c7040bc5441f56f0cc9ea4a6f8f2d6916fccb16166dae5017` |
| Fresh base `main` | `AUDIT/fresh-base/ExeFS/main` | 81455823 | `a7dd65cfcbd920527f5a99e5dabbe00dc42456b515a79f323e638f5fb6aedcac` |
| Fresh update `main` | `AUDIT/fresh-update/ExeFS/main` | 81518033 | `4e4280baa5f6f2966ab81ade05625dd6c1408879ad60ef585eaffcc36a39e21f` |
| Fresh normalized base | `AUDIT/normalized-base.nso` | 221127620 | `708eb46d14539a30db9ab3a5eed9b312456e53bbd53ea5820d14803128906182` |
| Fresh normalized update | `AUDIT/normalized-update.nso` | 221301956 | `2445a558b320d574cf228083e54726bfde1ffd202bac8197d70a99907fe3d6b6` |

The original base NSZ and converted NSP have byte-identical Meta NCA (`fed6f0c2fa991234681b16a48c114b5a.cnmt.nca`, SHA-256 `fed6f0c2fa991234681b16a48c114b5ad05ce274d9245c53dc8097da80a44fa2`), ticket and other uncompressed members. Ticket bytes were compared in memory without printing their contents or digest. The sole NCZ's content-ID stem matches the converted Program NCA and their first 16384 retained bytes match. The converted NCA's full SHA-256 independently equals the Program record in that same Meta NCA. `AUDIT/logs/base-members-compare.jsonl`, `base-ncz-header.json`, `cnmt-program.log` and `program-nca-sha.jsonl` provide these checks. The entire original NCZ was **not** decompressed again in this audit; its complete decompressed bytes have therefore not been independently compared to the previously converted NSP. The historical `W/logs/base-decompress.log` records `100% Done` but does not preserve a complete command line or input digest. The supplied filenames and matching content records establish a consistent chain, not the original source or purchase provenance.

The independently decoded CNMT identifies application `0100C49025D3E000`, v0, and patch `0100C49025D3E800`, v327680, belonging to that application. Both selected Program NCA headers identify program `0100C49025D3E000`; their selected content IDs and complete encrypted NCA hashes match their respective CNMT Program records (`AUDIT/logs/cnmt-program.log` and `program-nca-sha.jsonl`). The update ExeFS was read through LibHac's base-plus-patch code filesystem; it produced the update `main`, not a copy of base `main`. Base control data reports `1.0.0`; update control data's literal display string is `1.8c.fd45`, not independently mapped to a conventional version.

## Key and decryption evidence

The actual `prod.keys` path supplied to **both fresh extractions** was `/path/to/console-keys/prod.keys`. In a bounded depth-three search under `/path/to/game-inputs` and `/path/to/checkouts`, 11 files named `prod.keys` were readable and byte-identical to the one used; these are not necessarily all copies on the machine (`AUDIT/logs/key-path-inventory.json`). Equality was computed in memory; no contents or key hashes were emitted. No different key file was supplied to the fresh extractor, CNMT probe or NCZ conversion evidence examined here. Historical logs do not themselves preserve every command argument; prior paths are supported by the available task record, not invented from log text.

The probe read both Program NCA headers as NCA3: their legacy/current crypto-generation fields are 2/22, and both use ticket title-key mode. The tool's key reader accepted the file and successfully resolved the key material needed for these specific inputs. Neither LibHac nor the probe provides a universal minimum `prod.keys` version, and generation 22 is an NCA field, not a version label for the whole key file. No missing-key, insufficient-generation, decrypt or accessed-block integrity error occurred in these successful runs. This does **not** prove that the key file contains every key for other titles, every NCA or every unaccessed section. If another NCA fails later, repeat its offline read and record the tool's error and required key *name* or generation without printing values; do not replace the file on this evidence.

Unlike a metadata-only read, `nx_extract --program-only` opened the Program code filesystem with `IntegrityCheckLevel.ErrorOnInvalid` and copied every ExeFS file, not merely the NCA header. Both runs returned exit 0. No `--allow-damaged` bypass was used. The base/update Program NCA full-file SHA-256 comparison covers encrypted bytes against CNMT; LibHac's integrity checking covers accessed code/control blocks. Full RomFS decryption and every section's internal integrity were not revalidated. The native metadata reader's attempt directly on the compressed NSZ failed with `CNMT input/keys/container: Operation not supported` (`AUDIT/logs/base-nsz-cnmt.log`); this is a container-reader limitation, not a missing-key diagnostic. The original and converted Meta NCA were instead compared byte-for-byte as described above.

Tools: existing `W/nxbin/nx_extract.dll` SHA-256 `6f825703d8b1f035233b34173ac6a72e2c0e1c5f2b19065eea8c6b84d0cc279b`. Its dependency manifest names LibHac 0.19.0; `LibHac.dll` SHA-256 is `df35642dd8d43472414a58a45fb7c5c22858764abf114ea09bff7bb08bad5b16`. Runtime was .NET 10.0.402. The retained build source `W/nxsrc/Program.cs` and this repository's `dm/tools/nx_extract/Program.cs` share SHA-256 `ac45173d474a65531e24dd0dfe032af9ad65df26116d9b0ed83bb47bba1b656d`; the historical build log does not prove a reproducible binary build. The existing NSZ tool is 5.0.0, `lz4` 4.4.5, and the external research-only `zbic` package 1.0.1.post1. `W/normalize_zbic.py` SHA-256 is `4e5e4800098f44aa664f3e9c0e1db39159c98cdb030bc91549dcb96cba95d1f2`; its installed decoder binary SHA-256 is `f928f374955a321aad78f2cdf50d3043adf2b74bfdb86baf95d6372404e02ff2`. GPL licensing and production integration remain separate concerns.

## NSO results

Fresh files have NSO0 magic. Build IDs are the first 16 bytes used by the existing tooling; module header ranges were checked against the actual file length, compressed ranges do not overlap, and memory ranges do not overlap. Bit 7 and each segment's `ZBIC` magic agree for the two `main` modules; the three compressed segments and their hash flags are set (`0xbf`). Exact offsets, stored sizes, memory offsets and all segment digests are in `AUDIT/logs/modules-memory-bounds.jsonl`.

| Version | `main` Build ID | text / ro / data uncompressed bytes | SHA-256 of decoded text / ro / data; each matches NSO header |
|---|---|---|---|
| Base | `c2a256339b29922415331fab57de2565` | 194478320 / 10980980 / 15668064 | `68d672371b16d23207dd210957ae41cb8b97aa5723e7e4d8505e3226a95bfcc7` / `ab55008a7dbb969173c086e0fee8fd7aa469bf24cbd21a9ea9d06010121829bc` / `c101cbd70abeb73d27f7edf7d32411a08dd759a09a9de2752849c00f1706a40e` |
| Update | `9636bcd68e2ef2c863194d76f308c98c` | 194640832 / 10988180 / 15672688 | `ba3320df5d27d6105ffaeebf2a9b716bde91d4798ded16f1da0a3c3447bf0495` / `06f5effbf84f50a177d63fb9dcfced493bb6a6d8b302555b789f5c7cbb9f2bee` / `16357bcf04c711492af0867619756952534fc2febb964e43661254e2e2d3f00d` |

`W/normalize_zbic.py`, using the external ZBIC implementation, read each fresh original `main`, checked each decoded length and each enabled header digest, then wrote a new uncompressed NSO in `AUDIT`. The new normalized files' complete hashes match `W/normalized-base-main` and `W/normalized/ExeFS/main`, respectively. This establishes exact correspondence of these retained outputs to the audited extraction under the same decoder, not independent validation of the decoder's behavior on damaged inputs.

Both versions' SDK Build ID is `fed212d6e0963706f9f4b16ea5d65879`, NSO SHA-256 `78a5c1861da411802714080f4f74017a94cd839f8fe5b447dabfce81fc9abb6f`; both rtld Build ID is `56533df3bb579c77f5b2f78ea047a44a`, NSO SHA-256 `ee8fd522d4961802e7f3c356ffee80a3f5eec3c3eb8e1f3a1155aeea4d4e091e`. Their `0x3f` LZ4 sections all decoded to declared sizes and matched all header digests. All four fresh ExeFS files per version, including `main.npdm`, match their corresponding earlier `W/extract-base/ExeFS` or `W/extract-update/ExeFS` files by SHA-256 (`AUDIT/logs/file-inventory.jsonl`). Base and update NPDM are distinct: SHA-256 `42eb6aaa615c1e5c646d037494b5d3f02c0480a5c029ea31cf5bd0792e3b1876` and `03fc132912d9abfb8a126687aef48dae07c4dcc45f0ccd509784e74b74b56955`. At this historical stage there was no registered FC27 profile under `dm/games/0100C49025D3E000`; there is consequently no profile Build ID to compare.

## Checks, commands and limitations

`AUDIT` commands below use the exact key *path*, not its content. The full command outputs and additional precise sizes/fingerprints are in the audit subdirectory.

1. **Pass — code/control extraction** (run separately for the two inputs; `AUDIT` was the working directory):

   ```sh
   dotnet "$W/nxbin/nx_extract.dll" /path/to/console-keys/prod.keys \
     "$W/nsp/EA SPORTS FC 27 v1.0.0[0100C49025D3E000][v0][APP].nsp" - fresh-base --program-only
   dotnet "$W/nxbin/nx_extract.dll" /path/to/console-keys/prod.keys \
     "$W/nsp/EA SPORTS FC 27 v1.0.0[0100C49025D3E000][v0][APP].nsp" \
     /path/to/fc27-inputs/v-ea_sports_fc_27_v327680.nsp fresh-update --program-only
   ```

   The actual invocations also set `TMPDIR` and `DOTNET_CLI_HOME` to `AUDIT/tmp`, disable telemetry and redirect output to `AUDIT/logs/base-extract.log` and `update-extract.log`.
2. **Pass — CNMT and complete Program NCA SHA-256:** `AUDIT/metaprobe/nxrom.c` is an audit-only instrumented copy of the existing native CNMT reader; its selection result and key mode are logged without key material. `AUDIT/verify_nca.py` reads the PFS0 member ranges and hashes both complete NCAs. `AUDIT/compare_packages.py` compares common NSZ/NSP members; `AUDIT/compare_ncz_header.py` compares their retained Program header. No full NCZ re-conversion was performed.
3. **Pass — NSO and normalization:** the existing external Python environment ran `W/normalize_zbic.py AUDIT/fresh-base/ExeFS/main AUDIT/normalized-base.nso` and the corresponding update command with `PYTHONPATH=W/pydeps`, `TMPDIR=AUDIT/tmp` and bytecode disabled. Logs are `normalize-base.log` and `normalize-update.log`. `AUDIT/verify_modules.py` checked actual ranges, headers, digests and normalized output correspondence; `AUDIT/hash_inventory.py` recorded the entire file inventory. These are scratch scripts, not production tools.
4. **Historical failure — unsupported format:** `W/logs/rewrite-raw.log` records `LZ4BlockError: Decompression failed: corrupt input or insufficient space in destination buffer. Error code: 9` from the old tool treating ZBIC as LZ4. Current `W/logs/stage2-raw-base.log` and `stage2-raw-update.log` show the intentional `ZBIC-compressed NSO segments are not supported` rejection. This is not an NCA decryption error.
5. **Historical incomplete rewrite:** `W/logs/rewrite-normalized.log` ends in `KeyboardInterrupt` during disassembly; `W/logs/stage2-base.log` and `stage2-update.log` show the subsequent conservative single-area reach preflight rejection. `W/logs/rewrite-sdk.log` and `rewrite-nro.log` record earlier SDK/NRO static rewrites. This audit did not repeat them or run a large-module pressure test. No main rewrite, structural proof or runtime execution is claimed.
6. **Not checked:** independent supplier/console provenance; full original NCZ decompression; full unaccessed RomFS integrity; all other NCAs and optional update delta-fragment semantics; every potential key file; target-game runtime, profile registration and production ZBIC integration. The directly attempted native NSZ metadata read failed with `Operation not supported` as stated above.

## Classification and next gate

- **A — keys/decryption:** no observed failure on these Program NCA code/control paths. Sufficient for these reads, not a universal key-version certification.
- **B — mixed inputs:** no mismatch found in the checked CNMTs, Program NCA hashes, version-specific Build IDs, freshly extracted modules or normalized outputs. Original acquisition provenance and complete NCZ-to-NSP re-conversion remain unverified.
- **C — ZBIC toolchain:** confirmed; inputs contain valid hash-checked ZBIC segments under the external decoder, while production nxnative does not yet support them. Its earlier LZ4 error is not evidence of a key problem.
- **D — large NSO rewrite:** remains open; both confirmed normalized inputs hit the current conservative layout guard and historical rewrites did not finish. A failed or interrupted rewrite does not establish a decryption problem.

No correction to the supplied keys or checked inputs is justified by the evidence. The next phase may use these identified inputs for decoder and rewrite development, provided each run rechecks input SHA-256 and segment hashes, keeps base/update separate, and preserves a read-only source. Enter module-processing validation only after a license-reviewed ZBIC implementation, bounded failure tests, completed independent rewrites of both builds and structural/semantic verification. Hash agreement alone does not authorize a runtime-success claim.
