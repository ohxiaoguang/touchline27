# Metal buffer indices of a translated shader, in one place so two bindings cannot land on one index.
#
# Metal reserves a buffer location per function: an entry point that declares [[buffer(13)]] twice does not compile
# ("cannot reserve 'buffer' resource location at index 13"). Five tools each spell out the bindings a vertex shader
# carries, and each used to choose its own constant:
#
#     0        the argument buffer (spirv-cross: constant spvDescriptorSetBuffer0& spvDescriptorSet0 [[buffer(0)]])
#     1..12    vertex conversion staging (nvn_mtl.m vconv_bind, chosen per pipeline out of the free indices)
#     8..11    transform feedback buffers 0..3 (dmsh_build.py vs_tf, TF_SLOT)
#     12       the indirect-read pool (dmsh_ptrfix.py POOL_SLOT)
#     13       the indirect-read base (dmsh_ptrfix.py SLOT)
#     13       the geometry capture record (dmsh_geometry.py CAPTURE_SLOT)
#     14..29   vertex streams 0..13 (and 14 / 15 for streams 14 and 15; nvn_mtl.m VB_SLOT)
#     30       the zero buffer that every shadow vertex input reads (nvn_mtl.m ZERO_ATTR)
#
# FIFA 23's skinned shadow vertex shaders - 862235caa035b230 and a1feb9dd02bc6e19 - are both of the two things that
# wanted 13. dmsh_ptrfix rewrote their unresolved indirect reads onto 12 and 13; dmsh_geometry appends a capture entry
# point that copies main0's parameter list, [[buffer(13)]] among it, and then adds its own binding at 13. main0_gs is
# the only function holding both, so only it failed to compile; main0 and main0_z of the same shaders were fine.
#
# The allocation therefore cannot be a constant per tool. plan() derives it from the features a shader actually has -
# never from its key or its game - the reflection records what it chose (geometry_capture_slot, ptrfix.slot,
# ptrfix.pool_slot), and the runtime binds what the reflection says instead of repeating the numbers.
#
# Two ranges cannot move: 14..30 belong to the vertex descriptor, and an Apple GPU exposes 31 buffer entries (0..30),
# so an auxiliary binding has to share the low block with the conversion staging. The conversion staging is the only
# range the build cannot see, because which attributes need conversion depends on the pipeline's formats: it takes the
# complement of the plan instead (nvn_mtl.m vconv_slot), which is also what keeps it off the transform feedback
# buffers - at 8..11 it used to overwrite a feedback buffer of a shader with that many conversions.
import json
import os
import re

ARG = 0                                      # the argument buffer spirv-cross emits for every stage
VCONV_FIRST, VCONV_LAST = 1, 12              # conversion staging: nvn_mtl.m VCONV_SLOT0 / VCONV_MAX
TF_FIRST, TF_COUNT = 8, 4                    # transform feedback buffers 0..3: dmsh_build.py TF_SLOT
PF_POOL, PF_BASE = 12, 13                    # indirect-read pool and base: dmsh_ptrfix.py
CAPTURE_FIRST = 13                           # the capture record's historical index; plan() moves it when it is taken
STREAM_FIRST, STREAM_LAST = 14, 29           # vertex streams: nvn_mtl.m VB_SLOT(st)
ZERO = 30                                    # the zero buffer a shadow vertex input reads (nvn_mtl.m ZERO_ATTR)
LAST = ZERO                                  # an Apple GPU exposes 31 buffer entries, 0..30


def plan(ptrfix, tf):
    """{'capture': n, 'ptrfix_base': n, 'ptrfix_pool': n, 'tf': [n, ..]} for one vertex shader.
    Deterministic in (ptrfix, tf) alone, so the build and its reflection describe the same function and the runtime
    never guesses. The capture record keeps 13 (its index before this plan existed) unless the indirect-read bindings
    need it; then it takes the highest free index below the transform feedback range, so the conversion staging keeps
    its contiguous low block."""
    slots, taken = {}, set()
    if ptrfix:
        slots['ptrfix_pool'], slots['ptrfix_base'] = PF_POOL, PF_BASE
        taken |= {PF_POOL, PF_BASE}
    if tf:
        taken |= set(range(TF_FIRST, TF_FIRST + TF_COUNT))
    for s in [CAPTURE_FIRST] + list(range(TF_FIRST - 1, VCONV_FIRST - 1, -1)):
        if s not in taken:
            slots['capture'] = s
            break
    else:
        raise ValueError('no free Metal buffer index for the geometry capture record')
    slots['tf'] = [TF_FIRST + b for b in range(TF_COUNT)] if tf else []
    return slots


# --- the check: one entry point may not declare a buffer index twice -------------------------------------------------
ENTRY = re.compile(r'\b(?:vertex|fragment|kernel)\s+[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\(')
BUF = re.compile(r'buffer\((\d+)\)')


def entries(msl):
    """[(entry point name, [buffer index per parameter])] in source order. Comments are dropped first: the translated
    source quotes bindings in its comments (dmsh_fetch.py cuts at a signature it found that way)."""
    src = re.sub(r'//[^\n]*', '', re.sub(r'/\*.*?\*/', '', msl, flags=re.S))
    out = []
    for m in ENTRY.finditer(src):
        depth, i = 1, m.end()
        while i < len(src) and depth:
            depth += src[i] == '('
            depth -= src[i] == ')'
            i += 1
        out.append((m.group(1), [int(x) for x in BUF.findall(src[m.end():i])]))
    return out


def conflicts(msl):
    """[(entry point, index)] for every buffer index one entry point declares more than once. Empty is the contract."""
    bad = []
    for name, idx in entries(msl):
        seen = set()
        for i in idx:
            if i in seen:
                bad.append((name, i))
            seen.add(i)
    return bad


def check_library(d):
    """[finding] for a library directory b-<V>: a duplicate buffer index in any generated MSL, and a vertex shader
    whose reflection does not name the slot its capture entry point reads. Both are what a mismatch between the tools
    looks like after the fact, so a build directory can be audited as a whole."""
    out = []
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        try:
            if n.endswith('_b.metal'):
                with open(p, encoding='utf-8', errors='replace') as f:
                    for name, i in conflicts(f.read()):
                        out.append(f'{n}: entry {name} declares buffer({i}) more than once')
            elif n.endswith('_b.json'):
                with open(p, encoding='utf-8', errors='replace') as f:
                    j = json.load(f)
                if isinstance(j, dict) and j.get('entry_geometry_capture') and 'geometry_capture_slot' not in j:
                    out.append(f'{n}: capture entry {j["entry_geometry_capture"]} has no geometry_capture_slot')
        except (OSError, ValueError) as e:
            out.append(f'{n}: {e}')
    return out


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        findings = check_library(sys.argv[1])
        for f in findings:
            print('[RED] ' + f)
        print(f'{sys.argv[1]}: {len(findings)} slot finding(s)'
              + ('' if findings else f'; {len([n for n in os.listdir(sys.argv[1]) if n.endswith("_b.metal")])} MSL files, every entry point has unique buffer indices'))
        sys.exit(1 if findings else 0)
    for pf in (False, True):
        for tf in (False, True):
            p = plan(pf, tf)
            print(f'ptrfix={"on " if pf else "off"} tf={"on " if tf else "off"}: capture {p["capture"]}, '
                  f'ptrfix base {p.get("ptrfix_base", "-")} pool {p.get("ptrfix_pool", "-")}, tf {p["tf"] or "-"}')
