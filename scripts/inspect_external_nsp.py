#!/usr/bin/env python3
"""Inspect/verify/read external NSP resources without extracting a RomFS tree.
F5 in Spyder uses the settings below; command-line arguments override settings.
Outputs and the small native tool stay beside the user's NSP, never in HOME.
"""
NSP = ''
UPDATE = ''
KEYS = ''
TITLE = ''
VERIFY = False
WORK = ''
SURVEY_EXEFS = ''

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def survey(exefs, resources):
    """Use the preparation pipeline's existing census and profile rules."""
    repo = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo / 'dm/games'))
    import profile_guess as pg
    facts = pg.facts_of(exefs, resources)
    if 'main' not in facts['mods']:
        raise ValueError('survey ExeFS has no main NSO module')
    for name, module in facts['mods'].items():
        resources.check_build(name, module['bid'])
    return {'sdk': facts['sdk'], 'program': facts['program'], 'system_resource': facts['sysres'],
            'modules': {name: {'build_id': m['bid'], 'kind': m['kind'], 'sizes': m['sizes'],
                               'bss': m['bss'], 'imports': len(m['imports']), 'exports': len(m['exports'])}
                        for name, m in facts['mods'].items()},
            'romfs': facts['romfs'], 'suggested_profile': pg.guess(facts)}


def json_value(value):
    if isinstance(value, set):
        return sorted(value)
    raise TypeError('unsupported survey value: ' + type(value).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default=NSP, required=not NSP)
    parser.add_argument('--update', default=UPDATE)
    parser.add_argument('--keys', default=KEYS, required=not KEYS)
    parser.add_argument('--title', default=TITLE, help='expected base Program ID (hex)')
    parser.add_argument('--verify', action='store_true', default=VERIFY)
    parser.add_argument('--read', help='relative resource path, binary data to stdout')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--length', type=int)
    parser.add_argument('--work', default=WORK)
    parser.add_argument('--survey-exefs', type=Path, default=Path(SURVEY_EXEFS) if SURVEY_EXEFS else None,
                        help='survey NSP resources with existing matching ExeFS; JSON to stdout, no extraction')
    args = parser.parse_args(argv)
    if args.survey_exefs and (args.verify or args.read is not None or args.length is not None or args.offset):
        parser.error('--survey-exefs cannot be combined with verify/read/range options')
    base = Path(args.base).expanduser().resolve()
    if not base.is_file():
        parser.error('base NSP does not exist')
    work = Path(args.work).expanduser().resolve() if args.work else base.parent / ((args.title or base.stem) + '-work') / 'nxrom'
    work.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    sources = repo / 'dm/resource'
    if args.survey_exefs:
        sys.path.insert(0, str(repo))
        from tools.nxrom.resourcefs import ResourceFS, build_library
        # A Spyder process may still hold an older CDLL mapping. Never overwrite
        # a mapped dylib when the source changes between F5 runs.
        fingerprint = hashlib.sha256(b''.join(p.read_bytes() for p in (sources/'nxrom.c', sources/'nxrom.h'))).hexdigest()[:16]
        library = work / ('nxrom-' + fingerprint + '.dylib')
        if not library.exists():
            build_library(library)
        with ResourceFS(library, base=base, keys=Path(args.keys).expanduser().resolve(),
                        update=Path(args.update).expanduser().resolve() if args.update else None,
                        title=int(args.title, 16) if args.title else 0) as resources:
            report = survey(args.survey_exefs.expanduser().resolve(), resources)
        print(json.dumps(report, default=json_value, sort_keys=True, indent=2))
        return 0
    tool = work / 'nxrom-inspect'
    if not tool.exists() or any(p.stat().st_mtime_ns > tool.stat().st_mtime_ns for p in (sources/'nxrom.c', sources/'nxrom.h', sources/'inspect.c')):
        subprocess.run(['xcrun', 'clang', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-deprecated-declarations', str(sources/'inspect.c'), str(sources/'nxrom.c'), '-o', str(tool)], check=True)
    cmd = [str(tool), '--base', str(base), '--keys', str(Path(args.keys).expanduser().resolve())]
    for option, value in (('--update', args.update), ('--title', args.title), ('--read', args.read)):
        if value:
            cmd += [option, str(Path(value).expanduser().resolve()) if option == '--update' else value]
    if args.verify:
        cmd += ['--verify']
    if args.read:
        cmd += ['--offset', str(args.offset)]
        if args.length is not None:
            cmd += ['--length', str(args.length)]
    return subprocess.run(cmd).returncode


if __name__ == '__main__':
    try:
        status = main([] if 'spyder_kernels' in sys.modules else None)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'[RED] inspection failed: {exc}', file=sys.stderr)
        status = 1
    if 'spyder_kernels' not in sys.modules:
        sys.exit(status)
