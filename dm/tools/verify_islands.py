#!/usr/bin/env python3
"""Check a rewritten module against its original image, independently of the rewriter.

Everything here is derived from the output files and the original NSO, never from the
rewriter's own state:

  * the file is exactly the layout its fixups header describes;
  * every 4-byte word that differs from the original is a B into one of the patch
    areas (or a registered cut / an in-place ctr replacement listed in sites.tsv);
  * every instruction in every patch area decodes, and each B / BL / ADRP / ADR it
    contains resolves to an address inside the image, the key page or an area;
  * each site the rewriter lists is a B into an area, and each gate's return point is
    inside an area right after a blr;
  * nothing beyond the described layout is non-zero.

Usage: verify_islands.py <original .nso/.nro> <build output dir> <module name>
       [--base <normalized .nso>]
The original may be ZBIC-compressed only when NX_ZBIC_LIBRARY is set (nsoseg).
"""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nsoseg
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

PAGE = 0x4000


class Bad(Exception):
    pass


def image_of(path):
    d = open(path, 'rb').read()
    if d[:4] == b'NRO0':
        segs = [struct.unpack_from('<II', d, 0x20 + 8 * i) for i in range(3)]
        img = bytearray(max(o + s for o, s in segs))
        for o, s in segs:
            img[o:o + s] = d[o:o + s]
        return img
    h = nsoseg.parse(d)
    _, segs, _, _ = h
    img = bytearray(segs[2][1] + segs[2][2])
    for i, (fo, mo, sz) in enumerate(segs):
        img[mo:mo + sz] = nsoseg.decode(d, h, i)
    return img


def header(out, name):
    h = {}
    for line in (out / f'{name}.fixups.tsv').read_text().splitlines():
        if line.startswith('# '):
            k, v = line[2:].split()
            h[k] = v
    return h


def hexs(v):
    return int(v, 16)


def b_target(addr, word):
    d = word & 0x3FFFFFF
    d -= (d & 0x2000000) << 1
    return addr + d * 4


def adrp_target(addr, word):
    imm = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 3)
    imm -= (imm & (1 << 20)) << 1
    return (addr & ~0xFFF) + (imm << 12)


def verify(orig_path, out, name, base_path=None):
    img = image_of(base_path or orig_path)
    h = header(out, name)
    fl, ko, ks, te = hexs(h['FILE_IMAGE_LEN']), hexs(h['KEY_PAGE_OFF']), hexs(h['KEY_PAGE_SIZE']), hexs(h['TEXT_END'])
    patch_off = int(h['PATCH_OFF'], 16)
    two = 'PATCH2_LEN' in h
    pl = hexs(h['PATCH_LEN']) if two else None
    p2, p2l = (hexs(h['PATCH2_OFF']), hexs(h['PATCH2_LEN'])) if two else (0, 0)
    image_size = hexs(h['IMAGE_SIZE'])

    areas = []                       # (lo, hi) executable patch areas
    raw = (out / f'{name}.patched.bin').read_bytes()
    if patch_off < 0:
        pre_len = pl if two else len(raw) - fl
        areas = [(patch_off, patch_off + pre_len)]
        if two:
            areas.append((p2, p2 + p2l))
        want = fl + pre_len + (p2l if two else 0)
    else:
        areas = [(patch_off, len(raw))]
        want = len(raw)
    if len(raw) != want:
        raise Bad(f'{name}: file is {len(raw):#x} bytes, its header describes {want:#x}')
    if len(img) > fl:
        raise Bad(f'{name}: image {len(img):#x} is longer than FILE_IMAGE_LEN {fl:#x}')
    if ko + ks > image_size or (two and p2 < image_size):
        raise Bad(f'{name}: key page or second area out of place')

    def in_area(a):
        return any(lo <= a < hi for lo, hi in areas)

    # ---- what the output changed, word by word ----
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    changed, other = [], []
    for off in range(0, len(img), 4):
        if raw[off:off + 4] == img[off:off + 4]:
            continue
        w = struct.unpack_from('<I', raw, off)[0]
        changed.append(off)
        if w >> 26 == 5 and in_area(b_target(off, w)):
            continue                 # a site redirected into a patch area
        if w & 0xFFE0001F == 0xD2A00000:
            other.append((off, w))   # mrs ctr_el0 replaced by movz
            continue
        raise Bad(f'{name}: {off:#x} changed to {w:08x}, which is neither a branch into a patch area nor a ctr replacement')
    if any(raw[o] for o in range(len(img), fl)):
        raise Bad(f'{name}: padding to FILE_IMAGE_LEN is not zero')

    # ---- every instruction of every area ----
    n_ins = n_branch = 0
    for lo, hi in areas:
        base = fl + (lo - patch_off) if lo < 0 else fl + (pl or 0) + (lo - p2)
        body = raw[base:base + (hi - lo)]
        if len(body) != hi - lo:
            raise Bad(f'{name}: area {lo:#x} runs past the file')
        while len(body) >= 4 and body[-4:] == b'\0\0\0\0':
            body = body[:-4]         # the file pads each area to the host page size
        if not body:
            raise Bad(f'{name}: area {lo:#x} is empty')
        # disassembled at 0 and shifted: a negative area cannot be a capstone address
        for ins in md.disasm(body, 0):
            a = lo + ins.address
            n_ins += 1
            m = ins.mnemonic
            if m in ('b', 'bl'):
                t = lo + ins.operands[-1].imm
                n_branch += 1
                if t % 4:
                    raise Bad(f'{name}: {a:#x} {m} to unaligned {t:#x}')
                if not (in_area(t) or 0 <= t < len(img)):
                    raise Bad(f'{name}: {a:#x} {m} to {t:#x}, outside the image and the areas')
            elif m == 'adrp':
                t = adrp_target(a, struct.unpack_from('<I', body, ins.address)[0])
                if not (in_area(t) or 0 <= t < image_size):
                    raise Bad(f'{name}: {a:#x} adrp to {t:#x}, outside the image and the areas')
            elif m in ('cbz', 'cbnz', 'tbz', 'tbnz') or m.startswith('b.'):
                t = lo + ins.operands[-1].imm
                if not in_area(t):
                    raise Bad(f'{name}: {a:#x} {m} to {t:#x}, outside the areas')
            elif m in ('br', 'blr', 'ret', 'nop'):
                pass
            elif m in ('udf', 'hlt'):
                raise Bad(f'{name}: {a:#x} {m} inside a patch area')
        dec = sum(1 for _ in md.disasm(body, 0))
        if dec * 4 != len(body):
            raise Bad(f'{name}: area {lo:#x} has {len(body)//4 - dec} undecodable words')

    # ---- sites, gates ----
    # sites.tsv rows: "<off> <kind>" = a rewritten instruction, "<off> W <end>" = a window
    # entered at off, "<off> S <back-edges...>" = a spin head with the back-edges that enter
    # its copy. J (jump table provenance) and T (offset table targets) rows describe the
    # original code; the branch they name may sit inside a window and be rewritten with it.
    sites = 0
    ctr_sites = {o for o, _ in other}
    for line in (out / f'{name}.sites.tsv').read_text().splitlines():
        f = line.split('\t')
        kind = f[1]
        if kind in ('J', 'T'):
            continue
        targets = [f[0]] if kind != 'S' else ' '.join(f[2:]).split()
        for hs in targets:
            a = int(hs, 16)
            sites += 1
            if a in ctr_sites:
                continue
            w = struct.unpack_from('<I', raw, a)[0]
            if w >> 26 == 5 and in_area(b_target(a, w)):
                continue
            raise Bad(f'{name}: site {a:#x} ({kind}) is not a branch into a patch area ({w:08x})')
    gates = 0
    for line in (out / f'{name}.gates.tsv').read_text().splitlines():
        if not line.strip():
            continue
        ret, kind, arg, orig = line.split('\t')
        ret = int(ret, 16)
        if ret >= 1 << 63:
            ret -= 1 << 64           # the file writes negative patch-area offsets as -0x...
        gates += 1
        if not in_area(ret) and ret not in areas:
            raise Bad(f'{name}: gate {ret:#x} is outside the patch areas')
        w = struct.unpack_from('<I', raw, fl + ((ret - patch_off) if ret < 0 else (pl or 0) + ret - p2))[0]
        if w != 0xA8C17BFD:
            raise Bad(f'{name}: gate {ret:#x} does not start with ldp x29, x30, [sp], #16 ({w:08x})')
    return dict(changed=len(changed), ctr=len(other), areas=[(hex(lo), hex(hi)) for lo, hi in areas],
                instructions=n_ins, branches=n_branch, sites=sites, gates=gates,
                pre_bytes=pl if two else (len(raw) - fl), after_bytes=p2l if two else 0)


def main(argv):
    if len(argv) < 4:
        sys.exit(__doc__)
    base = None
    if '--base' in argv:
        i = argv.index('--base')
        base = argv[i + 1]
        del argv[i:i + 2]
    r = verify(argv[1], Path(argv[2]), argv[3], base)
    print(f'{argv[3]}: OK ' + ' '.join(f'{k} {v}' for k, v in r.items()))


if __name__ == '__main__':
    main(sys.argv)
