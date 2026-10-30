"""Safety checks for real-run orchestration, using a tiny fake host only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name('smoke_real.py')


class SmokeRunnerSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.output = self.root / 'output'
        self.output.mkdir()
        self.seed = self.root / 'seed'
        self.seed.mkdir()
        (self.seed / 'progress').write_text('original')
        for name in ('base [01006BB00C6F0000].nsp',
                     'update [01006BB00C6F0800].nsp', 'prod.keys'):
            (self.root / name).touch()
        self.host = self.root / 'fake-host'
        self.host.write_text(
            '#!/usr/bin/env python3\n'
            'import json, os, sys\nfrom pathlib import Path\n'
            'Path("arguments.json").write_text(json.dumps(sys.argv))\n'
            'Path(os.environ["DM_SAVE"], "progress").write_text("test write")\n'
            'Path("environment.json").write_text(json.dumps({k:v for k,v in '
            'os.environ.items() if k.startswith("DM_")}))\n')
        self.host.chmod(0o755)
        self.cmd = [sys.executable, str(SCRIPT), '--root', str(self.root),
                    '--output', str(self.output), '--host', str(self.host),
                    '--profile', str(self.root / 'profile'), '--mode', 'nsp',
                    '--title','01006BB00C6F0000','--package','v131072',
                    '--seconds', '1', '--control', '--save-seed', str(self.seed)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_copy_and_environment_isolation(self):
        env = dict(os.environ, DM_ROMFS='must-not-inherit', DM_SAVE='must-not-use')
        result = subprocess.run(self.cmd, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.output / 'smoke-nsp'
        self.assertEqual((self.seed / 'progress').read_text(), 'original')
        self.assertEqual((run / 'save/progress').read_text(), 'test write')
        captured = json.loads((run / 'environment.json').read_text())
        self.assertNotIn('DM_ROMFS', captured)
        self.assertEqual(captured['DM_SAVE'], str(run / 'save'))
        self.assertEqual(captured['DM_CTL'], str(run / 'control.txt'))
        report = json.loads((run / 'summary.json').read_text())
        self.assertEqual(report['stop_reason'], 'process_exit')
        self.assertEqual(report['final_exit'], 0)
        again = subprocess.run(self.cmd, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual((run / 'save/progress').read_text(), 'test write')

    def test_reject_symlink_seed(self):
        (self.seed / 'link').symlink_to(self.root / 'prod.keys')
        result = subprocess.run(self.cmd, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.output / 'smoke-nsp/environment.json').exists())
        self.assertEqual((self.seed / 'progress').read_text(), 'original')

    def test_explicit_bundle_program_and_fonts(self):
        program=self.root/'bundle/program'; program.mkdir(parents=True)
        fonts=self.root/'bundle/font'; fonts.mkdir()
        result=subprocess.run(self.cmd+['--patched',str(program),'--fonts',str(fonts)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        run=self.output/'smoke-nsp'
        argv=json.loads((run/'arguments.json').read_text())
        self.assertEqual(argv[1],str(program.resolve()))
        captured=json.loads((run/'environment.json').read_text())
        self.assertEqual(captured['DM_FONT_DIR'],str(fonts.resolve()))
        self.assertEqual(json.loads((run/'summary.json').read_text())['patched'],str(program.resolve()))

    def test_mod_overlay_root_is_passed_and_must_exist(self):
        mods = self.root / 'mods/romfs'; mods.mkdir(parents=True)
        result = subprocess.run(self.cmd + ['--mods', str(mods)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        run = self.output / 'smoke-nsp'
        captured = json.loads((run / 'environment.json').read_text())
        self.assertEqual(captured['DM_ROMFS_OVERLAY'], str(mods.resolve()))
        self.assertEqual(json.loads((run / 'summary.json').read_text())['mods'], str(mods.resolve()))
        # A root that does not exist is a caller error, not something the host should discover mid-run.
        missing = subprocess.run(self.cmd + ['--mods', str(self.root / 'no-such-mods')], capture_output=True, text=True)
        self.assertNotEqual(missing.returncode, 0)

    def test_host_failure_is_not_reported_as_success(self):
        self.host.write_text('#!/usr/bin/env python3\nraise SystemExit(3)\n')
        result = subprocess.run(self.cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads((self.output / 'smoke-nsp/summary.json').read_text())
        self.assertEqual(report['final_exit'], 3)
        self.assertEqual(report['stop_reason'], 'process_exit')

    def test_other_title_and_base_only_do_not_inherit_update(self):
        (self.root/'wonder [010015100B514000].nsp').touch()
        cmd=list(self.cmd)
        cmd[cmd.index('--title')+1]='010015100B514000';cmd[cmd.index('--package')+1]='v0'
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        run=self.output/'smoke-nsp';env=json.loads((run/'environment.json').read_text())
        self.assertTrue(env['DM_RESOURCE_NSP'].endswith('wonder [010015100B514000].nsp'))
        self.assertNotIn('DM_RESOURCE_UPDATE',env)
        report=json.loads((run/'summary.json').read_text())
        self.assertEqual(report['title_id'],'010015100B514000');self.assertEqual(report['version'],'v0')


if __name__ == '__main__':
    unittest.main()
