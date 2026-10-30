"""Compare a stream-scan report with the original decoder on existing files.

Explicit selected inputs only; the reference files are never written. The report
checks every record, including duplicate sources, via an ordered provenance hash.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.nxrom.shader_scan import load_decoder


def bounded_reference_members(data):
    """Original sarc_members layout, avoiding split() over entire asset bodies.

    Deliberately independent of the new stream index parser. On valid little-
    endian inputs it yields the same names/bodies, with only name slicing bounded.
    """
    header, _, _, payload = struct.unpack_from('<HHII',data,4)
    count=struct.unpack_from('<H',data,header+6)[0]
    names=header+12+16*count+8
    for i in range(count):
        _, attributes, start, end=struct.unpack_from('<IIII',data,header+12+16*i)
        if attributes>>24:
            offset=names+(attributes&0xffffff)*4
            stop=data.find(b'\0',offset)
            name=data[offset:stop if stop>=0 else len(data)].decode('utf-8','replace')
        else: name='#'+str(i)
        yield name,data[payload+start:payload+end]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'directory', 'profile-map', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--main', type=Path)
    a = p.parse_args()
    if a.output.exists(): p.error('output exists; choose a new report path')
    actual = json.loads(a.manifest.read_text())
    decoder = load_decoder()
    decoder.sarc_members=bounded_reference_members
    reference = a.directory.resolve()
    total, keys, pairs = 0, set(), set()
    sources=[(entry,False) for entry in actual['files']]
    if actual.get('program'):
        if not a.main: p.error('--main is required for this report')
        sources.append((actual['program'],True))
    for entry, program in sources:
        print('Reference scan: '+('main' if program else entry['path']),file=sys.stderr,flush=True)
        if program:
            with a.main.open('rb') as source: header=source.read(80)
            if header[64:80].hex()!=entry['build_id']: raise ValueError('program build mismatch')
            data=decoder.nso_image(a.main)
            found=[]; decoder.scan_blob(data,'main',found)
            found+=decoder.glslc_shaders(data,'main',need=False)
            label='main'
        else:
            label=entry['path']
            path = (reference/label).resolve()
            if not path.is_relative_to(reference): raise ValueError('path escapes reference root')
            if path.stat().st_size != entry['size']: raise ValueError('source size mismatch')
            data = path.read_bytes()
            found = []; decoder.scan_blob(data, '/'+label, found)
        # Check raw records, not only keys: trailing controls and provenance may
        # differ without changing the key used by the runtime.
        digest = hashlib.sha256()
        rows, seen = [], set()
        for where, stage, control, code in found:
            key = decoder.skey(control, code)
            row = {'source': where, 'stage': stage, 'key': key,
                   'control_size': len(control), 'code_size': len(code),
                   'control_sha256': hashlib.sha256(control).hexdigest(),
                   'code_sha256': hashlib.sha256(code).hexdigest()}
            digest.update(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()+b'\n')
            identity = (stage, key, row['control_sha256'], row['code_sha256'])
            if identity not in seen: rows.append(row); seen.add(identity)
        expected_pairs = sorted(decoder.var_pairs(found))
        if digest.hexdigest()!=entry['provenance_sha256'] or len(found)!=entry['record_count']:
            raise ValueError('raw record/provenance mismatch: '+label)
        if sorted(rows, key=lambda r:(r['source'],r['stage'],r['key']))!=entry['records']:
            raise ValueError('code/control record mismatch: '+label)
        if [list(pair) for pair in expected_pairs]!=entry['pairs']:
            raise ValueError('pair mismatch: '+label)
        keys.update(r['key'] for r in rows); pairs.update(expected_pairs); total += len(found)
    if sorted(keys)!=actual['unique_keys']: raise ValueError('unique key inventory mismatch')
    profile_keys = {line.split('\t')[3] for line in a.profile_map.read_text().splitlines()
                    if line and not line.startswith('#') and not line.startswith('package\t')}
    if not keys <= profile_keys: raise ValueError('scanned keys absent from the supplied profile table')
    report = {'files':len(actual['files']), 'raw_records':total, 'unique_keys':len(keys),
              'pairs':len(pairs), 'program':actual.get('program') is not None,
              'all_records_and_provenance_equal':True,
              'all_pairs_equal':True, 'keys_in_profile':True,
              'profile_keys_outside_selection':len(profile_keys-keys),
              'complete_game_shader_scan':False}
    with a.output.open('x') as f: json.dump(report, f, indent=2); f.write('\n')
    print(json.dumps(report))


if __name__=='__main__': main()
