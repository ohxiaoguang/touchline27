"""Synthetic isolated compiler orchestration; no commercial assets or downloads."""
import io
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout

import test_prepared_build as fixtures
from tools.nxrom.shader_compile import validate_paths,snapshot,check_summary,compile_prepared,runtime_root
from tools.nxrom.prepared_build import validate_chain_sources
from scripts import compile_nsp_shaders as entry
from scripts import build_ipa_from_nsp as pipeline


class ShaderCompilation(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PreparedBuild(); self.fixture.setUp(); f=self.fixture
        self.repo=f.root/'repo'
        for folder in ('dm/gfx/tools/dmsh_xlate','dm/gfx/tools/dmsh_xlate_bin','dm/gfx/nvn','dm/games','dm/ios/tools'):
            (self.repo/folder).mkdir(parents=True)
        # The chain version header of the source tree (one for every game): a context is refused when it names another version.
        (self.repo/'dm/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "0123456789ab"\n')
        for name in ('dmsh_chain.py','dmsh_build.py','c1_guard.py','cb_extent.py','dmsh_chain.lock'):
            (self.repo/'dm/gfx/tools'/name).write_text('# fixture\n')
        (self.repo/'dm/gfx/tools/dmsh_chain.py').write_text(
            'FILES=["tools/dmsh_chain.py","tools/dmsh_build.py","tools/dmsh_chain.lock","../ios/tools/ios_metal.py"]\nprint("0123456789ab")\n')
        for name in ('Program.cs','dmsh_xlate.csproj'):
            (self.repo/'dm/gfx/tools/dmsh_xlate'/name).write_text('synthetic source')
        (self.repo/'dm/gfx/tools/dmsh_xlate_bin/dmsh_xlate').write_text('synthetic tool')
        (self.repo/'dm/games/game.py').write_text('# fixture\n')
        (self.repo/'dm/ios/tools/ios_metal.py').write_text('# fixture\n')
        self.args=SimpleNamespace(nsp_dir=f.root,prepared=f.prep,profile=f.profile_dir,
                                  output=f.root/'compiled',package='v0',jobs=2)
        self.calls=[]; self.fail_build=False

    def tearDown(self):
        with redirect_stdout(io.StringIO()): pipeline.PROG.close(ok=False)
        self.fixture.tearDown()

    def fake_game(self,path):
        f=self.fixture
        return SimpleNamespace(id=f.profile.id,dir=Path(path),table=lambda n:Path(path)/n,
                               words=f.profile.words,builds=f.profile.builds)

    def fake_run(self,cmd,log,env=None):
        self.calls.append((cmd,dict(env)))
        tool=Path(cmd[1]).name
        Path(log).write_text('synthetic log\n')
        if tool=='dmsh_chain.py' and cmd[-1]=='--header':
            header=self.args.output/'toolchain/gfx/nvn/dmsh_chain.h'; header.parent.mkdir(parents=True,exist_ok=True)
            header.write_text('#define DMSH_CHAIN "0123456789ab"\n')
        if tool=='dmsh_build.py':
            for folder,sdk in (('cache','macosx'),('ios','iphoneos')):
                cache=self.args.output/folder/'b-0123456789ab'; cache.mkdir(parents=True)
                reflection=cache/self.fixture.reflection.name
                reflection.write_text(json.dumps({'key':reflection.stem,'chain':'0123456789ab','chain_metal':sdk}))
                reflection.with_suffix('.metallib').write_bytes(b'MTLB'+bytes(32))
                if folder=='cache': reflection.with_suffix('.metal').write_text('void main0() {}\n')
                if folder=='cache':
                    (cache/'_b_build.json').write_text(json.dumps([{'key':'0123456789abcdef','st':'bad' if self.fail_build else 'ok'}]))
        if tool in ('c1_guard.py','cb_extent.py'): Path(cmd[-1]).write_text('# chain b-0123456789ab\n')

    def run_compile(self):
        sys.path.insert(0,str(fixtures.HERE.parents[2]/'dm/games'))
        import game
        with patch.object(game,'Game',side_effect=self.fake_game), \
             patch.object(pipeline,'free_gb',return_value=20), \
             patch('tools.nxrom.shader_compile.shutil.which',return_value='/bin/true'), \
             patch('tools.nxrom.shader_compile.runtime_root',return_value=str(self.fixture.root/'runtime')), \
             patch.object(pipeline,'run',side_effect=self.fake_run), \
             patch.object(pipeline,'ShaderWatch',return_value=lambda:{}),redirect_stdout(io.StringIO()):
            return compile_prepared(self.args,self.repo)

    def test_complete_cold_context_both_targets_and_order(self):
        with patch.dict(os.environ,DMSH_PREFILL='must-not-use',DMSH_CAS='must-not-write'):
            result=self.run_compile()
        self.assertEqual(result['shader_count'],1)
        self.assertEqual(set(result['targets']),{'cache','ios'})
        tools=[Path(cmd[1]).name for cmd,_ in self.calls]
        self.assertEqual(tools,['dmsh_chain.py']*3+['dmsh_build.py','c1_guard.py','cb_extent.py'])
        for _,env in self.calls:
            self.assertNotIn('DMSH_PREFILL',env)
            self.assertEqual(env['DMSH_CAS'],str(self.args.output/'cache/cas'))
        self.assertTrue((self.args.output/'shader-summary.json').is_file())
        self.assertTrue(json.loads((self.args.output/'compile-report.json').read_text())['cold_cache_at_start'])
        self.assertEqual(self.fixture.profile.table('game.tsv').read_text(),'# fixture\n')

    def test_failure_does_not_publish_success(self):
        self.fail_build=True
        with self.assertRaisesRegex(ValueError,'every registered key'): self.run_compile()
        self.assertFalse((self.args.output/'shader-summary.json').exists())
        self.assertTrue((self.args.output/'logs/shader-build.log').exists())

    def test_snapshot_has_independent_source_and_profile(self):
        self.args.output.mkdir()
        gfx,selected=snapshot(self.repo,self.fake_game(self.fixture.profile_dir),self.args.output)
        source=self.repo/'dm/gfx/tools/dmsh_build.py'; source.write_text('# later change\n')
        self.assertEqual((gfx/source.name).read_text(),'# fixture\n')
        self.assertFalse(any(p.is_symlink() for p in self.args.output.rglob('*')))
        (selected/'game.tsv').write_text('new isolated value')
        self.assertEqual(self.fixture.profile.table('game.tsv').read_text(),'# fixture\n')

    def test_output_guards_preserve_existing_files(self):
        f=self.fixture; existing=f.root/'existing'; existing.mkdir(); (existing/'user').write_text('preserve')
        for output in (existing,f.prep/'new',f.profile_dir/'new',f.root.parent/'outside'):
            with self.subTest(output=output),self.assertRaises(ValueError):
                validate_paths(f.root,f.prep,f.profile_dir,output)
        self.assertEqual((existing/'user').read_text(),'preserve')

    def test_summary_rejects_incomplete_and_red_diagnostics(self):
        cache=self.fixture.root/'cache'; cache.mkdir(); marker=cache/'_b_build.json'
        marker.write_text(json.dumps([{'key':'wrong','st':'ok'}]))
        with self.assertRaises(ValueError): check_summary(cache,{'right'},'')
        marker.write_text(json.dumps([{'key':'right','st':'ok'}]))
        with self.assertRaisesRegex(ValueError,'RED'): check_summary(cache,{'right'},'[RED] failed variant')
        check_summary(cache,{'right'},'unrecognized binding kinds (loading them at run time prints [RED] lines)\n')

    def test_public_dispatch(self):
        f=self.fixture
        args=['--nsp-dir',str(f.root),'--prepared',str(f.prep),'--profile',str(f.profile_dir),
              '--output',str(self.args.output),'--package','v0']
        with patch('tools.nxrom.shader_compile.compile_prepared') as call:
            entry.main(args); call.assert_called_once()

    def test_runtime_root_uses_muxer_location_not_wrapper_directory(self):
        shared=self.fixture.root/'dotnet/libexec/shared/Microsoft.NETCore.App'
        shared.mkdir(parents=True)
        result=SimpleNamespace(stdout=f'Microsoft.NETCore.App 10.0.13 [{shared}]\n')
        with patch('tools.nxrom.shader_compile.shutil.which',return_value='/synthetic/bin/dotnet'), \
             patch('tools.nxrom.shader_compile.subprocess.run',return_value=result):
            self.assertEqual(runtime_root({'PATH':'/synthetic/bin'}),str(shared.parents[1]))

    def test_spyder_settings_and_cli_override(self):
        f=self.fixture
        with patch.multiple(entry,NSP_DIR=str(f.root),PREPARED_DIR=str(f.prep),
                            GAME_PROFILE=str(f.profile_dir),OUTPUT_DIR=str(self.args.output),PACKAGE='v0'), \
             patch('tools.nxrom.shader_compile.compile_prepared') as call:
            entry.main([])
            self.assertEqual(call.call_args.args[0].prepared,f.prep)
            entry.main(['--output',str(f.root/'override')])
            self.assertEqual(call.call_args.args[0].output,f.root/'override')

    def test_snapshot_cannot_hide_changed_repository_sources(self):
        self.args.output.mkdir()
        gfx,_=snapshot(self.repo,self.fake_game(self.fixture.profile_dir),self.args.output)
        (gfx/'dmsh_chain.lock').write_text('different measured tool lock is allowed')
        validate_chain_sources(self.args.output,self.repo)
        (self.repo/'dm/gfx/tools/dmsh_build.py').write_text('# changed translation source\n')
        with self.assertRaisesRegex(ValueError,'current repository source'):
            validate_chain_sources(self.args.output,self.repo)

    def test_finalize_existing_never_recompiles_or_replaces_published_context(self):
        self.run_compile()
        (self.args.output/'shader-summary.json').unlink()
        self.args.finalize_existing=True; self.calls=[]
        self.run_compile()
        self.assertEqual([Path(cmd[1]).name for cmd,_ in self.calls],['c1_guard.py','cb_extent.py'])
        report=json.loads((self.args.output/'compile-report.json').read_text())
        self.assertTrue(report['finalized_existing']); self.assertIsNone(report['cold_cache_at_start'])
        before=(self.args.output/'shader-summary.json').read_bytes(); self.calls=[]
        with self.assertRaisesRegex(ValueError,'already published'): self.run_compile()
        self.assertEqual(self.calls,[])
        self.assertEqual((self.args.output/'shader-summary.json').read_bytes(),before)

    def test_finalize_rejects_missing_msl_and_escaping_output_link(self):
        self.run_compile(); (self.args.output/'shader-summary.json').unlink()
        self.args.finalize_existing=True
        source=next((self.args.output/'cache').rglob('*_b.metal')); source.unlink()
        with self.assertRaisesRegex(ValueError,'Metal sources'): self.run_compile()
        source.write_text('void main0() {}\n')
        report=self.args.output/'compile-report.json'; report.unlink(); report.symlink_to(self.fixture.root/'outside.json')
        with self.assertRaisesRegex(ValueError,'links escape'): self.run_compile()
        self.assertFalse((self.fixture.root/'outside.json').exists())


if __name__=='__main__': unittest.main()
