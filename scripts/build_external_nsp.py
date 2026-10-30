#!/usr/bin/env python3
"""Prepare external NSP resources, compile Shaders and package Mac/iOS apps."""
import argparse
from pathlib import Path
import subprocess
import sys

# Settings for Spyder F5; command-line options override these values.
NSP_DIR=''
PROD_KEYS=''
GAME_PROFILE=''
PACKAGE=''
WORK_DIR=''
TARGET='both'
PREPARED_DIR=''
SHADER_CONTEXT=''
NSP_EXTRACTOR=''
APP_NAME=''
JOBS=8
PROGRESS='lines'


def parse_args(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for flag,value in (('nsp-dir',NSP_DIR),('keys',PROD_KEYS),('profile',GAME_PROFILE),
                       ('work',WORK_DIR),('prepared',PREPARED_DIR),
                       ('shader-context',SHADER_CONTEXT),('nsp-extractor',NSP_EXTRACTOR)):
        p.add_argument('--'+flag,type=Path,default=Path(value) if value else None)
    p.add_argument('--package',default=PACKAGE,help='registered single-version package, e.g. v131072')
    p.add_argument('--target',choices=('macos','ios','both'),default=TARGET)
    p.add_argument('--app-name',default=APP_NAME or None)
    p.add_argument('--jobs',type=int,default=JOBS)
    p.add_argument('--progress',choices=('lines','bar','json','off'),default=PROGRESS)
    a=p.parse_args(argv)
    if not all((a.nsp_dir,a.keys,a.profile,a.work,a.package)):
        p.error('set Settings or supply --nsp-dir, --keys, --profile, --work and --package')
    if not 1<=a.jobs<=32: p.error('--jobs must be from 1 to 32')
    return a


def main(argv=None):
    a=parse_args(argv)
    repo=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(repo))
    from tools.nxrom.build_pipeline import build
    from scripts.build_ipa_from_nsp import BuildError
    try: return build(a,repo)
    except (OSError,ValueError,subprocess.CalledProcessError,BuildError) as exc:
        raise SystemExit('[RED] external NSP build failed: '+str(exc)) from exc


if __name__=='__main__':
    try: main()
    except SystemExit:
        if not callable(globals().get('get_ipython')): raise
