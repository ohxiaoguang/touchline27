#!/usr/bin/env python3
"""Turn the control and code sections DM_NVN_SHDUMP saved into a shader_split-style package
and the shader_map.tsv rows that point at it.

A game's shaders normally come out of its own archives (shader_split.py). When an archive
format is not parsed yet, the shaders the game actually asks for can still be taken from the
running program: with DM_NVN_SHDUMP=<dir> the host writes, for every shader missing from the
map, <key>.ctl (the 0x880-byte control section), <key>.code (the code area) and <key>.stg (the
stage index NVN reported). Those are the game's own bytes, unchanged — nothing here invents a
shader or a key.

Package format (what dmsh_build.py reads): records separated by "BTCDBTCD", each
{0x38-byte prefix}{code area}{control section}; the key is sha256(control[:0x880] +
code)[:8] as hex, which is exactly what the host computes (hle_nvn.c keys_hash).

Usage: shdump_pack.py <dump dir> <output pack dir> [--map <output map tsv>]
Stage names follow dmsh_build's package naming: vs_, ps_, gs_, hs_, ds_, cs_.
"""
import glob
import hashlib
import os
import struct
import sys

STAGE = {0: 'vs', 1: 'ps', 2: 'gs', 3: 'hs', 4: 'ds', 5: 'cs'}
FULL = {'vs': 'vertex', 'ps': 'pixel', 'gs': 'geometry', 'hs': 'hull', 'ds': 'domain', 'cs': 'compute'}
CTL_LEN = 0x880
PREFIX = 0x38              # dmsh_build.py: record[0x38:ctl_offset] is the code area
MARK = b'BTCDBTCD'
GFX_MAGIC, CS_MAGIC = 0x12345678, 0x12345679
SPH_STAGE = {1: 'vs', 2: 'hs', 3: 'ds', 4: 'gs', 5: 'ps'}


def stage_of(code, idx):
    """The shader's stage, from its own bytes (shader_split.py's rule): the code area's header magic
    says compute (0x12345679, instructions start at +0x100) or graphics (0x12345678, a 0x50-byte SPH
    at +0x30 whose word 0 holds the stage in bits 10..13). The NVN shader index (.stg) is only a
    cross-check: a program of one compute shader passes it at index 0, which reads as vertex."""
    if len(code) < 0x34:
        return None, 'code area too short'
    magic = struct.unpack_from('<I', code, 0)[0]
    if magic == CS_MAGIC:
        st = 'cs'
    elif magic == GFX_MAGIC:
        w = struct.unpack_from('<I', code, 0x30)[0]
        st = 'vs' if (w >> 10) & 0xf == 0 and w & 0x1f == 1 else SPH_STAGE.get((w >> 10) & 0xf)
        if st is None:
            return None, f'graphics code area with SPH word 0 {w:#010x}'
    else:
        return None, f'unknown code header {magic:#010x}'
    if idx in STAGE and STAGE[idx] != st:
        # only a warning: the index is the NVN array slot, which for a one-shader compute program is 0
        print(f'note: NVN shader index {idx} ({STAGE[idx]}) but the bytes say {st}')
    return st, None


def key_of(ctl, code):
    """The shader key: sha256 of the control section and the code area, first 8 bytes.
    The control section's own length (+0x20) is used when it is smaller than 0x880, as
    hle_nvn.c keys_hash does for the SDK 10 builds whose sections are 0x850 bytes."""
    own = struct.unpack_from('<I', ctl, 0x20)[0]
    n = own if 0x760 <= own < CTL_LEN else CTL_LEN
    return hashlib.sha256(ctl[:n] + code).digest()[:8].hex()


def load(dump):
    out = []
    for ctl_path in sorted(glob.glob(os.path.join(dump, '*.ctl'))):
        key = os.path.basename(ctl_path)[:-4]
        ctl = open(ctl_path, 'rb').read()
        code_path = ctl_path[:-4] + '.code'
        code = open(code_path, 'rb').read() if os.path.exists(code_path) else b''
        stg_path = ctl_path[:-4] + '.stg'
        stg = int(open(stg_path).read().strip()) if os.path.exists(stg_path) else -1
        if len(ctl) < CTL_LEN or struct.unpack_from('<I', ctl, 0)[0] != 0x98761234:
            sys.exit(f'{ctl_path}: not a control section (0x{len(ctl):x} bytes)')
        ncode = struct.unpack_from('<I', ctl, 0x704)[0]
        if ncode != len(code):
            sys.exit(f'{key}: control says {ncode:#x} bytes of code, the dump holds {len(code):#x}')
        if MARK in code or MARK in ctl:
            sys.exit(f'{key}: a record separator appears inside the shader bytes; the package format cannot carry it')
        if key_of(ctl, code) != key:
            sys.exit(f'{key}: the dumped bytes hash to {key_of(ctl, code)}')
        st, why = stage_of(code, stg)
        if st is None:
            sys.exit(f'{key}: cannot tell the stage: {why}')
        out.append((st, key, ctl, code))
    return out


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    dump, packs = argv[1], argv[2]
    map_path = argv[argv.index('--map') + 1] if '--map' in argv else None
    rows = load(dump)
    os.makedirs(packs, exist_ok=True)
    by_stage = {}
    for st, key, ctl, code in rows:
        by_stage.setdefault(st, []).append((key, ctl, code))
    map_rows = []
    for st in sorted(by_stage):
        name = f'{st}_dump.bin'
        with open(os.path.join(packs, name), 'wb') as f:
            for i, (key, ctl, code) in enumerate(by_stage[st]):
                f.write(MARK + bytes(PREFIX - len(MARK)) + code + ctl)
                map_rows.append((name, i, FULL[st], key))
        print(f'{name}: {len(by_stage[st])} shaders')
    if map_path:
        with open(map_path, 'w') as f:
            f.write('# shaders the game asked for at run time, taken from DM_NVN_SHDUMP (dm/gfx/tools/shdump_pack.py); the bytes are the game\'s own\n')
            f.write('package\tindex\tstage\tdm_ctl_sha16\tsource\n')
            for name, i, stage, key in map_rows:
                f.write(f'{name}\t{i}\t{stage}\t{key}\tDM_NVN_SHDUMP#{key}\n')
        print(f'{map_path}: {len(map_rows)} rows')


if __name__ == '__main__':
    main(sys.argv)
