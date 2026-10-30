"""Bounded host smoke test; isolated writable state, never the user's save."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--host',type=Path,required=True)
p.add_argument('--profile',type=Path,required=True)
p.add_argument('--title',required=True,help='base title ID; no default game')
p.add_argument('--package',required=True,help='prepared program version, e.g. v0')
p.add_argument('--mode',choices=('nsp','directory'),required=True)
p.add_argument('--libraries',type=Path,help='Override the prepared Metal library root')
p.add_argument('--patched',type=Path,help='Explicit rewritten program directory (e.g. the new App bundle)')
p.add_argument('--fonts',type=Path,help='Explicit runtime font directory (e.g. the new App bundle)')
p.add_argument('--mods',type=Path,help='Mod overlay root mounted as DM_ROMFS_OVERLAY (a mods/romfs tree)')
p.add_argument('--seconds',type=float,default=20,help='Bounded run duration (1 to 1800 seconds)')
p.add_argument('--window',action='store_true',help='Enable the macOS window and actual presentation')
p.add_argument('--shots',default='60,180,600',help='Comma-separated present-frame screenshot numbers')
p.add_argument('--shot-output',help='Capture through present_encode at WIDTHxHEIGHT instead of dumping the source texture')
p.add_argument('--input',help='Optional DM_KEYS script; only the isolated test save is writable')
p.add_argument('--keyboard',help='DM_KBD text for the game software keyboard')
p.add_argument('--save-seed',type=Path,help='Read-only source copied into a new isolated test save')
p.add_argument('--control',action='store_true',help='Enable the existing DM_CTL diagnostic command file')
p.add_argument('--opmode',choices=('handheld','docked'),help='Explicit console mode for isolated regression')
p.add_argument('--fullscreen',action='store_true')
p.add_argument('--metal-hud',action='store_true')
p.add_argument('--audio',action='store_true',help='Use the real audio sink, as the launcher does')
p.add_argument('--language',help='Explicit language for matching a user run')
a=p.parse_args()
if len(a.title)!=16 or any(c not in '0123456789abcdefABCDEF' for c in a.title): p.error('--title requires 16 hexadecimal digits')
a.title=a.title.upper()
if not a.package.startswith('v') or not a.package[1:].isdigit(): p.error('--package requires v followed by digits')
if not 1 <= a.seconds <= 1800: p.error('--seconds must be between 1 and 1800')
if not all(x.isdigit() and int(x)>0 for x in a.shots.split(',')): p.error('--shots requires positive frame numbers')
if a.shot_output:
    dimensions=a.shot_output.split('x')
    if len(dimensions)!=2 or not all(x.isdigit() and 0<int(x)<=4096 for x in dimensions):
        p.error('--shot-output requires WIDTHxHEIGHT, each from 1 to 4096')
for name in ('patched','fonts','mods'):
    value=getattr(a,name)
    if value and not value.is_dir(): p.error('--'+name+' must be an existing directory')
root=a.root; build=root/(a.title+'_build'); run=a.output/('smoke-'+a.mode)
patched=(a.patched or build/('patched_'+a.package)).resolve()
run.mkdir(); (run/'temp').mkdir()
if a.save_seed:
    # Never mount the source itself, or follow symlinks to files outside it.
    seed=a.save_seed.resolve(strict=True)
    if not seed.is_dir() or any(p.is_symlink() for p in seed.rglob('*')):
        p.error('--save-seed must be a directory without symlinks')
    shutil.copytree(seed,run/'save')
else: (run/'save').mkdir()
env={k:v for k,v in os.environ.items() if not k.startswith('DM_')}
env.update(DM_ROOT=str(run),DM_SAVE=str(run/'save'),DM_TEMP=str(run/'temp'),DM_FONT_DIR=str(build/'font'),DM_MSL_DIR=str(build/'shader/cache'),DM_NVN_SHMAP=str(a.profile.resolve()/'shader_map.tsv'),DM_RESOURCE_BACKEND=a.mode,DM_FSLOG=str(run/'reads.tsv'),DM_FSLOG_HASH='1')
env['DM_MEMSTAT']=str(run/'memory.tsv')
if a.libraries: env['DM_MSL_DIR']=str(a.libraries.resolve())
if a.fonts: env['DM_FONT_DIR']=str(a.fonts.resolve())
if a.mods: env['DM_ROMFS_OVERLAY']=str(a.mods.resolve())
if a.opmode: env['DM_OPMODE']='0' if a.opmode=='handheld' else '1'
if a.fullscreen: env['DM_FULLSCREEN']='1'
if a.metal_hud: env['DM_METAL_HUD']='1'
if a.audio: env['DM_AUDIO']='1'
if a.language: env['DM_LANG']=a.language
if a.window:
    env.update(DM_WINDOW='1',DM_NVN_SHOT=a.shots+':'+str(run/'frame-%d.png'))
    if a.shot_output: env['DM_NVN_SHOT_OUT']=a.shot_output
if a.input: env['DM_KEYS']=a.input
if a.keyboard is not None: env['DM_KBD']=a.keyboard
if a.control:
    (run/'control.txt').touch(exist_ok=False)
    env['DM_CTL']=str(run/'control.txt')
if a.mode=='nsp':
    # An XCI gamecard base mounts through the same nsp backend (content-detected).
    bases=[p for suffix in ('.nsp','.xci') for p in root.glob('*[[]'+a.title+'[]]*'+suffix)]
    updates=[] if a.package=='v0' else list(root.glob('*[[]'+f'{int(a.title,16)+0x800:016X}'+'[]]*.nsp'))
    if len(bases)!=1 or (a.package!='v0' and len(updates)!=1):p.error('select one unambiguous NSP base/update pair')
    env.update(DM_RESOURCE_NSP=str(bases[0]),DM_RESOURCE_KEYS=str(root/'prod.keys'))
    if updates:env['DM_RESOURCE_UPDATE']=str(updates[0])
else: env['DM_ROMFS']=str(build/'extract'/a.package/'RomFS')
log=run/'host.log'; t=time.perf_counter();stop_reason='duration'
with log.open('xb') as f:
    child=subprocess.Popen([str(a.host.resolve()),str(patched)],env=env,cwd=run,stdout=f,stderr=subprocess.STDOUT)
    try:
        (run/'host.pid').write_text(str(child.pid)+'\n')
        while child.poll() is None and time.perf_counter()-t<a.seconds:
            if log.stat().st_size>8*1024*1024:
                stop_reason='log_limit';break
            time.sleep(.25)
    finally:
        spontaneous=child.poll()
        if spontaneous is not None: stop_reason='process_exit'
        if spontaneous is None:
            child.terminate()
            try: child.wait(5)
            except subprocess.TimeoutExpired: child.kill();child.wait()
report={'mode':a.mode,'seconds':time.perf_counter()-t,'stop_reason':stop_reason,'spontaneous_exit':spontaneous,'final_exit':child.returncode,'log_bytes':log.stat().st_size,'read_records':sum(1 for _ in (run/'reads.tsv').open()) if (run/'reads.tsv').exists() else 0,'isolated_save':True,'save_seed':str(seed) if a.save_seed else None,'libraries':env['DM_MSL_DIR'],'window':a.window,'opmode':a.opmode,'language':a.language,'fullscreen':a.fullscreen,'metal_hud':a.metal_hud,'audio':a.audio,'screenshots':sorted(x.name for x in run.glob('frame-*.png'))}
report.update(patched=str(patched),fonts=env['DM_FONT_DIR'],mods=env.get('DM_ROMFS_OVERLAY'))
report.update(title_id=a.title,version=a.package)
(run/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if stop_reason=='log_limit' or (spontaneous is not None and spontaneous!=0):
    raise SystemExit(1)
