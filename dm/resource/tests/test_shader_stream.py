"""Raw BNSH stream scans must match the unchanged shader_split decoder."""
import io
import json
from contextlib import redirect_stdout
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from tools.nxrom.resourcefs import ResourceFS, build_library
from tools.nxrom.shader_scan import iter_bnsh, iter_resource, _unyaz0, program_manifest, load_decoder, manifest, main
from fixture import write_fixture, pfs, romfs, patch_nca, TITLE, BUILD_ID, with_code, nca
from validate_shader_stream_real import bounded_reference_members


def bnsh(seed=1):
    d = bytearray(0x1400)
    d[:8] = b'BNSH\0\0\0\0'; struct.pack_into('<I', d, 0x1c, len(d))
    d[0x60:0x64] = b'grsc'; struct.pack_into('<IQ', d, 0x7c, 1, 0x100)
    struct.pack_into('<Q', d, 0x110, 0x140)
    for stage, descriptor, ctl, code, sph in ((0, 0x180, 0x200, 0xa80, 1), (4, 0x1c0, 0xb00, 0x1380, 5)):
        struct.pack_into('<Q', d, 0x148+8*stage, descriptor)
        struct.pack_into('<QQII', d, descriptor+8, ctl, code, 0x80, 0x880)
        d[ctl:ctl+4] = bytes.fromhex('34127698')
        struct.pack_into('<I', d, ctl+0x20, 0x880)
        struct.pack_into('<I', d, ctl+0x704, 0x80)
        d[code:code+4] = bytes.fromhex('78563412')
        struct.pack_into('<I', d, code+0x30, 0x61 | sph << 10)
        d[code+0x7f] = seed
    return bytes(d)


def sarc(files):
    names, nodes, payload = bytearray(), bytearray(), bytearray()
    for name, body in files:
        offset=len(names)//4
        names.extend(name.encode()+b'\0'); names.extend(bytes(-len(names)%4))
        nodes.extend(struct.pack('<IIII',0,0x1000000|offset,len(payload),len(payload)+len(body)))
        payload.extend(body)
    data_offset=20+12+len(nodes)+8+len(names)
    header=struct.pack('<4sHHIIHH',b'SARC',20,0xfeff,data_offset+len(payload),data_offset,0x100,0)
    return header+struct.pack('<4sHHI',b'SFAT',12,len(files),0x65)+nodes+struct.pack('<4sHH',b'SFNT',8,0)+names+payload


def yaz_literal(body):
    return b'Yaz0'+len(body).to_bytes(4,'big')+bytes(8)+b''.join(b'\xff'+body[i:i+8] for i in range(0,len(body),8))


def nso_image_file(image, build=BUILD_ID):
    header=bytearray(256); header[:4]=b'NSO0'; header[64:80]=build
    for i in range(3):
        struct.pack_into('<III',header,0x10+16*i,256 if not i else 256+len(image),
                         0 if not i else len(image),len(image) if not i else 0)
    struct.pack_into('<III',header,0x60,len(image),0,0)
    return header+image


class ShaderStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch.dict(os.environ, DM_GAME='0100C49025D3E000'):
            cls.decoder = load_decoder()
        (HERE/'build').mkdir(exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix='shader-stream-', dir=HERE/'build')
        cls.root = Path(cls.tmp.name)
        cls.library = build_library(cls.root/'reader.dylib')
        cls.data = {'nested/shader.bfsha': b'prefix'+bnsh(), 'zero': b'',
                    'plain': b'not a shader' * 1000}
        write_fixture(cls.root, cls.data)
        cls.updated = dict(cls.data)
        cls.updated['nested/shader.bfsha'] = b'prefix'+bnsh(2)
        (cls.root/'update.nsp').write_bytes(pfs([('patch.nca', patch_nca(romfs(cls.data), romfs(cls.updated)))]))
        cls.directory = cls.root/'directory'
        (cls.directory/'nested').mkdir(parents=True)
        for path, data in cls.updated.items(): (cls.directory/path).write_bytes(data)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_boundary_offsets_duplicates_and_payload_parity(self):
        for prefix in (0, 1, 57, 61, 63, 64, 65, 127):
            data = b'\xff'*prefix + bnsh() + b'separator' + bnsh(2)
            expected = []
            self.decoder.scan_blob(data, '/test', expected)
            self.assertEqual(list(iter_bnsh(io.BytesIO(data), '/test', self.decoder, chunk_size=64)), expected)
            self.assertEqual(len(expected), 4)

    def test_native_base_update_and_directory_manifest(self):
        with ResourceFS(self.library, base=self.root/'base.nsp', keys=self.root/'test.keys', title=TITLE) as base, \
             ResourceFS(self.library, base=self.root/'base.nsp', update=self.root/'update.nsp', keys=self.root/'test.keys', title=TITLE) as updated, \
             ResourceFS(self.library, directory=self.directory) as directory:
            paths = list(self.data)
            self.assertEqual(manifest(updated, paths, self.decoder), manifest(directory, paths, self.decoder))
            self.assertNotEqual(manifest(base, paths, self.decoder)['unique_keys'],
                                manifest(updated, paths, self.decoder)['unique_keys'])
            for fs, files in ((base, self.data), (updated, self.updated)):
                for path, data in files.items():
                    expected = []; self.decoder.scan_blob(data, '/'+path, expected)
                    with fs.open(path, buffering=0) as stream:
                        self.assertEqual(list(iter_bnsh(stream, '/'+path, self.decoder)), expected)

    def test_bounded_requests_and_no_unbounded_read(self):
        class Guard(io.BytesIO):
            def read(inner, size=-1):
                self.assertGreaterEqual(size, 0)
                self.assertLessEqual(size, 1024*1024)
                return super().read(size)
        data = b'x'*(1024*1024-3)+bnsh()
        self.assertEqual(len(list(iter_bnsh(Guard(data), '/bounded', self.decoder))), 2)

    def test_damage_limits_and_unsupported_formats(self):
        for data in (b'Yaz0'+bytes(40), b'SARC'+bytes(40), b'UnityFS\0'+bytes(40)):
            with self.assertRaisesRegex(ValueError, 'separate stream adapter'):
                list(iter_bnsh(io.BytesIO(data), '/unsupported', self.decoder))
        for size in (1, 0xffffffff):
            data = bytearray(bnsh()); struct.pack_into('<I', data, 0x1c, size)
            with self.assertRaisesRegex(ValueError, 'invalid size'):
                list(iter_bnsh(io.BytesIO(data), '/damaged', self.decoder))
        with self.assertRaisesRegex(ValueError, 'limit'):
            list(iter_bnsh(io.BytesIO(bnsh()), '/limit', self.decoder, max_container=4096))
        data = bytearray(bnsh()); struct.pack_into('<Q', data, 0x80, 0xfffffff)
        with self.assertRaisesRegex(ValueError, 'invalid BNSH'):
            list(iter_bnsh(io.BytesIO(data), '/bad-index', self.decoder))

    def test_cli_selection_and_existing_report_preservation(self):
        output = self.root/'selected-report.json'
        args = ['--library', str(self.library), '--directory', str(self.directory),
                '--suffix', '.bfsha', '--output', str(output)]
        with patch.dict(os.environ, DM_GAME='0100C49025D3E000'), redirect_stdout(io.StringIO()):
            main(args)
        original = output.read_bytes()
        report = json.loads(original)
        self.assertFalse(report['complete_game_shader_scan'])
        self.assertEqual(len(report['files']), 1)
        self.assertEqual(report['files'][0]['record_count'], 2)
        self.assertEqual(len(report['files'][0]['pairs']), 1)
        with patch('sys.stderr', io.StringIO()), self.assertRaises(SystemExit): main(args)
        self.assertEqual(output.read_bytes(), original)

    def test_sarc_nested_yaz0_and_stable_member_labels(self):
        data=sarc([('folder/shader.bfsha',bnsh()),('caf\u00e9.arc',yaz_literal(sarc([('inner',bnsh(2))])))])
        for body in (data,yaz_literal(data)):
            expected=[]; self.decoder.scan_blob(body,'/archive',expected)
            actual=list(iter_resource(io.BytesIO(body),'/archive',self.decoder))
            self.assertEqual(actual,expected)
            self.assertEqual(len(actual),4)
        self.assertEqual(list(bounded_reference_members(data)),list(self.decoder.sarc_members(data)))

    def test_sarc_damage_paths_and_yaz0_limits(self):
        valid=sarc([('shader',bnsh())])
        bads=[]
        for offset,value in ((12,20),(32+8,0xffffffff),(8,len(valid)+1)):
            blob=bytearray(valid); struct.pack_into('<I',blob,offset,value); bads.append(blob)
        bads.extend((sarc([('../escape',bnsh())]),sarc([('same',bnsh()),('same',bnsh())])))
        overlap=bytearray(sarc([('first',bnsh()),('second',bnsh())]))
        struct.pack_into('<I',overlap,32+16+8,1)
        bads.append(overlap)
        endian=bytearray(valid); endian[6:8]=b'\xfe\xff'; bads.append(endian)
        for body in bads:
            with self.assertRaises(ValueError): list(iter_resource(io.BytesIO(body),'/bad',self.decoder))
        for body in (b'Yaz0'+(0xffffffff).to_bytes(4,'big')+bytes(8),
                     b'Yaz0'+(5).to_bytes(4,'big')+bytes(8)+b'\0\x10\0',
                     yaz_literal(valid)[:-10]):
            with self.assertRaises(ValueError): list(iter_resource(io.BytesIO(body),'/bad-yaz',self.decoder))
        nested=bnsh()
        for _ in range(10): nested=sarc([('nested',nested)])
        with self.assertRaisesRegex(ValueError,'nesting limit'):
            list(iter_resource(io.BytesIO(nested),'/deep',self.decoder))

    def test_yaz0_valid_backreferences_and_expansion_budget(self):
        for size, commands in ((21,b'\x80A\0\0\x02'),(12,b'\xe0abc\x70\x02')):
            data=b'Yaz0'+size.to_bytes(4,'big')+bytes(8)+commands
            self.assertEqual(_unyaz0(data,[100]),self.decoder.yaz0(data))
        with self.assertRaisesRegex(ValueError,'expansion limit'):
            _unyaz0(yaz_literal(bnsh()),[len(bnsh())-1])

    def test_zstd_raw_nested_sarc_and_original_decoder_parity(self):
        zstd=self.decoder.zstd_mod()
        for raw in (bnsh(),sarc([('shader',bnsh()),('nested',bnsh(2))])):
            body=zstd.compress(raw)
            expected=[];self.decoder.scan_blob(zstd.decompress(body),'/compressed.zs',expected)
            before=set(self.root.iterdir())
            actual=list(iter_resource(io.BytesIO(body),'/compressed.zs',self.decoder,scratch=self.root))
            self.assertEqual(actual,expected)
            self.assertEqual(set(self.root.iterdir()),before)
        nested=sarc([('nested',zstd.compress(bnsh(2)))])
        expected=[];self.decoder.scan_blob(bnsh(2),'/nested.zs/nested',expected)
        self.assertEqual(list(iter_resource(io.BytesIO(zstd.compress(nested)),'/nested.zs',self.decoder,scratch=self.root)),expected)

    def test_zstd_bounds_damage_scratch_and_cleanup(self):
        body=self.decoder.zstd_mod().compress(bnsh())
        with self.assertRaisesRegex(ValueError,'scratch'):
            list(iter_resource(io.BytesIO(body),'/z',self.decoder))
        before=set(self.root.iterdir())
        with self.assertRaisesRegex(ValueError,'expansion limit'):
            list(iter_resource(io.BytesIO(body),'/z',self.decoder,scratch=self.root,budget=[100]))
        with self.assertRaises(ValueError):
            list(iter_resource(io.BytesIO(body[:-4]),'/truncated',self.decoder,scratch=self.root))
        self.assertEqual(set(self.root.iterdir()),before)

    def test_bahs_original_decoder_parity_inside_zstd_and_sarc(self):
        records=[];self.decoder.scan_blob(bnsh(),'/seed',records)
        _,_,control,code=records[0];control=bytearray(control)
        struct.pack_into('<I',control,0x704,len(code))
        body=bytearray(0x1000+len(code));body[:4]=b'BAHS'
        struct.pack_into('<II',body,0x18,len(code),0x1000)
        struct.pack_into('<IIIi',body,0x40,0,0,len(control),0x100-0x40)
        body[0x100:0x100+len(control)]=control;body[0x1000:]=code
        expected=self.decoder.bahs_shaders(body,'/shader');self.assertEqual(len(expected),1)
        self.assertEqual(list(iter_resource(io.BytesIO(body),'/shader',self.decoder)),expected)
        wrapped=self.decoder.zstd_mod().compress(sarc([('shader',body)]))
        expected=self.decoder.bahs_shaders(body,'/archive/shader')
        self.assertEqual(list(iter_resource(io.BytesIO(wrapped),'/archive',self.decoder,scratch=self.root)),expected)
        struct.pack_into('<I',body,0x1c,0xffffffff)
        with self.assertRaisesRegex(ValueError,'code region'):
            list(iter_resource(io.BytesIO(body),'/bad',self.decoder))

    def test_native_archive_and_program_build_identity(self):
        archive=sarc([('shader.bfsha',bnsh()),('nested.arc',sarc([('shader',bnsh(2))]))])
        archive_nsp=self.root/'archive.nsp'
        archive_nsp.write_bytes(pfs([('program.nca',with_code(nca(romfs({'nested/ui.arc':archive}))))]))
        program=self.root/'main'
        program.write_bytes(nso_image_file(b'program-prefix'+bnsh(3)))
        with ResourceFS(self.library,base=archive_nsp,keys=self.root/'test.keys',title=TITLE) as fs:
            with fs.open('nested/ui.arc',buffering=0) as stream:
                expected=[]; self.decoder.scan_blob(archive,'/ui',expected)
                self.assertEqual(list(iter_resource(stream,'/ui',self.decoder)),expected)
            result=program_manifest(program,fs,self.decoder,True)
            self.assertEqual(result['record_count'],2)
            self.assertTrue(result['build_checked'])
            program.write_bytes(nso_image_file(bnsh(),bytes(16)))
            with self.assertRaises(OSError): program_manifest(program,fs,self.decoder,True)
            bad=bytearray(nso_image_file(bnsh())); struct.pack_into('<I',bad,0x18,0xffffffff)
            program.write_bytes(bad)
            with self.assertRaisesRegex(ValueError,'bounds'):
                program_manifest(program,fs,self.decoder,True)


if __name__ == '__main__': unittest.main()
