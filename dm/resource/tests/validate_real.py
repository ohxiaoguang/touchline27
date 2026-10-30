"""Explicit, read-only differential validation. Records go only to --output.
No resource extraction and no automatic search beyond --root's top-level NSPs.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--title',required=True)
p.add_argument('--native',type=Path,required=True)
p.add_argument('--oracle',type=Path,required=True)
a=p.parse_args()
nsps=list(a.root.glob('*.nsp'))+list(a.root.glob('*.xci'))
base=[x for x in nsps if f'[{a.title}]' in x.name]
update=[x for x in a.root.glob('*.nsp') if f'[{int(a.title,16)+0x800:016X}]' in x.name.upper()]
if len(base)!=1 or len(update)!=1: raise SystemExit('select one unambiguous base/update pair')
a.output.mkdir(exist_ok=True)
summary={'title':a.title,'base':base[0].name,'update':update[0].name,'tests':[]}
for patched in (False,True):
    label='updated' if patched else 'base'
    manifests={}
    for reader in ('native','libhac'):
        path=a.output/f'{label}-{reader}.tsv'; log=a.output/f'{label}-{reader}.log'
        if path.exists() or log.exists(): raise SystemExit('output exists; use a new validation directory')
        if reader=='native': cmd=[str(a.native.resolve()),'--base',str(base[0]),'--keys',str(a.root/'prod.keys'),'--title',a.title,'--verify']+(['--update',str(update[0])] if patched else [])
        else: cmd=['dotnet',str(a.oracle.resolve()),str(a.root/'prod.keys'),str(base[0])]+([str(update[0])] if patched else [])
        t=time.perf_counter()
        with path.open('xb') as out, log.open('xb') as err: result=subprocess.run(cmd,stdout=out,stderr=err)
        item={'view':label,'reader':reader,'exit':result.returncode,'seconds':time.perf_counter()-t}
        summary['tests'].append(item); print(json.dumps(item),flush=True)
        if result.returncode: (a.output/'summary.json').write_text(json.dumps(summary,indent=2));raise SystemExit('reader failed; inspect key-free error log')
        manifests[reader]=set(path.read_text().splitlines())
    equal=manifests['native']==manifests['libhac']
    files=[line.split('\t') for line in manifests['native'] if line.startswith('f\t')]
    item={'view':label,'equal':equal,'files':len(files),'entries':len(manifests['native']),'bytes':sum(int(f[2]) for f in files)}
    summary['tests'].append(item);print(json.dumps(item),flush=True)
    if not equal: (a.output/'summary.json').write_text(json.dumps(summary,indent=2));raise SystemExit('manifest mismatch')
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
