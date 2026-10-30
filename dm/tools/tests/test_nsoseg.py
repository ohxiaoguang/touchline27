import hashlib
import os
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nsoseg


def fixture(compressed=False):
    import lz4.block
    parts = [b'abcd' * 4, b'efgh' * 4, b'ijkl' * 4]
    data = bytearray(0x100)
    data[:4] = b'NSO0'
    struct.pack_into('<I', data, 12, 0x38 | (7 if compressed else 0))
    for i, part in enumerate(parts):
        stored = lz4.block.compress(part, store_size=False) if compressed else part
        struct.pack_into('<III', data, 0x10 + 16 * i, len(data), i * 0x20, len(part))
        struct.pack_into('<I', data, 0x60 + 4 * i, len(stored))
        data[0xa0 + 32 * i:0xc0 + 32 * i] = hashlib.sha256(part).digest()
        data.extend(stored)
    return data, parts


class Segments(unittest.TestCase):
    def test_raw_and_lz4(self):
        for compressed in (False, True):
            d, parts = fixture(compressed)
            h = nsoseg.parse(d)
            self.assertEqual([nsoseg.decode(d, h, i) for i in range(3)], parts)

    def test_corruption_and_ranges(self):
        d, _ = fixture()
        for mutator in (
            lambda x: x.__setitem__(slice(0, 4), b'bad!'),
            lambda x: x.__delitem__(slice(-1, None)),
            lambda x: struct.pack_into('<I', x, 0x20, 0x100),
            lambda x: struct.pack_into('<I', x, 0x10, 0xff),
            lambda x: struct.pack_into('<I', x, 12, 0x100),
        ):
            copy = bytearray(d)
            mutator(copy)
            with self.assertRaises(nsoseg.NsoError): nsoseg.parse(copy)
        d[-1] ^= 1
        with self.assertRaisesRegex(nsoseg.NsoError, 'SHA-256'): nsoseg.decode(d, nsoseg.parse(d), 2)

    def test_short_zbic_frame(self):
        for raw in (b'', b'Z', b'ZB', b'ZBI', b'nope'):
            with self.assertRaises(nsoseg.NsoError): nsoseg._zbic(raw, 16)

    def test_zbic_needs_explicit_library(self):
        old = os.environ.pop('NX_ZBIC_LIBRARY', None)
        try:
            with self.assertRaisesRegex(nsoseg.NsoError, 'external decoder'): nsoseg._zbic(b'ZBIC', 16)
        finally:
            if old is not None: os.environ['NX_ZBIC_LIBRARY'] = old

    @unittest.skipUnless(os.environ.get('NX_ZBIC_LIBRARY'), 'external ZBIC library not configured')
    def test_external_zbic_frame_and_bad_sizes(self):
        payload = b'synthetic segment'
        frame = b'ZBIC' + bytes([0x20, len(payload)]) + struct.pack('<I', 1 | (len(payload) << 3))[:3] + payload
        self.assertEqual(nsoseg._zbic(frame, len(payload)), payload)
        for bad_frame, size in ((frame[:-1], len(payload)), (frame, len(payload) - 1), (frame, len(payload) + 1)):
            with self.assertRaises(nsoseg.NsoError): nsoseg._zbic(bad_frame, size)


if __name__ == '__main__': unittest.main()
