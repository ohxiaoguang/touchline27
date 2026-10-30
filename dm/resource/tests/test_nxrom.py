import ctypes as C
import errno
import hashlib
import os
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from fixture import write_fixture, pfs, nca, romfs, patch_nca, with_code, xci, gamecard, hfs0, hfs0_fixed, ivfc, BUILD_ID, TITLE

HERE=Path(__file__).resolve().parent
class Info(C.Structure):
    _fields_=[('path',C.c_char_p),('size',C.c_uint64),('directory',C.c_int)]

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work=tempfile.TemporaryDirectory(prefix='nxrom-',dir=HERE/'build')
        cls.root=Path(cls.work.name)
        lib=cls.root/'reader.dylib'
        subprocess.run(['clang','-dynamiclib','-O1','-g','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',str(HERE.parent/'nxrom.c'),'-o',str(lib)],check=True)
        cls.lib=C.CDLL(str(lib),use_errno=True)
        cls.lib.nxrom_open.argtypes=[C.c_char_p,C.c_char_p,C.c_char_p,C.c_uint64,C.POINTER(C.c_void_p),C.c_char_p,C.c_size_t]
        cls.lib.nxrom_directory.argtypes=[C.c_char_p,C.POINTER(C.c_void_p)]
        cls.lib.nxrom_find.argtypes=[C.c_void_p,C.c_char_p,C.POINTER(C.c_uint64)]
        cls.lib.nxrom_stat.argtypes=[C.c_void_p,C.c_uint64,C.POINTER(Info)]
        cls.lib.nxrom_read.argtypes=[C.c_void_p,C.c_uint64,C.c_void_p,C.c_size_t,C.c_int64]; cls.lib.nxrom_read.restype=C.c_ssize_t
        cls.lib.nxrom_next.argtypes=[C.c_void_p,C.c_uint64,C.POINTER(C.c_uint64),C.POINTER(Info)]
        cls.lib.nxrom_close.argtypes=[C.c_void_p]
        cls.lib.nxrom_check_build.argtypes=[C.c_void_p,C.c_char_p,C.c_char_p]
        cls.files=write_fixture(cls.root)
    @classmethod
    def tearDownClass(cls): cls.work.cleanup()
    def mount(self,path='base.nsp',title=TITLE,update=None,keys='test.keys'):
        fs=C.c_void_p(); error=C.create_string_buffer(256)
        r=self.lib.nxrom_open(os.fsencode(self.root/path),os.fsencode(self.root/update) if update else None,os.fsencode(self.root/keys),title,C.byref(fs),error,256)
        return r,fs,error.value
    def lookup(self,fs,path):
        id=C.c_uint64(); self.assertEqual(self.lib.nxrom_find(fs,path.encode(),C.byref(id)),0,path); return id.value
    def read(self,fs,id,off,size):
        data=C.create_string_buffer(size); n=self.lib.nxrom_read(fs,id,data,size,off)
        self.assertGreaterEqual(n,0); return data.raw[:n]
    def test_content_random_concurrent_eof(self):
        r,fs,error=self.mount(); self.assertEqual(r,0,error)
        try:
            for path,data in self.files.items():
                id=self.lookup(fs,path); info=Info(); self.assertEqual(self.lib.nxrom_stat(fs,id,C.byref(info)),0); self.assertEqual(info.size,len(data))
                self.assertEqual(self.read(fs,id,0,len(data)+10),data)
                rng=random.Random(23); jobs=[(rng.randrange(len(data)+2),rng.randrange(1,12000)) for _ in range(60)]
                with ThreadPoolExecutor(max_workers=4) as pool:
                    actual=list(pool.map(lambda pair:self.read(fs,id,*pair),jobs))
                self.assertEqual(actual,[data[o:o+n] for o,n in jobs])
                self.assertEqual(self.lib.nxrom_read(fs,id,None,0,-1),-1)
            for path in ('../small','nested/../../small','/small','nested//big','missing'):
                id=C.c_uint64(); self.assertEqual(self.lib.nxrom_find(fs,path.encode(),C.byref(id)),-1)
        finally: self.lib.nxrom_close(fs)
    def test_directory_parity(self):
        directory=self.root/'dir'; directory.mkdir(exist_ok=True); (directory/'empty').mkdir(exist_ok=True); (directory/'nested').mkdir(exist_ok=True)
        for p,b in self.files.items(): (directory/p).write_bytes(b)
        r,a,error=self.mount(); self.assertEqual(r,0,error); d=C.c_void_p(); self.assertEqual(self.lib.nxrom_directory(os.fsencode(directory),C.byref(d)),0)
        def listing(fs,path):
            id=self.lookup(fs,path); cursor=C.c_uint64(); info=Info(); out=[]
            while self.lib.nxrom_next(fs,id,C.byref(cursor),C.byref(info))==1: out.append((info.path.decode(),info.size,info.directory))
            return out
        try:
            for path in ('','empty','nested'): self.assertEqual(listing(a,path),listing(d,path))
            for path,data in self.files.items(): self.assertEqual(self.read(a,self.lookup(a,path),4090,9000),self.read(d,self.lookup(d,path),4090,9000))
        finally: self.lib.nxrom_close(a); self.lib.nxrom_close(d)
    def test_reject_header_identity_ncz(self):
        for name,blob in [('bad.nsp',b'wrong'*30),('compressed.nsp',pfs([('a.ncz',b'abc')])),('longname.nsp',pfs([('a'*1000+'.nca',b'abc')])),('truncated.nsp',(self.root/'base.nsp').read_bytes()[:300])]:
            (self.root/name).write_bytes(blob); r,fs,error=self.mount(name); self.assertEqual(r,-1,error); self.assertFalse(fs.value)
        self.assertEqual(self.mount(title=TITLE+1)[0],-1)
    def test_payload_integrity(self):
        blob=bytearray((self.root/'base.nsp').read_bytes()); blob[-4096+17]^=1
        (self.root/'corrupt.nsp').write_bytes(blob); r,fs,error=self.mount('corrupt.nsp')
        if not r:
            try:
                id=self.lookup(fs,'nested/big'); b=C.create_string_buffer(len(self.files['nested/big'])); self.assertEqual(self.lib.nxrom_read(fs,id,b,len(b),0),-1); self.assertEqual(C.get_errno(),errno.EBADMSG)
            finally: self.lib.nxrom_close(fs)
        else: self.assertIn(b'integrity',error)

    def test_missing_wrong_keys_and_failed_mount_cleanup(self):
        original=(self.root/'test.keys').read_text()
        (self.root/'empty.keys').write_text('# no keys\n')
        (self.root/'wrong.keys').write_text('header_key = '+'00'*32+'\n')
        key_values=[x.split('=',1)[1].strip().encode() for x in original.splitlines() if '=' in x]
        before=len(os.listdir('/dev/fd'))
        cases=[dict(keys='missing.keys'),dict(keys='empty.keys'),dict(keys='wrong.keys'),
               dict(path='missing.nsp'),dict(update='missing-update.nsp'),dict(update='base.nsp')]
        for _ in range(12):
            for case in cases:
                r,fs,error=self.mount(**case)
                self.assertEqual(r,-1,case);self.assertFalse(fs.value,case);self.assertTrue(error,case)
                for value in key_values: self.assertNotIn(value,error)
        self.assertLessEqual(len(os.listdir('/dev/fd')),before+1)

    def test_open_inode_survives_path_change_and_reports_storage_loss(self):
        original=(self.root/'base.nsp').read_bytes()
        path=self.root/'runtime.nsp'; moved=self.root/'runtime-moved.nsp'
        path.write_bytes(original);r,fs,error=self.mount('runtime.nsp');self.assertEqual(r,0,error)
        try:
            id=self.lookup(fs,'nested/big')
            path.rename(moved);path.write_bytes(b'replacement is not a container')
            self.assertEqual(self.read(fs,id,160000,100),self.files['nested/big'][160000:160100])
            moved.write_bytes(b'')   # Only this test's copied synthetic inode is modified.
            b=C.create_string_buffer(100)
            self.assertEqual(self.lib.nxrom_read(fs,id,b,len(b),250000),-1)
            self.assertEqual(C.get_errno(),errno.EIO)
            moved.write_bytes(original)
            self.assertEqual(self.read(fs,id,250000,100),self.files['nested/big'][250000:250100])
        finally:self.lib.nxrom_close(fs)
    def test_exefs_build_identity(self):
        (self.root/'code.nsp').write_bytes(pfs([('program.nca',with_code(nca(romfs(self.files))))]))
        r,fs,error=self.mount('code.nsp'); self.assertEqual(r,0,error)
        try:
            self.assertEqual(self.lib.nxrom_check_build(fs,b'main',BUILD_ID.hex().encode()),0)
            self.assertEqual(self.lib.nxrom_check_build(fs,b'main',b'0'*32),-1)
            self.assertEqual(self.lib.nxrom_check_build(fs,b'missing',BUILD_ID.hex().encode()),-1)
        finally: self.lib.nxrom_close(fs)

    def test_update_mapping_and_oracle(self):
        new=dict(self.files); new['nested/big']=self.files['nested/big'][:-8000]+b'UPDATED!'*1000
        (self.root/'update.nsp').write_bytes(pfs([('patch.nca',patch_nca(romfs(self.files),romfs(new)))]))
        r,fs,error=self.mount(update='update.nsp'); self.assertEqual(r,0,error)
        try:
            for path,data in new.items():
                id=self.lookup(fs,path)
                self.assertEqual(self.read(fs,id,0,len(data)),data)
                for off in (1,4090,65000,280000): self.assertEqual(self.read(fs,id,off,17000),data[off:off+17000])
        finally: self.lib.nxrom_close(fs)
        oracle=HERE/'build/oracle/Oracle.dll'
        if oracle.exists():
            for update,expected in ((False,self.files),(True,new)):
                args=['dotnet',str(oracle),str(self.root/'test.keys'),str(self.root/'base.nsp')]+([str(self.root/'update.nsp')] if update else [])
                result=subprocess.run(args,capture_output=True,text=True,check=True)
                actual={}
                for line in result.stdout.splitlines():
                    columns=line.split('\t')
                    if columns[0]=='f': actual[columns[1][1:]]=(int(columns[2]),columns[3])
                self.assertEqual(actual,{path:(len(data),hashlib.sha256(data).hexdigest()) for path,data in expected.items()})
        (self.root/'wrongupdate.nsp').write_bytes(pfs([('patch.nca',patch_nca(romfs(self.files),romfs(new),TITLE+1))]))
        self.assertEqual(self.mount(update='wrongupdate.nsp')[0],-1)

    def test_xci_base_update_and_identity(self):
        (self.root/'base.xci').write_bytes(xci(self.files,code=True))
        r,fs,error=self.mount('base.xci'); self.assertEqual(r,0,error)
        try:
            for path,data in self.files.items():
                id=self.lookup(fs,path)
                info=Info(); self.assertEqual(self.lib.nxrom_stat(fs,id,C.byref(info)),0); self.assertEqual(info.size,len(data))
                self.assertEqual(self.read(fs,id,0,len(data)+10),data)
                rng=random.Random(47); jobs=[(rng.randrange(len(data)+2),rng.randrange(1,12000)) for _ in range(60)]
                with ThreadPoolExecutor(max_workers=4) as pool:
                    actual=list(pool.map(lambda pair:self.read(fs,id,*pair),jobs))
                self.assertEqual(actual,[data[o:o+n] for o,n in jobs])
            self.assertEqual(self.lib.nxrom_check_build(fs,b'main',BUILD_ID.hex().encode()),0)
            self.assertEqual(self.lib.nxrom_check_build(fs,b'main',b'0'*32),-1)
        finally: self.lib.nxrom_close(fs)
        # The same RomFS bytes must come out of an NSP and an XCI base.
        nsp=C.c_void_p(); error=C.create_string_buffer(256)
        self.assertEqual(self.lib.nxrom_open(os.fsencode(self.root/'base.nsp'),None,os.fsencode(self.root/'test.keys'),
                                             TITLE,C.byref(nsp),error,256),0,error.value)
        x=C.c_void_p()
        self.assertEqual(self.lib.nxrom_open(os.fsencode(self.root/'base.xci'),None,os.fsencode(self.root/'test.keys'),
                                             TITLE,C.byref(x),error,256),0,error.value)
        try:
            for path in self.files:
                a,b=self.lookup(nsp,path),self.lookup(x,path)
                size=self.files[path] and 4090 or 0
                self.assertEqual(self.read(nsp,a,0,9000) if size else b'',self.read(x,b,0,9000) if size else b'')
                if size: self.assertEqual(self.read(nsp,a,4090,9000),self.read(x,b,4090,9000))
        finally: self.lib.nxrom_close(nsp); self.lib.nxrom_close(x)
        # XCI base + NSP update (BKTR view over the gamecard program).
        new=dict(self.files); new['nested/big']=self.files['nested/big'][:-8000]+b'UPDATED!'*1000
        (self.root/'update.nsp').write_bytes(pfs([('patch.nca',patch_nca(romfs(self.files),romfs(new)))]))
        r,fs,error=self.mount('base.xci',update='update.nsp'); self.assertEqual(r,0,error)
        try:
            for path,data in new.items():
                id=self.lookup(fs,path)
                self.assertEqual(self.read(fs,id,0,len(data)),data)
                for off in (1,4090,65000,280000): self.assertEqual(self.read(fs,id,off,17000),data[off:off+17000])
        finally: self.lib.nxrom_close(fs)
        self.assertEqual(self.mount('base.xci',title=TITLE+1)[0],-1)
        (self.root/'wrongupdate.nsp').write_bytes(pfs([('patch.nca',patch_nca(romfs(self.files),romfs(new),TITLE+1))]))
        self.assertEqual(self.mount('base.xci',update='wrongupdate.nsp')[0],-1)

    def test_update_tables_inside_the_subsection_region(self):
        # FIFA 23 lays its patch RomFS out with the relative table before the end
        # of the region the subsection table describes (that table's declared end
        # is its own start, past the relative table). The tables themselves are
        # read with the section's natural counter, which the covering subsection
        # carries, so the layout is self-consistent and must mount.
        (self.root/'fifa.xci').write_bytes(xci(self.files,code=True))
        new=dict(self.files); new['nested/big']=self.files['nested/big'][:-8000]+b'UPDATED!'*1000
        (self.root/'fifa-update.nsp').write_bytes(pfs([('patch.nca',
            patch_nca(romfs(self.files),romfs(new),fifa_layout=True))]))
        r,fs,error=self.mount('fifa.xci',update='fifa-update.nsp'); self.assertEqual(r,0,error)
        try:
            for path,data in new.items():
                id=self.lookup(fs,path)
                self.assertEqual(self.read(fs,id,0,len(data)),data)
                for off in (1,4090,65000,280000): self.assertEqual(self.read(fs,id,off,17000),data[off:off+17000])
        finally: self.lib.nxrom_close(fs)

    def test_update_rejects_subsection_region_past_its_own_table(self):
        # A declared region that climbs past the subsection table describing it is
        # not a layout the reader can account for, so it must stay refused even
        # though the table itself is well formed.
        (self.root/'fifabad.xci').write_bytes(xci(self.files))
        new=dict(self.files); new['small']=b'changed'
        logical,_=ivfc(romfs(new)); so=len(logical)+0x8000
        (self.root/'past.nsp').write_bytes(pfs([('patch.nca',patch_nca(
            romfs(self.files),romfs(new),fifa_layout=True,declared_end=so+0x4000))]))
        r,fs,error=self.mount('fifabad.xci',update='past.nsp')
        self.assertEqual(r,-1,error); self.assertFalse(fs.value)

    def test_xci_malformed_variants(self):
        original=xci(self.files)
        cases={}
        blob=bytearray(original); blob[0x101]=0x58; cases['magic.xci']=bytes(blob)
        cases['truncated.xci']=original[:0x158]
        blob=bytearray(original); struct.pack_into('<Q',blob,0x130,1<<48); cases['root-offset.xci']=bytes(blob)
        blob=bytearray(original); struct.pack_into('<Q',blob,0x138,0x400); cases['root-size.xci']=bytes(blob)
        blob=bytearray(original); blob[0x141]^=1; cases['root-hash.xci']=bytes(blob)
        cases['no-secure.xci']=gamecard([],partitions=[('update',hfs0([('f',bytes(8))]))],secure=False)
        cases['duplicate-secure.xci']=gamecard([('0100000000010000.nca',nca(romfs(self.files)))],partitions=[('secure',hfs0([]))])
        cases['ncz-member.xci']=gamecard([('a.ncz',bytes(4096))])
        cases['no-member.xci']=gamecard([])
        cases['overlap.xci']=gamecard([],partitions=[('secure',hfs0_fixed([('a.nca',0,4096),('b.nca',0x800,4096)],bytes(8192)))])
        cases['out-of-range.xci']=gamecard([],partitions=[('secure',hfs0_fixed([('a.nca',0,1<<20)],bytes(4096)))])
        for name,blob in cases.items():
            (self.root/name).write_bytes(blob); r,fs,error=self.mount(name)
            self.assertEqual((r,fs.value),(-1,None),name+': '+error.decode(errors='replace'))
        # A corrupt RomFS block: caught either by the secure-partition hash at
        # open, or by IVFC at read time; both must refuse the corrupt bytes.
        blob=bytearray(original); blob[-4096+17]^=1; (self.root/'payload.xci').write_bytes(bytes(blob))
        r,fs,error=self.mount('payload.xci')
        if not r:
            try:
                id=self.lookup(fs,'nested/big'); b=C.create_string_buffer(len(self.files['nested/big']))
                self.assertEqual(self.lib.nxrom_read(fs,id,b,len(b),0),-1); self.assertEqual(C.get_errno(),errno.EBADMSG)
            finally: self.lib.nxrom_close(fs)
        else: self.assertIn(b'base container',error)

    def test_empty_unicode_case_and_bad_index(self):
        for i,files in enumerate(({}, {'A':b'A','a':b'a','caf\u00e9':b'utf8'}, {'nested/x':b'x'*20000})):
            name=f'case{i}.nsp'; (self.root/name).write_bytes(pfs([('program.nca',nca(romfs(files)))])); r,fs,error=self.mount(name); self.assertEqual(r,0,error)
            try:
                for path,data in files.items(): self.assertEqual(self.read(fs,self.lookup(fs,path),0,len(data)),data)
            finally: self.lib.nxrom_close(fs)
        bad=bytearray(romfs({'small':b'a'})); bad[0:8]=bytes(8)
        (self.root/'badindex.nsp').write_bytes(pfs([('program.nca',nca(bad))])); self.assertEqual(self.mount('badindex.nsp')[0],-1)

if __name__=='__main__':
    (HERE/'build').mkdir(exist_ok=True)
    unittest.main()
