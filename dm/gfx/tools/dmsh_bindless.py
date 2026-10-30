"""Lower Ryujinx Direct handle arrays to Metal descriptor-pool arrays.

Direct handles carry pool IDs, including when loaded through a vertex varying.
They must not index the command buffer's bound texture slots. Only resource
declarations and the clamps feeding those arrays are changed; no shader keys
or game-specific coordinates are used.
"""
import re

POOL_CAPACITY = 16384  # A bounded offline specialization; reflected and checked by the host.
SAMPLER_CAPACITY = 4096
_MEMBER = re.compile(r'(?m)^(\s*)(.+?)\s+(\w+)\s*\[\[id\((\d+)\)\]\];')
_ARRAY = re.compile(r'array<(.+),\s*(\d+)>$')


def apply(source):
    body = re.search(r'struct spvDescriptorSetBuffer0\s*\{(.*?)\};', source, re.S)
    if not body:
        return source, False
    members = list(_MEMBER.finditer(body.group(1)))
    direct = [m for m in members if m[3].endswith('_cb0_40000000')]
    if not direct:
        return source, False
    replacements = {}
    for m in direct:
        array = _ARRAY.fullmatch(m[2])
        if not array:
            raise ValueError(f'Direct handle resource {m[3]} is not an array')
        old_count = int(array[2])
        if old_count != 32:
            raise ValueError(f'Direct handle resource {m[3]}: unexpected source capacity {old_count}')
        # Follow the index used by this resource to its SSA definition. Never
        # replace unrelated min(..., 31) expressions in the shader.
        indices = re.findall(r'\b' + re.escape(m[3]) + r'\[int\((_[0-9]+)\)\]', source)
        if not indices:
            raise ValueError(f'Direct handle resource {m[3]} has no recognized index')
        for index in set(indices):
            pattern = re.compile(r'(\buint\s+' + re.escape(index) + r'\s*=\s*min\([^;]+,\s*)31u(\);)')
            if not pattern.search(source):
                raise ValueError(f'Direct handle resource {m[3]}: unrecognized clamp for {index}')
            replacements[index] = (pattern, SAMPLER_CAPACITY if array[1] == 'sampler' else POOL_CAPACITY)
    for pattern, capacity in replacements.values():
        source = pattern.sub(lambda m: m[1] + str(capacity - 1) + 'u' + m[2], source)
    # Argument-buffer IDs count array elements. Expand each Direct member and
    # move every subsequent member, including ordinary fixed bindings.
    shift = 0
    declarations = {}
    for m in sorted(members, key=lambda m: int(m[4])):
        ty, name, aid = m[2], m[3], int(m[4])
        delta = 0
        if name.endswith('_cb0_40000000'):
            a = _ARRAY.fullmatch(ty)
            capacity = SAMPLER_CAPACITY if a[1] == 'sampler' else POOL_CAPACITY
            ty = f'array<{a[1]}, {capacity}>'
            delta = capacity - int(a[2])
        declarations[name] = f'{m[1]}{ty} {name} [[id({aid + shift})]];'
        shift += delta
    body = re.search(r'struct spvDescriptorSetBuffer0\s*\{(.*?)\};', source, re.S)
    new_body = _MEMBER.sub(lambda m: declarations[m[3]], body[1])
    source = source[:body.start(1)] + new_body + source[body.end(1):]
    return source, True
