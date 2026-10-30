"""Isolated macOS consumer of verified NSP preparation and compiled Shaders."""
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sys

from tools.nxrom.prepared_build import validate_prepared,validate_context
from tools.nxrom.resourcefs import ResourceFS,build_library
from tools.nxrom.shader_package import digest


def validate_paths(nsp_dir,prepared,context,work,output):
    if (not nsp_dir.is_dir() or work==nsp_dir or not work.is_relative_to(nsp_dir)
        or work.is_relative_to(prepared) or prepared.is_relative_to(work)
        or context.is_relative_to(work) or work.is_relative_to(context/'cache')
        or work.is_relative_to(context/'ios') or work.exists() or output.exists()
        or output.suffix!='.app' or not output.is_relative_to(work)):
        raise ValueError('choose a new game-drive work folder and a new App inside it; keep preparation and Shader caches separate')


def audit_app(app,profile,patched,host,shader,backend='nsp',romfs_marker=None,layer=None):
    """Check all copied runtime bytes, absence of external data and source links.

    ``layer`` names an OpenGL/Vulkan library folder (``msl/gl``): such a library is
    one metallib plus the table that names its Metal functions, so it has neither
    the chain's per-shader reflections nor the inputs.tsv stamp that lets the host
    trust c1_full.tsv / cb_extent.tsv. Every other check is the same.
    """
    paths=list(app.rglob('*'))
    for p in paths:
        if p.is_symlink() or not (p.is_file() or p.is_dir()): raise ValueError('link or special file in Mac App')
        parts=p.relative_to(app).parts
        lowered={part.lower() for part in parts}
        # Bundled game data is expected in the directory backend and forbidden in
        # the external one; signatures are never carried.
        if (lowered & ({'_codesignature'} if backend=='directory' else {'romfs','aoc','_codesignature'})
            or p.suffix.lower() in ('.nsp','.nsz','.nca','.ncz','.keys','.mobileprovision')):
            raise ValueError('external or private game material in Mac App: '+p.name)
    root=app/'Contents'; resources=root/'Resources'
    info=plistlib.loads((root/'Info.plist').read_bytes())
    if info.get('NXTitleID')!=profile.id or info.get('NXResourceBackend')!=backend:
        raise ValueError('Mac App title/backend mismatch')
    if backend=='directory':
        if not romfs_marker: raise ValueError('directory App audit needs the game RomFS marker')
        if not (resources/'romfs'/romfs_marker).is_file():
            raise ValueError('Mac App does not carry the game RomFS (missing romfs/'+romfs_marker+')')
    elif (resources/'romfs').exists(): raise ValueError('external-resource App must not carry romfs/')
    if info.get('CFBundleExecutable')!='launch': raise ValueError('Mac App launcher entry mismatch')
    for name in ('launch','dmhost'):
        binary=root/'MacOS'/name
        if not binary.is_file() or not os.access(binary,os.X_OK): raise ValueError('missing Mac executable: '+name)
    if digest(root/'MacOS/dmhost')!=digest(host): raise ValueError('bundled host differs from new build')
    expected={}
    modules=list(profile.words('modules'))
    # The NRO modules a game loads with nn::ro are named by their table (hle_ro.c), so the App
    # carries it beside the modules; without it LoadModule fails at the game's first load.
    nro_table=patched/'nro.tsv'
    if nro_table.is_file():
        for line in nro_table.read_text().splitlines():
            if line and line[0]!='#' and not line.startswith('refused\t') and line.split('\t')[0] not in modules:
                modules.append(line.split('\t')[0])
    for module in modules:
        for suffix in ('.patched.bin','.fixups.tsv','.gates.tsv','.cuts.tsv','.obs.tsv'):
            name=module+suffix; source=patched/name
            if not source.is_file(): raise ValueError('missing rewritten program file: '+name)
            expected[name]=digest(source)
    if nro_table.is_file(): expected['nro.tsv']=digest(nro_table)
    programs={p.name:digest(p) for p in (resources/'program').iterdir() if p.is_file()}
    if programs!=expected: raise ValueError('bundled program inventory/bytes differ from rewrite')
    builds={}
    for line in (resources/'profile/prepared_builds.tsv').read_text().splitlines():
        name,bid=line.split('\t'); builds[name]=bid
    if set(builds)!=set(profile.words('modules')): raise ValueError('bundled module identity inventory differs')
    for module,bid in builds.items():
        original=(patched/(module+'.fixups.tsv')).read_text()
        if not re.search(r'^# BUILD_ID\t'+re.escape(bid)+r'$',original,re.M):
            raise ValueError('bundled module identity differs from rewrite')
    for name in (['shader_map.tsv','pso_manifest.tsv','gl_capture.tsv'] if layer else
                 ['shader_map.tsv','pso_manifest.tsv','c1_full.tsv','cb_extent.tsv']):   # the chain version header is not a profile table (dm/gfx/nvn/dmsh_chain.h)
        if digest(resources/'profile'/name)!=digest(profile.table(name)):
            raise ValueError('bundled Profile table differs: '+name)
    cache=resources/'msl'/(layer or ('b-'+shader['chain']))
    if layer:
        from tools.nxrom.gl_library import validate
        validate(cache, profile.table('gl_capture.tsv'))
        # One metallib and its table; the table's first column is the program key.
        table=cache/(layer+'_shaders.tsv')
        if not table.is_file(): raise ValueError('bundled layer library has no '+layer+'_shaders.tsv')
        if not (cache/(layer+'_shaders.metallib')).is_file():
            raise ValueError('bundled layer library has no '+layer+'_shaders.metallib')
        inventory={p.name:digest(p) for p in cache.iterdir() if p.is_file()}
        if inventory!=shader['files_sha256']: raise ValueError('bundled Shader bytes differ from validated cache')
    else:
        # The stamp (inputs.tsv) is not part of the library inventory: build_mac_app.py copies it
        # beside the libraries so the host can trust c1_full.tsv / cb_extent.tsv.
        inventory={p.name:digest(p) for p in cache.iterdir() if p.is_file() and p.name!='inputs.tsv'}
        if inventory!=shader['files_sha256']: raise ValueError('bundled Shader bytes differ from validated cache')
        if not (cache/'inputs.tsv').is_file(): raise ValueError('bundled Shader library has no stamp (inputs.tsv)')
    return {'files':sum(p.is_file() for p in paths),'bytes':sum(p.stat().st_size for p in paths if p.is_file()),
            'shader_bytes_match_cache':True,'program_bytes_match_rewrite':True,
            'romfs_bundled':backend=='directory','containers_or_keys_bundled':False,'distribution_signed':False}


def build(args,repo):
    from scripts import build_ipa_from_nsp as pipeline
    sys.path.insert(0,str(repo/'dm/games')); import game
    sys.path.insert(0,str(repo/'dm/tools')); import nacp
    nsp_dir=args.nsp_dir.expanduser().resolve()
    prepared=args.use_nsp_prepared.expanduser().resolve()
    context=args.shader_context.expanduser().resolve()
    work=args.work.expanduser().resolve(); output=args.output.expanduser().resolve()
    validate_paths(nsp_dir,prepared,context,work,output)
    profile=game.Game(args.profile.expanduser().resolve())
    report=validate_prepared(prepared,profile,args.package)
    # Match the profile search used by subprocess tools to the explicit input.
    env=dict(os.environ,DM_GAME=profile.id,DM_GAMES_FIRST='1',DM_GAMES_DIR=str(profile.dir.parent),
             DM_RESOURCE_BACKEND='nsp',DM_ROOT=str(work),WORK=str(work/'tmp'))
    env['PATH']=os.pathsep.join(pipeline.TOOL_PATHS+[env.get('PATH','/usr/bin:/bin')])
    shader=validate_context(context,profile,sys.executable,env,'macos',current_repo=repo)
    app,family=pipeline.scan_nsps(nsp_dir)
    if app!=profile.title_id or family['dlc']: raise ValueError('Mac prepared build requires matching title and no DLC')
    have=pipeline.nsp_versions(family,profile.builds())
    if args.package not in have: raise ValueError('requested update is not present in the NSP folder')
    base=family['base']; update=have[args.package]; keys=args.keys.expanduser().resolve()
    if base.suffix.lower() not in ('.nsp','.xci') or (update and update.suffix.lower()!='.nsp'):
        raise ValueError('Mac prepared build requires an uncompressed NSP/XCI base and NSP update inputs')
    if not keys.is_file(): raise ValueError('missing user keys file')
    for tool in ('make','xcrun'):
        if not shutil.which(tool,path=env['PATH']): raise ValueError('build tool missing: '+tool)
    if pipeline.free_gb(nsp_dir)<3: raise ValueError('less than 3 GB free for isolated Mac build')
    control=prepared/'program/control.nacp'
    name=args.name or nacp.name(control)
    version=nacp.version(control)
    if not name or not version: raise ValueError('missing prepared game name/version')
    work.mkdir(parents=True); (work/'tmp').mkdir(); (work/'tools').mkdir()
    library=build_library(work/'tools/nxrom.dylib')
    with ResourceFS(library,base=base,update=update,keys=keys,title=profile.title_id) as resources:
        for module,bid in profile.builds()[args.package].items():
            if module!='display': resources.check_build(module,bid)
    logs=work/'logs'; patched=work/('patched_'+args.package)
    pipeline.PROG.plan(4)
    pipeline.rewrite(sys.executable,repo,prepared/'program/ExeFS',patched,env,logs,profile)
    pipeline.PROG.stage('Mac host',step='compile current sources to isolated output')
    host=pipeline.build_mac_host(repo,work/'tools/dmhost',env,logs,profile)
    pipeline.PROG.end('new host compiled')
    font=work/'font'; font.mkdir()
    shutil.copyfile('/System/Library/Fonts/Supplemental/Arial Unicode.ttf',font/'standard.ttf')
    pipeline.run([sys.executable,repo/'dm/tools/make_ext_font.py',font/'nintendo_ext.ttf'],logs/'font.log',env=env)
    settings=work/'launcher.json'
    pipeline.run([sys.executable,repo/'dm/games/settings.py',profile.id,patched,control,settings],logs/'settings.log',env=env)
    pipeline.PROG.stage('Mac App',step='package explicit runtime files and compile launcher')
    output.parent.mkdir(parents=True,exist_ok=True)
    pipeline.run([sys.executable,repo/'scripts/build_mac_app.py','--host',host,'--patched',patched,
                  '--shaders',context/'cache'/('b-'+shader['chain']),'--profile',profile.dir,
                  '--font',font,'--settings',settings,'--output',output,'--title-id',profile.id,
                  '--name',name,'--version',version,'--icon',repo/'assets/app-icon/touchline27.png'],logs/'package.log',env=env)
    pipeline.PROG.end(output.name)
    pipeline.PROG.stage('Mac App audit',step='all program, table and Shader bytes')
    audit=audit_app(output,profile,patched,host,shader)
    (work/'shader-cache-inventory.json').write_text(json.dumps(shader.pop('files_sha256'),indent=2)+'\n')
    result={'title_id':profile.id,'version':args.package,'app':str(output),
            'prepared_ready_sha256':digest(prepared/'ready.json'),'program_sha256':report['program_sha256'],
            'shader_context':str(context),'shader':shader,'audit':audit,
            'shader_cache_inventory_sha256':digest(work/'shader-cache-inventory.json'),
            'new_host_sha256':digest(host),'romfs_extracted':False,'shader_compilation_run':False,
            'host_rebuilt':True,'game_run_verified':False,'launcher_interaction_verified':False}
    (work/'build-report.json').write_text(json.dumps(result,indent=2)+'\n')
    pipeline.PROG.end('external resources; all copied bytes match')
    pipeline.say('Mac prepared NSP build complete: '+str(output))
    return result
