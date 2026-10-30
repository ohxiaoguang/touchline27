"""Registered single-version NSP preparation, without a RomFS directory.

Only program/control metadata are extracted with the existing LibHac tool. All
resource files are scanned through the native reader. Success publishes a small
ready report only after complete Profile/table validation; no compilation or IPA
packaging runs here. Failed isolated output is retained for diagnosis.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from tools.nxrom.resourcefs import ResourceFS, build_library
from tools.nxrom.shader_package import collect, write_package, TABLES, digest
from tools.nxrom.shader_scan import load_decoder


def prepare(base, update, keys, profile, version, extractor, output, *, env=None):
    base,keys,extractor,output=map(Path,(base,keys,extractor,output))
    update=Path(update) if update else None
    if base.suffix.lower() not in ('.nsp','.xci') or (update and update.suffix.lower()!='.nsp'):
        raise ValueError('stream preparation requires an uncompressed NSP or XCI base and NSP update inputs')
    if profile.words('shader_versions')!=[version] or version not in profile.builds():
        raise ValueError('stream preparation requires one registered matching Shader version')
    if not extractor.is_file() or not os.access(extractor,os.X_OK):
        raise ValueError('a previously built nx_extract executable is required')
    environment=dict(os.environ if env is None else env)
    dll=extractor.with_suffix('.dll')
    command=[str(extractor.resolve())]
    if dll.is_file():
        # Homebrew's muxer knows its runtime root even when the apphost cannot
        # locate DOTNET_ROOT. Use the installed SDK; never download a runtime.
        dotnet=shutil.which('dotnet',path=environment.get('PATH'))
        if not dotnet: raise ValueError('existing dotnet runtime required to run nx_extract.dll')
        command=[dotnet,str(dll.resolve())]
    if output.exists(): raise ValueError('preparation output exists; choose a new directory')
    decoder=load_decoder()
    if decoder.GAME.id!=profile.id: raise ValueError('selected preparation Profile differs from DM_GAME')
    output.mkdir()
    tools=output/'tools'; tools.mkdir()
    library=build_library(tools/'nxrom.dylib')
    program=output/'program'
    with ResourceFS(library,base=base,update=update,keys=keys,title=profile.title_id) as resources:
        expected=profile.builds()[version]
        for module,build in expected.items():
            if module!='display': resources.check_build(module,build)
        with (output/'program-extraction.log').open('wb') as log:
            result=subprocess.run(command+[str(keys.resolve()),str(base.resolve()),
                                   str(update.resolve()) if update else '-',str(program.resolve()),'--manifest'],
                                  stdout=log,stderr=subprocess.STDOUT,env=environment)
        if result.returncode:
            raise ValueError('program-only extraction failed; see program-extraction.log')
        if (program/'RomFS').exists() or not (program/'romfs_manifest.tsv').is_file():
            raise ValueError('program extractor did not honor manifest-only mode')
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'dm/games'))
        import profile_guess as pg
        facts=pg.facts_of(program/'ExeFS',resources)
        reference=list(pg.romfs_files(program/'romfs_manifest.tsv'))
        native=list(pg.romfs_files(resources))
        if sorted(native)!=sorted(reference):
            raise ValueError('native resource headers differ from LibHac manifest')
        for module,info in facts['mods'].items(): resources.check_build(module,info['bid'])
        # The metadata stage itself must not silently assume a renderer or the
        # absence of run-time compiler/engine-specific Shader capture requirements.
        paths=[e.path for e in resources.files()]
        if any(path.endswith(('.pak','.utoc','.ucas','.trpfs','.bdt','.rdb')) for path in paths):
            raise ValueError('this resource set needs an engine archive adapter')
        imports=facts['mods']['main']['imports']
        compilers=[name for name in profile.words('modules') if name!='main'
                   and 'glslcCompile' in facts['mods'].get(name,{}).get('exports',set())]
        sources=pg.shader_sources(imports,facts['glsl_src'],compilers,
                                 facts['romfs']['mags']['SPIR-V'],0,gl_names=facts['gl_names'])
        if sources['graphics'][0]!='nvn' or any(sources[k][0] for k in ('glslc_capture','vk_capture','ue_decode','oodle_packs','ue_legacy')):
            raise ValueError('this renderer or Shader capture requirement is not supported by stream preparation')
        scratch=output/'scratch';scratch.mkdir()
        selected,pairs=collect(resources,paths,program/'ExeFS/main',decoder,True,scratch=scratch)
    registered={line.split('\t')[3] for line in profile.table(TABLES[0]).read_text().splitlines()
                if line and not line.startswith(('#','package\t'))}
    if set(selected)!=registered: raise ValueError('stream scan does not exactly cover the registered Profile keys')
    shader=output/'shader'
    write_package(selected,pairs,shader,decoder)
    matches={name:(shader/name).read_bytes()==profile.table(name).read_bytes() for name in TABLES}
    if not all(matches.values()): raise ValueError('generated Shader tables differ from the registered Profile')
    report={'schema':2,'title_id':profile.id,'version':version,'resource_backend':'nsp',
            'resource_files':len(paths),'resource_headers_match_libhac':True,
            'keys':len(selected),'pairs':len(pairs),'tables_byte_identical':matches,
            'package_sha256':{p.name:digest(p) for p in sorted((shader/'pkg').glob('*.bin'))},
            'program_sha256':{p.relative_to(program).as_posix():digest(p)
                              for p in sorted(program.rglob('*')) if p.is_file()},
            'profile_sha256':{name:digest(profile.table(name)) for name in ('game.tsv',)+TABLES},
            'romfs_directory_created':False,'translation_run':False,'ipa_built':False}
    (output/'ready.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
