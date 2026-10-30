# Indirect GPU pointer reads (the PTRFIX rule of the route-B build).
#
# A vertex shader that loads a 64-bit GPU address from memory and dereferences it - FIFA 23's skinned shadow vertex shader,
# a1feb9dd02bc6e19 - reaches Ryujinx's GlobalToStorage pass as a load with StorageKind.GlobalMemory. The pass rewrites the
# load into a call to a synthesized function that indexes the storage buffer by the whole address; its body is generated
# only when the address can be traced back to a constant-buffer base (FindUniqueBaseAddressCb). An address loaded from a
# storage buffer has no such base: TryGenerateMultiTargetStorageOp collects no target, and with targetCbs.Count == 0 it
# logs that failure - to an ILogger whose default implementation is empty, so silently - and still emits the function,
# now with an empty body. The shader reads 0 for every element of every bone matrix, all vertices of a skinned mesh
# collapse onto the instance translation, and the shadow mask the game projects onto the pitch stays empty.
#
# Signature of exactly that path (the other two exits of the pass look different): two int arguments, a name, and a body
# of "return 0". One argument per half of the 64-bit address (GenerateCallStorageOp with offset == null).
#
# The rewrite gives the function the base it lacks. The address and the buffer that holds it live inside one MTLBuffer -
# measured over 12615 historical draws. A later stage-transition capture also found valid bone pointers BEFORE the
# instance binding (28 instances in two draws), so using that binding as the lower bound rejects real data. Bind the
# complete backing pool separately for indirect reads; ordinary vp_s0 accesses retain their original origin. A second
# binding supplies the pool's guest base and byte length.
#
# Both indices come from the shader's slot plan (dmsh_slots.py), not from constants here: the geometry capture entry
# point carries main0's parameters and adds a binding of its own, so whichever of the two runs second has to take what is
# still free, and the reflection records the result for the host. Neither index lands on the argument buffer (0), the
# transform feedback buffers (8-11) or the vertex streams (14-30). No CPU read of GPU-generated pointer contents is used.
# Every four-byte read must fit inside the pool. A failed mapping still returns zero.
#
# Used by dmsh_build.py (finish, vertex shaders); the reflection records {"slot", "pool_slot", "helpers", "reads"} and
# nvn_mtl.m binds the base from it. dmsh_chain.py hashes this file, so a change here changes the chain version.
import re

import dmsh_slots

SLOT = dmsh_slots.PF_BASE       # runtime pool base and length (the plan may move it; the reflection says where)
POOL_SLOT = dmsh_slots.PF_POOL  # complete backing buffer for indirect reads only
MAX_OFF = 0x80000000    # offset bound: keeps the uint index positive and inside any pool

DESC = 'spvDescriptorSetBuffer0'
# the storage buffer the addresses are relative to: the shader's device-pointer bindings, vp_s0 first
SBUF = re.compile(r'\n    const device (\w+)\* (vp_s\w+) \[\[id\(\d+\)\]\];')
# the synthesized function of GenerateCallStorageOp: two halves of an address, empty body
HELPER = re.compile(r'\nstatic inline __attribute__\(\(always_inline\)\)\nint (\w+)\(thread const int& (\w+), thread const int& (\w+)\)\n\{\n    return 0;\n\}\n')
STRUCT = """struct dm_ptrfix
{
    ulong base;
    ulong limit;
};
"""


def body(name, buf, lo, hi):
    """The read the pass meant to emit: the absolute address as an offset into the binding's own buffer"""
    return f"""
static inline __attribute__((always_inline))
int {name}(thread const int& {lo}, thread const int& {hi}, {buf} _pf_s0, dm_ptrfix _pf_b)
{{
    if (_pf_b.base == 0ul)
    {{
        return 0;
    }}
    ulong _pf_a = (ulong(uint({hi})) << 32) | ulong(uint({lo}));
    ulong _pf_off = _pf_a - _pf_b.base;
    if (_pf_b.limit < 4ul || _pf_off > _pf_b.limit - 4ul || _pf_off >= {MAX_OFF:#x}ul)
    {{
        return 0;
    }}
    return as_type<int>(_pf_s0->_m0[int(_pf_off >> 2)]);
}}
"""


def wanted(msl, stage):
    """Whether apply() will add its two bindings to this source. The build asks before it generates the geometry
    capture entry point: that entry point inherits main0's parameters, so the capture record has to be given an index
    that these two will not take (dmsh_slots.plan). Same tests as apply(), in the same order."""
    if stage != 'vs' or not HELPER.search(msl) or not SBUF.search(msl):
        return False
    return len(set(re.findall(r'constant ' + DESC + r'& (\w+) \[\[buffer\(0\)\]\]', msl))) == 1


def apply(msl, stage, slots=None):
    """(new MSL, info) for a vertex shader with unresolved indirect reads; (msl, None) when there is nothing to do.
    info is what the reflection records and the host binds. slots is the shader's plan (dmsh_slots.plan); without one
    the indirect-read bindings take their own fixed indices and no capture record is in the way. A plan that puts a
    second purpose on one of these indices is taken as given: the build checks the source it produced with
    dmsh_slots.conflicts before compiling it."""
    found = HELPER.findall(msl)
    if not found:
        return msl, None
    if stage != 'vs':
        return msl, {'unresolved': len(found), 'applied': False, 'why': 'only vertex shaders have the base slot wired'}   # reported by the build
    m = SBUF.search(msl)
    if not m:
        return msl, {'unresolved': len(found), 'applied': False, 'why': 'no storage buffer binding to take the base from'}
    slots = slots or dmsh_slots.plan(ptrfix=True, tf=False)
    base, pool = slots['ptrfix_base'], slots['ptrfix_pool']
    buf = 'const device %s*' % m.group(1)
    i = msl.index('\nstruct ' + DESC)
    msl = msl[:i] + '\n' + STRUCT + msl[i:]
    for name, lo, hi in found: msl = msl.replace(
        f'\nstatic inline __attribute__((always_inline))\nint {name}(thread const int& {lo}, thread const int& {hi})\n{{\n    return 0;\n}}\n',
        body(name, buf, lo, hi), 1)
    # entry points: the base binding, and the two values read once
    msl, n_entries = re.subn(r'(constant ' + DESC + r'& spvDescriptorSet\w+ \[\[buffer\(0\)\]\][^\n]*)\)\n\{\n',
                             r'\1, constant dm_ptrfix* _pf [[buffer(%d)]], %s _pf_pool [[buffer(%d)]])\n{\n    dm_ptrfix _pf_b = *_pf;\n' % (base, buf, pool), msl)
    descs = set(re.findall(r'constant ' + DESC + r'& (\w+) \[\[buffer\(0\)\]\]', msl))
    if len(descs) != 1:
        return msl, {'unresolved': len(found), 'applied': False, 'why': 'the entry points name their argument buffer differently: %s' % sorted(descs)}
    s0 = '_pf_pool'  # the original descriptor pointer still addresses instance data
    for name, lo, hi in found:
        msl = re.sub(r'\b%s\((_\w+), (_\w+)\)' % name, r'%s(\1, \2, %s, _pf_b)' % (name, s0), msl)
    reads = msl.count(', _pf_b)')
    return msl, {'applied': True, 'slot': base, 'pool_slot': pool, 'buffer': m.group(2), 'helpers': [n for n, _, _ in found], 'reads': reads, 'entries': n_entries}
