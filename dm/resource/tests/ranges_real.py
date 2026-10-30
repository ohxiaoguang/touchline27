"""Compare requested NSP ranges with the user's existing extracted view.
Never creates an extraction; selected bytes stay only in memory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--native',type=Path,required=True)
a=p.parse_args()
def manifest(path):
    out={}
    for line in path.read_text().splitlines():
        c=line.split('\t')
        if c[0]=='f': out[c[1]]=(int(c[2]),c[3])
    return out
base=manifest(a.output/'base-native.tsv');updated=manifest(a.output/'updated-native.tsv')
changed=[n for n,v in updated.items() if base.get(n)!=v]
big=sorted(updated,key=lambda n:updated[n][0],reverse=True)[:8]
rng=random.Random(23);selected=list(dict.fromkeys(changed[:12]+big+rng.sample(list(updated),12)))
root=a.root;directory=root/'01006BB00C6F0000_build/extract/v131072/RomFS'
cmd=[str(a.native.resolve()),'--base',str(next(root.glob('*[[]01006BB00C6F0000[]]*.nsp'))),'--update',str(next(root.glob('*[[]01006BB00C6F0800[]]*.nsp'))),'--keys',str(root/'prod.keys')]
results=[]
for name in selected:
    size=updated[name][0];offsets=[0,1,max(0,size//2-17),max(0,size-23),size,size+3]
    if size>1048576:offsets.append(1048567)
    for off in dict.fromkeys(offsets):
        n=16396
        run=subprocess.run(cmd+['--read',name.lstrip('/'),'--offset',str(off),'--length',str(n)],capture_output=True,check=True)
        with (directory/name.lstrip('/')).open('rb') as f:f.seek(off);expected=f.read(n)
        equal=run.stdout==expected
        results.append({'path':name,'offset':off,'length':n,'returned':len(run.stdout),'equal':equal,'sha256':hashlib.sha256(run.stdout).hexdigest()})
        if not equal:raise SystemExit(f'range mismatch: {name} at {off}')
(a.output/'ranges.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'files':len(selected),'ranges':len(results),'all_equal':True,'changed_files_in_view':len(changed)}))
