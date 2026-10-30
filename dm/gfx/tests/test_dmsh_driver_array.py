"""Indexed separate c2 textures must cover offsets beyond the 32-entry default."""
from pathlib import Path
import sys
import unittest
import ast
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dmsh_driver_array as d

SRC = '''struct spvDescriptorSetBuffer0
{
    array<texture2d<float>, 32> fp_t2d_cb196610_10570000 [[id(7)]];
    array<sampler, 32> fp_t2d_cb196610_10570000Smplr [[id(39)]];
    constant float4* tail [[id(71)]];
};
uint _317 = min(uint(_315), 31u);
int _1339 = int(_317);
uint _999 = min(uint(_998), 31u);
float4 color = set.fp_t2d_cb196610_10570000[_1339].sample(set.fp_t2d_cb196610_10570000Smplr[_1339], uv);
'''

class DriverArray(unittest.TestCase):
    def test_driver_extent_and_fixed_sampler(self):
        s = d.apply(SRC)
        self.assertIn('array<texture2d<float>, 173>', s)
        self.assertIn('min(uint(_315), 172u)', s)
        self.assertIn('uint _999 = min(uint(_998), 31u)', s)
        self.assertIn('sampler fp_t2d_cb196610_10570000Smplr [[id(180)]]', s)
        self.assertIn('tail [[id(181)]]', s)
        self.assertIn('Smplr, uv)', s)
        self.assertNotIn('Smplr[_1339]', s)
        # c2 offset 0x170 / 8 = 46: used to clamp incorrectly to 31.
        self.assertEqual(min(0x170 // 8, d.CAPACITY - 1), 46)

    def test_driver_read_contract(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'tools/dmsh_build.py').read_text())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'unfillable')
        env = {'DRV_FILL': {0: [(0, 16)], 2: [(0x20, 0x968)]}}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), '<contract>', 'exec'), env)
        reads = {'2': {'dynamic': True, 'vec4_offsets': []}}
        self.assertEqual(env['unfillable'](reads), ['c2 dynamic index'])
        binding = [{'kind':'tex_c2a', 'off':0, 'msl_type':'array<texture2d<float>, 173>'}]
        self.assertEqual(env['unfillable'](reads, binding), [])
        reads['2']['vec4_offsets'] = [0x1000]
        self.assertEqual(env['unfillable'](reads, binding), ['c2+0x1000'])
        self.assertEqual(env['unfillable']({'0': {'dynamic':True, 'vec4_offsets':[]}}, binding), ['c0 dynamic index'])

    def test_ordinary_arrays_unchanged(self):
        s = SRC.replace('cb196610', 'cb2')
        self.assertEqual(d.apply(s), s)

if __name__ == '__main__': unittest.main()
