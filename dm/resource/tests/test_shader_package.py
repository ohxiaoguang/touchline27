"""Independent exporter checked against the production writer's actual AST.

Only the test oracle extracts trusted repository code; production export contains
no AST rewriting or monkeypatch of the existing Shader preparation pipeline.
"""
import ast
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from tools.nxrom.shader_scan import load_decoder
from tools.nxrom.shader_package import collect,write_package,compare,TABLES
from test_shader_stream import bnsh


def original_writer(decoder):
    tree=ast.parse(Path(decoder.__file__).read_text())
    main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
    begin=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Assign)
               and any(isinstance(t,ast.Name) and t.id=='per_src' for t in n.targets))
    wrapper=ast.parse('def original(results,pkg,mapout,factsout,pairsout):\n    keys={}\n')
    wrapper.body[0].body.extend(main.body[begin:])
    namespace=dict(decoder.__dict__)
    exec(compile(ast.fix_missing_locations(wrapper),decoder.__file__,'exec'),namespace)
    return namespace['original']


class ShaderPackages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (HERE/'build').mkdir(exist_ok=True)
        with patch.dict(os.environ,DM_GAME='0100C49025D3E000'): cls.decoder=load_decoder()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='shader-package-',dir=HERE/'build')
        self.root=Path(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def records(self,seed=1,label='/region_common/shader/example'):
        found=[]; self.decoder.scan_blob(bnsh(seed),label,found); return found

    def test_original_writer_byte_parity_and_manual_facts(self):
        found=self.records()
        control=bytearray(found[0][2]); code=bytearray(found[0][3])
        code[:4]=self.decoder.CS_MAGIC
        struct.pack_into('<III',control,0x748,2,3,4)
        struct.pack_into('<I',control,0x754,17)
        found.append(('/region_common/effect/test#compute','cs',bytes(control),bytes(code)))
        key=self.decoder.skey(control,code)
        glslc=bytearray(found[0][3]); glslc[-1]=9
        found.append(('main#GLSLC@0x100','vs',found[0][2],bytes(glslc)))
        (self.root/'shader_facts_manual.tsv').write_text(key+'\t'+json.dumps({'shared':48,'attr':{'1':'float'}})+'\n')
        game=SimpleNamespace(table=lambda name:self.root/name)
        keys=self.decoder.uniq_keys(found); pairs=self.decoder.var_pairs(found)
        reference=self.root/'reference'; reference.mkdir()
        with patch.object(self.decoder,'GAME',game):
            with redirect_stdout(io.StringIO()):
                original_writer(self.decoder)([('test',keys,pairs,{})],str(reference/'pkg'),
                                              *(str(reference/name) for name in TABLES))
            augmented=pairs|self.decoder.separable_pairs(keys)[0]
            write_package(keys,augmented,self.root/'actual',self.decoder)
        expected={str(p.relative_to(reference)):p.read_bytes() for p in reference.rglob('*') if p.is_file()}
        actual={str(p.relative_to(self.root/'actual')):p.read_bytes() for p in (self.root/'actual').rglob('*') if p.is_file()}
        self.assertEqual(actual,expected)
        self.assertIn(b'"shared":48',actual['shader_facts.tsv'])

    def test_main_last_copy_and_sorted_file_first_copy(self):
        decoder=self.decoder
        first=self.records(label='main#first')
        last=[('main#last'+w[len('main#first'):],s,c,k) for w,s,c,k in first]
        fs=SimpleNamespace(open=lambda *args,**kw:io.BytesIO(bnsh(2)+bnsh(2)))
        with patch('tools.nxrom.shader_package.program_records',return_value=('build',first+last)):
            keys,pairs=collect(fs,['b','a'],'main',decoder,False)
        self.assertEqual(len(keys),4)
        self.assertEqual(len(pairs),2)
        for key in decoder.uniq_keys(first): self.assertTrue(keys[key][0].startswith('main#last'))
        for key in decoder.uniq_keys(self.records(2)):
            self.assertEqual(keys[key][0],'/a#BNSH@0x0#var0')

    def test_existing_output_is_preserved(self):
        target=self.root/'existing'; target.mkdir()
        (target/'user-file').write_bytes(b'preserve')
        found=self.records()
        with self.assertRaises(FileExistsError):
            write_package(self.decoder.uniq_keys(found),self.decoder.var_pairs(found),target,self.decoder)
        self.assertEqual(list(target.iterdir()),[target/'user-file'])
        self.assertEqual((target/'user-file').read_bytes(),b'preserve')

    def test_complete_hash_comparison_detects_changes(self):
        found=self.records(); keys=self.decoder.uniq_keys(found)
        for name in ('actual','reference'): write_package(keys,self.decoder.var_pairs(found),self.root/name,self.decoder)
        game=SimpleNamespace(table=lambda name:self.root/'reference'/name)
        with patch.object(self.decoder,'GAME',game):
            report=compare(self.root/'actual',self.root/'reference/pkg',self.decoder)
            self.assertTrue(report['packages_equal']); self.assertTrue(all(report['tables_byte_identical'].values()))
            package=next((self.root/'actual/pkg').glob('*.bin'))
            blob=bytearray(package.read_bytes()); blob[-1]^=1; package.write_bytes(blob)
            self.assertFalse(compare(self.root/'actual',self.root/'reference/pkg',self.decoder)['packages_equal'])


if __name__=='__main__': unittest.main()
