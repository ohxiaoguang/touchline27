#!/usr/bin/env python3
"""Package the macOS App in either resource mode.

directory: the game's RomFS is copied into the App and read from there, as the iOS
           build has always done; the launcher asks for nothing.
nsp:       the App carries no game data; the launcher asks for the containers and
           keys at run time and the host reads them in place.

Both modes share everything else: the rewritten modules, the profile tables, the
macOS Shader libraries, the fonts and the launcher. Only where the game data comes
from changes.
"""
import argparse
import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# The runtime's two resource modes. "nsp" is the compatibility name for external
# containers; XCI, NSZ and NCZ join that side later, so no mode is added per format.
BACKENDS = ('directory', 'nsp')
EXTERNAL = 'nsp'
# Audited OpenGL libraries use msl/gl instead of the NVN chain directory.
# Vulkan remains unsupported by this artifact audit.
LAYERS = ('gl',)
# Game data and private key material must never be inside the App.
FORBIDDEN_SUFFIXES = ('.nsp', '.nsz', '.ncz', '.xci', '.xcz', '.nca', '.keys', '.tik', '.mobileprovision')
# The App icon: one square PNG from the source tree, rendered into the iconset iconutil
# packs. Finder and the Dock read it from Contents/Resources/AppIcon.icns, which
# CFBundleIconFile names; iOS builds its catalog from the same file.
ICON_SIZES = ((16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2))


def make_icns(source, dst):
    """Render AppIcon.icns from one square image: sips scales, iconutil packs."""
    if not source.is_file(): raise ValueError('missing App icon: ' + str(source))
    with tempfile.TemporaryDirectory(prefix='icns-') as tmp:
        iconset = Path(tmp)/'AppIcon.iconset'
        iconset.mkdir()
        for size, scale in ICON_SIZES:
            px = size*scale
            name = 'icon_%dx%d%s.png' % (size, size, '@2x' if scale == 2 else '')
            subprocess.run(['sips','-s','format','png','-z',str(px),str(px),str(source),'--out',str(iconset/name)],
                           check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(dst)],check=True)


def resolve_backend(explicit, prepared, romfs):
    """The mode of this run: the explicit flag, else what the inputs imply.

    A prepared NSP build is always external; a --romfs input is always bundled; with
    neither, the App is external - which is what every command written before this
    option existed already did.
    """
    if explicit: return explicit
    if prepared: return EXTERNAL
    return 'directory' if romfs else EXTERNAL


def info_plist(name, title_id, version, backend, icon=None):
    """The App's Info.plist. NXResourceBackend is what the launcher and the host read."""
    bundle = 'org.nxnative.dir.' if backend == 'directory' else 'org.nxnative.nsp.'
    info = dict(CFBundleExecutable='launch', CFBundleIdentifier=bundle + title_id.lower(), CFBundleName=name,
                CFBundleDisplayName=name, CFBundlePackageType='APPL', CFBundleVersion='1',
                NSHighResolutionCapable=True, CFBundleShortVersionString=version,
                NXTitleID=title_id, NXResourceBackend=backend, LSMinimumSystemVersion='26.0',
                NSRemovableVolumesUsageDescription='Read the selected game folder and store saves and logs in it.')
    if icon: info['CFBundleIconFile'] = icon
    return info


def readme(backend, title_id):
    """What the player has to know, which differs only in where the game data comes from."""
    controls = 'Sound is enabled. Use WASD, J/K (A/B), Q/E (L/R), Return (+).\n'
    tail = (f'Save, temporary files and log.txt are in nxnative-{title_id} inside the folder you choose.\n'
            'This local development App is not signed or notarized.\n')
    if backend == 'directory':
        return ('Choose a writable storage folder, then play.\n'
                'The game files are inside this App (Contents/Resources/romfs); no other file is needed.\n'
                + controls + tail)
    return ('Choose the folder that holds this game\'s files, and a storage folder, then play.\n'
            'The base game (NSP or XCI), the update and prod.keys may sit in any sub-folder;\n'
            'they are found and checked automatically and read where they are.\n'
            'Containers and keys remain external. No RomFS extraction is performed.\n'
            + controls + tail)


def build_launcher(output):
    app=next((p for p in output.parents if p.suffix=='.app'),None)
    cache=(app.parent if app else output.parent)/'.nxnative-launcher-module-cache'
    with tempfile.TemporaryDirectory(prefix='mac-launcher-', dir=output.parent) as tmp:
        objects=[]
        for source in ('dm/resource/nxrom.c', 'dm/macos/resource_check.c'):
            obj=Path(tmp)/(Path(source).stem+'.o')
            subprocess.run(['xcrun','clang','-O1','-Wall','-Wextra','-Werror','-Wno-deprecated-declarations',
                            '-mmacosx-version-min=26.0','-c',str(REPO/source),'-o',str(obj)],check=True)
            objects.append(str(obj))
        # The launcher and the shared discovery/settings sources the iOS target also
        # compiles (dm/apple): one scan path for both platforms, never two.
        shared=sorted(str(p) for p in (REPO/'dm/apple').glob('*.swift'))
        subprocess.run(['xcrun','swiftc','-swift-version','5','-parse-as-library','-O','-target','arm64-apple-macos26.0',
                        '-module-cache-path',str(cache),*shared,str(REPO/'dm/macos/Launcher.swift'),*objects,
                        '-o',str(output)],check=True)


def prepared_builds(patched):
    # The manifest names the modules the container's ExeFS holds: the launcher compares their
    # Build IDs before it mounts anything (dm/apple/ResourceDiscovery.swift). A module the game
    # loads with nn::ro is not in the ExeFS at all - it lives in the game's own data and nro.tsv
    # names it by SHA-256, which the host matches when the game asks for it (hle_ro.c) - so it
    # has no Build ID to compare here, and listing it refused every matching base and update.
    runtime=set()
    table=patched/'nro.tsv'
    if table.is_file():
        runtime={l.split('\t')[0] for l in table.read_text().splitlines() if l and l[0]!='#'}
    rows=[]
    for program in sorted(patched.glob('*.patched.bin')):
        name=program.name.removesuffix('.patched.bin')
        if name in runtime: continue
        text=(patched/(name+'.fixups.tsv')).read_text()
        build=re.search(r'^# BUILD_ID\t([a-fA-F0-9]{32})$',text,re.M)
        if not build: raise ValueError('missing prepared build ID: '+name)
        rows.append(name+'\t'+build[1]+'\n')
    return ''.join(rows)


def romfs_marker(profile):
    """The profile's romfs_marker: the path that proves a folder is this game's RomFS."""
    for line in (profile/'game.tsv').read_text(errors='replace').splitlines():
        if line.startswith('romfs_marker\t'): return line.split('\t',1)[1].strip()
    return None


def copy_tree(src, dst):
    """Copy the game's RomFS into the App: a clone when the volume allows it, else a copy."""
    result=subprocess.run(['/bin/cp','-cR',str(src),str(dst)])
    if result.returncode:
        shutil.copytree(src,dst)


def audit(app, backend, marker, stamp_dir=None, layer=None):
    """Nothing private, nothing stale: the App holds exactly what the mode should."""
    for p in app.rglob('*'):
        if p.is_symlink() or not (p.is_file() or p.is_dir()): raise ValueError('link or special file in Mac App: '+str(p))
        if p.suffix.lower() in FORBIDDEN_SUFFIXES: raise ValueError('game container or key material in Mac App: '+p.name)
        parts=p.relative_to(app).parts
        if any(part.lower() == '_codesignature' or (part.lower() == 'aoc' and backend != 'directory') for part in parts):
            raise ValueError('add-on content or signature in Mac App: '+p.name)
        if any(part.lower()=='romfs' for part in parts) and backend!='directory':
            raise ValueError('bundled RomFS in an external-resource Mac App: '+p.name)
    res=app/'Contents/Resources'
    if backend=='directory':
        if not (res/'romfs'/marker).is_file(): raise ValueError('App does not carry the game RomFS (missing romfs/'+marker+')')
        if (res/'aoc').exists():
            sys.path.insert(0, str(REPO))
            from tools.nxrom.dlc import audit_tree
            info = plistlib.loads((app/'Contents/Info.plist').read_bytes())
            audit_tree(res/'aoc', int(info['NXTitleID'], 16))
    elif (res/'romfs').exists(): raise ValueError('external-resource App must not carry romfs/')
    for name in ('launch','dmhost'):
        binary=app/'Contents/MacOS'/name
        if not binary.is_file() or not os.access(binary,os.X_OK): raise ValueError('missing Mac executable: '+name)
    # The stamp the host checks before it uses the profile's c1 / uniform extent tables.
    if stamp_dir and not (res/'msl'/stamp_dir/'inputs.tsv').is_file():
        raise ValueError('Shader library stamp (inputs.tsv) missing from the App')
    # A layer library is one metallib plus the table that names its Metal functions.
    if layer:
        from tools.nxrom.gl_library import validate
        validate(res / 'msl' / layer, res / 'profile/gl_capture.tsv')


def package(a, launcher=None):
    """Write the App for a.resource_backend. The caller resolves the backend first."""
    launcher = launcher or build_launcher
    backend = a.resource_backend
    aoc = getattr(a, 'aoc', None)
    if aoc:
        if backend != 'directory': raise ValueError('--aoc requires directory mode')
        sys.path.insert(0, str(REPO))
        from tools.nxrom.dlc import audit_tree
        audit_tree(aoc, int(a.title_id, 16))
    if a.output.suffix != '.app' or a.output.exists(): raise ValueError('output must be a new .app path')
    if not re.fullmatch('[0-9a-fA-F]{16}', a.title_id): raise ValueError('invalid title ID')
    if not a.settings.is_file(): raise ValueError('missing launcher settings JSON (generate with dm/games/settings.py)')
    header = Path(getattr(a, 'chain_header', None) or REPO/'dm/gfx/nvn/dmsh_chain.h')   # one chain version for every game, carried by the source tree
    # An OpenGL game's library comes from its layer, which has no chain version
    # to agree on: the host resolves a shader by its source hash and its table, not by a
    # chain build, so neither the header nor the host's chain string applies to it.
    layer = a.shaders.name if a.shaders.name in LAYERS else None
    if not layer:
        if not header.is_file(): raise ValueError('missing chain version header: ' + str(header))
        chain = re.search(r'^#define DMSH_CHAIN "([a-f0-9]+)"', header.read_text(), re.M)
        if not chain or a.shaders.name != 'b-' + chain[1]: raise ValueError('Shader directory/chain header mismatch')
        if chain[1].encode() not in a.host.read_bytes(): raise ValueError('host/chain header mismatch')
    # c1_full.tsv and cb_extent.tsv describe NVN's constant segments; a layer's shaders have neither.
    tables = ['shader_map.tsv', 'pso_manifest.tsv'] + (['gl_capture.tsv'] if layer else ['c1_full.tsv', 'cb_extent.tsv'])
    if layer:
        from tools.nxrom.gl_library import validate
        validate(a.shaders, a.profile / 'gl_capture.tsv')
    for name in tables:
        if not (a.profile/name).is_file(): raise ValueError('missing profile table: ' + name)
    programs = sorted(a.patched.glob('*.patched.bin'))
    if not programs: raise ValueError('no prepared modules')
    names = {p.name.removesuffix('.patched.bin') for p in programs}
    for p in programs:
        if not p.with_name(p.name.removesuffix('.patched.bin') + '.fixups.tsv').is_file(): raise ValueError('missing module fixups')
    # A game may load modules at run time with nn::ro (hle_ro.c): its NROs are rewritten like the
    # other modules and named by SHA-256 in nro.tsv, so the table and every module it names go in.
    # Without them LoadModule fails and the game jumps through the null the symbol resolved to.
    nro_table = a.patched/'nro.tsv'
    if nro_table.is_file():
        for line in nro_table.read_text().splitlines():
            if not line or line[0] == '#' or line.startswith('refused\t'): continue
            if line.split('\t')[0] not in names: raise ValueError('nro.tsv lists ' + line.split('\t')[0] + ', which has no rewritten module')
    builds = prepared_builds(a.patched)
    # The compiler's build summary is not a runtime reflection file. A layer writes one
    # metallib and the table that names its functions; the NVN chain writes one per shader.
    shaders = sorted(p for p in a.shaders.iterdir()
                     if p.suffix in (('.metallib', '.tsv') if layer else ('.metallib', '.json')) and p.name!='_b_build.json')
    if not any(p.suffix == '.metallib' for p in shaders): raise ValueError('no compiled Shader libraries')
    if layer and not any(p.name == layer + '_shaders.tsv' for p in shaders):
        raise ValueError(f'{a.shaders} has no {layer}_shaders.tsv: the host cannot find a shader without the table')
    # The library stamp (inputs.tsv, written by a full dmsh_build.py run) is what lets the
    # host trust c1_full.tsv and cb_extent.tsv; without it it falls back to a 64 KB c1 per
    # draw. The IPA packs the whole library directory, so the App carries the stamp too.
    stamp = a.shaders/'inputs.tsv'
    if not layer and (a.profile/'c1_full.tsv').is_file() and not stamp.is_file():
        raise ValueError(f'{a.shaders} has no inputs.tsv: c1_full.tsv cannot be trusted at '
                         'run time, so package a full dmsh_build.py run')
    for name in ('standard.ttf', 'nintendo_ext.ttf'):
        if not (a.font/name).is_file(): raise ValueError('missing font: ' + name)
    marker = None
    if backend == 'directory':
        if not a.romfs: raise ValueError('directory mode needs --romfs: the game RomFS folder to bundle')
        if not a.romfs.is_dir(): raise ValueError('not a folder: ' + str(a.romfs))
        marker = romfs_marker(a.profile)
        if not marker: raise ValueError('game profile has no romfs_marker row: ' + str(a.profile/'game.tsv'))
        if not (a.romfs/marker).is_file(): raise ValueError(f'{a.romfs} is not this game\'s RomFS (missing {marker})')
    elif a.romfs: raise ValueError('--romfs belongs to directory mode; external-resource Apps carry no game data')
    # Only explicit runtime inputs enter the App. Never copy the game's work folder.
    root = a.output/'Contents'; res = root/'Resources'
    (root/'MacOS').mkdir(parents=True)
    for d in ('program', 'profile', 'font', 'msl/' + a.shaders.name): (res/d).mkdir(parents=True)
    def copy(src, dst):
        if src.is_symlink() or not src.is_file(): raise ValueError('input must be a regular file: ' + str(src))
        # System fonts carry protected flags which must not propagate into an App.
        shutil.copyfile(src, dst)
        shutil.copymode(src, dst)
    copy(a.host, root/'MacOS/dmhost')
    for p in programs: copy(p, res/'program'/p.name)
    for p in a.patched.glob('*.tsv'):
        if p.name.endswith(('.fixups.tsv', '.gates.tsv', '.cuts.tsv', '.obs.tsv')): copy(p, res/'program'/p.name)
    if nro_table.is_file(): copy(nro_table, res/'program/nro.tsv')
    for name in tables: copy(a.profile/name, res/'profile'/name)
    copy(a.settings, res/'profile/launcher.json')
    (res/'profile/prepared_builds.tsv').write_text(builds)
    if backend == 'directory':
        # The whole game RomFS, as the iOS build bundles it: the host reads DM_ROMFS from here.
        copy_tree(a.romfs.resolve(), res/'romfs')
        if aoc:
            copy_tree(Path(aoc).resolve(), res/'aoc')
    # The prepared font directory may link to macOS's system font; bundle its bytes.
    for name in ('standard.ttf', 'nintendo_ext.ttf'): copy((a.font/name).resolve(strict=True), res/'font'/name)
    for p in shaders: copy(p, res/'msl'/a.shaders.name/p.name)
    if stamp.is_file(): copy(stamp, res/'msl'/a.shaders.name/'inputs.tsv')
    if a.icon: make_icns(a.icon, res/'AppIcon.icns')
    launcher(root/'MacOS/launch')
    with (root/'Info.plist').open('wb') as f:
        plistlib.dump(info_plist(a.name, a.title_id, a.version, backend, 'AppIcon' if a.icon else None), f)
    (res/'Readme.txt').write_text(readme(backend, a.title_id))
    audit(a.output, backend, marker, a.shaders.name if stamp.is_file() else None, layer)
    return {'backend': backend, 'programs': len(programs), 'shader_files': len(shaders),
            'shader_stamp': stamp.is_file(), 'gfx': layer or 'nvn',
            'romfs_bundled': backend == 'directory', 'addon_content_bundled': bool(aoc), 'containers_or_keys_bundled': False}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for flag in ('host', 'patched', 'shaders', 'profile', 'font', 'settings', 'output'):
        ap.add_argument('--' + flag, type=Path, required=flag in ('profile','output'))
    ap.add_argument('--resource-backend', choices=BACKENDS,
                    help='directory: bundle --romfs in the App; nsp: read an external container at run time (default: nsp, '
                         'or directory when --romfs is given)')
    ap.add_argument('--romfs', type=Path, help='directory mode: the game RomFS folder to bundle')
    ap.add_argument('--icon', type=Path,
                    help='the App icon (png or jpg): rendered into AppIcon.icns, which Finder and the Dock show')
    ap.add_argument('--aoc', type=Path, help='directory mode: verified AOC tree with manifest.json')
    ap.add_argument('--chain-header', type=Path,
                    help='the chain version header the host was built with (default: dm/gfx/nvn/dmsh_chain.h in this source tree)')
    ap.add_argument('--title-id')
    ap.add_argument('--name')
    ap.add_argument('--version', default='1.0')
    ap.add_argument('--use-nsp-prepared',type=Path,help='schema-2 preparation directory; build a new host and App')
    ap.add_argument('--shader-context',type=Path,help='certified macOS Shader context with source-chain verifier')
    ap.add_argument('--nsp-dir',type=Path,help='user game folder containing matching base/update NSPs')
    ap.add_argument('--keys',type=Path,help='user keys file; never copied into the App')
    ap.add_argument('--package',help='registered version, e.g. v131072')
    ap.add_argument('--work',type=Path,help='new build work directory under the NSP folder; output must be inside it')
    ap.add_argument('--progress',choices=('lines','bar','json','off'),default='lines')
    a = ap.parse_args(argv)
    if sys.platform != 'darwin': ap.error('macOS is required')
    a.resource_backend = resolve_backend(a.resource_backend, a.use_nsp_prepared, a.romfs)
    if a.use_nsp_prepared and a.romfs:
        ap.error('--romfs is for directory mode; a prepared NSP build carries no game data')
    if a.resource_backend == 'directory' and (a.use_nsp_prepared or any((a.shader_context,a.nsp_dir,a.keys,a.package,a.work))):
        ap.error('NSP preparation arguments build an external-resource App; --romfs cannot be combined with them')
    if a.use_nsp_prepared:
        if any((a.host,a.patched,a.shaders,a.font,a.settings,a.title_id,a.romfs)):
            ap.error('prepared mode cannot combine with explicit host/runtime asset arguments')
        if not all((a.shader_context,a.nsp_dir,a.keys,a.package,a.work)):
            ap.error('prepared mode requires --shader-context, --nsp-dir, --keys, --package and --work')
        sys.path.insert(0,str(REPO))
        from tools.nxrom.mac_build import build
        from scripts.build_ipa_from_nsp import BuildError,PROG
        PROG.mode=a.progress
        try: build(a,REPO)
        except (OSError,ValueError,subprocess.CalledProcessError,BuildError) as exc: ap.error(str(exc))
        return
    if any((a.shader_context,a.nsp_dir,a.keys,a.package,a.work)):
        ap.error('NSP build arguments require --use-nsp-prepared')
    if not all((a.host,a.patched,a.shaders,a.font,a.settings,a.title_id,a.name)):
        ap.error('asset packaging requires --host, --patched, --shaders, --font, --settings, --title-id and --name')
    try: summary = package(a)
    except (OSError,ValueError) as exc: ap.error(str(exc))
    print(f'App: {a.output}; {summary["programs"]} prepared modules; {summary["shader_files"]} Shader files ({summary["gfx"]}); '
          f'backend {summary["backend"]}; ' + ('game RomFS bundled' if summary['romfs_bundled'] else 'no game containers or keys')
          + ('; add-on content bundled' if summary['addon_content_bundled'] else ''))


if __name__ == '__main__': main()
