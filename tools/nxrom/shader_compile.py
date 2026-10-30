"""Build both Shader targets from verified packages in an isolated source snapshot.

No resource extraction, old library prefill, shared CAS writes or Profile updates.
A successful context is published only after all keys and both targets validate.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from tools.nxrom.prepared_build import validate_prepared,validate_context,shader_keys
from tools.nxrom.shader_package import digest


def runtime_root(env):
    """Resolve an installed .NET runtime through its muxer (Homebrew wraps it)."""
    muxer=shutil.which('dotnet',path=env['PATH'])
    result=subprocess.run([muxer,'--list-runtimes'],env=env,check=True,capture_output=True,text=True)
    for location in re.findall(r'^Microsoft\.NETCore\.App\s+\S+\s+\[(.+)\]$',result.stdout,re.M):
        root=Path(location).parents[1]
        if (root/'shared/Microsoft.NETCore.App').is_dir(): return str(root)
    raise ValueError('installed .NET runtime root not found; see dotnet --list-runtimes')


def validate_paths(nsp_dir,prepared,profile,output):
    if (not nsp_dir.is_dir() or output==nsp_dir or not output.is_relative_to(nsp_dir)
        or output.exists() or output.is_relative_to(prepared) or prepared.is_relative_to(output)
        or profile.is_relative_to(output) or output.is_relative_to(profile)):
        raise ValueError('choose a new Shader output folder under the game NSP folder, separate from inputs')


def chain_header(output):
    """The chain version header of the snapshot: it belongs to the source tree (one for every game), not to a game profile."""
    return Path(output)/'toolchain/gfx/nvn/dmsh_chain.h'


def chain_of(output):
    """The chain version the snapshot's tools wrote (dmsh_chain.py --header); a missing or unreadable header is an error, never a default."""
    path=chain_header(output)
    if not path.is_file(): raise ValueError('no chain version header in the Shader snapshot: '+str(path))
    match=re.search(r'#define DMSH_CHAIN "([a-f0-9]{12})"',path.read_text())
    if not match: raise ValueError('unreadable chain version header: '+str(path))
    return match.group(1)


def snapshot(repo,profile,output):
    """Copy source/tool bytes, rather than source links that later edits can change."""
    gfx=output/'toolchain/gfx/tools'; gfx.mkdir(parents=True)
    for path in sorted((repo/'dm/gfx/tools').glob('*.py')): shutil.copyfile(path,gfx/path.name)
    shutil.copyfile(repo/'dm/gfx/tools/dmsh_chain.lock',gfx/'dmsh_chain.lock')
    # The chain version header lives in the source tree beside the NVN layer; dmsh_chain.py --header rewrites this same path inside the snapshot
    nvn=output/'toolchain/gfx/nvn'; nvn.mkdir()
    header=repo/'dm/gfx/nvn/dmsh_chain.h'
    if header.is_file(): shutil.copyfile(header,nvn/'dmsh_chain.h')
    xlate=gfx/'dmsh_xlate'; xlate.mkdir()
    for name in ('Program.cs','dmsh_xlate.csproj'):
        shutil.copyfile(repo/'dm/gfx/tools/dmsh_xlate'/name,xlate/name)
    # The already installed translator is a runtime dependency, not rebuilt here.
    shutil.copytree(repo/'dm/gfx/tools/dmsh_xlate_bin',gfx/'dmsh_xlate_bin')
    games=output/'toolchain/games'; games.mkdir()
    shutil.copyfile(repo/'dm/games/game.py',games/'game.py')
    ios=output/'toolchain/ios/tools'; ios.mkdir(parents=True)
    shutil.copyfile(repo/'dm/ios/tools/ios_metal.py',ios/'ios_metal.py')
    selected=output/'profiles'/profile.id; selected.mkdir(parents=True)
    for path in sorted(profile.dir.iterdir()):
        if path.suffix in ('.tsv','.h'):
            if path.is_symlink() or not path.is_file(): raise ValueError('Profile input must be a regular file: '+path.name)
            shutil.copyfile(path,selected/path.name)
    return gfx,selected


def check_summary(cache,keys,log):
    results=json.loads((cache/'_b_build.json').read_text())
    if (not isinstance(results,list) or len(results)!=len(keys)
        or {row.get('key') for row in results}!=keys
        or any(row.get('st')!='ok' for row in results)):
        raise ValueError('Shader compiler did not successfully build every registered key; see shader-build.log')
    if re.search(r'^\s*\[RED\]',log,re.M):
        raise ValueError('Shader build emitted RED diagnostics; context not published')
    return {'compiler_warning_lines':sum('warning:' in line for line in log.splitlines()),
            'compiler_error_lines':sum('error:' in line for line in log.splitlines())}


def compile_prepared(args,repo):
    from scripts import build_ipa_from_nsp as pipeline
    sys.path.insert(0,str(repo/'dm/games')); import game
    nsp_dir=args.nsp_dir.expanduser().resolve(); prepared=args.prepared.expanduser().resolve()
    output=args.output.expanduser().resolve(); profile=game.Game(args.profile.expanduser().resolve())
    if getattr(args,'finalize_existing',False):
        if (not output.is_dir() or output==nsp_dir or not output.is_relative_to(nsp_dir)
            or output.is_relative_to(prepared) or prepared.is_relative_to(output)
            or profile.dir.is_relative_to(output) or output.is_relative_to(profile.dir)):
            raise ValueError('finalization requires a separate existing context under the NSP folder')
        env=dict(os.environ,DM_GAME=profile.id,DM_GAMES_FIRST='1',DM_GAMES_DIR=str(output/'profiles'),
                 WORK=str(output/'tmp'),PYTHONPYCACHEPREFIX=str(output/'tmp/pycache'))
        pipeline.PROG.plan(2)
        return finalize_context(prepared,profile,args.package,output,repo,env,recovered=True)
    validate_paths(nsp_dir,prepared,profile.dir,output)
    if not 1<=args.jobs<=32: raise ValueError('jobs must be from 1 to 32')
    report=validate_prepared(prepared,profile,args.package)
    if pipeline.free_gb(nsp_dir)<10: raise ValueError('less than 10 GB free for isolated Shader compilation')
    env=dict(os.environ)
    env['PATH']=os.pathsep.join(pipeline.TOOL_PATHS+[env.get('PATH','/usr/bin:/bin')])
    for name in ('dotnet','spirv-cross','xcrun'):
        if not shutil.which(name,path=env['PATH']): raise ValueError('installed compiler dependency missing: '+name)
    # The .NET apphost otherwise may miss Homebrew's installed runtime root.
    env['DOTNET_ROOT']=env['DOTNET_ROOT_ARM64']=runtime_root(env)
    output.mkdir(parents=True)
    gfx,selected=snapshot(repo,profile,output)
    (output/'tmp').mkdir(); logs=output/'logs'; logs.mkdir()
    env.update(DM_GAME=profile.id,DM_GAMES_FIRST='1',DM_GAMES_DIR=str(output/'profiles'),
               DM_ROOT=str(output),WORK=str(output/'tmp'),TMPDIR=str(output/'tmp'),J=str(args.jobs),
               DMSH_CAS=str(output/'cache/cas'),IOSOUT=str(output/'ios'),
               XLATE=str(gfx/'dmsh_xlate_bin/dmsh_xlate'),PYTHONPYCACHEPREFIX=str(output/'tmp/pycache'))
    env.pop('DMSH_PREFILL',None)
    copied=game.Game(selected)
    pipeline.PROG.plan(4)
    pipeline.PROG.stage('Shader chain',step='measure installed tools in isolated snapshot')
    pipeline.run([sys.executable,gfx/'dmsh_chain.py','--update-lock'],logs/'tool-lock.log',env=env)
    pipeline.run([sys.executable,gfx/'dmsh_chain.py','--check-tools'],logs/'check-tools.log',env=env)
    pipeline.run([sys.executable,gfx/'dmsh_chain.py','--header'],logs/'chain-header.log',env=env)
    chain=chain_of(output)
    pipeline.PROG.end(chain)
    pipeline.PROG.stage('Shader compilation',step='cold Mac and iOS translation/compile')
    pipeline.PROG.watch(pipeline.ShaderWatch(copied,output/'ios',output/'tmp'))
    try:
        pipeline.run([sys.executable,gfx/'dmsh_build.py',prepared/'shader/pkg',output/'cache'],logs/'shader-build.log',env=env)
    finally: pipeline.PROG.watch(None)
    return finalize_context(prepared,profile,args.package,output,repo,env)


def finalize_context(prepared,profile,version,output,repo,env,*,recovered=False):
    """Validate completed outputs and derive runtime tables without recompiling.

    Recovery is explicit; it never changes an already published context, copies
    libraries from elsewhere, or claims a missing build-start history as proven.
    """
    from scripts import build_ipa_from_nsp as pipeline
    import game
    marker=output/'shader-summary.json'
    if marker.exists() or marker.is_symlink(): raise ValueError('context already published; choose another output')
    report=validate_prepared(prepared,profile,version)
    gfx=output/'toolchain/gfx/tools'; selected=output/'profiles'/profile.id
    copied=game.Game(selected)
    validate_prepared(prepared,copied,version)
    writes=[selected/'c1_full.tsv',selected/'cb_extent.tsv',output/'logs/c1-guard.log',
            output/'logs/cb-extent.log']+[output/name for name in
            ('source-inventory.json','macos-shader-inventory.json','ios-shader-inventory.json',
             'compile-report.json','shader-summary.json')]
    if any(p.is_symlink() or not p.resolve().is_relative_to(output) for p in writes):
        raise ValueError('finalization output links escape the isolated context')
    chain=chain_of(output)
    logs=output/'logs'
    keys=shader_keys(copied); cache=output/'cache'/('b-'+chain)
    compiler_log=(logs/'shader-build.log').read_text(errors='replace')
    diagnostics=check_summary(cache,keys,compiler_log)
    if diagnostics['compiler_error_lines']: raise ValueError('compiler error diagnostics; context not published')
    if {p.name[:-8] for p in cache.glob('*_b.metal')}!=keys:
        raise ValueError('translated Metal sources do not cover every registered key')
    if not recovered: pipeline.PROG.end(f'{len(keys):,} Shader keys verified')
    pipeline.PROG.stage('Shader runtime tables',step='regenerate c1 guard and uniform extents')
    pipeline.run([sys.executable,gfx/'c1_guard.py',cache,copied.table('c1_full.tsv')],logs/'c1-guard.log',env=env)
    pipeline.run([sys.executable,gfx/'cb_extent.py',cache,copied.table('cb_extent.tsv')],logs/'cb-extent.log',env=env)
    pipeline.PROG.end('copied Profile updated; original unchanged')
    pipeline.PROG.stage('Shader validation',step='coverage, platform records, library headers and hashes')
    summary={'chain':chain,'shader_count':len(keys),'failed':0,**diagnostics,'targets':{}}
    for folder in ('cache','ios'):
        path=output/folder/('b-'+chain)
        summary['targets'][folder]={'reflections':len(list(path.glob('*_b.json'))),
                                    'library_files':len(list(path.glob('*.metallib')))}
    inventories={}
    for target in ('macos','ios'):
        checked=validate_context(output,copied,sys.executable,env,target,summary=summary,current_repo=repo)
        inventories[target]=checked.pop('files_sha256')
    # Inputs remain unchanged even if compilation took a long time.
    validate_prepared(prepared,profile,version)
    source_files={p.relative_to(output).as_posix():digest(p) for p in (output/'toolchain').rglob('*') if p.is_file()}
    (output/'source-inventory.json').write_text(json.dumps(source_files,indent=2)+'\n')
    for target,inventory in inventories.items():
        (output/(target+'-shader-inventory.json')).write_text(json.dumps(inventory,indent=2)+'\n')
    cache_stats=re.search(r'shader cache: hit (\d+), rebuilt (\d+)',compiler_log)
    record={'title_id':profile.id,'version':version,'prepared_ready_sha256':digest(prepared/'ready.json'),
            'prepared_package_sha256':report['package_sha256'],'source_inventory_sha256':digest(output/'source-inventory.json'),
            'profile':str(selected),'chain':chain,'old_library_prefill':None if recovered else False,
            'shared_cas_used':None if recovered else False,'cold_cache_at_start':None if recovered else True,
            'finalized_existing':recovered,
            'compiler_reported_shader_cache':{'hit':int(cache_stats[1]),'rebuilt':int(cache_stats[2])} if cache_stats else None,
            'romfs_extracted':False,'game_run_verified':False}
    (output/'compile-report.json').write_text(json.dumps(record,indent=2)+'\n')
    # Consumers accept this publication marker only after every validation passes.
    (output/'shader-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    pipeline.PROG.end('both targets verified; context published')
    pipeline.say('Prepared NSP Shader context: '+str(output))
    return summary
