"""Mac prepared consumer: shared cache checks, safe paths and copied-byte audit."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import sys
import unittest
from unittest.mock import patch

import test_prepared_build as fixtures
from tools.nxrom.mac_build import audit_app,validate_paths
from tools.nxrom.prepared_build import validate_context
from scripts import build_mac_app as packer


class MacPreparedBuild(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.PreparedBuild(); self.fixture.setUp()
        f=self.fixture; self.root=f.root
        self.cache=f.context/'cache/b-0123456789ab'
        shutil.copytree(f.context/'ios/b-0123456789ab',self.cache)
        reflection=self.cache/f.reflection.name
        data=json.loads(reflection.read_text()); data['chain_metal']='xcrun -sdk macosx metal'
        reflection.write_text(json.dumps(data))
        summary=f.context/'shader-summary.json'; data=json.loads(summary.read_text())
        data['targets']['cache']=data['targets']['ios']; summary.write_text(json.dumps(data))
        self.shader=validate_context(f.context,f.profile,sys.executable,os.environ,'macos')
        (self.cache/'inputs.tsv').write_text('game\t'+f.profile.id+'\ninputs\tfixture\n')
        self.patched=self.root/'patched'; self.patched.mkdir()
        for suffix in ('.patched.bin','.gates.tsv','.cuts.tsv','.obs.tsv'):
            (self.patched/('main'+suffix)).write_bytes(b'synthetic program data')
        (self.patched/'main.fixups.tsv').write_text('# BUILD_ID\t'+'ab'*16+'\n')
        for name in ('pso_manifest.tsv','c1_full.tsv','cb_extent.tsv'):
            f.profile.table(name).write_text('# synthetic table\n')
        self.host=self.root/'host'; self.host.write_bytes(b'synthetic host'); self.host.chmod(0o755)
        self.app=self.root/'Test.app'; resources=self.app/'Contents/Resources'
        (self.app/'Contents/MacOS').mkdir(parents=True)
        for name in ('launch','dmhost'): shutil.copyfile(self.host,self.app/'Contents/MacOS'/name); (self.app/'Contents/MacOS'/name).chmod(0o755)
        shutil.copytree(self.patched,resources/'program')
        shutil.copytree(self.cache,resources/'msl/b-0123456789ab')
        profile=resources/'profile'; profile.mkdir()
        for name in ('shader_map.tsv','pso_manifest.tsv','c1_full.tsv','cb_extent.tsv'):   # the chain version header is not a profile table
            shutil.copyfile(f.profile.table(name),profile/name)
        (profile/'prepared_builds.tsv').write_text('main\t'+'ab'*16+'\n')
        (self.app/'Contents/Info.plist').write_bytes(plistlib.dumps({'NXTitleID':f.profile.id,'NXResourceBackend':'nsp','CFBundleExecutable':'launch'}))

    def tearDown(self): self.fixture.tearDown()

    def audit(self): return audit_app(self.app,self.fixture.profile,self.patched,self.host,self.shader)

    def test_bundled_shader_stamp_is_required(self):
        (self.app/'Contents/Resources/msl/b-0123456789ab/inputs.tsv').unlink()
        with self.assertRaisesRegex(ValueError, 'no stamp'):
            self.audit()

    def test_mac_cache_rejects_ios_platform_and_checks_target(self):
        f=self.fixture
        self.assertEqual(self.shader['libraries'],1)
        reflection=self.cache/f.reflection.name
        data=json.loads(reflection.read_text()); data['chain_metal']='iphoneos'
        reflection.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'platform'):
            validate_context(f.context,f.profile,sys.executable,os.environ,'macos')
        with self.assertRaisesRegex(ValueError,'unknown'):
            validate_context(f.context,f.profile,sys.executable,os.environ,'wrong')

    def test_audit_all_copied_bytes_and_no_private_material(self):
        self.assertTrue(self.audit()['program_bytes_match_rewrite'])
        resources=self.app/'Contents/Resources'
        for name in ('romfs/data','aoc/test','prod.keys','base.nsp'):
            path=resources/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'test')
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'private'): self.audit()
            path.unlink()
            if path.parent!=resources: path.parent.rmdir()
        lib=resources/'msl/b-0123456789ab'/self.fixture.library.name; lib.write_bytes(b'MTLB changed')
        with self.assertRaisesRegex(ValueError,'Shader bytes'): self.audit()

    def test_audit_program_and_link_mismatch(self):
        program=self.app/'Contents/Resources/program/main.patched.bin'
        program.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'program inventory'): self.audit()
        program.unlink(); program.symlink_to(self.patched/'main.patched.bin')
        with self.assertRaisesRegex(ValueError,'link'): self.audit()

    def test_audit_carries_the_nro_table_beside_the_modules(self):
        # A game's runtime NROs arrive as modules of their own plus the table that names them by
        # SHA-256; the audit counts them in the program inventory and checks the table's bytes.
        files={'render.patched.bin':b'nro program','render.fixups.tsv':('# BUILD_ID\t'+'cd'*16+'\n').encode(),
               'render.gates.tsv':b'# none\n','render.cuts.tsv':b'# none\n','render.obs.tsv':b'# none\n'}
        for name,data in files.items():
            (self.patched/name).write_bytes(data); (self.app/'Contents/Resources/program'/name).write_bytes(data)
        table='render\t'+'ab'*32+'\t4096\n'
        (self.patched/'nro.tsv').write_text(table)
        bundled=self.app/'Contents/Resources/program/nro.tsv'; bundled.write_text(table)
        self.assertTrue(self.audit()['program_bytes_match_rewrite'])
        bundled.write_text(table.replace('4096','8192'))
        with self.assertRaisesRegex(ValueError,'program inventory'): self.audit()

    def test_existing_work_and_cache_nesting_are_preserved(self):
        f=self.fixture; work=self.root/'existing'; work.mkdir(); note=work/'user'; note.write_text('preserve')
        for bad in (work,f.prep/'new',f.context/'cache/new',self.root.parent/'outside'):
            with self.subTest(path=bad),self.assertRaises(ValueError):
                validate_paths(self.root,f.prep,f.context,bad,bad/'Test.app')
        validate_paths(self.root,f.prep,f.context,self.root/'new',self.root/'new/Test.app')
        self.assertEqual(note.read_text(),'preserve')

    def test_public_dispatch_keeps_asset_mode_separate(self):
        f=self.fixture
        args=['build_mac_app.py','--profile',str(f.profile_dir),'--output',str(self.root/'new/Test.app'),
              '--use-nsp-prepared',str(f.prep),'--shader-context',str(f.context),'--nsp-dir',str(self.root),
              '--keys',str(self.root/'synthetic.keys'),'--package','v0','--work',str(self.root/'new')]
        with patch.object(sys,'argv',args),patch('tools.nxrom.mac_build.build') as called:
            packer.main(); called.assert_called_once()
        with patch.object(sys,'argv',args+['--host',str(self.host)]),redirect_stderr(io.StringIO()), \
             patch('tools.nxrom.mac_build.build') as called,self.assertRaises(SystemExit):
            packer.main()
        called.assert_not_called()


if __name__=='__main__': unittest.main()
