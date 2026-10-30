"""Fail closed before the rewriter allocates unsupported NSO images."""
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from nso_asm import B


def header(flags, text_size, data_offset=0, data_size=0, bss=0):
    data = bytearray(0x100)
    data[:4] = b'NSO0'
    struct.pack_into('<I', data, 0x0c, flags)
    struct.pack_into('<III', data, 0x10, 0x100, 0, text_size)
    struct.pack_into('<III', data, 0x30, 0x100, data_offset, data_size)
    struct.pack_into('<I', data, 0x3c, bss)
    return data


class Preflight(unittest.TestCase):
    def run_rewriter(self, data, **extra):
        with tempfile.TemporaryDirectory() as tmp:
            source, out = Path(tmp) / 'in.nso', Path(tmp) / 'out'
            source.write_bytes(data)
            result = subprocess.run([sys.executable, str(TOOLS / 'patch_nso.py'), str(source), str(out), 'main'],
                                    capture_output=True, text=True, timeout=10, env={**os.environ, **extra})
            return result, out.exists()

    def test_zbic_does_not_fall_through_to_lz4(self):
        r, made = self.run_rewriter(header(0xbf, 0x1000))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('ZBIC-compressed NSO segments are not supported', r.stderr)
        self.assertNotIn('LZ4BlockError', r.stderr)
        self.assertFalse(made)

    def test_oversize_text_plans_two_areas_before_reading_segments(self):
        # 185.6 MB of text (EA SPORTS FC 27's main) is beyond one patch area but inside two:
        # the rewriter no longer rejects it up front, so the truncated fixture is stopped by
        # the segment range check, not by a single-area layout guard
        d = header(0, 194640832, 0xc41b000, 0xef2570, 0xba7a90)
        for override in ('0', '0x2000000'):
            with self.subTest(override=override):
                r, made = self.run_rewriter(d, DM_PATCH_FRONT=override)
                self.assertNotEqual(r.returncode, 0)
                self.assertNotIn('multiple patch areas are required', r.stderr)
                self.assertNotIn('exceeds two patch areas', r.stderr)
                self.assertIn('invalid file range or size', r.stderr)
                self.assertFalse(made)


    def test_branch_encoding_boundaries(self):
        for delta in (-0x8000000, 0x7fffffc):
            word = B(0x10000000, 0x10000000 + delta)
            imm = word & 0x3ffffff
            signed = (imm ^ 0x2000000) - 0x2000000
            self.assertEqual(signed * 4, delta)
        for delta in (-0x8000004, 0x8000000, 2):
            with self.assertRaises(AssertionError):
                B(0x10000000, 0x10000000 + delta)
        for frm, to in ((1, 5), (2, 6), (3, -1)):
            with self.assertRaises(AssertionError):
                B(frm, to)

    def test_branch_guard_survives_optimized_python(self):
        script = 'from nso_asm import B; B(0, 0x8000000)'
        env = {**os.environ, 'PYTHONPATH': str(TOOLS)}
        r = subprocess.run([sys.executable, '-O', '-c', script], capture_output=True, text=True, env=env, timeout=10)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('B out of range or unaligned', r.stderr)


if __name__ == '__main__':
    unittest.main()
