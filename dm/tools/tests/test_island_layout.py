"""Conservative branch-island planning, without game data or loader changes."""
import sys
import random
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from island_layout import Area, LayoutError, Unit, plan, reachable, two_area
from nso_asm import B


class LayoutTests(unittest.TestCase):
    def test_branch_edges_and_alignment(self):
        r = 1 << 27
        self.assertTrue(reachable(0x10000000, 0x10000000 - r))
        self.assertTrue(reachable(0x10000000, 0x10000000 + r - 4))
        self.assertFalse(reachable(0x10000000, 0x10000000 - r - 4))
        self.assertFalse(reachable(0x10000000, 0x10000000 + r))
        self.assertFalse(reachable(0x10000000, 0x10000002))

    def test_two_areas_and_round_trip(self):
        result = plan(0x30000, 0x4000, 0x4000,
                      [Unit(0, 0x100, 0x20), Unit(0x2ff00, 0x2fffc, 0x20)], reach_bits=17)
        self.assertEqual([a.area for a in result], ['pre', 'after'])
        for unit, a in zip([Unit(0, 0x100, 0x20), Unit(0x2ff00, 0x2fffc, 0x20)], result):
            for src in (unit.low, unit.high):
                for dst in (a.start, a.end - 4):
                    self.assertTrue(reachable(src, dst, 17))
                    self.assertTrue(reachable(dst, src, 17))

    def test_separate_allocations_and_capacity(self):
        units = [Unit(0, 0, 0x2000), Unit(4, 4, 0x2000)]
        result = plan(0x30000, 0x4000, 0x4000, units, reach_bits=17)
        self.assertLessEqual(result[0].end, result[1].start)
        with self.assertRaisesRegex(LayoutError, 'cannot place'):
            plan(0x30000, 0x4000, 0x4000, units + [Unit(8, 8, 4)], reach_bits=17)

    def test_spanning_unit_cannot_be_split(self):
        with self.assertRaisesRegex(LayoutError, 'cannot place'):
            plan(0x30000, 0x4000, 0x4000, [Unit(0, 0x2fffc, 4)], reach_bits=17)

    def test_image_bounds_and_invalid_metadata(self):
        for args in ((0x30000, 0x4001, 0x4000, []), (0x30000, 0x4000, -1, []),
                     (0x30000, 0x4000, 0x4000, [Unit(0, 0x30000, 4)]),
                     (0x30000, 0x4000, 0x4000, [Unit(3, 4, 4)]),
                     (0x30000, 0x4000, 0x4000, [Unit(8, 4, 4)]),
                     (0x30000, 0x4000, 0x4000, [Unit(0, 0, 2)])):
            with self.subTest(args=args), self.assertRaises(LayoutError):
                plan(*args, reach_bits=18)

    def test_cross_area_jumps_must_be_checked_separately(self):
        a = plan(0x30000, 0x4000, 0x4000,
                 [Unit(0, 0, 4), Unit(0x2fffc, 0x2fffc, 4)], reach_bits=17)
        self.assertFalse(reachable(a[0].start, a[1].start, 17))
        self.assertFalse(reachable(a[1].start, a[0].start, 17))

    def test_real_scale_synthetic_extremes(self):
        text_size = 194640832
        image_size = 0xc41b000 + 0xef2570 + 0xba7a90 + 0x4000
        units = [Unit(0, 0, 64), Unit(0x6000000, 0x6000004, 64),
                 Unit(text_size - 4, text_size - 4, 64)]
        allocations = plan(image_size, 0x100000, 0x100000, units)
        self.assertEqual({a.area for a in allocations}, {'pre', 'after'})
        for unit, allocation in zip(units, allocations):
            for src in (unit.low, unit.high):
                for dst in (allocation.start, allocation.end - 4):
                    for a, b in ((src, dst), (dst, src)):
                        word = B(a, b)
                        signed = ((word & 0x3ffffff) ^ 0x2000000) - 0x2000000
                        self.assertEqual(a + signed * 4, b)

    def test_randomized_accepted_ranges_have_reachable_endpoints(self):
        rng = random.Random(0xFC27)
        for _ in range(1000):
            low = rng.randrange(0, 0x30000 // 4) * 4
            high = min(0x2fffc, low + rng.randrange(0, 64) * 4)
            unit = Unit(low, high, rng.randrange(1, 32) * 4)
            try:
                a = plan(0x30000, 0x4000, 0x4000, [unit], reach_bits=17)[0]
            except LayoutError:
                continue
            for src in (unit.low, unit.high):
                for dst in (a.start, a.end - 4):
                    self.assertTrue(reachable(src, dst, 17))
                    self.assertTrue(reachable(dst, src, 17))


class TwoAreaTests(unittest.TestCase):
    """The layout patch_nso.py emits through for text one area cannot reach."""

    UPDATE = dict(text=0xb99fbc0, image=0xd310000 + 0x4000, pre=0x1000000)

    def layout(self, **kw):
        d = dict(self.UPDATE, **kw)
        return two_area(d['image'], d['text'], pre_size=d['pre'])

    def test_fc27_split_covers_the_text_both_ways(self):
        l = self.layout()
        self.assertEqual(l.pre.off, -0x1000000)
        self.assertEqual(l.after.off, 0xd314000)
        self.assertLessEqual(l.after.off - (1 << 27), l.split)
        self.assertLess(l.split + 0x1000000, 1 << 27)
        # every site reaches its own area from the area's first byte and back
        for site in (0, 0x1000, l.split - 4, l.split, 0xb99fbc0 - 4):
            area = l.pre if site < l.split else l.after
            self.assertLess(abs(area.off - site), 1 << 27, (hex(site), area.name))

    def test_emission_point_keeps_sites_in_reach(self):
        # the pre area fills from -pre upwards, so a site just below the split is the
        # farthest from its stub: it must still be inside one B
        l = self.layout()
        for used in (0, 0x1000, 0x800000, 0x1000000 - 4):
            a = Area('pre', -0x1000000, cap=0x1000000)
            a.buf = bytearray(used)
            self.assertTrue(a.reaches(l.split - 4), (hex(used), hex(a.next)))
        a = Area('after', l.after.off)
        self.assertTrue(a.reaches(l.split))

    def test_pre_area_capacity_is_enforced(self):
        a = Area('pre', -0x8000, cap=0x8000)
        a.emit(0xd503201f)
        with self.assertRaisesRegex(LayoutError, 'patch area full'):
            a.buf = bytearray(0x8000)
            a.emit(0xd503201f)

    def test_unreachable_text_is_rejected_not_masked(self):
        with self.assertRaisesRegex(LayoutError, 'two patch areas cannot reach'):
            two_area(0xee00000, 0xedffffc, pre_size=0x1000000)
        with self.assertRaises(LayoutError):
            two_area(0x1000, 0x1000, pre_size=0x1001)
        with self.assertRaises(LayoutError):
            two_area(0x1000, 0x2000, pre_size=0x1000000)   # text beyond the image


    def test_alignment_of_both_areas(self):
        for image in (0x1000, 0x4000, 0x4001, 0xd314001):
            l = two_area(image, 0x1000, pre_size=0x1000000)
            self.assertEqual(l.after.off % 0x4000, 0)
            self.assertGreaterEqual(l.after.off, image)



if __name__ == '__main__':
    unittest.main()
