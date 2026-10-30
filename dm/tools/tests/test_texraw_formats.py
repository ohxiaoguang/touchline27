"""Metal format numbers and packed HDR read-back regression tests."""
import importlib.util
from pathlib import Path
import struct
import unittest

spec = importlib.util.spec_from_file_location('texraw', Path(__file__).resolve().parents[1] / 'texraw2png.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class Formats(unittest.TestCase):
    def test_packed_hdr_one(self):
        # Unsigned floats: five exponent bits, six/six/five mantissa bits.
        word = (15 << 6) | ((15 << 6) << 11) | ((15 << 5) << 22)
        self.assertEqual(t.TEXEL[92], 4)
        self.assertEqual(t.decode(92, struct.pack('<I', word), 1, False), (255, 255, 255))

    def test_rgb10a2_channels(self):
        self.assertEqual(t.TEXEL[90], 4)
        self.assertEqual(t.decode(90, struct.pack('<I', 1023 | (3 << 30)), 1, False), (255, 0, 0))

    def test_half_and_full_float_formats(self):
        self.assertEqual(t.decode(115, struct.pack('<4e', 1, 0, 0, 1), 1, False), (255, 0, 0))
        self.assertEqual(t.TEXEL[125], 16)
        self.assertEqual(t.TEXEL[252], 4)

    def test_hdr_subnormal(self):
        self.assertEqual(t.unsigned_float(1, 6), 2 ** -20)
        self.assertEqual(t.unsigned_float(15 << 5, 5), 1)


if __name__ == '__main__':
    unittest.main()
