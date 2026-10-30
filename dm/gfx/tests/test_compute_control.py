"""Compute jobs must retain launch dimensions without a profile answer row."""
import ast
from pathlib import Path
import struct
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools' / 'dmsh_build.py'
TREE = ast.parse(SOURCE.read_text())
JOB = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'job_for')


class ComputeControl(unittest.TestCase):
    def job(self, facts, dims=(4, 4, 4), shared=17):
        # A package record with headerless compute instructions and a GLSLC control section.
        rec = bytearray(0x38 + 32 + 0x800)
        ci = 0x38 + 32
        rec[ci:ci + 4] = bytes.fromhex('34127698')
        struct.pack_into('<4I', rec, ci + 0x748, *dims, shared)
        env = dict(struct=struct, os=__import__('os'), FACTS=facts)
        exec(compile(ast.Module(body=[JOB], type_ignores=[]), str(SOURCE), 'exec'), env)
        with tempfile.TemporaryDirectory() as d:
            return env['job_for']('fixture', 'cs_fixture', bytes(rec), d)[0]

    def test_absent_facts_keeps_control_dimensions(self):
        j = self.job({})
        self.assertEqual(j['local'], [4, 4, 4])
        self.assertEqual(j['shared'], 32)
        self.assertTrue(j['no_facts'])

    def test_other_profile_answers_do_not_erase_dimensions(self):
        j = self.job({'fixture': {'tex': {'90': '3d'}}}, dims=(8, 8, 1), shared=0)
        self.assertEqual(j['local'], [8, 8, 1])
        self.assertEqual(j['shared'], 0)

    def test_explicit_profile_answers_remain_authoritative(self):
        j = self.job({'fixture': {'local': [64, 1, 1], 'shared': 48}})
        self.assertEqual(j['local'], [64, 1, 1])
        self.assertEqual(j['shared'], 48)

    def test_zero_control_is_not_guessed(self):
        self.assertNotIn('local', self.job({}, dims=(0, 0, 0)))


if __name__ == '__main__':
    unittest.main()
