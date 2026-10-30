"""Synthetic, non-game NSP/NCA fixtures. Keys are generated dummy test data.
Apple CommonCrypto is called through ctypes; no package downloads needed.
"""
import ctypes as C
import hashlib
import struct as S

cc = C.CDLL('/usr/lib/system/libcommonCrypto.dylib')
cc.CCCrypt.argtypes = [C.c_uint,C.c_uint,C.c_uint,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t)]

def ecb(key, data, decrypt=False):
    out = C.create_string_buffer(len(data)); done = C.c_size_t()
    assert cc.CCCrypt(int(decrypt),0,2,key,len(key),None,data,len(data),out,len(data),C.byref(done)) == 0
    return out.raw

def xts(data, key, decrypt=False):
    out = bytearray()
    for sector in range(len(data)//512):
        tweak = int.from_bytes(ecb(key[16:], sector.to_bytes(16,'big')), 'little')
        for off in range(sector*512, (sector+1)*512,16):
            mask = tweak.to_bytes(16,'little')
            block = bytes(a^b for a,b in zip(data[off:off+16],mask))
            block = ecb(key[:16],block,decrypt)
            out.extend(a^b for a,b in zip(block,mask))
            carry = tweak>>127
            tweak = ((tweak<<1)&((1<<128)-1)) ^ (0x87 if carry else 0)
    return bytes(out)

def ctr(data,key,hi,absolute):
    out=bytearray()
    for off in range(0,len(data),16):
        pad=ecb(key,hi.to_bytes(8,'big')+((absolute+off)//16).to_bytes(8,'big'))
        out.extend(a^b for a,b in zip(data[off:off+16],pad))
    return bytes(out)

def pfs(entries):
    names=bytearray(); table=bytearray(); data=bytearray()
    for name,blob in entries:
        table+=S.pack('<QQII',len(data),len(blob),len(names),0)
        names+=name.encode()+b'\0'; data+=blob
    return S.pack('<4sIII',b'PFS0',len(entries),len(names),0)+table+names+data

def _hfs0_table(entries):
    """(header, data): entry offsets are relative to the data area, after the header."""
    names=bytearray(); table=bytearray(); data=bytearray()
    for name,blob in entries:
        table+=S.pack('<QQIIQ',len(data),len(blob),len(names),len(blob),0)+hashlib.sha256(blob).digest()
        names+=name.encode()+b'\0'; data+=blob
    return S.pack('<4sIII',b'HFS0',len(entries),len(names),0)+table+names,bytes(data)

def hfs0(entries):
    """Gamecard partition: 0x40-byte entries with a whole-member hash."""
    header,data=_hfs0_table(entries)
    return header+data

def hfs0_fixed(entries, payload):
    """Entries with explicit offsets/sizes into one payload; no member hashes."""
    names=bytearray(); table=bytearray()
    for name,off,size in entries:
        table+=S.pack('<QQIIQ',off,size,len(names),0,0)+bytes(32)
        names+=name.encode()+b'\0'
    return S.pack('<4sIII',b'HFS0',len(entries),len(names),0)+table+names+payload

def romfs(files, directories=('', 'empty', 'nested')):
    dirs=bytearray(); dt={}; ft={}; fs=bytearray(); payload=bytearray()
    directories=list(directories)
    for path in directories:
        dt[path]=len(dirs); n=path.rpartition('/')[2].encode(); dirs+=bytes(24+len(n)); dirs+=bytes(-len(dirs)%4)
    for path,blob in files.items():
        ft[path]=len(fs); n=path.rpartition('/')[2].encode(); fs+=bytes(32+len(n)); fs+=bytes(-len(fs)%4)
    for path in directories:
        children=[p for p in directories if p and p.rpartition('/')[0]==path]
        siblings=[p for p in directories if p and p.rpartition('/')[0]==path.rpartition('/')[0]]
        members=[p for p in files if p.rpartition('/')[0]==path]
        sibling=siblings[siblings.index(path)+1] if path and siblings.index(path)+1<len(siblings) else None
        n=path.rpartition('/')[2].encode(); at=dt[path]
        S.pack_into('<IIIIII',dirs,at,dt.get(path.rpartition('/')[0],0),dt[sibling] if sibling else 0xffffffff,dt[children[0]] if children else 0xffffffff,ft[members[0]] if members else 0xffffffff,0xffffffff,len(n)); dirs[at+24:at+24+len(n)]=n
    for path,blob in files.items():
        parent=path.rpartition('/')[0]; siblings=[p for p in files if p.rpartition('/')[0]==parent]; k=siblings.index(path)
        n=path.rpartition('/')[2].encode(); at=ft[path]
        S.pack_into('<IIQQII',fs,at,dt[parent],ft[siblings[k+1]] if k+1<len(siblings) else 0xffffffff,len(payload),len(blob),0xffffffff,len(n)); fs[at+32:at+32+len(n)]=n; payload+=blob
    for i,path in enumerate(directories):
        S.pack_into('<I',dirs,dt[path]+16,dt[directories[i+1]] if i+1<len(directories) else 0xffffffff)
    names=list(files)
    for i,path in enumerate(names):
        S.pack_into('<I',fs,ft[path]+24,ft[names[i+1]] if i+1<len(names) else 0xffffffff)
    od=84; hf=od+len(dirs); of=hf+4; data=of+len(fs)
    return S.pack('<10Q',80,80,4,od,len(dirs),hf,4,of,len(fs),data)+S.pack('<I',0)+dirs+S.pack('<I',0 if files else 0xffffffff)+fs+payload

HEADER_KEY=bytes(range(32)); AREA_KEY=bytes(range(16)); CONTENT_KEY=bytes(range(16,32))
TITLE=0x010015100B514000

def ivfc(rom):
    levels=[rom]
    while len(levels)<6:
        data=levels[0]
        hashes=b''.join(hashlib.sha256(data[i:i+4096].ljust(4096,b'\0')).digest() for i in range(0,len(data),4096))
        levels.insert(0,hashes)
    h=bytearray(512); h[2]=0; h[3]=3; h[4]=3
    h[8:12]=b'IVFC'; S.pack_into('<III',h,12,0x20000,32,7)
    section=bytearray()
    for i,data in enumerate(levels):
        S.pack_into('<QQII',h,0x18+i*24,len(section),len(data),12,0)
        section+=data; section+=bytes(-len(section)%4096)
    h[0xc8:0xe8]=hashlib.sha256(levels[0].ljust(4096,b'\0')).digest()
    S.pack_into('<Q',h,0x140,0x123400000001)
    return bytes(section),h

def nca(rom,title=TITLE):
    section,fh=ivfc(rom); h=bytearray(0xc00)
    h[0x200:0x204]=b'NCA3'; h[0x205]=0; h[0x206]=1
    S.pack_into('<QQ',h,0x208,0xc00+len(section),title)
    S.pack_into('<II',h,0x250,6,(0xc00+len(section))//512)
    h[0x320:0x330]=ecb(AREA_KEY,CONTENT_KEY)
    h[0x600:0x800]=fh; h[0x2a0:0x2c0]=hashlib.sha256(fh).digest()
    return xts(h,HEADER_KEY)+ctr(section,CONTENT_KEY,S.unpack_from('<Q',fh,0x140)[0],0xc00)

def gamecard(members, root_offset=0xf000, partitions=None, secure=True):
    """A gamecard image whose secure partition carries members verbatim.
    Mirrors retail layout: HEAD at 0x100, the root HFS0 header (table only) at
    0x130/0x138 with its SHA-256 at 0x140, partition data after the header."""
    partitions=list(partitions) if partitions is not None else [
        ('update',hfs0([('firmware.bin',bytes(64))])),('logo',hfs0([('nintendo_logo',bytes(32))])),('normal',hfs0([]))]
    if secure: partitions.append(('secure',hfs0(members)))
    header,data=_hfs0_table(partitions)
    card=bytearray(0x200)
    card[0x100:0x104]=b'HEAD'
    S.pack_into('<QQ',card,0x130,root_offset,len(header))
    card[0x140:0x160]=hashlib.sha256(header).digest()
    return bytes(card)+bytes(root_offset-0x200)+header+data

def xci(files, code=False, title=TITLE):
    blob=nca(romfs(files),title)
    if code: blob=with_code(blob)
    return gamecard([('0100000000010000.nca',blob)])

def write_fixture(root, files=None):
    files=files or {'small':b'hello','zero':b'', 'nested/big':bytes(range(256))*1200}
    (root/'test.keys').write_text('header_key = '+HEADER_KEY.hex()+'\nkey_area_key_application_00 = '+AREA_KEY.hex()+'\n')
    (root/'base.nsp').write_bytes(pfs([('program.nca',nca(romfs(files)))]))
    return files

def bucket(entries, total, subsection=False):
    data=bytearray(0x8000)
    S.pack_into('<IIQ',data,0,0,1,total)
    S.pack_into('<Q',data,16,0)
    S.pack_into('<IIQ',data,0x4000,0,len(entries),total)
    for i,(virtual,physical,source) in enumerate(entries):
        if subsection: S.pack_into('<QII',data,0x4010+i*16,virtual,0,physical)
        else: S.pack_into('<QQI',data,0x4010+i*20,virtual,physical,source)
    return bytes(data)

def patch_nca(base_rom, new_rom, title=TITLE, fifa_layout=False, declared_end=None, header=None):
    """Patch NCA whose BKTR maps the new RomFS over the base one.

    fifa_layout writes the shape FIFA 23 uses: the subsection table describes the
    region up to its own start, so its declared end sits past the relative table
    (ro), and the subsection that covers both tables carries the section's
    natural counter -- which is what keeps that layout self-consistent.
    declared_end overrides the field to build a variant that must be rejected;
    header(fh) may bend the section header afterwards, for malformed cases.
    """
    base,_=ivfc(base_rom); logical,fh=ivfc(new_rom)
    maps=[]
    for off in range(0,len(logical),4096):
        source=int(logical[off:off+4096]!=base[off:off+4096])
        if not maps or maps[-1][2]!=source: maps.append((off,off,source))
    reloc=bucket(maps,len(logical))
    ro=len(logical); so=ro+len(reloc)
    split=min(4096*16,len(logical)-4096)
    subentries=[(0,2,1)]+([(split,1,1)] if fifa_layout else [(split,3,1)])
    subsections=bucket(subentries,declared_end if declared_end is not None
                       else so if fifa_layout else ro,True)
    S.pack_into('<QQ4sIII',fh,0x100,ro,len(reloc),b'BKTR',1,len(maps),0)
    S.pack_into('<QQ4sIII',fh,0x120,so,len(subsections),b'BKTR',1,len(subentries),0)
    fh[4]=4
    if header: header(fh)
    hi=S.unpack_from('<Q',fh,0x140)[0]
    cipher=ctr(logical[:split],CONTENT_KEY,(hi&0xffffffff00000000)|2,0xc00)
    cipher+=ctr(logical[split:],CONTENT_KEY,hi if fifa_layout else (hi&0xffffffff00000000)|3,0xc00+split)
    cipher+=ctr(reloc+subsections,CONTENT_KEY,hi,0xc00+ro)
    h=bytearray(0xc00); h[0x200:0x204]=b'NCA3'; h[0x206]=1
    S.pack_into('<QQ',h,0x208,0xc00+len(cipher),title)
    S.pack_into('<II',h,0x250,6,(0xc00+len(cipher))//512)
    h[0x320:0x330]=ecb(AREA_KEY,CONTENT_KEY)
    h[0x600:0x800]=fh; h[0x2a0:0x2c0]=hashlib.sha256(fh).digest()
    return xts(h,HEADER_KEY)+cipher

BUILD_ID=bytes(range(32,48))
def with_code(nca_blob,build=BUILD_ID):
    """Give an NCA a Program ExeFS whose main has this Build ID. An update's ExeFS
    is the code that runs, so a build id other than the base game's is what makes
    a prepared build match one of the two."""
    nso=bytearray(80); nso[:4]=b'NSO0'; nso[64:80]=build
    return with_pfs(nca_blob, [('main',bytes(nso))])

def with_pfs(nca_blob, entries):
    h=bytearray(xts(nca_blob[:0xc00],HEADER_KEY,True))
    code=pfs(entries); hashes=b''.join(hashlib.sha256(code[i:i+4096]).digest() for i in range(0,len(code),4096))
    section=hashes.ljust(4096,b'\0')+code; section=section.ljust((len(section)+511)//512*512,b'\0')
    fh=bytearray(512); fh[2:5]=bytes((1,2,3)); fh[8:40]=hashlib.sha256(hashes).digest()
    S.pack_into('<II',fh,0x28,4096,2); S.pack_into('<QQQQ',fh,0x30,0,len(hashes),4096,len(code)); S.pack_into('<Q',fh,0x140,0x9999)
    off=len(nca_blob); S.pack_into('<II',h,0x240,off//512,(off+len(section))//512)
    h[0x400:0x600]=fh; h[0x280:0x2a0]=hashlib.sha256(fh).digest(); S.pack_into('<Q',h,0x208,off+len(section))
    return xts(h,HEADER_KEY)+nca_blob[0xc00:]+ctr(section,CONTENT_KEY,0x9999,off)


def aoc_nsp(files=None, application=TITLE, index=1, version=0, required=0, title=None, meta_type=0x82, data_patch=0):
    """Independent CNMT + PublicData fixtures, without any real game bytes."""
    title = application + 0x1000 + index if title is None else title
    data = nca(romfs({"marker": b""} if files is None else files), title=title)
    header = bytearray(xts(data[:0xc00], HEADER_KEY, True)); header[0x205] = 5
    # PublicData's RomFS is section 0 (Program uses section 1).
    header[0x240:0x250] = header[0x250:0x260]; header[0x250:0x260] = bytes(16)
    header[0x400:0x600] = header[0x600:0x800]; header[0x600:0x800] = bytes(512)
    header[0x280:0x2a0] = header[0x2a0:0x2c0]; header[0x2a0:0x2c0] = bytes(32)
    data = xts(header, HEADER_KEY) + data[0xc00:]
    content_id = hashlib.sha256(data).digest()[:16]
    ext = S.pack('<QIIQ', application, required, 0, data_patch)
    header = bytearray(0x20)
    S.pack_into('<QIBBHHH', header, 0, title, version, meta_type, 0, len(ext), 1, 0)
    record = hashlib.sha256(data).digest() + content_id + len(data).to_bytes(6, 'little') + bytes((2,0))
    cnmt = bytes(header) + ext + record
    cnmt += hashlib.sha256(cnmt).digest()
    meta = bytearray(0xc00); meta[0x200:0x204] = b'NCA3'; meta[0x205] = 1; meta[0x206] = 1
    S.pack_into('<QQ', meta, 0x208, 0xc00, title)
    meta[0x320:0x330] = ecb(AREA_KEY,CONTENT_KEY)
    meta = with_pfs(xts(meta,HEADER_KEY), [('content.cnmt', cnmt)])
    return pfs([(content_id.hex()+'.nca', data), ('metadata.cnmt.nca', meta)])


def metadata_nca(title=TITLE, application=TITLE, version=0, meta_type=0x80):
    """Application/Patch CNMT used to prove the selected numeric version."""
    ext = S.pack('<QII', application + 0x800, 0, 0) if meta_type == 0x80 else S.pack('<QIIQ', application, 0, 0, 0)
    cnmt = bytearray(0x20)
    S.pack_into('<QIBBHHH', cnmt, 0, title, version, meta_type, 0, len(ext), 0, 0)
    cnmt = bytes(cnmt) + ext + bytes(32)  # mastering digest is opaque
    meta = bytearray(0xc00); meta[0x200:0x204] = b'NCA3'; meta[0x205] = 1; meta[0x206] = 1
    S.pack_into('<QQ', meta, 0x208, 0xc00, title)
    meta[0x320:0x330] = ecb(AREA_KEY, CONTENT_KEY)
    return with_pfs(xts(meta,HEADER_KEY), [('application.cnmt', cnmt)])
