"""Fail-closed orchestration of the existing no-RomFS preparation/build stages.

Each invocation owns a new work directory. Reuse is explicit and revalidated;
failed work is retained, never overwritten or silently treated as a cache.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from tools.nxrom.prepared_build import validate_prepared,validate_context
from tools.nxrom.shader_package import digest


def preflight(a,repo):
    from scripts import build_ipa_from_nsp as pipeline
    sys.path.insert(0,str(repo/'dm/games')); import game
    root=a.nsp_dir.expanduser().resolve(); work=a.work.expanduser().resolve()
    profile=game.Game(a.profile.expanduser().resolve())
    keys=a.keys.expanduser().resolve()
    prepared=a.prepared.expanduser().resolve() if a.prepared else work/'prepared'
    context=a.shader_context.expanduser().resolve() if a.shader_context else work/'shaders'
    if sys.platform!='darwin': raise ValueError('macOS is required for Apple Shader compilation and packaging')
    if not root.is_dir() or not keys.is_file(): raise ValueError('missing NSP folder or user keys file')
    if (work==root or not work.is_relative_to(root) or work.exists() or a.work.is_symlink()
        or profile.dir.is_relative_to(work) or keys.is_relative_to(work)):
        raise ValueError('choose a new work directory under the game NSP folder, separate from inputs')
    for explicit,path in ((a.prepared,prepared),(a.shader_context,context)):
        if explicit and (not path.is_dir() or path.is_relative_to(work) or work.is_relative_to(path)):
            raise ValueError('reused inputs must exist outside the new work directory and its ancestors')
    title,family=pipeline.scan_nsps(root)
    if title!=profile.title_id or family['dlc']: raise ValueError('requires one matching game and no DLC NSPs')
    versions=pipeline.nsp_versions(family,profile.builds())
    if (a.package not in versions or a.package not in profile.builds()
        or profile.words('shader_versions')!=[a.package]):
        raise ValueError('requires one matching registered Shader version present in the NSP folder')
    if family['base'].suffix.lower() not in ('.nsp','.xci') or (versions[a.package] and versions[a.package].suffix.lower()!='.nsp'):
        raise ValueError('requires an uncompressed NSP/XCI base and NSP update inputs')
    if a.app_name and (a.app_name in ('.','..') or any(c in a.app_name for c in ('/','\\','\x00'))):
        raise ValueError('app name must be a single file name')
    env={k:v for k,v in os.environ.items() if not k.startswith(('DM_','DMSH_'))}
    env.update(DM_GAME=profile.id,DM_GAMES_FIRST='1',DM_GAMES_DIR=str(profile.dir.parent),J=str(a.jobs),
               PYTHONPYCACHEPREFIX=str(work/'tmp/pycache'))
    env['PATH']=os.pathsep.join(pipeline.TOOL_PATHS+[env.get('PATH','/usr/bin:/bin')])
    # Preflight validation must not create the requested work directory.
    check_env=dict(env,PYTHONDONTWRITEBYTECODE='1');check_env.pop('PYTHONPYCACHEPREFIX',None)
    if a.prepared: validate_prepared(prepared,profile,a.package)
    if a.shader_context:
        selected=game.Game(context/'profiles'/profile.id)
        # The original Profile header may have a different measured tools lock.
        # Verify the immutable preparation tables against both Profiles instead.
        for name in ('game.tsv','shader_map.tsv','shader_facts.tsv','shader_pairs.tsv'):
            if digest(profile.table(name))!=digest(selected.table(name)):
                raise ValueError('reused Shader Profile differs from selected input: '+name)
        for target in (('macos','ios') if a.target=='both' else (a.target,)):
            validate_context(context,selected,sys.executable,check_env,target,current_repo=repo)
    extractor=a.nsp_extractor or root/f'{profile.id}_build/tools/nx_extract/nx_extract'
    if not a.prepared and (not extractor.is_file() or not os.access(extractor,os.X_OK)):
        raise ValueError('existing nx_extract executable required; supply --nsp-extractor')
    tools={'make','xcrun'}
    if not a.prepared or not a.shader_context: tools.add('dotnet')
    if not a.shader_context: tools.add('spirv-cross')
    if a.target in ('ios','both'): tools.update(('xcodebuild','xcodegen'))
    for tool in sorted(tools):
        if not shutil.which(tool,path=env['PATH']): raise ValueError('installed build dependency missing: '+tool)
    if pipeline.free_gb(root)<(15 if not a.shader_context else 8):
        raise ValueError('insufficient free game-drive space for the requested workflow')
    env['PYTHONUNBUFFERED']='1'
    return root,work,keys,profile,prepared,context,env,extractor


def build(a,repo):
    from scripts import build_ipa_from_nsp as pipeline
    pipeline.PROG.mode=a.progress
    root,work,keys,profile,prepared,context,env,extractor=preflight(a,repo)
    import game
    work.mkdir(parents=True); (work/'tmp').mkdir()
    record={'schema':1,'title_id':profile.id,'version':a.package,'target':a.target,
            'status':'running','prepared':str(prepared),'shader_context':str(context),
            'stages':[],'artifacts':{},'romfs_extracted':False,
            'unused_compressed_inputs':sorted(p.name for p in root.iterdir() if p.suffix.lower() in ('.nsz','.ncz','.xcz')),
            'game_run_verified':False,'device_run_verified':False}
    report=work/'pipeline-report.json'
    def save():
        temp=work/'pipeline-report.tmp';temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(report)
    def stage(name,command=None):
        row={'name':name,'status':'running' if command else 'reused'};record['stages'].append(row);save()
        start=time.monotonic()
        if command:
            pipeline.say('External NSP workflow: '+name)
            subprocess.run([str(x) for x in command],env=env,check=True)
            row['status']='complete'
        row['seconds']=round(time.monotonic()-start,3);save()
    common=[sys.executable,repo/'scripts/build_ipa_from_nsp.py',root,'--keys',keys,
            '--resource-backend','nsp','--package',a.package,'--progress',a.progress]
    save()
    try:
        if record['unused_compressed_inputs']:
            pipeline.say('Using uncompressed NSP inputs only; compressed files are not read or decompressed: '+
                         ', '.join(record['unused_compressed_inputs']))
        stage('prepare',None if a.prepared else common+['--prepare-nsp-resources',prepared,'--nsp-extractor',extractor])
        validate_prepared(prepared,profile,a.package)
        record['prepared_ready_sha256']=digest(prepared/'ready.json');save()
        stage('shaders',None if a.shader_context else [sys.executable,repo/'scripts/compile_nsp_shaders.py',
              '--nsp-dir',root,'--prepared',prepared,'--profile',profile.dir,'--package',a.package,
              '--output',context,'--jobs',a.jobs,'--progress',a.progress])
        selected=game.Game(context/'profiles'/profile.id)
        validate_prepared(prepared,selected,a.package)
        for target in (('macos','ios') if a.target=='both' else (a.target,)):
            validate_context(context,selected,sys.executable,env,target,current_repo=repo)
        record['shader_summary_sha256']=digest(context/'shader-summary.json');save()
        env['DM_GAMES_DIR']=str(selected.dir.parent)
        name=a.app_name or 'External NSP'
        if a.target in ('macos','both'):
            w=work/'macos'; out=w/(name+'.app')
            cmd=[sys.executable,repo/'scripts/build_mac_app.py','--nsp-dir',root,'--keys',keys,
                 '--use-nsp-prepared',prepared,'--shader-context',context,'--profile',selected.dir,
                 '--package',a.package,'--work',w,'--output',out,'--progress',a.progress]
            if a.app_name: cmd+=['--name',a.app_name]
            stage('macos',cmd)
            result=w/'build-report.json'
            record['artifacts']['macos']={'path':str(out),'report':str(result),'report_sha256':digest(result)};save()
        if a.target in ('ios','both'):
            w=work/'ios';out=w/(name+'.ipa')
            cmd=common+['--use-nsp-prepared',prepared,'--ios-shader-context',context,'--nsp-build-work',w,'--out',out]
            if a.app_name: cmd+=['--app-name',a.app_name]
            stage('ios',cmd)
            result=w/'build-report.json'
            record['artifacts']['ios']={'path':str(out),'sha256':digest(out),'report':str(result),'report_sha256':digest(result)};save()
        record['status']='complete';save()
        pipeline.say('External NSP workflow complete: '+str(report))
        return record
    except BaseException:
        record['status']='failed'
        if record['stages']:
            record['failure_stage']=record['stages'][-1]['name']
            record['stages'][-1]['status']='failed'
        # Do not persist exception/command strings: they can include a user key path.
        save()
        raise
