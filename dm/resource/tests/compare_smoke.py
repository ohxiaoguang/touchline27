"""Compare immutable RomFS reads observed in two bounded real host runs.

Different thread schedules need not produce identical traces. This compares only
shared (path, offset, returned length) requests, and explicitly reports coverage.
FNV traces supplement, rather than replace, full LibHac/SHA-256 validation.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path


def reads(path):
    result = defaultdict(set)
    count = 0
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split('\t')
        if len(fields) != 6:
            raise ValueError(f'{path}:{number}: expected DM_FSLOG_HASH trace')
        _, name, offset, length, _, digest = fields
        if not name.startswith('rom:'):
            continue
        if len(digest) != 16 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError(f'{path}:{number}: invalid FNV-1a hash')
        result[(name, int(offset), int(length))].add(digest)
        count += 1
    return result, count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nsp', type=Path)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    a, na = reads(args.nsp)
    b, nb = reads(args.directory)
    shared = a.keys() & b.keys()
    mismatches = [list(k) for k in sorted(shared) if a[k] != b[k]]
    inconsistent = [list(k) for k in sorted(a.keys() | b.keys())
                    if len(a.get(k, ())) > 1 or len(b.get(k, ())) > 1]
    report = dict(nsp_records=na, directory_records=nb,
                  shared_unique_requests=len(shared),
                  nsp_only_unique_requests=len(a.keys() - b.keys()),
                  directory_only_unique_requests=len(b.keys() - a.keys()),
                  mismatches=mismatches, inconsistent_reads=inconsistent,
                  hash='FNV-1a-64; full-file SHA-256 checked separately')
    with args.output.open('x') as output:
        json.dump(report, output, indent=2)
        output.write('\n')
    print(json.dumps(report))
    return int(not shared or bool(mismatches) or bool(inconsistent))


if __name__ == '__main__':
    raise SystemExit(main())
