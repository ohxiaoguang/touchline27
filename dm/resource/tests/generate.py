from pathlib import Path
import sys
from fixture import *
p=Path(sys.argv[1]);p.mkdir(parents=True,exist_ok=True)
files=write_fixture(p)
(p/'base.nsp').write_bytes(pfs([('program.nca',with_code(nca(romfs(files))))]))
(p/'base.xci').write_bytes(xci(files,code=True))
new=dict(files);new['nested/big']=files['nested/big'][:-8000]+b'UPDATED!'*1000
(p/'update.nsp').write_bytes(pfs([('patch.nca',with_code(patch_nca(romfs(files),romfs(new))))]))

(p/'aoc.nsp').write_bytes(aoc_nsp(files={'small':b'DLC content'}))
