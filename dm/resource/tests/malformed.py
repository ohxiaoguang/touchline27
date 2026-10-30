"""Deterministic malformed containers; run native inspector under ASan/UBSan."""
from pathlib import Path
import subprocess
import struct
import sys
from fixture import pfs, nca, romfs, write_fixture, gamecard, hfs0, hfs0_fixed, xci, patch_nca

root = Path(sys.argv[2]); root.mkdir(parents=True, exist_ok=True)
write_fixture(root)
tool = str(Path(sys.argv[1]).resolve())
original = romfs({'small': b'hello', 'nested/big': bytes(range(256))*100})
fixtures = []
for offset in (0,24,32,56,64,72):
    for value in (0, (1<<64)-1):
        blob = bytearray(original); struct.pack_into('<Q',blob,offset,value)
        fixtures.append(pfs([('p.nca',nca(blob))]))
# Cyclic directory sibling, file chain, oversized name and file interval.
od = struct.unpack_from('<Q',original,24)[0]
of = struct.unpack_from('<Q',original,56)[0]
for offset,fmt,value in ((od+8,'I',0),(of+4,'I',0),(of+28,'I',0xffffffff),(of+8,'Q',(1<<64)-1),(of+16,'Q',(1<<63))):
    blob=bytearray(original); struct.pack_into('<'+fmt,blob,offset,value)
    fixtures.append(pfs([('p.nca',nca(blob))]))
# Malformed outer directory and duplicate members.
fixtures += [pfs([('p.nca',b'x')])[:n] for n in (0,1,15,16,25)]
fixtures += [pfs([('same.nca',b'x'),('same.nca',b'y')]),pfs([('../bad.nca',b'x')])]
# Malformed gamecard images: header, root table and secure member corruptions.
card = xci({'small': b'hello', 'nested/big': bytes(range(256))*100})
fixtures += [card[:n] for n in (0, 0x104, 0x15f, 0x200, 0xf001, 0xf011)]
for offset in (0x101, 0x104, 0x108, 0x118, 0x130, 0x138, 0x13c, 0x140, 0x144, 0x148, 0x14c, 0x150):
    for value in (0, (1<<64)-1, 0x4141414141414141):
        blob = bytearray(card)
        struct.pack_into('<Q', blob, offset, value)
        fixtures.append(bytes(blob))
root_off, root_hdr = struct.unpack_from('<QQ', card, 0x130)
for offset in (0, 4, 8, 0x10, 0x14, 0x18, 0x20, 0x44, 0x48, 0x50, 0x54):
    for value in (0, (1<<64)-1):
        blob = bytearray(card)
        struct.pack_into('<Q', blob, root_off+offset, value)
        fixtures.append(bytes(blob))
fixtures += [
    gamecard([('a.ncz', b'x')]),
    gamecard([], partitions=[('secure', hfs0([])), ('secure', hfs0([('a.nca', b'x')]))]),
    gamecard([], partitions=[('update', hfs0([('f', b'x')]))], secure=False),
    gamecard([], partitions=[('secure', hfs0_fixed([('a.nca', 0, 1<<20)], bytes(4096)))]),
    gamecard([], partitions=[('secure', hfs0_fixed([('a.nca', 0, 4096), ('b.nca', 0x800, 4096)], bytes(8192)))]),
    gamecard([], partitions=[('secure', hfs0_fixed([('../a.nca', 0, 16)], bytes(16)))]),
    gamecard([], partitions=[('secure', hfs0_fixed([('a.nca', 0, 0), ('a.nca', 0, 0)], bytes(16)))]),
]
for i,blob in enumerate(fixtures):
    path=root/'malformed.nsp'; path.write_bytes(blob)
    run=subprocess.run([tool,'--base',str(path),'--keys',str(root/'test.keys'),'--verify'],capture_output=True,timeout=10)
    if run.returncode not in (0,1) or b'AddressSanitizer' in run.stderr or b'runtime error:' in run.stderr:
        raise SystemExit(f'case {i}: sanitizer failure: {run.stderr.decode()}')

# BKTR patch fields, in the FIFA-shaped layout (the subsection table describes the
# region up to its own start): every declared bound and both table magic/version
# words moved out of place, read through a base + update mount.
base_files={'small':b'hello','nested/big':bytes(range(256))*100}
new_files=dict(base_files); new_files['nested/big']=base_files['nested/big'][:200]+b'P'*300
base=root/'bktr-base.nsp'; base.write_bytes(pfs([('p.nca',nca(romfs(base_files)))]))
def patch(change=None):
    return pfs([('patch.nca',patch_nca(romfs(base_files),romfs(new_files),fifa_layout=True,
                                      header=change))])
patches=[patch()]
for offset in (0x100,0x108,0x110,0x114,0x120,0x128,0x130,0x134):
    for value in (0,0x10,(1<<64)-1):
        patches.append(patch(lambda fh,o=offset,v=value: struct.pack_into('<Q',fh,o,v)))
for i,blob in enumerate(patches):
    path=root/'bktr-update.nsp'; path.write_bytes(blob)
    run=subprocess.run([tool,'--base',str(base),'--update',str(path),'--keys',str(root/'test.keys'),'--verify'],capture_output=True,timeout=10)
    if run.returncode not in (0,1) or b'AddressSanitizer' in run.stderr or b'runtime error:' in run.stderr:
        raise SystemExit(f'BKTR case {i}: sanitizer failure: {run.stderr.decode()}')
print(f'{len(fixtures)} malformed-container cases and {len(patches)} BKTR cases: no sanitizer findings')
