#!/usr/bin/env python3
import argparse
import json
import sys
import time
from nxdata import pack

p = argparse.ArgumentParser(description='Stream a runtime resource tree into NXDATA v1')
p.add_argument('--input', required=True)
p.add_argument('--output', required=True)
p.add_argument('--block-size', type=int, default=262144)
p.add_argument('--store', action='store_true', help='disable compression')
p.add_argument('--force', action='store_true', help='explicitly overwrite output')
a = p.parse_args()
t = time.perf_counter()
try:
    stats = pack(a.input, a.output, a.block_size, not a.store, a.force)
    stats['seconds'] = time.perf_counter() - t
    stats['stored_percent'] = 100 * stats['archive_bytes'] / stats['raw_bytes'] if stats['raw_bytes'] else None
    stats['failed_files'] = []
    print(json.dumps(stats, indent=2))
except (OSError, ValueError) as e:
    print(f'[RED] pack failed: {e}; any partial output is retained, not a valid archive', file=sys.stderr)
    sys.exit(1)
