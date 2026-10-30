"""Fail-closed prepared input, cache and IPA consumer checks (synthetic data)."""
import io
import json
import os
import plistlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
from contextlib import redirect_stdout

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from tools.nxrom.prepared_build import validate_prepared,validate_ios_context,audit_ipa,build
from tools.nxrom.shader_package import TABLES,digest
from scripts import build_ipa_from_nsp as pipeline


class PreparedBuild(unittest.TestCase):
    def setUp(self):
        (HERE/'build').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(prefix='consumer-',dir=HERE/'build')
        self.root=Path(self.tmp.name).resolve(); self.prep=self.root/'prepared'
        self.profile_dir=self.root/'profile'; self.profile_dir.mkdir()
        for name in ('game.tsv',)+TABLES: (self.profile_dir/name).write_text('# fixture\n')
        (self.profile_dir/'shader_map.tsv').write_text('package\tindex\tstage\tkey\nvs.bin\t0\tvs\t0123456789abcdef\n')
        self.profile=SimpleNamespace(id='01006BB00C6F0000',
            table=lambda name:self.profile_dir/name,
            words=lambda name:['v0'] if name=='shader_versions' else ['main'],
            builds=lambda:{'v0':{'main':'ab'*16}})
        for name in ('program/ExeFS','shader/pkg'): (self.prep/name).mkdir(parents=True)
        (self.prep/'program/ExeFS/main').write_bytes(b'program')
        (self.prep/'shader/pkg/vs.bin').write_bytes(b'shader')
        for name in TABLES: (self.prep/'shader'/name).write_bytes(self.profile.table(name).read_bytes())
        self.report={'schema':2,'title_id':self.profile.id,'version':'v0','resource_backend':'nsp',
                     'resource_headers_match_libhac':True,'romfs_directory_created':False,
                     'profile_sha256':{name:digest(self.profile.table(name)) for name in ('game.tsv',)+TABLES},
                     'program_sha256':{'ExeFS/main':digest(self.prep/'program/ExeFS/main')},
                     'package_sha256':{'vs.bin':digest(self.prep/'shader/pkg/vs.bin')}}
        self.save_report()
        self.context=self.root/'context'
        cache=self.context/'ios/b-0123456789ab'; cache.mkdir(parents=True)
        self.reflection=cache/'0123456789abcdef_b.json'
        self.reflection.write_text(json.dumps({'key':self.reflection.stem,'chain':'0123456789ab','chain_metal':'xcrun -sdk iphoneos metal'}))
        self.library=self.reflection.with_suffix('.metallib'); self.library.write_bytes(b'MTLB'+bytes(32))
        (self.context/'toolchain/gfx/tools').mkdir(parents=True)
        (self.context/'toolchain/gfx/nvn').mkdir()   # the chain version header of the snapshot (dm/gfx/nvn/dmsh_chain.h), one for every game
        (self.context/'toolchain/gfx/nvn/dmsh_chain.h').write_text('#define DMSH_CHAIN "0123456789ab"\n')
        (self.context/'toolchain/gfx/tools/dmsh_chain.py').write_text('print("0123456789ab")\n')
        (self.context/'shader-summary.json').write_text(json.dumps({'chain':'0123456789ab','failed':0,
            'compiler_error_lines':0,'shader_count':1,'targets':{'ios':{'reflections':1,'library_files':1}}}))

    def tearDown(self): self.tmp.cleanup()

    def save_report(self): (self.prep/'ready.json').write_text(json.dumps(self.report))

    def validate(self): return validate_prepared(self.prep,self.profile,'v0')

    def test_input_inventory_and_hashes(self):
        self.assertEqual(self.validate(),self.report)
        target=self.prep/'program/ExeFS/main'; target.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'hash mismatch'): self.validate()
        target.write_bytes(b'program')
        extra=self.prep/'program/user-note'; extra.write_text('preserve')
        with self.assertRaisesRegex(ValueError,'inventory changed'): self.validate()
        self.assertEqual(extra.read_text(),'preserve')

    def test_profile_schema_and_links(self):
        self.report['schema']=1; self.save_report()
        with self.assertRaisesRegex(ValueError,'schema'): self.validate()
        self.report['schema']=2; self.save_report()
        shader=self.prep/'shader/pkg/vs.bin'; shader.unlink(); shader.symlink_to(self.prep/'program/ExeFS/main')
        with self.assertRaisesRegex(ValueError,'links'): self.validate()
        shader.unlink(); shader.write_bytes(b'shader')
        self.profile.table('game.tsv').write_text('# changed\n')
        with self.assertRaisesRegex(ValueError,'Profile inputs changed'): self.validate()

    def cache(self): return validate_ios_context(self.context,self.profile,sys.executable,os.environ)

    def test_cache_chain_platform_and_completeness(self):
        self.assertEqual(self.cache()['libraries'],1)
        data=json.loads(self.reflection.read_text()); data['chain_metal']='xcrun -sdk macosx metal'
        self.reflection.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'platform'): self.cache()
        data['chain_metal']='iphoneos'; self.reflection.write_text(json.dumps(data))
        self.library.write_bytes(b'corrupted'+bytes(32))
        with self.assertRaisesRegex(ValueError,'invalid iOS'): self.cache()
        self.library.unlink()
        with self.assertRaisesRegex(ValueError,'missing base'): self.cache()

    def test_changed_sources_reject_cache(self):
        (self.context/'toolchain/gfx/tools/dmsh_chain.py').write_text('print("000000000000")\n')
        with self.assertRaisesRegex(ValueError,'sources/tools'): self.cache()

    def test_ipa_audit_and_forbidden_resources(self):
        output=self.root/'test.ipa'
        def write_app(extra=None):
            with zipfile.ZipFile(output,'w') as archive:
                archive.writestr('Payload/',b'')
                archive.writestr('Payload/DmIOS.app/',b'')
                archive.writestr('Payload/DmIOS.app/msl/b-v/a.metallib',b'MTLB')
                archive.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps({'DMResourceBackend':'nsp','CFBundleExecutable':'DmIOS'}))
                archive.writestr('Payload/DmIOS.app/DmIOS',b'synthetic')
                if extra: archive.writestr('Payload/DmIOS.app/'+extra,b'test')
        write_app()
        self.assertTrue(audit_ipa(output,1)['crc_checked'])
        for name in ('romfs/test','aoc/data','prod.keys','base.nsp','_CodeSignature/CodeResources'):
            with self.subTest(name=name):
                write_app(name)
                with self.assertRaises(ValueError): audit_ipa(output,1)

    def test_ipa_checks_shader_bytes_not_just_count(self):
        shader=self.cache(); output=self.root/'test.ipa'
        with zipfile.ZipFile(output,'w') as archive:
            archive.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps({'DMResourceBackend':'nsp','CFBundleExecutable':'DmIOS'}))
            archive.writestr('Payload/DmIOS.app/DmIOS',b'synthetic')
            archive.writestr('Payload/DmIOS.app/msl/b-'+shader['chain']+'/inputs.tsv',b'stamp')
            for name in shader['files_sha256']:
                archive.writestr('Payload/DmIOS.app/msl/b-'+shader['chain']+'/'+name,b'changed')
        with self.assertRaisesRegex(ValueError,'bytes differ'): audit_ipa(output,1,shader)

    def test_ipa_identity_stamp_and_complete_directory_bytes(self):
        import hashlib
        output=self.root/'directory.ipa'
        shader=dict(chain='fixture', files_sha256={},
                    inputs_sha256=hashlib.sha256(b'stamp').hexdigest())
        resources={'romfs/data3.big':dict(bytes=4,sha256=hashlib.sha256(b'data').hexdigest())}
        def write(bundle='org.nxnative.test', stamp=b'stamp', resource=b'data', extra=False):
            with zipfile.ZipFile(output,'w') as archive:
                archive.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps(dict(
                    DMResourceBackend='directory',CFBundleIdentifier=bundle,CFBundleExecutable='DmIOS')))
                archive.writestr('Payload/DmIOS.app/DmIOS',b'synthetic')
                archive.writestr('Payload/DmIOS.app/msl/b-fixture/inputs.tsv',stamp)
                if resource is not None: archive.writestr('Payload/DmIOS.app/romfs/data3.big',resource)
                if extra: archive.writestr('Payload/DmIOS.app/romfs/unexpected',b'extra')
        def audit():
            return audit_ipa(output,0,shader,backend='directory',romfs_marker='data3.big',
                             expected_bundle_id='org.nxnative.test',resources=resources)
        write(); self.assertTrue(audit()['crc_checked'])
        for kwargs,error in [(dict(bundle='wrong'),'Bundle ID'),(dict(stamp=b'wrong'),'stamp differs'),
                             (dict(resource=None),'missing romfs'),(dict(resource=b'xxxx'),'bytes differ'),
                             (dict(extra=True),'inventory differs')]:
            with self.subTest(kwargs=kwargs):
                write(**kwargs)
                with self.assertRaisesRegex(ValueError,error): audit()

    def test_existing_work_preserved_before_build(self):
        work=self.root/'existing'; work.mkdir(); note=work/'user'; note.write_text('preserve')
        args=SimpleNamespace(use_nsp_prepared=str(self.prep),ios_shader_context=str(self.context),
                             nsp_build_work=str(work),out=str(work/'test.ipa'))
        with self.assertRaisesRegex(ValueError,'new work folder'):
            build(pipeline,args,HERE.parents[2],self.root,None,None,None,self.profile,'v0',{},'en-US')
        self.assertEqual(note.read_text(),'preserve')

    def test_public_dispatch_does_not_enter_extraction_or_shader_build(self):
        sys.path.insert(0,str(HERE.parents[2]/'dm/games')); import game
        keyfile=self.root/'test.keys'; keyfile.write_text('# synthetic\n')
        args=pipeline.parse_args([str(self.root),'-k',str(keyfile),'--resource-backend','nsp',
            '--use-nsp-prepared',str(self.prep),'--ios-shader-context',str(self.context),
            '--nsp-build-work',str(self.root/'new'),'-o',str(self.root/'new/test.ipa')])
        family={'base':self.root/'base.nsp','updates':[],'dlc':[]}
        with patch.object(pipeline,'scan_nsps',return_value=(int(self.profile.id,16),family)), \
             patch.object(game,'by_title',return_value=self.profile), \
             patch('tools.nxrom.prepared_build.build') as consumer, \
             patch.object(pipeline,'extract') as extract,patch.object(pipeline,'build_shaders') as shaders, \
             redirect_stdout(io.StringIO()):
            pipeline.main(args)
            consumer.assert_called_once(); extract.assert_not_called(); shaders.assert_not_called()
            args.resource_backend='directory'
            with self.assertRaises(pipeline.BuildError): pipeline.main(args)
            self.assertEqual(consumer.call_count,1)


if __name__=='__main__': unittest.main()
