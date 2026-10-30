"""Unified workflow routing, reuse and failure preservation without game assets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import io
from contextlib import redirect_stdout
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_prepared_build as fixtures
from tools.nxrom import build_pipeline as flow
from scripts import build_external_nsp as entry

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'games'))
import game


class UnifiedBuild(unittest.TestCase):
    def setUp(self):
        self.f=fixtures.PreparedBuild();self.f.setUp();f=self.f
        f.profile.dir=f.profile_dir;f.profile.title_id=int(f.profile.id,16)
        self.keys=f.root/'private.keys';self.keys.write_text('synthetic secret')
        self.extractor=f.root/'nx_extract';self.extractor.touch();self.extractor.chmod(0o755)
        self.a=SimpleNamespace(nsp_dir=f.root,keys=self.keys,profile=f.profile_dir,
             work=f.root/'new-work',prepared=None,shader_context=None,nsp_extractor=self.extractor,
             package='v0',target='both',app_name='Test',jobs=3,progress='off')
        self.repo=Path(__file__).resolve().parents[3]
        self.commands=[]

    def tearDown(self): self.f.tearDown()

    def invoke(self,fail=None):
        a=self.a;f=self.f;prepared=a.prepared or a.work/'prepared';context=a.shader_context or a.work/'shaders'
        def run(cmd,**kw):
            self.commands.append(cmd)
            if fail and fail in str(cmd): raise subprocess.CalledProcessError(1,cmd)
            if '--prepare-nsp-resources' in cmd:
                prepared.mkdir();(prepared/'ready.json').write_text('{}')
            elif 'compile_nsp_shaders.py' in str(cmd):
                context.mkdir();(context/'shader-summary.json').write_text('{}')
            else:
                w=a.work/('macos' if 'build_mac_app.py' in str(cmd) else 'ios');w.mkdir()
                (w/'build-report.json').write_text('{}')
                if w.name=='ios': (w/'Test.ipa').write_bytes(b'fake archive')
        result=(f.root,a.work,self.keys,f.profile,prepared,context,dict(os.environ),self.extractor)
        with patch.object(flow,'preflight',return_value=result),patch.object(game,'Game',return_value=f.profile),\
             patch.object(flow,'validate_prepared'),patch.object(flow,'validate_context'),\
             patch.object(flow.subprocess,'run',side_effect=run):
            return flow.build(a,self.repo)

    def test_fresh_stage_order_and_explicit_no_romfs_routes(self):
        r=self.invoke()
        self.assertEqual([s['name'] for s in r['stages']],['prepare','shaders','macos','ios'])
        self.assertEqual(r['status'],'complete');self.assertEqual(len(self.commands),4)
        self.assertIn('--prepare-nsp-resources',self.commands[0]);self.assertIn('--jobs',self.commands[1])
        self.assertIn('--use-nsp-prepared',self.commands[2]);self.assertIn('--use-nsp-prepared',self.commands[3])
        text=(self.a.work/'pipeline-report.json').read_text()
        self.assertNotIn(str(self.keys),text);self.assertNotIn('synthetic secret',text)
        self.assertFalse(r['game_run_verified']);self.assertFalse(r['device_run_verified'])

    def test_explicit_reuse_skips_preparation_and_compile(self):
        self.a.prepared=self.f.prep;self.a.shader_context=self.f.context
        before=(self.f.prep/'ready.json').read_bytes()
        r=self.invoke();self.assertEqual(len(self.commands),2)
        self.assertEqual([s['status'] for s in r['stages'][:2]],['reused','reused'])
        self.assertEqual(before,(self.f.prep/'ready.json').read_bytes())

    def test_each_platform_can_build_alone(self):
        for target in ('macos','ios'):
            self.a.target=target;self.a.work=self.f.root/('single-'+target)
            r=self.invoke();self.assertEqual(set(r['artifacts']),{target})

    def test_failed_stage_preserves_work_and_stops_later_builds(self):
        with self.assertRaises(subprocess.CalledProcessError):self.invoke('compile_nsp_shaders.py')
        r=json.loads((self.a.work/'pipeline-report.json').read_text())
        self.assertEqual(r['status'],'failed');self.assertEqual(r['stages'][-1]['status'],'failed')
        self.assertEqual(len(self.commands),2);self.assertTrue((self.a.work/'prepared/ready.json').exists())

    def test_preflight_rejects_existing_output_without_mutation(self):
        self.a.work.mkdir();sentinel=self.a.work/'keep';sentinel.write_text('user data')
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'):
            with self.assertRaisesRegex(ValueError,'new work'):flow.preflight(self.a,self.repo)
        self.assertEqual(sentinel.read_text(),'user data')

    def test_preflight_rejects_compressed_input_without_creating_work(self):
        (self.f.root/'game.nsz').touch()
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'):
            with self.assertRaisesRegex(Exception,'NSZ/NCZ'):flow.preflight(self.a,self.repo)
        self.assertFalse(self.a.work.exists())

    def test_preflight_checks_reused_preparation_before_any_write(self):
        self.a.prepared=self.f.prep;(self.f.prep/'program/ExeFS/main').write_bytes(b'changed')
        family={'base':self.f.root/'base.nsp','updates':[],'dlc':[]}
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'),\
             patch('scripts.build_ipa_from_nsp.scan_nsps',return_value=(self.f.profile.title_id,family)):
            with self.assertRaisesRegex(ValueError,'hash mismatch'):flow.preflight(self.a,self.repo)
        self.assertFalse(self.a.work.exists())

    def test_preflight_rejects_invalid_name_and_version(self):
        family={'base':self.f.root/'base.nsp','updates':[],'dlc':[]}
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'),\
             patch('scripts.build_ipa_from_nsp.scan_nsps',return_value=(self.f.profile.title_id,family)):
            self.a.app_name='../escape'
            with self.assertRaisesRegex(ValueError,'single file'):flow.preflight(self.a,self.repo)
            self.a.app_name='Test';self.a.package='v9'
            with self.assertRaisesRegex(ValueError,'registered'):flow.preflight(self.a,self.repo)

    def test_spyder_settings_cli_override(self):
        with patch.object(entry,'NSP_DIR','/settings'),patch.object(entry,'PROD_KEYS','/keys'),\
             patch.object(entry,'GAME_PROFILE','/profile'),patch.object(entry,'WORK_DIR','/work'),\
             patch.object(entry,'PACKAGE','v0'):
            a=entry.parse_args(['--nsp-dir','/override','--target','macos','--jobs','2'])
        self.assertEqual(a.nsp_dir,Path('/override'));self.assertEqual(a.target,'macos');self.assertEqual(a.jobs,2)

    def test_mixed_folder_records_unused_compressed_files(self):
        (self.f.root/'original.nsz').touch()
        r=self.invoke()
        self.assertEqual(r['unused_compressed_inputs'],['original.nsz'])
        self.assertNotIn('original.nsz',str(self.commands))

    def test_reused_context_is_checked_for_each_requested_target(self):
        self.a.prepared=self.f.prep;self.a.shader_context=self.f.context
        family={'base':self.f.root/'base.nsp','updates':[],'dlc':[]}
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'),\
             patch('scripts.build_ipa_from_nsp.scan_nsps',return_value=(self.f.profile.title_id,family)),\
             patch.object(flow,'validate_context') as checked,patch.object(flow.shutil,'which',return_value='/installed'),\
             patch('scripts.build_ipa_from_nsp.free_gb',return_value=100):
            flow.preflight(self.a,self.repo)
            self.assertEqual([c.args[4] for c in checked.call_args_list],['macos','ios'])
            checked.side_effect=ValueError('changed source')
            with self.assertRaisesRegex(ValueError,'changed source'):flow.preflight(self.a,self.repo)
        self.assertFalse(self.a.work.exists())

    def test_dependency_failure_precedes_work_creation(self):
        family={'base':self.f.root/'base.nsp','updates':[],'dlc':[]}
        with patch.object(game,'Game',return_value=self.f.profile),patch.object(sys,'platform','darwin'),\
             patch('scripts.build_ipa_from_nsp.scan_nsps',return_value=(self.f.profile.title_id,family)),\
             patch.object(flow.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'dependency missing'):flow.preflight(self.a,self.repo)
        self.assertFalse(self.a.work.exists())

    def test_json_progress_emits_structured_workflow_messages(self):
        self.a.progress='json'
        output=io.StringIO()
        with redirect_stdout(output):self.invoke()
        lines=output.getvalue().splitlines()
        self.assertTrue(lines)
        self.assertTrue(all(isinstance(json.loads(line),dict) for line in lines))


if __name__=='__main__':unittest.main()
