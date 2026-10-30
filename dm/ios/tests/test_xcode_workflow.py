"""Exercise the preparation pipeline with synthetic inputs, and stage tiny resources."""
from contextlib import ExitStack, redirect_stdout
import io
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
for folder in ('scripts', 'dm/games', 'dm/tools', 'dm/ios/tools'):
    sys.path.insert(0, str(REPO / folder))
import build_ipa_from_nsp as build
import game
import gen_resources
import nacp
import profile_guess
import xcode_projects


class XcodePipelineTests(unittest.TestCase):
    def test_provisional_warning_stays_json(self):
        output = io.StringIO()
        profile = SimpleNamespace(dir=Path('/external/profile/fixture'), id='fixture')
        with patch.object(build, 'PROG', build.Progress('json')), redirect_stdout(output):
            build.report_profile_status(profile, profile, 'v0', False, True, 'Xcode project')
        events = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertIn('Xcode project was built from a provisional', events[0]['msg'])


class ResourceStagingTests(unittest.TestCase):
    def test_nvn_vulkan_gl_and_incremental_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve() / "Game's $ literal `ticks`"
            ios, romfs, shaders, aoc = [root / name for name in ('xcode', 'romfs', 'shaders', 'aoc')]
            for folder in (ios / 'Gen', romfs, aoc / '1'):
                folder.mkdir(parents=True)
            (ios / 'Gen/dm.xcconfig').touch()
            (romfs / 'marker').write_text('game')
            (aoc / '1/content').write_text('dlc')
            chain_h = root / 'dmsh_chain.h'
            chain_h.write_text('#define DMSH_CHAIN "fixture"\n')
            app = root / 'products/DmIOS.app'
            environment = dict(os.environ, SRCROOT=str(ios), TARGET_BUILD_DIR=str(app.parent),
                               UNLOCALIZED_RESOURCES_FOLDER_PATH=app.name, PLATFORM_NAME='iphoneos')
            for chain in ('b-fixture', 'vk', 'gl'):
                with self.subTest(chain=chain):
                    shader = shaders / chain
                    shader.mkdir(parents=True)
                    (shader / 'fixture.metallib').write_text(chain)
                    arguments = ['gen_resources.py', str(ios), str(romfs), 'marker', str(shader), chain, str(aoc), str(root / 'dd'), str(chain_h)]
                    with patch.object(sys, 'argv', arguments):
                        gen_resources.main()
                    result = subprocess.run(['bash', str(REPO / 'dm/ios/tools/stage_resources.sh')],
                                            env=environment, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual((app / 'romfs/marker').read_text(), 'game')
                    self.assertEqual((app / 'msl' / chain / 'fixture.metallib').read_text(), chain)
                    self.assertEqual([p.name for p in (app / 'msl').iterdir()], [chain])
                    self.assertEqual((app / 'aoc/1/content').read_text(), 'dlc')
            # Sources moved to another shader chain since preparing: stop before copying anything.
            arguments = ['gen_resources.py', str(ios), str(romfs), 'marker', str(shaders / 'b-fixture'), 'b-fixture', str(aoc), str(root / 'dd'), str(chain_h)]
            with patch.object(sys, 'argv', arguments):
                gen_resources.main()
            chain_h.write_text('#define DMSH_CHAIN "newer"\n')
            result = subprocess.run(['bash', str(REPO / 'dm/ios/tools/stage_resources.sh')],
                                    env=environment, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('prepare the game again', result.stderr)
            self.assertEqual([p.name for p in (app / 'msl').iterdir()], ['gl'])
            # A disconnected drive fails before deleting the last good app's resources.
            (romfs / 'marker').unlink()
            result = subprocess.run(['bash', str(REPO / 'dm/ios/tools/stage_resources.sh')],
                                    env=environment, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue((app / 'romfs/marker').exists())
            self.assertTrue((app / 'msl/gl/fixture.metallib').exists())
            # Unsigned IPA mode bypasses staging even without a device or mounted data.
            environment.update(DM_COPY_GAME_RESOURCES='NO', PLATFORM_NAME='iphonesimulator')
            result = subprocess.run(['bash', str(REPO / 'dm/ios/tools/stage_resources.sh')], env=environment)
            self.assertEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
