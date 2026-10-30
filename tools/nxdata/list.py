#!/usr/bin/env python3
import argparse
import sys
from nxdata import Archive
p = argparse.ArgumentParser(description='List NXDATA entries (index validation only)')
p.add_argument('archive')
a = p.parse_args()
try:
    ar = Archive(a.archive)
    try:
        for name, (size, kind, _, _) in ar.entries.items():
            print(f'{"d" if kind else "f"}\t{size}\t{name or "/"}')
        print(f'{len(ar.entries)} entries, {len(ar.blocks)} blocks')
    finally:
        ar.close()
except (OSError, ValueError, __import__('struct').error) as e:
    print(f'[RED] list failed: {e}', file=sys.stderr)
    sys.exit(1)
