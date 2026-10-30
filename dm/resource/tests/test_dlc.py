"""Synthetic DLC CNMT, extraction, packaging and runtime regression tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path[:0] = [str(REPO), str(HERE)]
from fixture import (TITLE, HEADER_KEY, aoc_nsp, write_fixture, pfs, nca, romfs,
                     metadata_nca, with_code)
from tools.nxrom import dlc
from tools.nxrom.resourcefs import ResourceFS, build_library


class DLC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = HERE / 'build'; cls.build.mkdir(exist_ok=True)
        cls.library = build_library(cls.build / 'dlc.dylib')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.build)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_fixture(self.root)
        self.keys = self.root / 'test.keys'

    def add(self, name='dlc.nsp', **kwargs):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(aoc_nsp(**kwargs)); return p

    def discover(self, version=0):
        return dlc.discover(self.library, self.root, self.keys, TITLE, version)

    def test_base_without_dlc(self):
        self.assertEqual(self.discover()['dlcs'], [])
        self.assertEqual(self.discover()['errors'], [])

    def test_one_dlc_uses_cnmt_not_filename(self):
        p = self.add('wrong-[0100000000000000]-[UPD].nsp')
        result = self.discover()
        self.assertEqual(result['dlcs'][0]['application'], TITLE)
        self.assertEqual(result['dlcs'][0]['index'], 1)
        self.assertEqual(dlc.metadata(self.library,p,self.keys)['type'], 0x82)

    def test_multiple_dlc_and_other_games(self):
        self.add(index=2); self.add('nested/second.nsp', index=1)
        self.add('other.nsp',application=TITLE+0x200000)
        result = self.discover()
        self.assertEqual([d['index'] for d in result['dlcs']], [1,2])
        self.assertEqual(len(result['warnings']), 1)

    def test_wrong_title_range_is_unsupported(self):
        self.add(title=TITLE+0x9000)
        self.assertTrue(self.discover()['errors'])

    def test_required_application_version(self):
        self.add(required=65536)
        self.assertTrue(self.discover()['errors'])
        self.assertEqual(len(self.discover(65536)['dlcs']), 1)

    def test_identical_duplicates_included_once(self):
        p = self.add(); shutil.copyfile(p,self.root/'copy.nsp')
        result = self.discover()
        self.assertEqual(len(result['dlcs']),1)
        self.assertIn('duplicate', result['warnings'][0])

    def test_conflicting_revisions_never_pick_highest(self):
        self.add(); self.add('copy.nsp',version=65536)
        self.assertIn('conflicting',self.discover()['errors'][0])

    def test_corrupt_and_truncated_packages_are_errors(self):
        p = self.add(); p.write_bytes(p.read_bytes()[:120])
        self.assertTrue(self.discover()['errors'])

    def test_missing_metadata_is_not_a_dlc(self):
        self.add().write_bytes(pfs([('payload.nca',nca(romfs({'marker':b''}),TITLE+0x1001))]))
        self.assertFalse(self.discover()['dlcs'])

    def test_datapatch_is_explicitly_unsupported(self):
        self.add(data_patch=TITLE+0x1800)
        self.assertTrue(self.discover()['errors'])

    def test_raw_content_access_and_foreign_mount_refusal(self):
        p = self.add(files={'small':b'actual content'})
        with ResourceFS(self.library,base=p,keys=self.keys,title=TITLE,aoc=True) as fs:
            with fs.open('small') as f: self.assertEqual(f.read(),b'actual content')
        with self.assertRaises(OSError):
            ResourceFS(self.library,base=p,keys=self.keys,title=TITLE+0x200000,aoc=True)

    def test_nonempty_resources_even_with_shader_names_are_not_new_code(self):
        self.add(files={'shader.bin':b'ordinary data', 'main.nso':b'also ordinary data'})
        addons = self.discover()['dlcs']
        dlc.prepare_inputs(self.library,addons,self.keys,TITLE,0)
        self.assertEqual(addons[0]['files']['shader.bin']['bytes'],13)

    def test_actual_executable_bytes_need_collection_and_rewriting(self):
        header=bytearray(0x80);header[0x10:0x14]=b'NRO0'
        self.add(files={'ordinary-name.dat':bytes(header)})
        with self.assertRaisesRegex(OSError,'executable module requires collection and rewriting'):
            dlc.prepare_inputs(self.library,self.discover()['dlcs'],self.keys,TITLE,0)

    def extracted(self):
        self.add(files={'marker':b'first DLC payload'}); self.add('second.nsp',index=2,files={'marker':b'second DLC payload'})
        addons = self.discover()['dlcs']
        dlc.prepare_inputs(self.library,addons,self.keys,TITLE,0)
        def run(argv):
            dest = Path(argv[-3]); dest.mkdir(); (dest/'marker').write_bytes(b'first DLC payload' if dest.name=='1' else b'second DLC payload')
        out = self.root/'aoc'
        dlc.extract(addons,out,['fixture-extractor',str(self.keys)],run)
        return out

    def test_atomic_extraction_and_manifest(self):
        out = self.extracted(); saved = dlc.audit_tree(out,TITLE)
        self.assertEqual(len(saved['dlcs']),2)
        self.assertNotIn('path',saved['dlcs'][0])
        with self.assertRaises(ValueError): dlc.extract([],out,[],lambda _:None)

    def test_source_changed_during_extraction_never_publishes(self):
        source=self.add(); addons=self.discover()['dlcs']
        def run(argv):
            dest=Path(argv[-3]);dest.mkdir();(dest/'marker').write_bytes(b'')
            source.write_bytes(b'changed while extracting')
        with self.assertRaisesRegex(ValueError,'during extraction'):
            dlc.extract(addons,self.root/'aoc',[],run)
        self.assertFalse((self.root/'aoc').exists())

    def test_native_inventory_catches_extractor_path_collisions(self):
        self.add(files={'A':b'', 'a':b''})
        addons=self.discover()['dlcs']
        dlc.prepare_inputs(self.library,addons,self.keys,TITLE,0)
        def run(argv):
            dest=Path(argv[-3]);dest.mkdir();(dest/'A').write_bytes(b'')
        with self.assertRaisesRegex(ValueError,'path collision'):
            dlc.extract(addons,self.root/'aoc',[],run)
        self.assertFalse((self.root/'aoc').exists())

    def test_failed_extraction_never_publishes_partial(self):
        self.add()
        def fail(_): raise OSError('extraction failed')
        with self.assertRaises(OSError): dlc.extract(self.discover()['dlcs'],self.root/'aoc',[],fail)
        self.assertFalse((self.root/'aoc').exists()); self.assertFalse((self.root/'aoc.partial').exists())

    def test_audit_missing_extra_conflicting_or_wrong_game(self):
        out = self.extracted()
        with self.assertRaises(ValueError): dlc.audit_tree(out,TITLE+1)
        (out/'1/marker').write_bytes(b'corrupt')
        with self.assertRaises(ValueError): dlc.audit_tree(out,TITLE)
        (out/'1/marker').write_bytes(b'first DLC payload'); (out/'extra').write_bytes(b'')
        with self.assertRaises(ValueError): dlc.audit_tree(out,TITLE)

    def test_mac_bundles_all_dlc_and_external_refuses_them(self):
        from test_build_modes import make_inputs,args_for,mac_app,stub_launcher
        out = self.extracted(); inputs = make_inputs(self.root/'inputs')
        args = args_for(inputs,self.root/'Game.app','directory',inputs.romfs); args.aoc=out
        mac_app.package(args,launcher=stub_launcher)
        self.assertEqual(dlc.audit_tree(out,TITLE),dlc.audit_tree(args.output/'Contents/Resources/aoc',TITLE))
        args.output=self.root/'External.app'; args.resource_backend='nsp'
        with self.assertRaises(ValueError): mac_app.package(args,launcher=stub_launcher)

    def test_ipa_contains_all_indices_and_manifest(self):
        out=self.extracted(); app=self.root/'Test.app'; (app/'romfs').mkdir(parents=True)
        (app/'romfs/marker').write_bytes(b'base'); shutil.copytree(out,app/'aoc')
        ipa=self.root/'Test.ipa'
        subprocess.run([sys.executable,str(REPO/'dm/ios/tools/pack_ipa.py'),str(ipa),
                        '--require-romfs','Payload/Test.app='+str(app)],check=True,capture_output=True)
        with zipfile.ZipFile(ipa) as z:
            self.assertIsNone(z.testzip())
            for path in ('aoc/1/marker','aoc/2/marker','aoc/manifest.json'):
                self.assertIn('Payload/Test.app/'+path,z.namelist())

    @unittest.skipUnless(os.environ.get('NX_DLC_EXTRACTOR'),'set NX_DLC_EXTRACTOR for actual LibHac extraction')
    def test_actual_upstream_extractor_multiple_dlc(self):
        self.add(files={'marker':b'first DLC payload'});self.add('second.nsp',index=2,files={'marker':b'second DLC payload'})
        command=['dotnet',os.environ['NX_DLC_EXTRACTOR'],str(self.keys)]
        addons=self.discover()['dlcs'];dlc.prepare_inputs(self.library,addons,self.keys,TITLE,0)
        dlc.extract(addons,self.root/'aoc',command,
                    lambda argv:subprocess.run(argv,check=True,capture_output=True))
        self.assertEqual(len(dlc.audit_tree(self.root/'aoc',TITLE)['dlcs']),2)

    def test_hle_enumeration_mount_read_remove_and_more_than_64(self):
        one=self.add(files={'marker':b'first DLC payload'});two=self.add('two.nsp',index=2,files={'marker':b'second DLC payload'})
        dirs=self.root/'installed';dirs.mkdir()
        for i in range(1,101):
            (dirs/str(i)).mkdir();(dirs/str(i)/'marker').write_bytes(b'')
        (dirs/'101').write_text('not a directory');(dirs/'102').symlink_to(dirs/'1')
        profile=REPO/'dm/host/gen/010015100B514000'
        subprocess.run(['make','-C',str(REPO/'dm/host'),'GAME=010015100B514000','game_profile'],check=True,capture_output=True)
        binary=self.root/'t_aoc'
        subprocess.run(['clang','-O1','-g','-fsanitize=address,undefined','-Wno-unused-function',
                        '-Wno-deprecated-declarations','-I'+str(profile),str(HERE/'t_aoc.c'),
                        str(REPO/'dm/host/tests/t_fs_stub.c'),str(REPO/'dm/host/hle_bigstack.c'),
                        str(REPO/'dm/host/hle_resource.c'),'-lz','-o',str(binary)],check=True,capture_output=True)
        subprocess.run([str(binary),str(self.keys),str(one),str(two),str(dirs)],check=True,capture_output=True)

if __name__=='__main__':unittest.main()
