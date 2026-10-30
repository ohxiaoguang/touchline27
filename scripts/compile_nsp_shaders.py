#!/usr/bin/env python3
"""Compile Mac/iOS Shaders from verified NSP preparation without extracting RomFS."""
import argparse
from pathlib import Path
import subprocess
import sys

# Settings for Spyder F5; command-line options override these values.
NSP_DIR=''
PREPARED_DIR=''
GAME_PROFILE=''
OUTPUT_DIR=''
PACKAGE=''
JOBS=8
PROGRESS='lines'


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for flag,value in (('nsp-dir',NSP_DIR),('prepared',PREPARED_DIR),('profile',GAME_PROFILE),('output',OUTPUT_DIR)):
        parser.add_argument('--'+flag,type=Path,default=Path(value) if value else None)
    parser.add_argument('--package',default=PACKAGE,help='registered single-version Shader package')
    parser.add_argument('--jobs',type=int,default=JOBS)
    parser.add_argument('--finalize-existing',action='store_true',help='verify a completed, unpublished context and regenerate copied runtime tables; never rerun translation/compilation')
    parser.add_argument('--progress',choices=('lines','bar','json','off'),default=PROGRESS)
    args=parser.parse_args(argv)
    if not all((args.nsp_dir,args.prepared,args.profile,args.output,args.package)):
        parser.error('set the Settings block or supply --nsp-dir, --prepared, --profile, --output and --package')
    repo=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(repo))
    from tools.nxrom.shader_compile import compile_prepared
    from scripts.build_ipa_from_nsp import BuildError,PROG
    PROG.mode=args.progress
    try: compile_prepared(args,repo)
    except (OSError,ValueError,subprocess.CalledProcessError,BuildError) as exc:
        PROG.close(ok=False); parser.error(str(exc))
    finally: PROG.close(ok=False)


if __name__=='__main__':
    try: main()
    except SystemExit:
        # Spyder displays the diagnostic but keeps its interactive console alive.
        if not callable(globals().get('get_ipython')): raise
