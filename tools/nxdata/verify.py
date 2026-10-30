#!/usr/bin/env python3
import argparse
import sys
from nxdata import Archive
p = argparse.ArgumentParser(description='Verify the index and every payload block')
p.add_argument('archive')
a = p.parse_args()
try:
    ar = Archive(a.archive)
    try:
        for name, (size, kind, _, _) in ar.entries.items():
            if not kind:
                for off in range(0, size, ar.bs):
                    ar.read(name, off, ar.bs)
        print(f'OK: {len(ar.entries)} entries, {len(ar.blocks)} blocks')
    finally:
        ar.close()
except (OSError, ValueError, KeyError, __import__('struct').error) as e:
    print(f'[RED] verify failed: {e}', file=sys.stderr)
    sys.exit(1)
