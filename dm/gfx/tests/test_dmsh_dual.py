"""Dual-source entry preserves MRT entry and compiles on both Apple targets."""
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dmsh_dual

SRC = '''#include <metal_stdlib>
using namespace metal;
struct main0_out { float4 a [[color(0)]]; float4 b [[color(1)]]; };
fragment main0_out main0() { main0_out out = {}; out.a=float4(0.25); out.b=float4(0.5); return out; }
'''

class Dual(unittest.TestCase):
    def test_variant_compiles(self):
        extra = dmsh_dual.variant(SRC)
        self.assertIn('[[color(0), index(1)]]', extra)
        self.assertIn('fragment main0_out_dual main0_dual(', extra)
        self.assertIn('main0_out_dual out', extra)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'dual.metal'; p.write_text(SRC + extra)
            for sdk in ['macosx', 'iphoneos']:
                r = subprocess.run(['xcrun', '-sdk', sdk, 'metal', '-fmodules-cache-path=' + str(Path(d)/'modules'), '-c', str(p), '-o', str(Path(d)/'dual.air')], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)

    def test_gpu_blend_and_mrt(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'probe.metal'; p.write_text(SRC + dmsh_dual.variant(SRC))
            binary = str(Path(d) / 'probe')
            subprocess.run(['clang', '-fobjc-arc', str(Path(__file__).with_name('t_dual_source.m')), '-framework', 'Metal', '-framework', 'Foundation', '-o', binary], check=True)
            subprocess.run([binary, str(p)], check=True)

    def test_other_outputs_unchanged(self):
        self.assertIsNone(dmsh_dual.variant(SRC.replace('color(1)', 'color(2)')))
        self.assertIn('[[color(1)]]', SRC)

if __name__ == '__main__': unittest.main()
