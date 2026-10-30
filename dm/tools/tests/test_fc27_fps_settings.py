import importlib.util
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'dm/games'))
import game
spec = importlib.util.spec_from_file_location('launcher_settings', ROOT/'dm/games/settings.py')
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)

class FC27Settings(unittest.TestCase):
    def test_default(self):
        g = game.load('0100C49025D3E000')
        self.assertEqual(g.get('fps_target'), '30')
        self.assertEqual(g.get('mem_reserve'), '0x142000000')
    def test_launcher(self):
        d = settings.build('0100C49025D3E000', '/tmp/no-rewrite', '/tmp/no-nacp')
        s = next(s for s in d['settings'] if s['env']=='DM_FPS_TARGET')
        self.assertEqual(s['default'], '30')
        self.assertEqual(s['options'], [['30','30 fps'],['60','60 fps (experimental)']])
        self.assertIn('restarting', s['note'])
    def test_only_one_profile_is_registered(self):
        self.assertEqual([g.id for g in game.all_games()], ['0100C49025D3E000'])
