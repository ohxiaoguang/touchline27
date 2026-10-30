"""NXDATA v1 wire format and streaming writer/reference reader (stdlib only)."""
import os
import struct
import zlib
from pathlib import Path

MAGIC = b'NXDATA\0\0'
HEADER = struct.Struct('<8sIIIIQQQQII')
ENTRY = struct.Struct('<IIQQII')
BLOCK = struct.Struct('<QIIII')
MAX_INDEX = 256 * 1024 * 1024


def valid_path(path):
    return (len(path.encode('utf-8')) <= 767 and '\\' not in path and '\0' not in path
            and (path == '' or all(p not in ('', '.', '..') and ':' not in p
                                   and len(p.encode('utf-8')) <= 768 for p in path.split('/'))))


def pack(root, output, block_size=262144, compress=True, force=False):
    root, output = Path(root).resolve(), Path(output).absolute()
    if not root.is_dir():
        raise ValueError('input must be a directory')
    if not 4096 <= block_size <= 1048576:
        raise ValueError('block size must be 4096..1048576')
    if output.resolve().is_relative_to(root):
        raise ValueError('output must be outside input tree')
    paths = [('', root, True)]
    # Only metadata is resident. Never follow links or accept devices/FIFOs.
    for parent, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            p = Path(parent) / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink() or not (p.is_dir() or p.is_file()):
                raise ValueError(f'unsupported file type: {rel}')
            if not valid_path(rel):
                raise ValueError(f'invalid path: {rel!r}')
            # nxnative stores case aliases in xattrs on case-insensitive APFS.
            parts = []
            for component in p.relative_to(root).parts:
                parts.append(component)
                physical = root.joinpath(*parts)
                try:
                    alias = os.getxattr(physical, 'org.d2rmobile.guest-name').decode('utf-8')
                except OSError:
                    alias = component
                if len(parts) == 1:
                    logical = alias
                else:
                    logical += '/' + alias
            if not valid_path(logical):
                raise ValueError(f'invalid guest path: {logical!r}')
            paths.append((logical, p, p.is_dir()))
    paths.sort(key=lambda item: item[0].encode('utf-8'))
    if len({p[0] for p in paths}) != len(paths):
        raise ValueError('duplicate logical path')
    entries, blocks, pool = [], [], bytearray()
    raw_total = 0
    # Exclusive creation by default. --force is an explicit destructive overwrite.
    with output.open('wb' if force else 'xb') as out:
        out.write(bytes(64))
        for rel, path, directory in paths:
            po = len(pool)
            encoded = rel.encode('utf-8')
            pool.extend(encoded + b'\0')
            first, size = len(blocks), 0
            if not directory:
                with path.open('rb') as source:
                    while data := source.read(block_size):
                        stored = zlib.compress(data, 1) if compress else data
                        codec = int(compress and len(stored) < len(data))
                        if not codec:
                            stored = data
                        blocks.append((out.tell(), len(stored), len(data), codec, zlib.crc32(data)))
                        out.write(stored)
                        size += len(data)
                raw_total += size
            entries.append((po, len(encoded), size, first, len(blocks) - first, int(directory)))
        index_at = out.tell()
        index = b''.join(ENTRY.pack(*e) for e in entries) + b''.join(BLOCK.pack(*b) for b in blocks) + pool
        if len(index) > MAX_INDEX:
            raise ValueError('index exceeds v1 limit')
        out.write(index)
        header = HEADER.pack(MAGIC, 1, 64, block_size, 0, index_at, len(index), len(entries), len(blocks), zlib.crc32(index), 0)
        out.seek(0)
        out.write(header[:60] + struct.pack('<I', zlib.crc32(header[:60])))
        out.flush()
        os.fsync(out.fileno())
    return dict(files=sum(not p[2] for p in paths), directories=sum(p[2] for p in paths),
                raw_bytes=raw_total, archive_bytes=output.stat().st_size, blocks=len(blocks))


class Archive:
    def __init__(self, path):
        self.f = open(path, 'rb')
        try:
            h = self.f.read(64)
            magic, ver, hs, self.bs, flags, at, size, ne, nb, crc, hc = HEADER.unpack(h)
            if (magic != MAGIC or ver != 1 or hs != 64 or flags or not 4096 <= self.bs <= 1048576
                    or zlib.crc32(h[:60]) != hc or size > MAX_INDEX or at < 64
                    or at + size != os.fstat(self.f.fileno()).st_size or ne < 1
                    or ne * ENTRY.size + nb * BLOCK.size > size):
                raise ValueError('invalid header/version/bounds')
            self.f.seek(at)
            index = self.f.read(size)
            if len(index) != size or zlib.crc32(index) != crc:
                raise ValueError('index checksum mismatch')
            pool = index[ne * 32 + nb * 24:]
            self.blocks = [BLOCK.unpack_from(index, ne * 32 + i * 24) for i in range(nb)]
            self.entries = {}
            previous, next_block, next_data, pool_end = None, 0, 64, 0
            for i in range(ne):
                po, pl, length, first, count, kind = ENTRY.unpack_from(index, i * 32)
                if po != pool_end or po + pl >= len(pool) or pool[po + pl] != 0:
                    raise ValueError('path bounds')
                raw = pool[po:po + pl]
                name = raw.decode('utf-8', errors='strict')
                if (not valid_path(name) or (previous is not None and raw <= previous)
                        or kind not in (0, 1) or first != next_block or count > nb - first
                        or (kind and (length or count)) or length > (1 << 63) - 1
                        or (not kind and count != (length + self.bs - 1) // self.bs)
                        or (i == 0 and (name != '' or kind != 1))):
                    raise ValueError('invalid/duplicate entry')
                if i and (name.rpartition('/')[0] not in self.entries
                          or not self.entries[name.rpartition('/')[0]][1]):
                    raise ValueError('parent missing or not directory')
                for j in range(count):
                    off, stored, raw_len, codec, checksum = self.blocks[first + j]
                    expected = min(self.bs, length - j * self.bs)
                    if (off != next_data or not 0 < stored <= self.bs or raw_len != expected
                            or codec not in (0, 1) or (codec == 0 and stored != raw_len)
                            or (codec == 1 and stored >= raw_len) or stored > at - off):
                        raise ValueError('invalid block bounds/codec')
                    next_data += stored
                self.entries[name] = (length, kind, first, count)
                next_block += count
                pool_end += pl + 1
                previous = raw
            if next_block != nb or next_data != at or pool_end != len(pool):
                raise ValueError('unreferenced index/payload')
        except BaseException:
            self.f.close()
            raise

    def close(self):
        self.f.close()

    def read(self, name, offset=0, size=None):
        length, kind, first, count = self.entries[name]
        if kind or offset < 0 or (size is not None and size < 0):
            raise ValueError('invalid read')
        remaining = max(0, length - offset) if size is None else min(size, max(0, length - offset))
        result = bytearray()
        while remaining:
            block, within = divmod(offset, self.bs)
            at, stored, raw_len, codec, crc = self.blocks[first + block]
            self.f.seek(at)
            data = self.f.read(stored)
            if codec:
                decoder = zlib.decompressobj()
                data = decoder.decompress(data, raw_len + 1)
                if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
                    raise ValueError('invalid compressed block')
            if len(data) != raw_len or zlib.crc32(data) != crc:
                raise ValueError('block checksum mismatch')
            n = min(remaining, raw_len - within)
            result += data[within:within + n]
            remaining -= n
            offset += n
        return bytes(result)
