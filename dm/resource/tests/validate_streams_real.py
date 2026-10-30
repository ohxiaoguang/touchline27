"""Read-only comparison of Python resource streams with an existing extraction.

No resource files are generated; --output is a small, exclusively created JSON
report. Pass paths explicitly. This tool never searches for games or keys.
"""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.nxrom.resourcefs import ResourceFS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('library', 'base', 'keys', 'directory', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--update', type=Path)
    p.add_argument('--title', type=lambda x: int(x, 16), required=True)
    a = p.parse_args()
    if a.output.exists():
        p.error('output already exists; choose a new report path')
    def listing(fs):
        entries, pending = {}, ['']
        while pending:
            for entry in fs.iterdir(pending.pop()):
                entries[entry.path] = (entry.is_dir, entry.size)
                if entry.is_dir: pending.append(entry.path)
        return entries
    with ResourceFS(a.library, base=a.base, update=a.update, keys=a.keys, title=a.title) as fs, \
            ResourceFS(a.library, directory=a.directory) as oracle:
        actual, expected = listing(fs), listing(oracle)
        if actual != expected:
            raise ValueError('directory/type/size listing differs from the supplied extraction')
        files = sorted(path for path, (is_dir, _) in actual.items() if not is_dir)
        rng = random.Random(20261023)
        selected = sorted(set(rng.sample(files, min(64, len(files)))) |
                          set(sorted(files, key=lambda x: actual[x][1], reverse=True)[:8]))
        digest, requests, total = hashlib.sha256(), 0, 0
        for path in selected:
            size = actual[path][1]
            offsets = (0, min(4093, size), rng.randrange(size + 1), max(0, size - 17), size + 1)
            with fs.open(path) as stream, oracle.open(path) as reference:
                for offset in offsets:
                    stream.seek(offset); reference.seek(offset)
                    data, wanted = stream.read(65537), reference.read(65537)
                    if data != wanted:
                        raise ValueError('resource stream mismatch: ' + path + ' at ' + str(offset))
                    digest.update(path.encode() + b'\0' + str(offset).encode() + b'\0' + data)
                    requests += 1; total += len(data)
        report = {'entries': len(actual), 'files': len(files), 'sampled_files': len(selected),
                  'requests': requests, 'compared_bytes': total, 'sample_sha256': digest.hexdigest(),
                  'metadata_match': True, 'range_bytes_match': True, 'update': a.update is not None}
    with a.output.open('x') as output:
        json.dump(report, output, indent=2); output.write('\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
