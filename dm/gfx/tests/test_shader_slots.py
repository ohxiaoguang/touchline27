"""Buffer-location contracts of a generated vertex library: synthetic MSL, no extracted game shaders.

The failure this pins down: FIFA 23's 862235caa035b230 and a1feb9dd02bc6e19 did not compile, because their main0_gs
declared constant dm_geometry_capture& dm_gs [[buffer(13)]] beside constant dm_ptrfix* _pf [[buffer(13)]]
("cannot reserve 'buffer' resource location at index 13"). Both tools picked their own constant; nothing checked the
result. dmsh_slots.py allocates instead, and these tests hold the two ends of that: the plan never hands one index to
two purposes, and the generated source never declares one index twice in one entry point.
"""
from pathlib import Path
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import dmsh_geometry
import dmsh_ptrfix
import dmsh_slots

# A vertex shader as spirv-cross writes it, with the unresolved indirect read the translator leaves behind (the shape
# dmsh_ptrfix rewrites). The capture entry point is generated from this source, not written by hand.
SOURCE = '''#include <metal_stdlib>
using namespace metal;
struct Data { uint _m0[1024]; };
struct spvDescriptorSetBuffer0
{
    const device Data* vp_s0 [[id(0)]];
};
static inline __attribute__((always_inline))
int indirect(thread const int& _1, thread const int& _2)
{
    return 0;
}
struct main0_out
{
    float4 gl_Position [[position]];
    float4 m_0 [[user(locn0)]];
};
vertex main0_out main0(constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]], uint dm_vid [[vertex_id]])
{
    main0_out out = {};
    out.gl_Position = float4(float(dm_vid));
    out.m_0 = float4(0.0);
    int v = indirect(int(dm_vid), 0);
    return out;
}
'''

# A vertex shader with no indirect read: only the capture record is added.
PLAIN = SOURCE.replace('''static inline __attribute__((always_inline))
int indirect(thread const int& _1, thread const int& _2)
{
    return 0;
}
''', '')
PLAIN = PLAIN.replace('    int v = indirect(int(dm_vid), 0);\n', '')


def vertex_library(source, tf=False):
    """What dmsh_build.py finish() assembles for a vertex shader, in the same order, with the same plan."""
    plan = dmsh_slots.plan(ptrfix=dmsh_ptrfix.wanted(source, 'vs'), tf=tf)
    capture = dmsh_geometry.capture(source, plan['capture'])
    full = source + capture
    if tf:   # main0_tf: the same body writing its outputs into four feedback buffers (dmsh_build.py vs_tf)
        full += ('\nvertex void main0_tf(constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]], uint dm_vid [[vertex_id]])\n'
                 '{ dm_tf0[dm_vid] = 0u; }\n')
    full, pf = dmsh_ptrfix.apply(full, 'vs', plan)
    return full, plan, pf


class SlotPlan(unittest.TestCase):
    def test_no_purpose_shares_an_index(self):
        for ptrfix in (False, True):
            for tf in (False, True):
                with self.subTest(ptrfix=ptrfix, tf=tf):
                    p = dmsh_slots.plan(ptrfix, tf)
                    used = [p['capture'], *p['tf'], *([p['ptrfix_base'], p['ptrfix_pool']] if ptrfix else [])]
                    self.assertEqual(len(used), len(set(used)), f'{used} has a repeat')

    def test_capture_keeps_its_index_until_something_takes_it(self):
        self.assertEqual(dmsh_slots.plan(ptrfix=False, tf=False)['capture'], 13)
        self.assertEqual(dmsh_slots.plan(ptrfix=False, tf=True)['capture'], 13)
        # The indirect-read bindings own 12 and 13, so the capture record moves below the feedback range
        moved = dmsh_slots.plan(ptrfix=True, tf=False)
        self.assertEqual((moved['ptrfix_base'], moved['ptrfix_pool'], moved['capture']), (13, 12, 7))
        self.assertEqual(dmsh_slots.plan(ptrfix=True, tf=True)['capture'], 7)

    def test_plan_stays_inside_the_ranges_the_host_owns(self):
        for ptrfix in (False, True):
            for tf in (False, True):
                p = dmsh_slots.plan(ptrfix, tf)
                self.assertTrue(0 < p['capture'] <= dmsh_slots.CAPTURE_FIRST)   # the auxiliary block below the streams
                self.assertNotIn(p['capture'], range(dmsh_slots.STREAM_FIRST, dmsh_slots.ZERO + 1))


class GeneratedEntryPoints(unittest.TestCase):
    def test_capture_beside_indirect_reads_compiles_with_one_slot_each(self):
        msl, plan, pf = vertex_library(SOURCE)
        self.assertTrue(pf['applied'])
        self.assertEqual(pf['slot'], plan['ptrfix_base'])
        self.assertEqual(pf['pool_slot'], plan['ptrfix_pool'])
        self.assertEqual(dmsh_slots.conflicts(msl), [])
        entries = dict(dmsh_slots.entries(msl))
        self.assertEqual(entries['main0_gs'], [0, plan['capture'], plan['ptrfix_base'], plan['ptrfix_pool']])
        self.assertEqual(entries['main0'], [0, plan['ptrfix_base'], plan['ptrfix_pool']])

    def test_the_fixed_indices_of_both_tools_reproduce_the_original_failure(self):
        # What the tools did before the plan: capture at 13, and dmsh_ptrfix on the fixed pair. main0_gs is the only
        # function that ends up holding both - which is why only that entry point failed and main0 built fine.
        plan = {'capture': 13, 'ptrfix_base': 13, 'ptrfix_pool': 12}
        msl, _ = dmsh_ptrfix.apply(SOURCE + dmsh_geometry.capture(SOURCE, 13), 'vs', plan)
        self.assertIn(('main0_gs', 13), dmsh_slots.conflicts(msl))
        # main0 alone is still consistent, exactly as in the two failing shaders
        self.assertNotIn(('main0', 13), dmsh_slots.conflicts(msl))

    def test_capture_without_indirect_reads_is_unchanged(self):
        msl, plan, pf = vertex_library(PLAIN)
        self.assertIsNone(pf)
        self.assertEqual(plan['capture'], 13)
        self.assertEqual(dmsh_slots.conflicts(msl), [])
        self.assertEqual(dict(dmsh_slots.entries(msl))['main0_gs'], [0, 13])

    def test_transform_feedback_stays_clear_of_the_capture_record(self):
        msl, plan, _ = vertex_library(PLAIN, tf=True)
        self.assertEqual(plan['tf'], [8, 9, 10, 11])
        self.assertNotIn(plan['capture'], range(8, 12))
        self.assertEqual(dmsh_slots.conflicts(msl), [])


class Validator(unittest.TestCase):
    def test_reads_every_entry_point_and_ignores_comments(self):
        msl = '''// kernel void decoy(device uint* a [[buffer(3)]], device uint* b [[buffer(3)]])
kernel void k(device uint* a [[buffer(0)]], device uint* b [[buffer(1)]])
{
    // a third [[buffer(0)]] in a comment is not a declaration
}
fragment float4 f(texture2d<float> t [[texture(0)]])
{
    return t.read(uint2(0));
}
'''
        self.assertEqual(dmsh_slots.conflicts(msl), [])
        self.assertEqual(dmsh_slots.entries(msl), [('k', [0, 1]), ('f', [])])

    def test_library_audit_reports_a_duplicate_and_a_missing_slot(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'aaaaaaaaaaaaaaaa_b.metal').write_text(SOURCE + dmsh_geometry.capture(SOURCE, 13))
            Path(d, 'aaaaaaaaaaaaaaaa_b.json').write_text(json.dumps({'key': 'aaaaaaaaaaaaaaaa_b', 'entry_geometry_capture': 'main0_gs'}))
            findings = dmsh_slots.check_library(d)
            self.assertEqual(len(findings), 1)
            self.assertIn('no geometry_capture_slot', findings[0])
            Path(d, 'aaaaaaaaaaaaaaaa_b.json').write_text(json.dumps({'key': 'aaaaaaaaaaaaaaaa_b', 'entry_geometry_capture': 'main0_gs', 'geometry_capture_slot': 13}))
            self.assertEqual(dmsh_slots.check_library(d), [])
            Path(d, 'aaaaaaaaaaaaaaaa_b.metal').write_text(dmsh_ptrfix.apply(SOURCE + dmsh_geometry.capture(SOURCE, 13), 'vs',
                                                                             {'capture': 13, 'ptrfix_base': 13, 'ptrfix_pool': 12})[0])
            findings = dmsh_slots.check_library(d)
            self.assertEqual(len(findings), 1)
            self.assertIn('buffer(13)', findings[0])


@unittest.skipUnless(os.environ.get('DMSH_LIB'), 'set DMSH_LIB=<library root>/b-<chain> to audit a built library')
class BuiltLibrary(unittest.TestCase):
    def test_no_entry_point_declares_one_index_twice(self):
        self.assertEqual(dmsh_slots.check_library(os.environ['DMSH_LIB']), [])


if __name__ == '__main__':
    unittest.main()
