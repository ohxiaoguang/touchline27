"""Expand indexed c2 texture tables; separate sampler remains a fixed binding."""
import re

CAPACITY = 0x568 // 8  # Combined handles plus the separate-texture table, not sampler words.


def apply(src):
    body = re.search(r'struct spvDescriptorSetBuffer0\s*\{(.*?)\};', src, re.S)
    if not body: return src
    member = re.compile(r'(?m)^(\s*)(.+?)\s+(\w+)\s*\[\[id\((\d+)\)\]\];')
    members = list(member.finditer(body[1])); selected = set()
    for m in members:
        match = re.fullmatch(r'[a-z]+_t\w*?_cb196610_([0-9A-F]+)', m[3])
        if not match or not m[2].startswith('array<texture'): continue
        h = int(match[1], 16)
        if h >> 28 == 1 and h & 0x3fff == 0 and ((h >> 14) & 0x3fff) * 4 >= 0x568:
            selected.add(m[3])
    if not selected: return src
    for name in selected:
        indices = re.findall(re.escape(name) + r'\[(_\d+)\]', src)
        for index in set(indices):
            alias = re.search(r'\bint\s+' + index + r'\s*=\s*int\((_[0-9]+)\);', src)
            clamp = alias[1] if alias else index
            pat = re.compile(r'(\buint\s+' + clamp + r'\s*=\s*min\([^;]+,\s*)31u(\);)')
            if not pat.search(src): raise ValueError('unrecognized c2 array index clamp: ' + index)
            src = pat.sub(lambda m: m[1] + str(CAPACITY - 1) + 'u' + m[2], src)
        # The sampler's handle is constant even though SPIRV-Cross emits an array.
        src = re.sub(re.escape(name + 'Smplr') + r'\[(_\d+)\]', name + 'Smplr', src)
    body = re.search(r'struct spvDescriptorSetBuffer0\s*\{(.*?)\};', src, re.S)
    shift = 0; declarations = {}
    for m in member.finditer(body[1]):
        ty, name, aid = m[2], m[3], int(m[4]); delta = 0
        if name in selected:
            ty = re.sub(r',\s*32>$', ', ' + str(CAPACITY) + '>', ty); delta = CAPACITY - 32
        elif name.endswith('Smplr') and name[:-5] in selected:
            ty = 'sampler'; delta = 1 - 32
        declarations[name] = f'{m[1]}{ty} {name} [[id({aid + shift})]];'; shift += delta
    new = member.sub(lambda m: declarations[m[3]], body[1])
    return src[:body.start(1)] + new + src[body.end(1):]
