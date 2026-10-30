#!/usr/bin/env python3
# OpenGL games' GLSL shaders → one Metal library + a table for the host's GL layer (dm/gfx/gl/hle_gl.m). Digimon Story Cyber Sleuth: Complete Edition renders with
# NVIDIA's desktop GL through EGL and compiles GLSL ES 3.20 source at run time (glShaderSource / glCompileShader); the host finds each shader again by the hash of its source.
# Sources, all searched in every input path:
#   · MVGL archives (*.mvgl, dm/gfx/tools/mvgl.py): every .shad file, named <material>_vp / <material>_fp (1,682 files, 615 distinct sources in Digimon);
#   · an NSO (a file that starts with NSO0, the game's main): every string that holds a shader and begins with a '#version' line (its built-in post effects, movie and shadow
#     shaders; Darkest Dungeon's begin with a newline, see nso_strings);
#   · capture folders (the Mac host's DM_GL_CAPTURE): <key>.vert / <key>.frag, what the game really compiled, for sources it puts together at run time;
#   · *.glsl files in the stages of the Darkest Dungeon layout (darkest_sections): one file holds both stages, between '//##Vertex//' / '//##Fragment//' markers and a
#     closing '//####'. The game hands glShaderSource the section from its marker up to the fifth character of that closer, with each '#line ....' filled in as
#     '#line <n>' (n = the line number the following line has in the file); the reader writes exactly those bytes, so its keys are the ones the game asks for.
# Per shader:
#   · key = sha256(the source text up to its first NUL)[:16] (hex), as the host hashes the strings glShaderSource gets; the Metal function is gl_<key>_v or gl_<key>_f;
#     the key is always the ORIGINAL source, whatever fixups the translation needs;
#   · the stage: a capture's extension, an archive file's _vp / _fp; a string in main says nothing of its stage, so it is translated as each stage that compiles (one of
#     Digimon's built-in fragment shaders names gl_Position in a #define);
#   · GLSL → SPIR-V with glslang (-V -R: relaxed Vulkan rules, which gather the loose uniforms into one block, gl_DefaultUniformBlock; --aml / --amb number the inputs,
#     outputs and bindings), SPIR-V → MSL with spirv-cross (--msl-decoration-binding: Metal slots = those bindings; vertex shaders --fixup-clipspace: GL's z from −w to w → 0 to w);
#   · varyings are matched by name, as GL links them: --aml numbers each stage's outputs in its own declaration order, so [[user(locnN)]] becomes [[user(<variable name>)]];
#   · the host renders in GL's orientation (row 0 at the bottom, the NVN layer's lower-left origin), so nothing is flipped here.
# GLSL 1.00–1.20 sources (every one of Darkest Dungeon's is #version 120) go through legacy() first: glslang's Vulkan front end refuses anything below 140.
# Output: <out>/gl/gl_shaders.metallib and <out>/gl/gl_shaders.tsv; --ios <dir> also writes <dir>/gl/ with an iPhone library (same table)
# Table rows: key <TAB> stage (vert / frag) <TAB> fields, space-separated (a key can have a row per stage):
#   a:<name>=<slot>:<type>                       a vertex input, [[attribute(slot)]]
#   u:<name>=<offset>:<type>:<count>:<stride>    a member of the default uniform block (count 0 = not an array)
#   b:<slot>:<size>                              the default uniform block: its buffer slot and size in bytes
#   t:<name>=<slot>:<type>                       a combined sampler: texture and sampler slot
#   s:<name>=<unit>                              the sampler's initial GL texture unit, when its declaration gives one (layout(binding = unit))
#   o:<name>=<location>                          a fragment output, [[color(location)]]
# <TAB> where it came from
# Usage: gl_shaders.py <input path>... <out dir> [--ios <dir>]   (input paths: the RomFS, the main NSO, capture folders)
import concurrent.futures as cf, hashlib, json, os, re, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mvgl
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'tools'))
import nsoseg

VEC_TYPES = {'float', 'vec2', 'vec3', 'vec4', 'int', 'ivec2', 'ivec3', 'ivec4', 'uint', 'uvec2', 'uvec3', 'uvec4', 'bool', 'mat2', 'mat3', 'mat4'}

def red(msg): sys.exit('[RED] ' + msg)

def text_of(b):
    b = bytes(b); z = b.find(b'\0')
    return b[:z] if z >= 0 else b

def nso_strings(path):
    """The GLSL sources an NSO's read-only segment holds as C strings (lz4 segments, as dm/tools/nso.py decompresses them): every 'void main' body that begins with a '#version' line. A
    main that links glslang (Balatro's LÖVE) also has its messages that start with '#version:' — those have no 'void main' and are dropped.

    Where the source's first byte may be either the '#version' itself or the newline that opens the literal (Darkest Dungeon's engine writes `"\\n#version 120\\n\\n..."`), both readings are
    offered: the host hashes the bytes glShaderSource was given, so the leading newline is part of the key when the game passes it, and only a capture says which. Offering both keeps the
    right one in the library (the other is one unused entry). The literal need not start at a NUL — the compiler packs the strings together, one of Darkest Dungeon's follows a float
    array's last byte with no terminator before it — so '#version' is searched anywhere and the source runs to the next NUL."""
    d = open(path, 'rb').read()
    img = nsoseg.decode(d, nsoseg.parse(d), 1)
    out, seen = [], set()
    for m in re.finditer(rb'#version\s+\d', img):
        starts = [m.start()]
        if m.start() > 0 and img[m.start() - 1:m.start()] == b'\n': starts.insert(0, m.start() - 1)
        for s in starts:
            t = text_of(img[s:s + 0x10000])
            if t in seen or b'void main' not in t: continue   # a message or a stray fragment, not a shader
            seen.add(t); out.append(t)
    return out

DD_MARKS = (('vert', b'//##Vertex//'), ('frag', b'//##Fragment//'))

def darkest_sections(raw):
    """[(source bytes, stage)] of a Darkest Dungeon *.glsl file: both stages in one file, each from its '//##Vertex//' / '//##Fragment//' marker to the '//####' that closes it.
    The game hands glShaderSource the marker line on, ending with the closer's first five characters, and fills each '#line ....' with '#line <n>' where n is the line number
    the following line has in the file ('#line 10  ' for a '#version 120' on line 8, then the blank line 10). Reproduced byte for byte: all 28 captures of this game's shaders
    that come from the 18 files hash to what this returns (the other 6 are strings in main)."""
    out = []
    for st, mark in DD_MARKS:
        i = raw.find(mark)
        if i < 0: continue
        j = raw.find(b'//####', i + len(mark))
        if j < 0: raise ValueError(f'{st} section: no //#### closes the //##{st.capitalize()}// marker')
        body = raw[i:j + 5]   # five of the closer's six characters, as the game takes it
        first = raw[:i].count(b'\n') + 1   # the marker's own line number
        lines = body.split(b'\n')
        for k, line in enumerate(lines):
            if line.lstrip().startswith(b'#line ....'):
                lines[k] = line.replace(b'....', b'%-4d' % (first + k + 1))
        out.append((b'\n'.join(lines), st))
    return out

def sources(roots):
    """(source bytes, stage or None, where) for every shader in the input paths"""
    for r in roots:
        if os.path.isfile(r):
            with open(r, 'rb') as f: head = f.read(4)
            if head == b'NSO0':
                for k, s in enumerate(nso_strings(r)): yield s, None, f'{os.path.basename(r)}#{k}'
            continue
        for d, _, fs in os.walk(r):
            for fn in sorted(fs):
                p = os.path.join(d, fn)
                if fn.endswith('.mvgl'):
                    try: a = mvgl.Archive(p)
                    except ValueError: continue   # the sound archives are CRI AFS2 under the same extension
                    for nm in sorted(a.files):
                        if not nm.endswith('.shad'): continue
                        st = 'vert' if nm.endswith('_vp.shad') else 'frag' if nm.endswith('_fp.shad') else None
                        yield text_of(a.read(nm)), st, f'/{os.path.relpath(p, r)}:{nm}'
                elif fn.endswith('.glsl'):
                    raw = open(p, 'rb').read()
                    if not any(m in raw for _, m in DD_MARKS): continue   # another engine's GLSL file: no stage is known for it, so it is left alone
                    for src, st in darkest_sections(raw):
                        yield src, st, '/' + os.path.relpath(p, r)
                elif fn.endswith(('.vert', '.frag')):
                    yield text_of(open(p, 'rb').read()), fn.rsplit('.', 1)[1], '/' + os.path.relpath(p, r)

# NVIDIA's GLSL compiler accepts more than the GLSL ES 3.20 specification, and glslang does not; these fix-ups run on the preprocessed text (glslang -E, so macros are expanded):
#   · the GLSL ES 1.0 texture functions (89 of Digimon's fragment shaders call textureCube; with -V glslang reads textureCube as Vulkan's texture type, so a macro cannot rename it);
#   · a redeclaration of gl_Position as a plain output (the built-in sprite shader of main declares `out float4 vPosition;` with vPosition defined as gl_Position);
#   · textureOffset with an offset that is not a constant (the built-in FXAA shader): Metal's sample offsets are constants too, so it becomes texture at P + offset / level 0 size
OLD_TEX = [(r'\btexture2DLod\s*\(', 'textureLod('), (r'\btextureCubeLod\s*\(', 'textureLod('), (r'\btexture2DProj\s*\(', 'textureProj('),
           (r'\btexture2D\s*\(', 'texture('), (r'\btextureCube\s*\(', 'texture(')]

# ---- GLSL 1.00–1.20 (desktop, no profile qualifiers): the dialect Darkest Dungeon's engine compiles ----
# glslang's Vulkan front end refuses a version below 140, so a legacy source is moved to 140 and its constructs are rewritten. 140 is the first version that has everything the
# rewrite needs — user-declared fragment outputs and no deprecation of `in` / `out` — while still allowing what these sources do:
#   · `#version 120` → `#version 140`;
#   · `attribute` → `in` (vertex only: a fragment source may not declare an attribute, so it is left for glslang to reject with its own message);
#   · `varying` → `out` (vertex) / `in` (fragment). GL links varyings by name and spirv-cross names Metal's user varyings by the same names, so the two stages still pair up;
#   · `gl_FragColor` → a declared `out vec4 dm_fragcolor` (spirv-cross gives it [[color(0)]], the slot gl_FragColor wrote);
#   · `texture3D` → `texture`, `texture2D` / `textureCube` and their Lod / Proj forms through OLD_TEX below (they are 1.20's names; `texture()` is the 1.30 one);
#   · `gl_FragData` and `ftransform()` have no equivalent here and are reported instead of being left to fail somewhere further down.
# What the rewrite does NOT need to touch, because 1.20 and 1.40 agree on it: gl_Position, gl_FragCoord, gl_PointSize, gl_FrontFacing, gl_PointCoord, gl_FragDepth, the `f` suffix on a
# float literal, matrix constructors, `if` / for loops and the built-ins. 1.20's implicit int → float conversion is gone in 140 but no source here relies on it.
# The replacement walks the text token by token and skips comments and string literals, so a mention of `varying` in a comment or a name like `myvarying` is left alone. The one line it
# adds (the fragment output) replaces a blank line of the header when there is one, so the text keeps its line numbers and a glslang error still points into the game's own file.
LEGACY_MAX = 129
LEGACY_TOKEN = re.compile(r'//[^\n]*|/\*(?:[^*]|\*(?!/))*\*/|"(?:\\.|[^"\\])*"'
                          r'|(?P<kw>\battribute\b|\bvarying\b|\bgl_FragColor\b|\bgl_FragData\b|\bftransform\b|\btexture3D\b)')
FRAG_OUT = 'dm_fragcolor'

def legacy(t, stage):
    """(text, None) for a GLSL 1.00–1.20 source moved to 1.40, or (None, error). A source at 130 or later is returned unchanged."""
    m = re.search(r'^[ \t]*#[ \t]*version[ \t]+(\d+)', t, re.M)
    if not m or int(m.group(1)) > LEGACY_MAX: return t, None
    if stage not in ('vert', 'frag'): return None, f'a GLSL {m.group(1)} source needs its stage'
    uses_fragcolor = fragdata = ftransform = False
    def sub(x):
        nonlocal uses_fragcolor, fragdata, ftransform
        k = x.group('kw')
        if not k: return x.group(0)
        if k == 'attribute': return 'in' if stage == 'vert' else x.group(0)
        if k == 'varying': return 'out' if stage == 'vert' else 'in'
        if k == 'texture3D': return 'texture'
        if k == 'gl_FragColor':
            if stage != 'frag': return x.group(0)
            uses_fragcolor = True; return FRAG_OUT
        if k == 'gl_FragData': fragdata = True; return x.group(0)
        ftransform = True; return x.group(0)
    body = LEGACY_TOKEN.sub(sub, t)
    if fragdata: return None, 'gl_FragData is not supported (only gl_FragColor, which is one colour output)'
    if ftransform: return None, 'ftransform() is not supported (the fixed-function matrix stack has no equivalent)'
    # the new version line, then the fragment output's declaration in the header, after the #version / #extension / #line block
    head = body[:m.start()] + re.sub(r'(\d+)', '140', m.group(0), count=1)
    rest = body[m.end():]
    if uses_fragcolor:
        lines = rest.split('\n'); k = 1   # lines[0]: what follows the version line
        while k < len(lines) and (not lines[k].strip() or lines[k].lstrip().startswith('#')): k += 1
        if k > 1 and not lines[k - 1].strip(): lines[k - 1] = f'out vec4 {FRAG_OUT};'   # a blank line of the header: the line numbers stay
        else: lines.insert(k, f'out vec4 {FRAG_OUT};')
        rest = '\n'.join(lines)
    return head + rest, None

def call_args(t, i):
    """the arguments of the call whose '(' is at t[i], and the index after its ')'"""
    depth, args, start = 0, [], i + 1
    for k in range(i, len(t)):
        c = t[k]
        if c == '(': depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0: args.append(t[start:k]); return args, k + 1
        elif c == ',' and depth == 1: args.append(t[start:k]); start = k + 1
    raise ValueError('unbalanced parentheses')

def fixups(t, stage):
    """(text, error): the preprocessed source as glslang -V takes it"""
    t, err = legacy(t, stage)
    if err: return None, err
    for a, b in OLD_TEX: t = re.sub(a, b, t)
    t = re.sub(r'^[ \t]*out\s+(?:highp\s+|mediump\s+|lowp\s+)?vec4\s+gl_Position\s*;', '', t, flags=re.M)
    out, i = [], 0
    for m in re.finditer(r'\btextureOffset\s*\(', t):
        if m.start() < i: continue
        args, end = call_args(t, m.end() - 1)
        if len(args) == 3 and re.search(r'[A-Za-z_]\w*', re.sub(r'\b[iu]?vec[234]\b', '', args[2])):   # an offset with a variable in it
            s_, p_, o_ = (x.strip() for x in args)
            out.append(t[i:m.start()] + f'texture({s_}, ({p_}) + vec2({o_}) / vec2(textureSize({s_}, 0)))'); i = end
    return ''.join(out) + t[i:], None

def glsl_type(t, refl):
    return refl['types'][t]['name'] if t in refl.get('types', {}) else t

def translate(src, stage, key, tmp, where=''):
    """GLSL → MSL; returns (msl path, table fields) or an error string. where names the source, for the error"""
    g = os.path.join(tmp, f'{key}.{stage}'); spv = g + '.spv'; msl = os.path.join(tmp, f'{key}_{stage[0]}.metal')
    open(g + '.in', 'wb').write(src)
    r = subprocess.run(['glslangValidator', '-E', '-S', stage, g + '.in'], capture_output=True, text=True)
    if r.returncode: return 'glslang -E: ' + ' | '.join(l for l in (r.stdout + r.stderr).splitlines() if 'ERROR' in l and 'compilation' not in l)[:400]
    pre = r.stdout[r.stdout.find('#version'):]   # warnings come first
    pp, err = fixups(pre, stage)
    if err: return err
    open(g, 'w').write(pp)
    # DM_GL_SHADER_DUMP=<dir>: keep the text glslang -V was handed, so a failure can be read against the game's own lines (glslang -E keeps them: it drops the '#line' but leaves the line)
    dump = os.environ.get('DM_GL_SHADER_DUMP')
    if dump:
        os.makedirs(dump, exist_ok=True)
        open(os.path.join(dump, f'{key}.{stage}.glsl'), 'w').write(pp)
        open(os.path.join(dump, f'{key}.{stage}.orig'), 'wb').write(src)
    r = subprocess.run(['glslangValidator', '-V', '-R', '--aml', '--amb', '-S', stage, g, '-o', spv], capture_output=True, text=True)
    if r.returncode: return f'glslang -V{(" on " + where) if where else ""}: ' + ' | '.join(l for l in (r.stdout + r.stderr).splitlines() if 'ERROR' in l and 'compilation' not in l)[:400]
    refl = json.loads(subprocess.run(['spirv-cross', spv, '--reflect'], capture_output=True, text=True, check=True).stdout)
    cmd = ['spirv-cross', spv, '--msl', '--msl-version', '20300', '--msl-decoration-binding', '--rename-entry-point', 'main', f'gl_{key}_{stage[0]}', stage, '--output', msl]
    if stage == 'vert': cmd.append('--fixup-clipspace')
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: return 'spirv-cross: ' + r.stderr.strip()[:300]
    m = open(msl).read()
    # Varyings by name: the out struct of a vertex shader and the in struct of a fragment shader (stage_in members of a vertex shader are [[attribute(n)]])
    m = re.sub(r'(\b(\w+)\s+\[\[)user\(locn\d+\)', lambda x: f'{x.group(1)}user({x.group(2)})', m)
    m = re.sub(r'\bfast::(min|max|clamp)\(', r'precise::\1(', m)   # a NaN operand gives the other one, as on the Switch's GPU (vk_shaders.py PRECISE)
    open(msl, 'w').write(m)
    f = []
    if stage == 'vert':
        for v in refl.get('inputs', []): f.append(f'a:{v["name"]}={v["location"]}:{v["type"]}')
    else:
        for v in refl.get('outputs', []): f.append(f'o:{v["name"]}={v["location"]}')
    # a bool uniform is a uint in the SPIR-V block (it has no bool members), but the game asks GL for its declared type: LÖVE's Shader:send takes only a boolean for a GLSL bool
    bools = {n for n in re.findall(r'\buniform\s+(?:(?:lowp|mediump|highp)\s+)?bool\s+(\w+)\s*;', pre)}
    for u in refl.get('ubos', []):
        t = refl['types'][u['type']]
        if t['name'] != 'gl_DefaultUniformBlock': return f'uniform block {t["name"]} is not the default block'
        f.append(f'b:{u["binding"]}:{u["block_size"]}')
        for mb in t['members']:
            arr = mb.get('array', [])
            if len(arr) > 1: return f'uniform {mb["name"]}: arrays of arrays'
            ty = glsl_type(mb['type'], refl)
            if ty == 'uint' and mb['name'] in bools: ty = 'bool'
            if ty not in VEC_TYPES: return f'uniform {mb["name"]}: type {ty} (structs are not implemented)'
            f.append(f'u:{mb["name"]}={mb["offset"]}:{ty}:{arr[0] if arr else 0}:{mb.get("array_stride", 0)}')
    for t in refl.get('textures', []):
        if t.get('array'): return f'sampler array {t["name"]}'
        f.append(f't:{t["name"]}={t["binding"]}:{t["type"]}')
    # A sampler's GL texture unit starts at the binding its declaration gives it (GLSL 4.2's `layout(binding = n)`; without one it starts at 0, as the
    # host's default). A game that never calls glUniform1i for a sampler relies on that initial value: Darkest Dungeon's YUV shader binds its two
    # textures this way ("layout(binding = 0) uniform sampler2D u_textureY", "... binding = 1 ... u_textureUV"), so without the field both samplers
    # read unit 0 and the movie came out as the luma plane only (a cyan-green picture)
    for n, nm in sorted(set(re.findall(r'layout\s*\(\s*binding\s*=\s*(\d+)\s*\)\s*(?:uniform\s+)?(?:(?:lowp|mediump|highp)\s+)?sampler\w+\s+(\w+)', pre))):
        f.append(f's:{nm}={int(n)}')
    for k in ('separate_images', 'separate_samplers', 'images', 'ssbos', 'push_constants'):
        if refl.get(k): return f'{k} are not implemented'
    if any(int(x) > 15 for x in re.findall(r'\[\[(?:sampler|buffer)\((\d+)\)\]\]', m)): return 'a buffer or sampler slot above 15'
    return msl, f

def one(item, tmp):
    """[(key, stage, fields, msl, where)], or [(key, None, errors, None, where)] when no stage translates"""
    src, stage, where = item
    key = hashlib.sha256(src).hexdigest()[:16]
    out, errs = [], []
    for st in [stage] if stage else ['vert', 'frag']:
        r = translate(src, st, key, tmp, where)
        if isinstance(r, tuple): out.append((key, st, r[1], r[0], where))
        else: errs.append(f'{st}: {r}')
    return out or [(key, None, errs, None, where)]

def metallib(msls, out, sdk, extra):
    os.makedirs(out, exist_ok=True)
    def comp(m):
        a = m[:-6] + f'.{sdk}.air'
        r = subprocess.run(['xcrun', '-sdk', sdk, 'metal', '-c', '-fpreserve-invariance', *extra, m, '-o', a], capture_output=True, text=True)
        if r.returncode: red(f'{m}: metal compile failed: {r.stderr.strip()[:400]}')
        return a
    with cf.ThreadPoolExecutor(os.cpu_count()) as ex: airs = list(ex.map(comp, msls))
    lib = os.path.join(out, 'gl_shaders.metallib')
    subprocess.run(['xcrun', '-sdk', sdk, 'metallib', *airs, '-o', lib], check=True)
    return lib

def main():
    a = sys.argv[1:]
    ios = None
    if '--ios' in a: i = a.index('--ios'); ios = a[i + 1]; del a[i:i + 2]
    if len(a) < 2: sys.exit('usage: gl_shaders.py <input path>... <out dir> [--ios <dir>]')
    roots, out = a[:-1], a[-1]
    items, seen_src = [], set()
    for s, st, where in sources(roots):
        if (s, st) in seen_src: continue
        seen_src.add((s, st)); items.append((s, st, where))
    if not items: red(f'no GLSL shaders in {" ".join(roots)}')
    with tempfile.TemporaryDirectory() as tmp:
        with cf.ThreadPoolExecutor(os.cpu_count()) as ex: rows = [r for rs in ex.map(lambda it: one(it, tmp), items) for r in rs]
        seen, failed = {}, []
        for key, stage, f, msl, where in rows:
            if not stage: failed.append((key, where, f)); continue
            if (key, stage) not in seen: seen[(key, stage)] = (stage, f, msl, where)
        for key, where, errs in failed:
            if not any(k == key for k, _ in seen): print(f'[RED] {where} ({key}) does not translate: {" / ".join(errs)}')
        tsv = ['# GL shaders (dm/gfx/tools/gl_shaders.py): key = sha256(GLSL source)[:16], Metal function gl_<key>_v / gl_<key>_f; a: vertex inputs, u: default uniform block members '
               '(offset:type:count:stride), b: the block (slot:size), t: combined samplers (slot:type), s: a sampler\'s initial unit (layout(binding = unit)), o: fragment outputs',
               '# ' + ' '.join(subprocess.run(['glslangValidator', '--version'], capture_output=True, text=True).stdout.split()[:3]) + '; spirv-cross '
               + ' '.join((lambda r: r.stdout + r.stderr)(subprocess.run(['spirv-cross', '--revision'], capture_output=True, text=True)).split())]
        tsv += [f'{k[0]}\t{v[0]}\t{" ".join(v[1])}\t{v[3]}' for k, v in sorted(seen.items())]
        dirs = [(os.path.join(out, 'gl'), 'macosx', [])]
        if ios: dirs.append((os.path.join(ios, 'gl'), 'iphoneos', ['-mios-version-min=18.0', '-fmetal-math-mode=relaxed']))   # relaxed as in vk_shaders.py and ios_metal.py: no NaN / Inf assumption on the iPhone's GPU compiler
        msls = [v[2] for v in seen.values()]
        for d, sdk, extra in dirs:
            lib = metallib(msls, d, sdk, extra)
            open(os.path.join(d, 'gl_shaders.tsv'), 'w').write('\n'.join(tsv) + '\n')
            print(f'{sdk}: {len(seen)} shaders ({sum(1 for v in seen.values() if v[0] == "vert")} vertex) → {lib}' + (f'; {len(failed)} failed' if failed else ''))

if __name__ == '__main__': main()
