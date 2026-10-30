"""Read BNSH/BAHS, SARC members and program Shaders through resource streams.

This opt-in scanner reuses shader_split's decoder without changing the existing
Shader chain or publishing replacement Shader tables. It is not a complete
replacement for shader_split: Unity and engine archives need their own stream
adapters. Yaz0 and Zstandard wrappers are bounded; Zstandard requires explicit
game-drive scratch space. Select inputs explicitly; no extension is assumed safe.
"""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from contextlib import contextmanager

MAGIC = b'BNSH\0\0\0\0'
MAX_CONTAINER = 64 * 1024 * 1024
CHUNK = 1024 * 1024
MAX_EXPANSION = 512 * 1024 * 1024


def _exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(min(CHUNK, size-len(data)))
        if not part: raise ValueError('truncated Shader resource')
        data.extend(part)
    return bytes(data)


class _Slice(io.RawIOBase):
    """Sequentially used view of one immutable parent; never owns its handle."""
    def __init__(self, parent, start, size):
        super().__init__()
        self.parent, self.start, self.size, self.position = parent, start, size, 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): self._checkClosed(); return self.position

    def seek(self, offset, whence=0):
        self._checkClosed()
        if whence not in (0, 1, 2): raise ValueError('invalid seek origin')
        position = offset+(0 if whence==0 else self.position if whence==1 else self.size)
        if position < 0: raise ValueError('negative slice offset')
        self.position = position
        return position

    def readinto(self, buffer):
        self._checkClosed()
        view = memoryview(buffer).cast('B')
        count = min(len(view), CHUNK, max(0, self.size-self.position))
        if not count: return 0
        self.parent.seek(self.start+self.position)
        data = self.parent.read(count)
        view[:len(data)] = data
        self.position += len(data)
        return len(data)


def sarc_members(stream):
    """Validated little-endian SARC index; member bodies remain in the parent."""
    length = stream.seek(0, 2); stream.seek(0)
    header = _exact(stream, 20)
    if header[:4]!=b'SARC' or header[6:8]!=b'\xff\xfe':
        raise ValueError('only little-endian SARC is supported')
    hsize, size, data_offset = struct.unpack_from('<H2xII', header, 4)
    if hsize<20 or not hsize<=data_offset<=size<=length:
        raise ValueError('invalid SARC header bounds')
    stream.seek(hsize); fat = _exact(stream, 12)
    if fat[:4]!=b'SFAT' or struct.unpack_from('<H',fat,4)[0]!=12:
        raise ValueError('invalid SARC SFAT header')
    count = struct.unpack_from('<H',fat,6)[0]
    names_start = hsize+12+16*count+8
    if names_start>data_offset or data_offset-names_start>8*1024*1024:
        raise ValueError('invalid or oversized SARC name table')
    nodes = _exact(stream, 16*count)
    nt = _exact(stream, 8)
    if nt[:4]!=b'SFNT' or struct.unpack_from('<H',nt,4)[0]!=8:
        raise ValueError('invalid SARC SFNT header')
    names = _exact(stream, data_offset-names_start)
    entries, used, ranges = [], set(), []
    for i in range(count):
        _, attributes, start, end = struct.unpack_from('<IIII',nodes,i*16)
        if attributes>>24 not in (0,1) or not start<=end<=size-data_offset:
            raise ValueError('invalid SARC member bounds or attributes')
        if attributes>>24:
            offset = (attributes&0xffffff)*4
            stop = names.find(b'\0',offset)
            if offset>=len(names) or stop<0 or stop-offset>4096:
                raise ValueError('invalid SARC member name')
            name = names[offset:stop].decode('utf-8')
            if not name or name.startswith('/') or '\\' in name or any(p in ('','.','..') for p in name.split('/')):
                raise ValueError('invalid SARC member path')
        else: name = '#'+str(i)
        if name in used: raise ValueError('duplicate SARC member name')
        used.add(name)
        entries.append((name,data_offset+start,end-start))
        if start!=end: ranges.append((start,end))
    previous = None
    for current in sorted(ranges):
        if previous and current[0]<previous[1] and current!=previous:
            raise ValueError('overlapping SARC members')
        previous = current
    return entries


def _unyaz0(data, budget):
    if len(data)<16: raise ValueError('truncated Yaz0 header')
    size = int.from_bytes(data[4:8],'big')
    if size>MAX_CONTAINER or size>budget[0]: raise ValueError('Yaz0 expansion limit exceeded')
    budget[0] -= size
    out, position = bytearray(), 16
    def take():
        nonlocal position
        if position>=len(data): raise ValueError('truncated Yaz0 command')
        value=data[position]; position+=1; return value
    while len(out)<size:
        flags=take()
        for bit in range(8):
            if flags & (128>>bit): out.append(take())
            else:
                first, second = take(), take()
                distance=((first&15)<<8 | second)+1
                count=(first>>4)+2 if first>>4 else take()+18
                if distance>len(out): raise ValueError('invalid Yaz0 back-reference')
                count=min(count,size-len(out))
                pattern=out[-distance:]
                out.extend((pattern*((count+distance-1)//distance))[:count])
            if len(out)>=size: break
    return bytes(out)


@contextmanager
def _zstd_resource(stream,decoder,scratch,budget):
    """One seekable temporary resource, never a resource directory or RAM copy.

    The caller must explicitly supply game-drive scratch space. Each decoded
    transfer is bounded; nested containers share an expansion budget. Closing
    the context removes only this tool-owned anonymous temporary file.
    """
    if scratch is None or not Path(scratch).is_dir():
        raise ValueError('Zstandard resources require an explicit existing game-drive scratch directory')
    stream.seek(0)
    zstd=decoder.zstd_mod()
    with tempfile.TemporaryFile(dir=scratch) as output:
        try:
            with zstd.ZstdFile(stream,'rb',options={zstd.DecompressionParameter.window_log_max:26}) as expanded:
                while True:
                    block=expanded.read(min(CHUNK,budget[0]+1))
                    if not block: break
                    budget[0]-=len(block)
                    if budget[0]<0: raise ValueError('Zstandard expansion limit exceeded')
                    output.write(block)
        except (EOFError,OSError,zstd.ZstdError) as exc:
            raise ValueError('invalid or truncated Zstandard resource') from exc
        output.seek(0)
        yield output


def iter_resource(stream, label, decoder, *, depth=0, budget=None,scratch=None):
    """BNSH in raw, SARC, Yaz0 or Zstandard, preserving scan_blob labels."""
    if depth>8: raise ValueError(label+': archive nesting limit exceeded')
    if budget is None: budget=[MAX_EXPANSION]
    length=stream.seek(0,2); stream.seek(0); head=stream.read(16)
    if head[:4]==b'SARC':
        for name, offset, size in sarc_members(stream):
            with _Slice(stream,offset,size) as member:
                yield from iter_resource(member,label+'/'+name,decoder,depth=depth+1,budget=budget,scratch=scratch)
    elif head[:4]==b'Yaz0':
        if length>MAX_CONTAINER: raise ValueError(label+': compressed Yaz0 input limit exceeded')
        stream.seek(0)
        with io.BytesIO(_unyaz0(_exact(stream,length),budget)) as expanded:
            yield from iter_resource(expanded,label,decoder,depth=depth+1,budget=budget,scratch=scratch)
    elif head[:4]==bytes.fromhex('28b52ffd'):
        with _zstd_resource(stream,decoder,scratch,budget) as expanded:
            yield from iter_resource(expanded,label,decoder,depth=depth+1,budget=budget,scratch=scratch)
    elif head[:4]==b'BAHS':
        if length<32 or length>MAX_CONTAINER: raise ValueError(label+': invalid or oversized BAHS resource')
        stream.seek(0);data=_exact(stream,length)
        size,offset=struct.unpack_from('<II',data,0x18)
        if offset<32 or offset+size>length: raise ValueError(label+': invalid BAHS code region')
        try: yield from decoder.bahs_shaders(data,label)
        except (struct.error,IndexError,SystemExit) as exc:
            raise ValueError(label+': invalid BAHS resource') from exc
    else:
        yield from iter_bnsh(stream,label,decoder)


def load_decoder():
    """The existing module requires DM_GAME, as its regular CLI does."""
    path = Path(__file__).resolve().parents[2]/'dm/gfx/tools/shader_split.py'
    spec = importlib.util.spec_from_file_location('_nxrom_shader_decoder', path)
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    return decoder


def iter_bnsh(stream, label, decoder, *, chunk_size=CHUNK, max_container=MAX_CONTAINER):
    """Yield the existing (source, stage, control, code) records, with stable labels.

    Read transfers are bounded. A candidate's declared BNSH size is capped before
    allocation. Only raw embedded BNSH is covered; an empty result says nothing
    about other shader formats. Sources must remain immutable while scanning.
    """
    if chunk_size < len(MAGIC) or max_container < 0x88:
        raise ValueError('invalid BNSH scanner limits')
    length = stream.seek(0, 2)
    stream.seek(0)
    head = stream.read(16)
    unsupported = (b'Yaz0', b'SARC', bytes.fromhex('28b52ffd'), b'UnityFS\0',
                   b'KPKA', b'ONEPACK\0', b'BDF3', b'SCNE', b'ARC\0', b'BAHS', b'MSHD')
    if head.startswith(unsupported):
        raise ValueError(label + ': this container needs a separate stream adapter; raw BNSH scanning is unsupported')
    position, tail = 0, b''
    while position < length:
        stream.seek(position)
        block = stream.read(min(chunk_size, length-position))
        if not block:
            raise OSError(label + ': source ended during BNSH scan')
        window = tail + block
        start, search = position-len(tail), 0
        while True:
            hit = window.find(MAGIC, search)
            if hit < 0:
                break
            search = hit+1
            offset = start+hit
            stream.seek(offset)
            header = stream.read(0x88)
            if len(header) < 0x64 or header[0x60:0x64] != b'grsc':
                continue  # Same signature/block discriminator as scan_blob.
            size = struct.unpack_from('<I', header, 0x1c)[0]
            if size < 0x88 or size > length-offset:
                raise ValueError(f'{label}: BNSH at {offset:#x} has an invalid size')
            if size > max_container:
                raise ValueError(f'{label}: BNSH at {offset:#x} exceeds the {max_container}-byte limit')
            stream.seek(offset)
            data = bytearray()
            while len(data) < size:
                part = stream.read(min(chunk_size, size-len(data)))
                if not part:
                    raise OSError(label + ': source ended while reading a BNSH container')
                data.extend(part)
            try:
                records = decoder.bnsh_shaders(data, 0, label)
            except (struct.error, IndexError, SystemExit) as exc:
                raise ValueError(f'{label}: invalid BNSH at {offset:#x}: {exc}') from exc
            # Reading a standalone slice rebases pointers, but output provenance
            # must retain the original offset, exactly as scan_blob does.
            prefix = label + '#BNSH@0x0'
            for where, stage, control, code in records:
                if not where.startswith(prefix):
                    raise ValueError('unexpected BNSH decoder source label')
                yield (label + f'#BNSH@{offset:#x}' + where[len(prefix):], stage,
                       bytes(control), bytes(code))
        tail = window[-(len(MAGIC)-1):]
        position += len(block)


def summarize(records, decoder):
    rows, variants, seen = [], {}, set()
    provenance, count = hashlib.sha256(), 0
    for where, stage, control, code in records:
        key = decoder.skey(control, code)
        row = {'source': where, 'stage': stage, 'key': key,
               'control_size': len(control), 'code_size': len(code),
               'control_sha256': hashlib.sha256(control).hexdigest(),
               'code_sha256': hashlib.sha256(code).hexdigest()}
        provenance.update(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()+b'\n')
        count += 1
        identity = (stage, key, row['control_sha256'], row['code_sha256'])
        if identity not in seen:
            rows.append(row); seen.add(identity)
        # Match var_pairs: single-stage GLSLC records do not form BNSH pairs.
        if '#var' in where: variants.setdefault(where, {})[stage] = key
    pairs = sorted({(v['vs'], v['ps']) for v in variants.values() if 'vs' in v and 'ps' in v})
    return {'record_count': count, 'provenance_sha256': provenance.hexdigest(),
            'records': sorted(rows, key=lambda r: (r['source'],r['stage'],r['key'])), 'pairs': pairs}


def program_records(path, resources, decoder, verify_build):
    path=Path(path)
    size=path.stat().st_size
    if size>256*1024*1024: raise ValueError('program NSO input limit exceeded')
    with path.open('rb') as f: header=_exact(f,256)
    if header[:4]!=b'NSO0': raise ValueError('program input is not an NSO')
    regions=[]
    flags=struct.unpack_from('<I',header,12)[0]
    for i in range(3):
        offset, memory, length=struct.unpack_from('<III',header,0x10+16*i)
        stored=struct.unpack_from('<I',header,0x60+4*i)[0]
        if offset+(stored if flags>>i&1 else length)>size or memory+length>256*1024*1024:
            raise ValueError('program NSO segment bounds or image limit exceeded')
        if length: regions.append((memory,memory+length))
    regions.sort()
    if any(a[1]>b[0] for a,b in zip(regions,regions[1:])):
        raise ValueError('overlapping program NSO segments')
    build=header[64:80].hex()
    if verify_build: resources.check_build('main',build)
    # Rewriting still needs this program independently of RomFS. Reuse the
    # existing decompressor; only resource archives are streamed in this stage.
    image=decoder.nso_image(path)
    found=[]; decoder.scan_blob(image,'main',found)
    found+=decoder.glslc_shaders(image,'main',need=False)
    return build,found


def program_manifest(path, resources, decoder, verify_build):
    build,found=program_records(path,resources,decoder,verify_build)
    return {'build_id':build, 'build_checked':verify_build, **summarize(found,decoder)}


def manifest(resources, paths, decoder, *, main=None, verify_build=False,scratch=None):
    results=[]
    for path in sorted(set(paths)):
        entry=resources.stat(path)
        if entry.is_dir: raise IsADirectoryError(path)
        with resources.open(path,buffering=0) as stream:
            summary=summarize(iter_resource(stream,'/'+path,decoder,scratch=scratch),decoder)
        results.append({'path':path,'size':entry.size,**summary})
    program=program_manifest(main,resources,decoder,verify_build) if main else None
    all_records=[r for f in results for r in f['records']]+(program['records'] if program else [])
    return {'scope':'bnsh-bahs-sarc-yaz0-zstd-and-optional-program', 'complete_game_shader_scan':False,
            'files':results,'program':program,'unique_keys':sorted({r['key'] for r in all_records})}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--library', type=Path, required=True)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--base', type=Path)
    source.add_argument('--directory', type=Path)
    p.add_argument('--update', type=Path)
    p.add_argument('--keys', type=Path)
    p.add_argument('--title', type=lambda s: int(s, 16), default=0)
    p.add_argument('--main', type=Path, help='existing matching main NSO; checked against selected NSP ExeFS')
    select = p.add_mutually_exclusive_group(required=True)
    select.add_argument('--path', action='append')
    select.add_argument('--suffix', action='append')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--scratch-dir',type=Path,help='existing game-drive directory for bounded anonymous Zstandard staging')
    a = p.parse_args(argv)
    if a.base and not a.keys:
        p.error('--base requires --keys')
    if a.directory and (a.keys or a.update or a.title):
        p.error('directory mode cannot use NSP options')
    if a.output.exists():
        p.error('output exists; choose a new report path')
    from tools.nxrom.resourcefs import ResourceFS
    options = dict(directory=a.directory) if a.directory else dict(base=a.base, update=a.update, keys=a.keys, title=a.title)
    decoder = load_decoder()
    with ResourceFS(a.library, **options) as resources:
        paths = a.path if a.path else [e.path for e in resources.files() if e.path.endswith(tuple(a.suffix))]
        if not paths:
            raise ValueError('no resources matched the selection')
        report = manifest(resources, paths, decoder, main=a.main, verify_build=a.base is not None,scratch=a.scratch_dir)
    with a.output.open('x') as output:
        json.dump(report, output, indent=2); output.write('\n')
    print(json.dumps({'files': len(report['files']), 'unique_keys': len(report['unique_keys']),
                      'scope': report['scope'], 'complete_game_shader_scan': False}))


if __name__ == '__main__':
    # Run as python -m tools.nxrom.shader_scan from the repository root.
    try:
        main()
    except (OSError, ValueError) as exc:
        sys.exit('[RED] BNSH scan failed: ' + str(exc))
