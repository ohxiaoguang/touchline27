"""Consume validated NSP preparation using an explicit existing iOS Shader context.

No extraction or Shader compilation fallback is allowed here. All generated
products live in a new game work directory; failures retain their logs.
"""
import json
import ast
import hashlib
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import zipfile

from tools.nxrom.resourcefs import ResourceFS, build_library
from tools.nxrom.shader_package import TABLES, digest


def checked_files(root, hashes):
    """Require a complete, flat-or-nested regular-file inventory, without links."""
    if root.is_symlink() or not root.is_dir() or not isinstance(hashes, dict) or not hashes:
        raise ValueError('invalid prepared file inventory: '+str(root))
    paths=list(root.rglob('*'))
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in paths):
        raise ValueError('links or special files in prepared inputs')
    files={p.relative_to(root).as_posix():p for p in paths if p.is_file()}
    if set(files)!=set(hashes): raise ValueError('prepared file inventory changed: '+str(root))
    if any(digest(p)!=hashes[name] for name,p in files.items()):
        raise ValueError('prepared input hash mismatch: '+str(root))


def validate_prepared(root, profile, version):
    root=Path(root)
    if (root/'shader').is_symlink() or (root/'ready.json').is_symlink():
        raise ValueError('links in prepared metadata or Shader directory')
    report=json.loads((root/'ready.json').read_text())
    if (report.get('schema')!=2 or report.get('title_id')!=profile.id or
        report.get('version')!=version or report.get('resource_backend')!='nsp' or
        report.get('resource_headers_match_libhac') is not True or
        report.get('romfs_directory_created') is not False):
        raise ValueError('preparation identity/schema is incompatible; prepare into a new directory')
    if profile.words('shader_versions')!=[version] or version not in profile.builds():
        raise ValueError('prepared build requires one registered matching Shader version')
    expected={name:digest(profile.table(name)) for name in ('game.tsv',)+TABLES}
    if report.get('profile_sha256')!=expected: raise ValueError('preparation Profile inputs changed')
    checked_files(root/'program',report.get('program_sha256'))
    checked_files(root/'shader/pkg',report.get('package_sha256'))
    if (root/'program/RomFS').exists(): raise ValueError('prepared build must not contain RomFS')
    for name in TABLES:
        p=root/'shader'/name
        if p.is_symlink() or digest(p)!=expected[name]: raise ValueError('prepared Shader table changed')
    modules=profile.words('modules')
    if any('ExeFS/'+m not in report['program_sha256'] for m in modules):
        raise ValueError('prepared executable module missing')
    return report


def shader_keys(profile):
    return {row.split('\t')[3] for row in profile.table('shader_map.tsv').read_text().splitlines()
            if row and not row.startswith(('#','package\t'))}


def validate_chain_sources(context,repo):
    """A frozen context must still match the translation sources of its consumer.

    The measured lock can differ from the repository lock: it identifies the
    compilers that actually built this cache. It is never replaced or ignored
    when computing the context's chain version.
    """
    snapshot=Path(context)/'toolchain/gfx'
    tree=ast.parse((snapshot/'tools/dmsh_chain.py').read_text())
    assignment=next((node for node in tree.body if isinstance(node,ast.Assign)
                     and any(isinstance(t,ast.Name) and t.id=='FILES' for t in node.targets)),None)
    names=ast.literal_eval(assignment.value) if assignment else None
    if not isinstance(names,list) or not names or any(not isinstance(n,str) for n in names):
        raise ValueError('Shader chain has no readable source inventory')
    for name in names:
        if name=='tools/dmsh_chain.lock': continue
        if Path(name).is_absolute(): raise ValueError('invalid Shader source inventory path')
        logical=Path(os.path.normpath(snapshot/name))
        if not logical.is_relative_to(snapshot.parent): raise ValueError('Shader source inventory escapes toolchain')
        current=Path(repo)/'dm/gfx'/name
        if not current.is_file() or digest(logical)!=digest(current):
            raise ValueError('Shader snapshot differs from current repository source: '+name+'; compile a new context')


def validate_context(context, profile, py, env, target, *, summary=None,current_repo=None):
    if target not in ('ios','macos'): raise ValueError('unknown Shader cache target')
    label='iOS' if target=='ios' else 'macOS'
    folder='ios' if target=='ios' else 'cache'
    sdk='iphoneos' if target=='ios' else 'macosx'
    context=Path(context)
    if summary is None: summary=json.loads((context/'shader-summary.json').read_text())
    chain=summary.get('chain','')
    if not re.fullmatch('[0-9a-f]{12}',chain) or summary.get('failed')!=0 or summary.get('compiler_error_lines')!=0:
        raise ValueError('Shader context is not a successful certified build')
    # The chain version belongs to the source tree the host is compiled with (dm/gfx/nvn/dmsh_chain.h, one for every game): a context built from another
    # tree, or from tools whose sources moved on, is refused rather than reused.
    header=(Path(current_repo)/'dm/gfx/nvn/dmsh_chain.h' if current_repo is not None
            else context/'toolchain/gfx/nvn/dmsh_chain.h')
    if not header.is_file(): raise ValueError('Shader context has no chain version header to compare with: '+str(header))
    if f'#define DMSH_CHAIN "{chain}"' not in header.read_text():
        raise ValueError('Shader context chain differs from the source tree the host is built from (dm/gfx/nvn/dmsh_chain.h); compile a new context')
    tool=context/'toolchain/gfx/tools/dmsh_chain.py'
    if not tool.is_file(): raise ValueError('Shader context has no source/tool-lock chain verifier')
    if current_repo is not None: validate_chain_sources(context,current_repo)
    current=subprocess.run([str(py),str(tool)],env=env,check=True,capture_output=True,text=True).stdout.strip()
    if current!=chain: raise ValueError('current Shader sources/tools no longer match the cached chain')
    cache=context/folder/('b-'+chain)
    if cache.is_symlink() or not cache.is_dir(): raise ValueError('missing '+label+' Shader cache')
    keys=shader_keys(profile)
    reflections=list(cache.glob('*_b.json'))
    if {p.name[:-7] for p in reflections}!=keys: raise ValueError(label+' reflection coverage differs from Profile')
    for p in reflections:
        data=json.loads(p.read_text())
        if p.is_symlink() or data.get('chain')!=chain or data.get('key')!=p.stem or sdk not in data.get('chain_metal',''):
            raise ValueError('wrong platform, key or chain in '+label+' Shader reflection: '+p.name)
        if not p.with_suffix('.metallib').is_file(): raise ValueError('missing base '+label+' Shader library: '+p.name)
    libraries=list(cache.glob('*.metallib'))
    counts=summary.get('targets',{}).get(folder,{})
    if (counts.get('reflections')!=len(keys) or counts.get('library_files')!=len(libraries)
        or summary.get('shader_count')!=len(keys)):
        raise ValueError(label+' Shader cache count differs from certified summary')
    for p in libraries:
        if p.is_symlink() or p.stem.split('_',1)[0] not in keys: raise ValueError('unexpected '+label+' Shader library: '+p.name)
        with p.open('rb') as f: magic=f.read(4)
        if magic!=b'MTLB' or p.stat().st_size<32: raise ValueError('invalid '+label+' Shader library: '+p.name)
    inventory={p.name:digest(p) for p in sorted(reflections+libraries)}
    return {'chain':chain,'reflections':len(reflections),'libraries':len(libraries),
            'files_sha256':inventory}


def validate_ios_context(context, profile, py, env, *, current_repo=None):
    return validate_context(context,profile,py,env,'ios',current_repo=current_repo)


def audit_ipa(path, expected_libraries, shader=None, backend='nsp', romfs_marker=None, aoc_indexes=(),
              expected_bundle_id=None, resources=None):
    """Audit one IPA. `backend='nsp'` is the external layout; 'directory' also
    requires the bundled RomFS (and, when given, one packed folder per add-on
    index) and no longer refuses those two trees."""
    if backend not in ('nsp', 'directory'):
        raise ValueError('unknown IPA resource backend')
    prefix = 'Payload/DmIOS.app/'
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(set(names))!=len(names): raise ValueError('duplicate IPA entries')
        for name in names:
            if name in ('Payload/',prefix): continue
            parts=Path(name).parts
            lowered={part.lower() for part in parts}
            bundled={'romfs','aoc'} if backend=='directory' else set()
            if (not name.startswith(prefix) or '..' in parts
                or (lowered & ({'romfs','aoc','_codesignature'} - bundled))
                or Path(name).suffix.lower() in ('.nsp','.nsz','.nca','.ncz','.keys','.mobileprovision')):
                raise ValueError('unexpected or private game material in IPA: '+name)
        info=plistlib.loads(archive.read(prefix+'Info.plist'))
        if expected_bundle_id and info.get('CFBundleIdentifier') != expected_bundle_id:
            raise ValueError('IPA Bundle ID differs from the selected game')
        if info.get('DMResourceBackend')!=backend:
            raise ValueError('IPA is not configured for the '+backend+' resource backend')
        binary=info.get('CFBundleExecutable')
        if not binary or '/' in binary or prefix+binary not in names:
            raise ValueError('missing IPA executable')
        if not archive.getinfo(prefix+binary).file_size:
            raise ValueError('empty IPA executable')
        if sum(n.endswith('.metallib') for n in names)!=expected_libraries:
            raise ValueError('IPA Shader library coverage changed')
        if shader:
            shader_prefix=prefix+'msl/b-'+shader['chain']+'/'
            packed={n[len(shader_prefix):]:n for n in names if n.startswith(shader_prefix) and not n.endswith('/')}
            # The library stamp travels with the libraries (build_ipa.sh packs the directory as
            # it is) and is what the host checks before it uses c1_full.tsv / cb_extent.tsv.
            if 'inputs.tsv' not in packed: raise ValueError('IPA Shader library has no stamp (inputs.tsv)')
            if shader.get('inputs_sha256') and hashlib.sha256(archive.read(packed['inputs.tsv'])).hexdigest()!=shader['inputs_sha256']:
                raise ValueError('IPA Shader stamp differs from validated cache')
            packed.pop('inputs.tsv')
            if set(packed)!=set(shader['files_sha256']): raise ValueError('IPA Shader file inventory differs from cache')
            for short,name in packed.items():
                if hashlib.sha256(archive.read(name)).hexdigest()!=shader['files_sha256'][short]:
                    raise ValueError('IPA Shader bytes differ from validated cache: '+short)
        if backend=='directory':
            if not romfs_marker: raise ValueError('directory IPA audit needs the game RomFS marker')
            if prefix+'romfs/'+romfs_marker not in names:
                raise ValueError('IPA does not carry the game RomFS (missing romfs/'+romfs_marker+')')
            packed_aoc=sorted({Path(name).parts[3] for name in names
                               if name.startswith(prefix+'aoc/') and len(Path(name).parts)>3
                               and Path(name).parts[3].isdigit()}, key=int)
            if list(packed_aoc)!=sorted({str(i) for i in aoc_indexes}, key=int):
                raise ValueError('IPA add-on content differs from the selected folder')
        if resources is not None:
            packed_resources={n[len(prefix):] for n in names if not n.endswith('/')
                              and n.startswith((prefix+'romfs/', prefix+'aoc/'))}
            if packed_resources != set(resources):
                raise ValueError('IPA game resource inventory differs from selected inputs')
            for name, expected in resources.items():
                item=archive.getinfo(prefix+name)
                if item.file_size != expected['bytes']:
                    raise ValueError('IPA game resource size differs: '+name)
                hashed=hashlib.sha256()
                with archive.open(item) as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''):
                        hashed.update(block)
                if hashed.hexdigest()!=expected['sha256']:
                    raise ValueError('IPA game resource bytes differ: '+name)
        bad=archive.testzip()
        if bad: raise ValueError('IPA CRC failed: '+bad)
    return {'entries':len(names),'metallibs':expected_libraries,'crc_checked':True,
            'shader_bytes_match_cache':bool(shader),
            'romfs_bundled':backend=='directory','container_or_keys_bundled':False,'signed':False}


def build(pipeline, args, repo, nsp_dir, base, update, keys, profile, version, env, language):
    prepared=Path(args.use_nsp_prepared).expanduser().resolve()
    context=Path(args.ios_shader_context).expanduser().resolve()
    work=Path(args.nsp_build_work).expanduser().resolve()
    output=Path(args.out).expanduser().resolve()
    if (work==nsp_dir or not work.is_relative_to(nsp_dir) or work.is_relative_to(prepared)
        or prepared.is_relative_to(work) or context.is_relative_to(work) or work.is_relative_to(context/'ios')
        or work.exists() or output.exists() or output.suffix.lower()!='.ipa'
        or not output.is_relative_to(work)):
        raise ValueError('choose a new work folder under the NSP folder and a new IPA path inside it; keep prepared inputs and Shader caches separate')
    report=validate_prepared(prepared,profile,version)
    env=dict(env,DM_GAME=profile.id,DM_ROOT=str(work),WORK=str(work/'tmp'))
    shader=validate_ios_context(context,profile,pipeline.sys.executable,env,current_repo=repo)
    for tool in ('xcodebuild','xcodegen','make'):
        if not shutil.which(tool,path=env['PATH']): raise ValueError('build tool missing: '+tool)
    if pipeline.free_gb(nsp_dir)<5: raise ValueError('less than 5 GB free for isolated iOS build')
    control=prepared/'program/control.nacp'
    supported=pipeline.nacp.languages(control)
    if language not in supported: raise ValueError('requested language is not supported by the prepared game')
    work.mkdir(parents=True)
    (work/'tmp').mkdir(); (work/'tools').mkdir()
    # Recheck selected container code identities with the current native reader.
    library=build_library(work/'tools/nxrom.dylib')
    with ResourceFS(library,base=base,update=update,keys=keys,title=profile.title_id) as resources:
        for module,bid in profile.builds()[version].items():
            if module!='display': resources.check_build(module,bid)
    logs=work/'logs'; patched=work/('patched_'+version)
    pipeline.PROG.plan(3)
    pipeline.rewrite(pipeline.sys.executable,repo,prepared/'program/ExeFS',patched,env,logs,profile)
    ipa_env=dict(env,GAME=profile.id,W=str(work/'ipa'),PATCHED=str(patched),
        # The parent supplies control metadata; this RomFS path never exists.
        ROMFS=str(prepared/'program/RomFS'),MSL_IOS=str(context/'ios'),GFXAPI='nvn',
        FONT_PY=pipeline.sys.executable,DM_RESOURCE_BACKEND='nsp',AOC='',
        DM_IOS_BUILD_DIR=str(work/'ios-project'),DM_XCODE_DERIVED_DATA=str(work/'xcode-derived-data'),
        DM_DISPLAY_NAME=args.app_name or pipeline.nacp.name(control),
        DM_APP_VERSION=pipeline.nacp.version(control),DM_LANG=language,
        DM_BUNDLE_ID=args.bundle_id or 'org.nxnative.'+profile.id.lower(),
        DM_ICON=str(repo/'assets/app-icon/touchline27.png') if (repo/'assets/app-icon/touchline27.png').is_file() else str(prepared/'program/icon.jpg'),
        DM_SHOW_FPS='1' if (pipeline.SHOW_FPS if args.show_fps is None else args.show_fps) else '0')
    # This mode intentionally does not bundle diagnostic environment files.
    ipa_env.pop('DM_ENV_FILE',None)
    output.parent.mkdir(parents=True,exist_ok=True)
    pipeline.PROG.stage('app build',step='unsigned iOS build using validated cache')
    pipeline.run(['bash',repo/'dm/ios/tools/build_ipa.sh',output],logs/'build_ipa.log',env=ipa_env)
    pipeline.PROG.end(output.name)
    pipeline.PROG.stage('audit IPA',step='CRC and resource inventory')
    audit=audit_ipa(output,shader['libraries'],shader)
    (work/'shader-cache-inventory.json').write_text(json.dumps(shader.pop('files_sha256'),indent=2)+'\n')
    result={'title_id':profile.id,'version':version,'prepared_ready_sha256':digest(prepared/'ready.json'),
            'shader_context':str(context),'shader':shader,'ipa':str(output),'ipa_sha256':digest(output),
            'shader_cache_inventory_sha256':digest(work/'shader-cache-inventory.json'),
            'audit':audit,'program_sha256':report['program_sha256'],'rewrite_run':True,
            'shader_compilation_run':False,'romfs_extracted':False,'device_run_verified':False}
    (work/'build-report.json').write_text(json.dumps(result,indent=2)+'\n')
    pipeline.PROG.end('no RomFS, containers or keys in unsigned IPA')
    pipeline.say(f'prepared NSP build complete: {output}; device runtime validation remains required')
    return result
