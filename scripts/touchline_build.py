#!/usr/bin/env python3
"""Build Touchline 27 (EA SPORTS FC 27, Nintendo Switch) for macOS or iOS.

The two entry points the project documents are the shell wrappers beside this
file, `scripts/build-mac.sh` and `scripts/build-ios.sh`; this module is the work
they share. It never ships game data: everything it produces is built from the
game files you own, and the packaged App/IPA carries no container and no key.

Stages, all rooted at the repository this file lives in:

  inputs     the game's ExeFS and control data (nx_extract, from your NSP/XCI)
  modules    the rewriter's patched modules (dm/tools/patch_nso.py)
  shaders    the Shader library the host links at run time (dm/gfx/tools/dmsh_build.py)
  package    macOS App (scripts/build_mac_app.py) or unsigned IPA (dm/ios/tools/build_ipa.sh)

Every stage can be skipped by pointing at output a previous run produced, which
is what `--exefs`, `--patched`, `--shaders` and `--shader-pack` are for.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAME_ID = '0100C49025D3E000'
PROFILE = ROOT / 'dm/games' / GAME_ID
DEFAULT_APP_NAME = 'Touchline 27'
# The identity the user's existing installation has: an IPA rebuilt with this
# bundle ID upgrades in place and keeps its Documents (imported NSPs, saves).
IOS_BUNDLE_ID = 'org.nxnative.' + GAME_ID.lower()
MAC_APP_NAME = 'Touchline27.app'
IOS_IPA_NAME = 'Touchline27.ipa'
# The project's own icon, used for both targets unless --icon names another image:
# the game's control-data icon.jpg is only a fallback for checkouts without it.
PROJECT_ICON = ROOT / 'assets/app-icon/touchline27.png'
# Nitro game data and private key material must never end up inside an artifact.
FORBIDDEN = ('.nsp', '.xci', '.nsz', '.ncz', '.xcz', '.nca', '.keys', '.tik')


class Failure(SystemExit):
    def __init__(self, message):
        super().__init__('[RED] ' + message)


def say(*parts):
    print('[%s]' % time.strftime('%H:%M:%S'), *parts, flush=True)


def run(argv, what, env=None, quiet=False):
    """Run a build step; stop with its last lines when it fails."""
    shown = ' '.join(str(a) for a in argv)
    try:
        if quiet:
            p = subprocess.run([str(a) for a in argv], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, errors='replace')
        else:
            p = subprocess.run([str(a) for a in argv], env=env)
    except FileNotFoundError as exc:
        raise Failure('%s: %s is not installed' % (what, exc.filename)) from exc
    if p.returncode:
        tail = ''
        if quiet and p.stdout:
            tail = '\n' + '\n'.join(p.stdout.strip().splitlines()[-25:])
        raise Failure('%s failed (exit %d): %s%s' % (what, p.returncode, shown, tail))
    return p.stdout if quiet else ''


def tool_env():
    env = dict(os.environ)
    env.setdefault('LC_ALL', 'C')
    # nx_extract and dmsh_xlate are framework-dependent .NET apps: launched
    # directly they find no runtime unless DOTNET_ROOT names one. Homebrew
    # keeps dotnet in its own cellar, so ask the shim where it points first.
    if not env.get('DOTNET_ROOT'):
        root = None
        binary = shutil.which('dotnet')
        if binary:
            for parent in Path(binary).resolve().parents:
                if (parent / 'shared').is_dir():
                    root = parent
                    break
        if not root:
            for guess in ('/opt/homebrew/opt/dotnet/libexec', '/usr/local/share/dotnet'):
                if Path(guess, 'shared').is_dir():
                    root = Path(guess)
                    break
        if root:
            env['DOTNET_ROOT'] = str(root)
            env.setdefault('DOTNET_ROOT_ARM64', str(root))
    return env


def need_tools(names, why):
    missing = [n for n in names if not shutil.which(n)]
    if missing:
        raise Failure('%s needs %s on PATH (missing: %s)' % (why, ' and '.join(names), ', '.join(missing)))


def has_module(python, module):
    p = subprocess.run([python, '-c', 'import %s' % module], capture_output=True)
    return p.returncode == 0


def chain_version():
    text = (ROOT / 'dm/gfx/nvn/dmsh_chain.h').read_text()
    m = re.search(r'#define\s+DMSH_CHAIN\s+"([^"]+)"', text)
    if not m:
        raise Failure('dm/gfx/nvn/dmsh_chain.h has no DMSH_CHAIN')
    return m.group(1)


def profile():
    """The registered FC 27 profile, read with the project's own reader."""
    sys.path.insert(0, str(ROOT / 'dm/games'))
    import game  # noqa: E402  (dm/games/game.py)
    return game.load(GAME_ID)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def newest(path, marker):
    paths = sorted(Path(path).rglob(marker), key=lambda p: p.stat().st_mtime)
    return paths[-1] if paths else None


# --------------------------------------------------------------------------
# inputs: ExeFS + control data
# --------------------------------------------------------------------------

def find_extractor(args):
    if args.nx_extract:
        if not Path(args.nx_extract).is_file():
            raise Failure('--nx-extract %s does not exist' % args.nx_extract)
        return Path(args.nx_extract)
    if os.environ.get('DM_NX_EXTRACT'):
        return Path(os.environ['DM_NX_EXTRACT'])
    built = ROOT / 'build/tools/nx_extract/nx_extract'
    if built.is_file():
        return built
    return None


def build_extractor():
    """nx_extract is C# over LibHac: build it once into build/tools (needs .NET 10)."""
    out = ROOT / 'build/tools/nx_extract'
    need_tools(['dotnet'], 'building nx_extract')
    say('building nx_extract into', out.relative_to(ROOT))
    out.mkdir(parents=True, exist_ok=True)
    run(['dotnet', 'build', ROOT / 'dm/tools/nx_extract/nx_extract.csproj', '-c', 'Release', '-o', out],
        'dotnet build dm/tools/nx_extract (first run restores LibHac from NuGet)')
    binary = out / 'nx_extract'
    if not binary.is_file():
        raise Failure('dotnet build produced no %s' % binary)
    return binary


def extract(args, work):
    """Run nx_extract for the ExeFS and the control data; no RomFS is written."""
    if args.exefs:
        exefs = Path(args.exefs)
        if (exefs / 'ExeFS').is_dir():
            exefs = exefs / 'ExeFS'
        if not exefs.is_dir():
            raise Failure('--exefs %s is not a directory' % args.exefs)
        return exefs
    if not args.base:
        raise Failure('give --nsp-dir (or --base and --keys) so the game\'s own ExeFS can be read, '
                      'or --exefs with an already extracted ExeFS')
    if not args.keys:
        raise Failure('--keys <prod.keys> is required to read the game\'s containers')
    out = work / 'extract'
    binary = find_extractor(args) or build_extractor()
    say('extracting ExeFS and control data (no RomFS)', Path(args.base).name)
    out.mkdir(parents=True, exist_ok=True)
    argv = [binary, args.keys, args.base, args.update or '-', out, '--program-only']
    run(argv, 'nx_extract', env=tool_env())
    exefs = out / 'ExeFS'
    if not exefs.is_dir():
        raise Failure('nx_extract wrote no ExeFS to %s' % out)
    return exefs


def control_data(args, exefs, work):
    """control.nacp and the App icon: they name the App, version the IPA, and give it its icon."""
    folder = exefs.parent if exefs else work / 'extract/ExeFS'
    nacp = None
    for candidate in (args.nacp, folder / 'control.nacp'):
        if candidate and Path(candidate).is_file():
            nacp = Path(candidate)
            break
    icon = None
    for candidate in (args.icon, PROJECT_ICON, folder / 'icon.jpg'):
        if candidate and Path(candidate).is_file():
            icon = Path(candidate)
            break
    return nacp, icon


# --------------------------------------------------------------------------
# modules: the patched NSO/NRO images
# --------------------------------------------------------------------------

def modules_ready(directory, names):
    return all((directory / (n + '.patched.bin')).is_file() and (directory / (n + '.fixups.tsv')).is_file()
               for n in names)


def zbic_compressed(path):
    """An NSO whose sections use the ZBIC codec instead of LZ4 (FC 27's main does)."""
    with open(path, 'rb') as f:
        head = f.read(0x14)
    return len(head) >= 0x14 and head[:4] == b'NSO0' and bool(int.from_bytes(head[0xc:0x10], 'little') & 0x80)


def require_zbic_decoder(sources):
    """The decoder is GPL-2.0 Atmosphère code: it is never bundled, only pointed at."""
    compressed = [name for name, src in sources.items() if Path(src).is_file() and zbic_compressed(src)]
    if compressed and not os.environ.get('NX_ZBIC_LIBRARY'):
        raise Failure('the game\'s %s use ZBIC-compressed sections, and the rewriter needs a decoder for them. '
                      'This project does not bundle one (Atmosphère\'s zbicdeclib is GPL-2.0): build a library that '
                      'exposes zbic_decompress and point NX_ZBIC_LIBRARY at it, or pass --patched with modules '
                      'rewritten on a machine that had one. See docs/building.md.'
                      % ', '.join(compressed))


def nro_table(directory):
    """The game's run-time NRO modules (nn::ro): name, hash, size, as nro_collect.py writes them."""
    table = directory / 'nro.tsv'
    if not table.is_file():
        return []
    return [l.split('\t')[0] for l in table.read_text().splitlines()
            if l.strip() and not l.startswith(('#', 'refused\t'))]


def collect_nros(args, work, g):
    """Find the NRO modules the game registers (FC 27's `render` is one) from what the user gave."""
    if args.nro:
        source = Path(args.nro)
        if not source.is_dir():
            raise Failure('--nro %s is not a directory' % args.nro)
        out = work / 'nro'
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        # The host finds a module by its SHA-256, so the label is only a name:
        # nro<index> in hash order, as dm/tools/nro_collect.py writes it, and
        # short enough for the 16-character section names gen_embed.py makes.
        found = sorted(source.glob('*.nro'), key=lambda p: digest(p))
        for index, nro in enumerate(found):
            name = 'nro%d' % index
            shutil.copyfile(nro, out / (name + '.nro'))
            rows.append('%s\t%s\t%d\t-\t%s' % (name, digest(nro), nro.stat().st_size, nro.name))
        if rows:
            (out / 'nro.tsv').write_text('# name\tsha256\tsize\tnrr\twhere\n' + '\n'.join(rows) + '\n')
        say('NRO modules from --nro:', ', '.join(r.split('\t')[0] + ' (' + r.split('\t')[4] + ')' for r in rows)
            or 'none found')
        return out
    if args.romfs:
        if not (has_module(args.font_python, 'compression.zstd') or
                has_module(args.font_python, 'backports.zstd')):
            raise Failure('%s has no compression.zstd (3.14+) or backports.zstd, which scanning a RomFS '
                          'needs (pip install backports.zstd), or pass --nro with the modules themselves'
                          % args.font_python)
        out = work / 'nro'
        say('collecting the NRO modules the game registers from', Path(args.romfs))
        run([args.font_python, ROOT / 'dm/tools/nro_collect.py', args.romfs, out], 'nro_collect')
        return out
    return None


def rewrite(args, exefs, work, g):
    if args.patched:
        patched = Path(args.patched)
        if not patched.is_dir():
            raise Failure('--patched %s is not a directory' % args.patched)
        names = list(g.words('modules')) + nro_table(patched)
        broken = [n for n in names if not modules_ready(patched, [n])]
        if broken:
            raise Failure('--patched %s has no rewritten %s (expected <module>.patched.bin and '
                          '<module>.fixups.tsv there)' % (patched, ', '.join(broken)))
        say('patched modules:', ', '.join(names), '(as given)')
        return patched
    if not has_module(args.font_python, 'capstone'):
        raise Failure('%s cannot import capstone, which the rewriter needs (pip install capstone), '
                      'or pass --patched with modules a previous build wrote' % args.font_python)
    out = work / 'patched'
    out.mkdir(parents=True, exist_ok=True)
    names = list(g.words('modules'))
    nro_dir = collect_nros(args, work, g)
    sources = {n: exefs / n for n in names}
    if nro_dir:
        if (nro_dir / 'nro.tsv').is_file():
            shutil.copyfile(nro_dir / 'nro.tsv', out / 'nro.tsv')
        for n in nro_table(nro_dir):
            sources[n] = nro_dir / (n + '.nro')
    require_zbic_decoder(sources)
    for name, src in sources.items():
        if not Path(src).is_file():
            raise Failure('the ExeFS has no module %s (%s)' % (name, src))
        say('rewriting', name, '(%.1f MB)' % (Path(src).stat().st_size / 2 ** 20))
        run([args.font_python, ROOT / 'dm/tools/patch_nso.py', src, out, name],
            'patch_nso.py %s' % name)
    if not modules_ready(out, list(sources)):
        raise Failure('the rewriter did not write every module into %s' % out)
    return out


# --------------------------------------------------------------------------
# shaders: the b-<chain> library
# --------------------------------------------------------------------------

def library_under(path, chain):
    path = Path(path)
    if path.name == 'b-' + chain and path.is_dir():
        return path
    for candidate in (path / ('b-' + chain), path / 'cache' / ('b-' + chain), path / 'ios' / ('b-' + chain)):
        if candidate.is_dir():
            return candidate
    found = sorted(path.rglob('b-' + chain)) if path.is_dir() else []
    return found[0] if found else None


def stamp(library):
    table = Path(library) / 'inputs.tsv'
    if not table.is_file():
        return {}
    rows = {}
    for line in table.read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            key, _, value = line.partition('\t')
            rows[key] = value
    return rows


def library_inputs(env):
    p = subprocess.run([sys.executable, ROOT / 'dm/gfx/tools/dmsh_chain.py', '--inputs'],
                       capture_output=True, text=True, env=env, cwd=str(ROOT))
    return p.stdout.strip() if p.returncode == 0 else None


def verify_library(library, chain, env):
    """The host ignores a table whose library was not built from this profile's inputs."""
    rows = stamp(library)
    if not rows:
        raise Failure('%s has no inputs.tsv: it is not a finished dmsh_build.py library '
                      '(build one with --shader-pack, or point --shaders at a full build)' % library)
    expected = library_inputs(env)
    problems = []
    if rows.get('game') != GAME_ID:
        problems.append('built for game %s' % rows.get('game'))
    if expected and rows.get('inputs') != expected:
        problems.append('built from inputs %s, this profile has %s' % (rows.get('inputs'), expected))
    if problems:
        raise Failure('%s is not a library of this profile (%s): build the Shaders again, or pass --shaders '
                      'with the one your working build used' % (library, '; '.join(problems)))
    return library


def build_library(args, work, target, chain, env):
    """dmsh_build.py turns a dump pack into a chain library for the requested target."""
    pack = Path(args.shader_pack)
    if not pack.is_dir():
        raise Failure('--shader-pack %s is not a directory' % pack)
    need_tools(['dotnet', 'spirv-cross'], 'building the Shader library')
    if not (Path(args.font_python).exists() or shutil.which(args.font_python)):
        raise Failure('--font-python %s does not exist' % args.font_python)
    out = work / 'shaders'
    out.mkdir(parents=True, exist_ok=True)
    env = dict(env)
    env['DM_GAME'] = GAME_ID
    if target == 'ios':
        env['IOSOUT'] = str(out / 'ios')
    say('translating and compiling the Shader pack', pack.name, 'for', target)
    run([sys.executable, ROOT / 'dm/gfx/tools/dmsh_build.py', pack, out], 'dmsh_build.py', env=env)
    library = out / ('b-' + chain) if target == 'mac' else out / 'ios' / ('b-' + chain)
    if not library.is_dir():
        raise Failure('dmsh_build.py wrote no %s' % library)
    return library


def tables(args, library, env):
    """c1_full.tsv and cb_extent.tsv are per-checkout build products the host reads."""
    want = {'c1_full.tsv': ROOT / 'dm/gfx/tools/c1_guard.py',
            'cb_extent.tsv': ROOT / 'dm/gfx/tools/cb_extent.py'}
    for name, tool in want.items():
        target = PROFILE / name
        head = target.read_text().splitlines()[0] if target.is_file() else ''
        if head.startswith('# chain b-') and library.name in head:
            say('runtime table', name, 'present')
            continue
        say('generating', name, 'from', library.name)
        run([sys.executable, tool, library, target], '%s (%s)' % (tool.name, name), env=env)


# --------------------------------------------------------------------------
# packaging
# --------------------------------------------------------------------------

def fonts(args, work):
    out = work / 'font'
    out.mkdir(parents=True, exist_ok=True)
    standard = out / 'standard.ttf'
    if not standard.is_file():
        source = Path(args.standard_font or '/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
        if not source.is_file():
            raise Failure('no standard font at %s (pass --standard-font with a Unicode TTF)' % source)
        shutil.copyfile(source, standard)
    ext = out / 'nintendo_ext.ttf'
    if not ext.is_file():
        if not has_module(args.font_python, 'fontTools'):
            raise Failure('%s cannot import fontTools, needed to draw the button glyphs '
                          '(pip install fonttools, or --font-python <python with it>)' % args.font_python)
        run([args.font_python, ROOT / 'dm/tools/make_ext_font.py', ext], 'make_ext_font.py', quiet=True)
    return out


def launcher_settings(args, patched, nacp, work):
    """The launcher's screen: settings.tsv filtered by this profile, as JSON."""
    out = work / 'launcher.json'
    env = dict(tool_env())
    env['DM_SHOW_FPS'] = 'YES' if args.show_fps == 1 else 'NO'
    env['DM_LANG'] = args.language or 'en-US'
    if not nacp:
        say('no control.nacp: the launcher will not offer the game languages '
            '(pass --nacp, or let the build extract the control data)')
    text = run([sys.executable, ROOT / 'dm/games/settings.py', GAME_ID, patched,
                nacp or Path('/nonexistent/control.nacp'), out],
               'dm/games/settings.py', env=env, quiet=True)
    say('launcher settings:', (text or '').strip())
    return out


def app_version(args, nacp):
    if args.version:
        return args.version
    if nacp:
        p = subprocess.run([sys.executable, ROOT / 'dm/tools/nacp.py', '--version', nacp],
                           capture_output=True, text=True)
        value = (p.stdout or '').strip()
        if p.returncode == 0 and value:
            return value
    say('no display version in the control data: using 1.0')
    return '1.0'


def build_mac(args, work, patched, library, nacp, icon):
    need_tools(['make', 'clang', 'xcrun', 'swiftc', 'sips'], 'building the macOS App')
    host = work / 'dmhost'
    say('compiling the host for macOS (this takes a few minutes)')
    run(['make', '-C', ROOT / 'dm/host', 'GAME=' + GAME_ID, 'GEN=' + str(work / 'gen'),
         'HOST=' + str(host), 'dmhost'], 'make -C dm/host')
    if not host.is_file():
        raise Failure('make wrote no host at %s' % host)
    out = Path(args.out) if args.out else ROOT / 'build' / MAC_APP_NAME
    out = out.resolve()
    if out.exists():
        if out.suffix != '.app':
            raise Failure('%s exists and is not a .app' % out)
        say('replacing the previous', out.name)
        shutil.rmtree(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    say('packaging', out.name)
    argv = [sys.executable, ROOT / 'scripts/build_mac_app.py',
            '--host', host, '--patched', patched, '--shaders', library, '--profile', PROFILE,
            '--font', fonts(args, work), '--settings', work / 'launcher.json',
            '--title-id', GAME_ID, '--name', args.app_name, '--version', app_version(args, nacp),
            '--resource-backend', 'nsp', '--output', out]
    if icon:
        argv += ['--icon', str(icon)]
    run(argv, 'build_mac_app.py')
    return out


def build_ios(args, work, patched, library, nacp, icon):
    need_tools(['xcodebuild', 'xcodegen', 'make'], 'building the iOS IPA')
    out = Path(args.out) if args.out else ROOT / 'build' / IOS_IPA_NAME
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    resources = work / 'res'
    (resources / 'RomFS').mkdir(parents=True, exist_ok=True)   # external mode: no RomFS is staged
    if nacp:
        shutil.copyfile(nacp, resources / 'control.nacp')
    if icon:
        shutil.copyfile(icon, resources / 'icon.jpg')
    else:
        say('no App icon (assets/app-icon/touchline27.png missing): the home-screen icon stays blank')
    project = work / 'ios-project'
    if project.exists():
        say('discarding the previous generated Xcode project')
        shutil.rmtree(project)
    env = tool_env()
    env.update({
        'GAME': GAME_ID,
        'W': str(work),
        'PATCHED': str(patched),
        'ROMFS': str(resources / 'RomFS'),
        'MSL_IOS': str(library.parent),
        'AOC': '',
        'DM_RESOURCE_BACKEND': 'nsp',
        'DM_IOS_BUILD_DIR': str(project),
        'DM_BUNDLE_ID': IOS_BUNDLE_ID,
        'DM_DISPLAY_NAME': args.app_name,
        'DM_APP_VERSION': app_version(args, nacp),
        'DM_LANG': args.language or 'en-US',
        'DM_SHOW_FPS': '1' if args.show_fps == 1 else '0',
        'FONT_PY': args.font_python,
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
    })
    if icon:
        env['DM_ICON'] = str(icon)   # build_ipa.sh otherwise defaults to the same project icon
    say('building the unsigned IPA (xcodegen + xcodebuild)')
    run(['bash', ROOT / 'dm/ios/tools/build_ipa.sh', out], 'dm/ios/tools/build_ipa.sh', env=env)
    return out


# --------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------

def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--target', choices=('mac', 'ios'), required=True)
    p.add_argument('--nsp-dir', type=Path, help='folder holding the base .nsp/.xci, an optional update .nsp and prod.keys')
    p.add_argument('--base', type=Path, help='the base game container (overrides --nsp-dir)')
    p.add_argument('--update', type=Path, help='the update container, if you have one')
    p.add_argument('--keys', type=Path, help='prod.keys')
    p.add_argument('--exefs', type=Path, help='an already extracted ExeFS (skips nx_extract)')
    p.add_argument('--nacp', type=Path, help='control.nacp (App name, version, languages)')
    p.add_argument('--icon', type=Path, help='the App icon, png or jpg (default: assets/app-icon/touchline27.png)')
    p.add_argument('--nx-extract', type=Path, help='the nx_extract binary (built into build/tools when absent)')
    p.add_argument('--patched', type=Path, help='already rewritten modules (skips the rewriter)')
    p.add_argument('--shaders', type=Path, help='a finished b-<chain> Shader library, or a folder holding one')
    p.add_argument('--shader-pack', type=Path, help='a Shader dump pack to build the library from (cs/ps/vs_dump.bin)')
    p.add_argument('--nro', type=Path, help='a folder with the game\'s run-time *.nro modules')
    p.add_argument('--romfs', type=Path, help='an extracted RomFS, to find the game\'s run-time NRO modules')
    p.add_argument('--work', type=Path, help='build work directory (default build/work)')
    p.add_argument('--out', type=Path, help='artifact path (default build/Touchline27.app or .ipa)')
    p.add_argument('--app-name', default=DEFAULT_APP_NAME, help='App display name (default %(default)s)')
    p.add_argument('--version', help='App version (default: the game\'s display version)')
    p.add_argument('--language', help='default game language (default en-US)')
    p.add_argument('--show-fps', type=int, choices=(0, 1), help='start with the frame-rate counter on')
    p.add_argument('--standard-font', type=Path, help='Unicode TTF stand-in for the system font')
    p.add_argument('--font-python', default=sys.executable,
                   help='a python with capstone/fontTools for the rewriter and font tools')
    p.add_argument('--force-stage', action='store_true', help='rebuild the modules even if --patched is complete')
    return p.parse_args(argv)


def probe_containers(folder, keys, work):
    """Let the project's own reader say which container is the base and which the update.

    Names say nothing reliable (an update may be called v-ea_sports_fc_27_v327680.nsp),
    so each container is opened and asked: the update's program carries the patch flag.
    """
    sys.path.insert(0, str(ROOT))
    from tools.nxrom import folder as nxfold
    from tools.nxrom.resourcefs import build_library
    library = work / 'tools/nxrom.dylib'
    library.parent.mkdir(parents=True, exist_ok=True)
    if not library.is_file():
        say('compiling the native container reader')
        build_library(library)
    title = int(GAME_ID, 16)
    base = update = None
    for path in nxfold.candidates(folder):
        try:
            facts = nxfold.probe(library, path, keys)
        except OSError as exc:
            if path.suffix.lower() in ('.nsz', '.ncz', '.xcz'):
                raise Failure('%s is compressed: decompress it first (nsz -D) and build from the .nsp/.xci'
                              % path.name) from exc
            say('not a readable container, left alone:', path.name)
            continue
        if facts['title'] not in (title, title + 0x800):
            continue          # another title's container (add-on content, another game)
        if facts['patched']:
            if update and update != path:
                raise Failure('two update containers in %s: pass --update with the one you want' % folder)
            update = path
        else:
            if base and base != path:
                raise Failure('two base containers in %s: pass --base with the one you want' % folder)
            base = path
    return base, update


def resolve_inputs(args, work):
    """--nsp-dir is the documented way in; --base/--keys are the explicit equivalent."""
    folder = args.nsp_dir
    if not folder:
        return args
    if not folder.is_dir():
        raise Failure('--nsp-dir %s is not a directory' % folder)
    if not args.keys and (folder / 'prod.keys').is_file():
        args.keys = folder / 'prod.keys'
    if not args.keys:
        raise Failure('--keys <prod.keys> is required to read the game\'s containers '
                      '(none was given and %s has no prod.keys)' % folder)
    if args.base and args.update:
        return args
    say('identifying the base and update containers in', folder)
    base, update = probe_containers(folder, args.keys, work)
    if not args.base:
        if not base:
            raise Failure('no base container for %s in %s (nothing there is a readable, unpatched .nsp/.xci)'
                          % (GAME_ID, folder))
        args.base = base
    if not args.update:
        args.update = update
    say('base:', args.base.name)
    say('update:', args.update.name if args.update else 'none (the base game only)')
    if not args.update:
        say('WARNING: no update container: the App will run the base build (1.0.0). '
            'The verified 60 fps mode and the tested match build use the update.')
    return args


def main(argv=None):
    args = parse_args(argv)
    sys.path.insert(0, str(ROOT))
    g = profile()
    chain = chain_version()
    work = (args.work or ROOT / 'build/work').resolve()
    work.mkdir(parents=True, exist_ok=True)
    say('Touchline 27:', args.target, '| profile', g.get('name'), '| chain b-' + chain)
    say('work directory', work)
    args = resolve_inputs(args, work)

    reuse = bool(args.patched) and not args.force_stage
    # The control data names the App, versions the IPA and lists the game's
    # languages for the launcher, so it is read even when the modules are reused.
    exefs = None
    if not reuse or not args.nacp:
        exefs = extract(args, work)
    patched = rewrite(args, exefs, work, g)
    nacp, icon = control_data(args, exefs, work)

    env = tool_env()
    env['DM_GAME'] = GAME_ID
    if args.shaders:
        library = library_under(args.shaders, chain)
        if not library:
            raise Failure('--shaders %s holds no b-%s' % (args.shaders, chain))
        say('Shader library', library)
    elif args.shader_pack:
        library = build_library(args, work, args.target, chain, env)
    else:
        raise Failure('the Shader library must come from somewhere: pass --shader-pack <dump pack> to build one, '
                      'or --shaders <finished b-%s> (see docs/building.md)' % chain)
    verify_library(library, chain, env)
    tables(args, library, env)

    launcher_settings(args, patched, nacp, work)
    if args.target == 'mac':
        out = build_mac(args, work, patched, library, nacp, icon)
    else:
        out = build_ios(args, work, patched, library, nacp, icon)
    if not out.exists():
        raise Failure('the build reported success but %s does not exist' % out)
    size = out.stat().st_size if out.is_file() else sum(f.stat().st_size for f in out.rglob('*') if f.is_file())
    say('done:', out)
    say('size: %d bytes (%.1f MiB)' % (size, size / 2 ** 20))
    if out.is_file():
        say('sha256:', digest(out))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Failure as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
