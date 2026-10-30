"""The guest address-space partition of a game profile (game.tsv mem_prefix / mem_alias / mem_stack / mem_reserve, read by dm/games/game.py header into game_profile.h and
laid out by dm/host/hle_svc.c mem_init): every profile leaves the heap room, and a profile that does not is refused where it is read, not at the host's start.
No game files (temporary profile folders only)."""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'dm/games'))
import game   # noqa: E402

MACRO = re.compile(r'^#define (DM_GAME_\w+) (.*)$', re.M)


def macros(text): return dict(MACRO.findall(text))
def num(m, key): return int(m[key].rstrip('ull'), 0)


def profile(tmp, **keys):
    """a profile folder with the keys header() needs, plus mem_prefix / stdalloc_cap when given"""
    d = tmp / '0100000000000000'
    d.mkdir(parents=True, exist_ok=True)
    rows = {'title_id': '0100000000000000', 'name': 'Test', 'program_id': '0100000000000000', 'modules': 'main sdk', 'romfs_marker': 'a/b.toc',
            'mem_reserve': '0x142000000', 'mem_alias': '0xF0000000', 'mem_stack': '0x4000000', 'app_pool': '0xCD500000'}
    rows.update(keys)
    (d / 'game.tsv').write_text(''.join(f'{k}\t{v}\n' for k, v in rows.items()))
    return str(d)


class Profiles(unittest.TestCase):
    def test_every_profile_has_room_for_its_heap(self):
        games = game.all_games()
        self.assertEqual([g.id for g in games], ['0100C49025D3E000'])
        for g in games:
            with self.subTest(game=g.id):
                m = macros(game.header(g))
                reserve, alias, stack, prefix = num(m, 'DM_GAME_MEM_RESERVE'), num(m, 'DM_GAME_MEM_ALIAS'), num(m, 'DM_GAME_MEM_STACK'), num(m, 'DM_GAME_MEM_PREFIX')
                self.assertLess(prefix + alias + stack, reserve)
                for v in (reserve, alias, stack, prefix): self.assertEqual(v & 0x3fff, 0, f'{g.id}: {v:#x} is no whole page')
                self.assertGreaterEqual(alias, 0x10000000)       # the host's DM_ALIAS_SIZE floor: the SDK's node area alone needs far less, but no profile goes below it

    def test_the_profile_values_reach_the_header(self):
        m = macros(game.header(game.load('0100C49025D3E000')))
        self.assertEqual([num(m, k) for k in ('DM_GAME_MEM_RESERVE', 'DM_GAME_MEM_PREFIX', 'DM_GAME_MEM_ALIAS', 'DM_GAME_MEM_STACK')],
                         [0x142000000, 0x1000000, 0xF0000000, 0x4000000])
        self.assertEqual(num(m, 'DM_GAME_STDALLOC_CAP'), 0)   # no stdalloc_cap row: the host gives it what the alias region has room for

    def test_prefix_and_stdalloc_cap_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = macros(game.header(game.load(profile(Path(tmp)))))
            self.assertEqual(num(m, 'DM_GAME_MEM_PREFIX'), 0x10000000)
            self.assertEqual(num(m, 'DM_GAME_STDALLOC_CAP'), 0)
            m = macros(game.header(game.load(profile(Path(tmp), mem_prefix='0x4000000', stdalloc_cap='0x20000000'))))
            self.assertEqual(num(m, 'DM_GAME_MEM_PREFIX'), 0x4000000)
            self.assertEqual(num(m, 'DM_GAME_STDALLOC_CAP'), 0x20000000)


class Refusals(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, self.tmp)

    def refused(self, **keys):
        with self.assertRaises(SystemExit) as e:
            game.header(game.load(profile(self.tmp, **keys)))
        return str(e.exception)

    def test_a_partition_that_leaves_no_heap(self):
        # exactly the block, and one page short of it: the heap (the rest of the block) would be empty or negative
        for reserve in ('0xF5000000', '0xF4FFC000'):
            with self.subTest(reserve=reserve):
                self.assertIn('leaves no heap', self.refused(mem_reserve=reserve, mem_prefix='0x1000000', mem_alias='0xF0000000', mem_stack='0x4000000'))
        # the default prefix (256 MB) is part of the sum too
        self.assertIn('leaves no heap', self.refused(mem_reserve='0xF5000000', mem_alias='0xF0000000', mem_stack='0x4000000'))

    def test_parts_that_are_no_whole_pages(self):
        for keys in ({'mem_prefix': '0x1000400'}, {'mem_alias': '0xF0001000'}, {'mem_stack': '0x4000001'}, {'mem_reserve': '0x142001000'}):
            with self.subTest(**keys):
                self.assertIn('whole 16 KB pages', self.refused(**keys))

    def test_a_partition_one_page_below_is_accepted(self):
        m = macros(game.header(game.load(profile(self.tmp, mem_reserve='0xF5004000',
                                                 mem_prefix='0x1000000', mem_alias='0xF0000000', mem_stack='0x4000000'))))
        self.assertEqual(num(m, 'DM_GAME_MEM_RESERVE') - num(m, 'DM_GAME_MEM_PREFIX') - num(m, 'DM_GAME_MEM_ALIAS') - num(m, 'DM_GAME_MEM_STACK'), 0x4000)


if __name__ == '__main__':
    unittest.main()
