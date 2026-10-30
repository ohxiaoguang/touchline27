import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
import zipfile

HERE=Path(__file__).resolve().parent
IOS=HERE.parents[1]/'ios/tools'
class Packaging(unittest.TestCase):
    def test_staging_and_refuse_stale_resources(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as temp:
            p=Path(temp); (p/'Gen').mkdir(); shader=p/'shader'; shader.mkdir(); (shader/'test.metallib').write_bytes(b'synthetic')
            chain=p/'chain.h'; chain.write_text('#define DMSH_CHAIN "test"\n')
            paths=dict(DM_RESOURCE_BACKEND='nsp',DM_RESOURCE_ROMFS=str(p/'missing-romfs'),DM_RESOURCE_MARKER='marker',DM_RESOURCE_SHADERS=str(shader),DM_RESOURCE_MSLDIR='b-test',DM_RESOURCE_AOC='',DM_RESOURCE_CHAIN_H=str(chain))
            (p/'Gen/resources.env').write_text(''.join(f'{k}={shlex.quote(v)}\n' for k,v in paths.items()))
            env=dict(os.environ,SRCROOT=str(p),TARGET_BUILD_DIR=str(p),UNLOCALIZED_RESOURCES_FOLDER_PATH='Test.app',PLATFORM_NAME='iphoneos')
            cmd=['bash',str(IOS/'stage_resources.sh')]
            r=subprocess.run(cmd,env=env,capture_output=True); self.assertEqual(r.returncode,0,r.stderr)
            self.assertEqual(sorted(x.name for x in (p/'Test.app').iterdir()),['msl'])
            (p/'Test.app/romfs').mkdir(); (p/'Test.app/romfs/keep').write_bytes(b'keep')
            self.assertNotEqual(subprocess.run(cmd,env=env,capture_output=True).returncode,0)
            self.assertEqual((p/'Test.app/romfs/keep').read_bytes(),b'keep')
    def test_ipa_policy(self):
        with tempfile.TemporaryDirectory(dir=HERE/'build') as temp:
            p=Path(temp); app=p/'Test.app'; app.mkdir(); (app/'binary').write_bytes(b'synthetic executable')
            cmd=['python3',str(IOS/'pack_ipa.py'),str(p/'out.ipa'),'--external-resources',f'Payload/Test.app={app}']
            r=subprocess.run(cmd,capture_output=True); self.assertEqual(r.returncode,0,r.stderr)
            with zipfile.ZipFile(p/'out.ipa') as z: self.assertIn('Payload/Test.app/binary',z.namelist())
            for name in ('prod.keys','base.nsp'):
                (app/name).write_bytes(b'synthetic')
                self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
                (app/name).unlink()
            (app/'romfs').mkdir()
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)

if __name__=='__main__': unittest.main()
