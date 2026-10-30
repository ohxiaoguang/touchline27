"""Program-only preparation and public script dispatch, using synthetic assets."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from tools.nxrom.prepare import prepare
from tools.nxrom.shader_scan import load_decoder
from tools.nxrom.shader_package import write_package,TABLES
from fixture import write_fixture,pfs,nca,romfs,with_code,xci,BUILD_ID,TITLE
from test_shader_stream import bnsh,nso_image_file
from scripts import build_ipa_from_nsp as pipeline


class NspPreparation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (HERE/'build').mkdir(exist_ok=True)
        with patch.dict(os.environ,DM_GAME='0100C49025D3E000'): cls.decoder=load_decoder()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='prepare-',dir=HERE/'build')
        self.root=Path(self.tmp.name).resolve()
        files={'nested/shader.bfsha':bnsh(2)}
        write_fixture(self.root,files)
        (self.root/'base.nsp').write_bytes(pfs([('program.nca',with_code(nca(romfs(files))))]))
        image=bytearray(256)
        struct.pack_into('<I',image,4,32); image[32:36]=b'MOD0'; struct.pack_into('<i',image,36,32)
        struct.pack_into('<qQqQ',image,64,5,216,6,192)
        image+=bnsh()
        source=self.root/'source-main'; source.write_bytes(nso_image_file(image))
        profile_dir=self.root/'profile'; profile_dir.mkdir()
        (profile_dir/'game.tsv').write_text('# synthetic preparation profile\n')
        self.profile=SimpleNamespace(id=f'{TITLE:016X}',title_id=TITLE,
            words=lambda key:['v0'] if key=='shader_versions' else ['main'],
            builds=lambda:{'v0':{'display':'1.0','main':BUILD_ID.hex()}},
            table=lambda name:profile_dir/name)
        found=[]; self.decoder.scan_blob(bytes(image),'main',found)
        self.decoder.scan_blob(files['nested/shader.bfsha'],'/nested/shader.bfsha',found)
        with patch.object(self.decoder,'GAME',self.profile):
            write_package(self.decoder.uniq_keys(found),self.decoder.var_pairs(found),self.root/'reference',self.decoder)
        for name in TABLES: shutil.copy2(self.root/'reference'/name,profile_dir/name)
        manifest='/nested/shader.bfsha\t'+str(len(files['nested/shader.bfsha']))+'\t'+files['nested/shader.bfsha'][:32].hex()+'\n'
        self.extractor=self.root/'extractor'
        self.extractor.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nimport shutil,sys\n'
            'assert sys.argv[-1]=="--manifest"\nout=Path(sys.argv[4])\n'
            '(out/"ExeFS").mkdir(parents=True)\n'
            f'shutil.copyfile({str(source)!r},out/"ExeFS/main")\n'
            f'(out/"romfs_manifest.tsv").write_text({manifest!r})\n')
        self.extractor.chmod(0o755)

    def tearDown(self): self.tmp.cleanup()

    def run_prepare(self,output):
        with patch('tools.nxrom.prepare.load_decoder',return_value=self.decoder),patch.object(self.decoder,'GAME',self.profile):
            return prepare(self.root/'base.nsp',None,self.root/'test.keys',self.profile,'v0',self.extractor,output)

    def test_complete_preparation_without_romfs(self):
        output=self.root/'prepared'
        report=self.run_prepare(output)
        self.assertEqual(report['keys'],4)
        self.assertTrue(report['resource_headers_match_libhac'])
        self.assertTrue(all(report['tables_byte_identical'].values()))
        self.assertFalse((output/'program/RomFS').exists())
        self.assertFalse(any(output.rglob('*.keys')))
        self.assertTrue((output/'ready.json').is_file())
        for name in TABLES: self.assertEqual((output/'shader'/name).read_bytes(),self.profile.table(name).read_bytes())

    def test_gamecard_base_preparation(self):
        files={'nested/shader.bfsha':bnsh(2)}
        (self.root/'base.xci').write_bytes(xci(files,code=True))
        output=self.root/'prepared-xci'
        with patch('tools.nxrom.prepare.load_decoder',return_value=self.decoder),patch.object(self.decoder,'GAME',self.profile):
            report=prepare(self.root/'base.xci',None,self.root/'test.keys',self.profile,'v0',self.extractor,output)
        self.assertEqual(report['keys'],4)
        self.assertTrue((output/'ready.json').is_file())
        (self.root/'update.xci').write_bytes(xci(files))
        with self.assertRaisesRegex(ValueError,'NSP'):
            prepare(self.root/'base.nsp',self.root/'update.xci',self.root/'test.keys',self.profile,'v0',self.extractor,self.root/'no')

    def test_existing_output_and_wrong_build_fail_closed(self):
        output=self.root/'existing'; output.mkdir(); (output/'user').write_text('preserve')
        with self.assertRaises(ValueError): self.run_prepare(output)
        self.assertEqual(list(output.iterdir()),[output/'user'])
        with patch.object(self.profile,'builds',return_value={'v0':{'main':'0'*32}}):
            with self.assertRaises(OSError): self.run_prepare(self.root/'wrong-build')
        self.assertFalse((self.root/'wrong-build/ready.json').exists())
        self.assertFalse((self.root/'wrong-build/program-extraction.log').exists())

    def test_extractor_violating_manifest_mode_is_rejected(self):
        with self.extractor.open('a') as stream: stream.write('(out/"RomFS").mkdir()\n')
        output=self.root/'bad-extractor'
        with self.assertRaisesRegex(ValueError,'manifest-only'): self.run_prepare(output)
        self.assertFalse((output/'ready.json').exists())

    def test_existing_dotnet_muxer_runs_sidecar_dll(self):
        self.extractor.with_suffix('.dll').write_bytes(b'synthetic dll marker')
        muxer=self.root/'dotnet'
        muxer.write_text('#!'+sys.executable+'\nimport os,sys\n'
                         f'os.execv({str(self.extractor)!r},[{str(self.extractor)!r}]+sys.argv[2:])\n')
        muxer.chmod(0o755)
        with patch('tools.nxrom.prepare.shutil.which',return_value=str(muxer)):
            report=self.run_prepare(self.root/'muxer-output')
        self.assertEqual(report['keys'],4)

    def test_table_mismatch_does_not_publish_ready(self):
        facts=self.profile.table('shader_facts.tsv')
        facts.write_bytes(facts.read_bytes()+b'# incompatible registered table\n')
        output=self.root/'bad-tables'
        with self.assertRaisesRegex(ValueError,'tables differ'): self.run_prepare(output)
        self.assertFalse((output/'ready.json').exists())

    def test_public_entry_stops_before_existing_build(self):
        import game
        args=pipeline.parse_args([str(self.root),'-k',str(self.root/'test.keys'),
                                  '--resource-backend','nsp','--prepare-nsp-resources','public-out'])
        family={'base':self.root/'base.nsp','updates':[],'dlc':[]}
        with patch.dict(os.environ),patch.object(pipeline,'scan_nsps',return_value=(TITLE,family)), \
             patch.object(game,'by_title',return_value=self.profile), \
             patch('tools.nxrom.prepare.prepare',return_value={'keys':4}) as called, \
             patch.object(pipeline,'check_prereqs') as prerequisites, \
             patch.object(pipeline,'build_nx_extract') as build,redirect_stdout(io.StringIO()):
            pipeline.main(args)
            called.assert_called_once()
            self.assertEqual(called.call_args.args[-1],self.root/'public-out')
            prerequisites.assert_not_called(); build.assert_not_called()
            args.resource_backend='directory'
            with self.assertRaises(pipeline.BuildError): pipeline.main(args)
            self.assertEqual(called.call_count,1)
            args.resource_backend='nsp'
            args.prepare_nsp_resources='/private/tmp/outside-game-root'
            with self.assertRaises(pipeline.BuildError): pipeline.main(args)
            family['dlc']=[(TITLE+0x1001,0,self.root/'dlc.nsp')]
            with self.assertRaises(pipeline.BuildError): pipeline.main(args)
            self.assertEqual(called.call_count,1)


if __name__=='__main__': unittest.main()
