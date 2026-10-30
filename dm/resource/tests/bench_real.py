"""Explicit, read-only I/O benchmark for the external-resource reader.

Compares the same byte ranges through the container (AES-CTR + IVFC verified)
and through the raw container file (pread ceiling, no decryption), and against
an extracted directory when one is supplied. Records go only to --output.
"""
import argparse
from pathlib import Path
import random
import statistics
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from tools.nxrom.resourcefs import ResourceFS, build_library

p = argparse.ArgumentParser()
p.add_argument('--library', type=Path, required=True)
p.add_argument('--base', type=Path, required=True, help='an NSP or XCI base')
p.add_argument('--keys', type=Path, required=True)
p.add_argument('--title', required=True)
p.add_argument('--directory', type=Path, help='an extracted RomFS tree to compare')
p.add_argument('--file', required=True, help='a large file inside the mount')
p.add_argument('--bytes', type=int, default=335544320, help='sequential bytes to read')
p.add_argument('--random-count', type=int, default=200)
p.add_argument('--random-size', type=int, default=65536)
a = p.parse_args()


def sequential(stream, limit):
    total = 0
    start = time.perf_counter()
    while total < limit:
        block = stream.read(min(1 << 20, limit - total))
        if not block:
            break
        total += len(block)
    return total, time.perf_counter() - start


def random_reads(open_file, size, count, chunk, rng):
    offsets = [rng.randrange(size - chunk) for _ in range(count)]
    start = time.perf_counter()
    times = []
    for offset in offsets:
        t = time.perf_counter()
        open_file.seek(offset)
        if len(open_file.read(chunk)) != chunk:
            raise SystemExit('short read')
        times.append(time.perf_counter() - t)
    elapsed = time.perf_counter() - start
    times.sort()
    return {'mean_ms': 1000 * statistics.mean(times),
            'p50_ms': 1000 * times[len(times) // 2],
            'p99_ms': 1000 * times[min(len(times) - 1, round(0.99 * len(times)))],
            'wall_s': elapsed}


mount_start = time.perf_counter()
fs = ResourceFS(a.library, base=a.base, keys=a.keys, title=int(a.title, 16))
mount_seconds = time.perf_counter() - mount_start
entry = fs.stat(a.file)
size = entry.size
rng = random.Random(7)
print(f'mount: {mount_seconds:.3f}s  {a.file}: {size} bytes')

with fs.open(a.file, buffering=0) as stream:
    total, seconds = sequential(stream, min(a.bytes, size))
print(f'container sequential: {total / seconds / 1048576:.0f} MiB/s ({total} bytes in {seconds:.3f}s)')

with a.base.open('rb') as raw:  # the physical ceiling: same drive, no crypto
    total, seconds = sequential(raw, min(a.bytes, size))
print(f'raw file sequential:  {total / seconds / 1048576:.0f} MiB/s ({total} bytes in {seconds:.3f}s)')

with fs.open(a.file, buffering=0) as stream:
    stats = random_reads(stream, size, a.random_count, a.random_size, rng)
print(f'container random {a.random_size // 1024}KiB x{a.random_count}: '
      f'mean {stats["mean_ms"]:.3f}ms p50 {stats["p50_ms"]:.3f}ms p99 {stats["p99_ms"]:.3f}ms wall {stats["wall_s"]:.3f}s')

if a.directory:
    with ResourceFS(a.library, directory=a.directory) as tree:
        same = tree.stat(a.file)
        if same.size != size:
            raise SystemExit(f'directory file size differs: {same.size}')
        with tree.open(a.file, buffering=0) as stream:
            total, seconds = sequential(stream, min(a.bytes, size))
        print(f'directory sequential: {total / seconds / 1048576:.0f} MiB/s ({total} bytes in {seconds:.3f}s)')
        with tree.open(a.file, buffering=0) as stream:
            stats = random_reads(stream, size, a.random_count, a.random_size, rng)
        print(f'directory random {a.random_size // 1024}KiB x{a.random_count}: '
              f'mean {stats["mean_ms"]:.3f}ms p50 {stats["p50_ms"]:.3f}ms p99 {stats["p99_ms"]:.3f}ms wall {stats["wall_s"]:.3f}s')
fs.close()
