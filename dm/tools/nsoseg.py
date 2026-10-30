"""Read NSO segments with bounded ranges and integrity checks.

ZBIC support uses an explicitly supplied external library exposing the
zbic_decompress interface; no decoder is bundled or built by this module.
"""
import ctypes
import hashlib
import os
from pathlib import Path
import struct

LIMIT = 2 << 30
IMAGE_LIMIT = 4 << 30


class NsoError(ValueError):
    pass


def parse(data):
    if len(data) < 0x100 or data[:4] != b'NSO0':
        raise NsoError('invalid or truncated NSO header')
    flags = struct.unpack_from('<I', data, 0xc)[0]
    if flags & ~0xff:
        raise NsoError('unknown NSO flags')
    segs = [struct.unpack_from('<III', data, 0x10 + i * 0x10) for i in range(3)]
    stored = struct.unpack_from('<III', data, 0x60)
    ranges, memory = [], []
    for i, (fo, mo, size) in enumerate(segs):
        length = stored[i] if flags & (1 << i) else size
        if not size or size > LIMIT or not length or fo < 0x100 or fo + length > len(data):
            raise NsoError(f'invalid file range or size for segment {i}')
        ranges.append((fo, fo + length))
        memory.append((mo, mo + size))
    for group in (ranges, memory):
        ordered = sorted(group)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise NsoError('overlapping NSO segments')
    if memory != sorted(memory):
        raise NsoError('NSO memory segments are out of order')
    if max(end for _, end in memory) > IMAGE_LIMIT:
        raise NsoError('NSO image too large')
    return flags, segs, stored, struct.unpack_from('<I', data, 0x3c)[0]


def _zbic(raw, size):
    # This check also protects wrappers that inspect four magic bytes before
    # checking their input length.
    if len(raw) < 4 or raw[:4] != b'ZBIC':
        raise NsoError('invalid or truncated ZBIC frame')
    path = os.environ.get('NX_ZBIC_LIBRARY')
    if not path:
        raise NsoError('ZBIC requires an external decoder: set NX_ZBIC_LIBRARY')
    lib = ctypes.CDLL(path)
    fn = lib.zbic_decompress
    fn.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t,
                   ctypes.POINTER(ctypes.c_size_t), ctypes.c_char_p, ctypes.c_size_t]
    fn.restype = ctypes.c_int
    out = ctypes.create_string_buffer(size)
    err = ctypes.create_string_buffer(256)
    produced = ctypes.c_size_t()
    if fn(out, size, raw, len(raw), ctypes.byref(produced), err, len(err)):
        raise NsoError('ZBIC decode failed: ' + err.value.decode('utf-8', 'replace'))
    if produced.value != size:
        raise NsoError('ZBIC decoded length mismatch')
    return out.raw


def decode(data, header, index):
    flags, segs, stored, _ = header
    fo, _, size = segs[index]
    compressed = bool(flags & (1 << index))
    raw = bytes(data[fo:fo + (stored[index] if compressed else size)])
    if compressed and flags & 0x80:
        raw = _zbic(raw, size)
    elif compressed:
        import lz4.block
        try:
            raw = lz4.block.decompress(raw, uncompressed_size=size)
        except Exception as exc:
            raise NsoError(f'LZ4 decode failed for segment {index}: {exc}') from exc
    if len(raw) != size:
        raise NsoError(f'decoded length mismatch for segment {index}')
    if flags & (1 << (index + 3)) and hashlib.sha256(raw).digest() != data[0xa0 + index * 32:0xc0 + index * 32]:
        raise NsoError(f'SHA-256 mismatch for segment {index}')
    return raw


def load(path, bss=True):
    data = Path(path).read_bytes()
    header = parse(data)
    _, segs, _, bss_size = header
    size = max(mo + sz for _, mo, sz in segs) + (bss_size if bss else 0)
    if size > IMAGE_LIMIT:
        raise NsoError('NSO image and BSS too large')
    image = bytearray(size)
    for i, (_, mo, sz) in enumerate(segs):
        image[mo:mo + sz] = decode(data, header, i)
    return bytes(image), data[0x40:0x50].hex(), [sz for _, _, sz in segs], bss_size
