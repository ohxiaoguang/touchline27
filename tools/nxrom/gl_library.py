"""Validate the GL table against recorded stages and compiled Metal functions."""
from pathlib import Path
import re
import subprocess


def validate(folder, capture=None):
    folder = Path(folder)
    table, library = folder / 'gl_shaders.tsv', folder / 'gl_shaders.metallib'
    if not table.is_file() or not library.is_file():
        raise ValueError('Missing GL Shader table or metallib: ' + str(folder))
    if table.is_symlink() or library.is_symlink():
        raise ValueError('GL Shader inputs must be regular files')
    pairs = set()
    for line in table.read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        row = line.split('\t')
        if len(row) < 3 or not re.fullmatch('[0-9a-f]{16}', row[0]) or row[1] not in ('vert', 'frag'):
            raise ValueError('Invalid GL Shader table row: ' + line)
        pair = (row[0], row[1])
        if pair in pairs:
            raise ValueError('Duplicate GL Shader key/stage: ' + '.'.join(pair))
        pairs.add(pair)
    if not pairs:
        raise ValueError('Empty GL Shader table')
    if capture is not None:
        capture = Path(capture)
        if not capture.is_file():
            raise ValueError('Missing GL capture inventory: ' + str(capture))
        wanted = set()
        for line in capture.read_text().splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            if not re.fullmatch(r'[0-9a-f]{16}\.(vert|frag)', line):
                raise ValueError('Invalid GL capture entry: ' + line)
            wanted.add(tuple(line.rsplit('.', 1)))
        if not wanted or wanted - pairs:
            raise ValueError('GL Shader table misses captured stages: ' + str(sorted(wanted - pairs)))
    with library.open('rb') as stream:
        if stream.read(4) != b'MTLB' or library.stat().st_size < 32:
            raise ValueError('Invalid GL Shader library: ' + str(library))
    # Read actual compiled symbols; a header or table alone cannot prove coverage.
    result = subprocess.run(['xcrun', 'metal-nm', str(library)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Cannot inspect GL Metal library: ' + result.stderr.strip())
    functions = set(re.findall(r'\bT\s+(gl_[0-9a-f]{16}_[vf])$', result.stdout, re.M))
    expected = {'gl_' + key + ('_v' if stage == 'vert' else '_f') for key, stage in pairs}
    if functions != expected:
        raise ValueError('GL Metal function inventory differs from table; missing=' + str(sorted(expected - functions))
                         + '; extra=' + str(sorted(functions - expected)))
    return dict(shader_count=len(pairs), program_keys=len({key for key, _ in pairs}), functions=len(functions))
