import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parents[2]/'scripts/build_mac_app.py'

class MacPackaging(unittest.TestCase):
    def test_runtime_inventory_and_refuse_overwrite(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as temp:
            p=Path(temp)
            for d in ('program','profile','font','b-123abc'): (p/d).mkdir()
            (p/'host').write_bytes(b'synthetic host 123abc')
            os.chmod(p/'host',0o755)
            (p/'program/main.patched.bin').write_bytes(b'synthetic program')
            (p/'program/main.fixups.tsv').write_text('# BUILD_ID\t'+'00'*16+'\n')
            (p/'launcher.json').write_text('{"settings":[]}')
            (p/'program/prod.keys').write_text('must not be copied')
            (p/'program/romfs').mkdir()
            for n in ('shader_map.tsv','pso_manifest.tsv','c1_full.tsv','cb_extent.tsv'): (p/'profile'/n).write_text('synthetic')
            (p/'chain.h').write_text('#define DMSH_CHAIN "123abc"\n')
            for n in ('standard.ttf','nintendo_ext.ttf'): (p/'font'/n).write_bytes(b'synthetic')
            (p/'font/standard.ttf').rename(p/'font-source.ttf')
            (p/'font/standard.ttf').symlink_to(p/'font-source.ttf')
            (p/'b-123abc/a.metallib').write_bytes(b'synthetic')
            (p/'b-123abc/a.json').write_text('{}')
            (p/'b-123abc/a.metal').write_text('build-only source')
            (p/'b-123abc/_b_build.json').write_text('{"build_only":true}')
            (p/'b-123abc/inputs.tsv').write_text('synthetic library stamp')   # c1_full.tsv is trusted only with it
            app=p/'Test.app'
            cmd=['python3',str(SCRIPT),'--host',str(p/'host'),'--patched',str(p/'program'),'--shaders',str(p/'b-123abc'),
                 '--profile',str(p/'profile'),'--chain-header',str(p/'chain.h'),'--font',str(p/'font'),'--settings',str(p/'launcher.json'),'--output',str(app),'--title-id','0100000000000000','--name','Test']
            r=subprocess.run(cmd,capture_output=True); self.assertEqual(r.returncode,0,r.stderr)
            names={str(x.relative_to(app)) for x in app.rglob('*')}
            self.assertFalse(any(x.endswith(('.keys','.metal')) or '/romfs' in x for x in names))
            self.assertFalse(any(x.endswith('_b_build.json') for x in names))
            self.assertIn('Contents/Resources/msl/b-123abc/a.metallib',names)
            self.assertIn('Contents/Resources/program/main.patched.bin',names)
            with (app/'Contents/Info.plist').open('rb') as f: self.assertEqual(plistlib.load(f)['CFBundleExecutable'],'launch')
            launcher=app/'Contents/MacOS/launch'
            self.assertEqual(launcher.read_bytes()[:4],b'\xcf\xfa\xed\xfe')
            self.assertTrue(os.access(launcher,os.X_OK))
            self.assertIn('Contents/Resources/profile/launcher.json',names)
            self.assertEqual((app/'Contents/Resources/profile/prepared_builds.tsv').read_text(),'main\t'+'00'*16+'\n')
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual((app/'Contents/MacOS/dmhost').read_bytes(),b'synthetic host 123abc')

if __name__=='__main__': unittest.main()
