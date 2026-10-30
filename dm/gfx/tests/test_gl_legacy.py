"""GLSL 1.00–1.20 → Metal, and where the Darkest Dungeon sources come from.

The failure this pins down: Darkest Dungeon (SDK 3.6, Red Hook's own engine, OpenGL through EGL) compiles its shaders at
run time from `#version 120` sources — `attribute`, `varying`, `gl_FragColor`, `texture2D`, `texture3D` — and glslang's
Vulkan front end refuses anything below 140, so every one of its 34 captured programs translated to nothing and the host,
which finds a program by the hash of the source it was given, skipped every draw.

Two things have to hold, and they are separate claims: the legacy source must become valid 140 that Metal accepts, and the
key must stay the hash of the ORIGINAL bytes, because that is what glShaderSource was handed and what glCompileShader
hashes (dm/gfx/gl/hle_gl.m). A fix-up that changed the key would compile and still find nothing at run time.

The real game files are not in the repository. What needs them (the 18 files' sections against the 34 captured programs)
runs when DD_BUILD names a build directory; everything else runs on synthetic sources written in the same shapes.
"""
from pathlib import Path
import hashlib
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import gl_shaders

HAVE_TOOLS = bool(shutil.which('glslangValidator') and shutil.which('spirv-cross'))

# The shape of the engine's own shaders: a uniform, two attributes, two varyings, gl_FragColor out of a texture. These are
# the FILES (marker, '#line ....' unfilled, closing //####); VERT / FRAG below are what the game hands glShaderSource, made
# by the reader itself, so every test below works on the bytes the host hashes.
VERT_FILE = '''//##Vertex//---------------------------------------------------------------------------------------
//
#version 120
#line ....

// Transform
uniform mat4 modelviewProjection;
uniform float fade;

attribute vec3 vPosition;		// vertex in
attribute vec4 vColour;
attribute vec2 vTexcoord;

varying vec4 sColour;		// setup (for interpolator) out
varying vec2 sTexcoord;

// Main
void main(void)
{
	sTexcoord	= vTexcoord;
	sColour		= vColour;
	sColour.a	*= fade;
	gl_Position = modelviewProjection * vec4(vPosition, 1.0);
}
//####
'''

FRAG_FILE = '''//##Fragment//-------------------------------------------------------------------------------------
//
#version 120
#line ....

varying vec4 sColour;		// setup (interpolated) in
varying vec2 sTexcoord;

varying vec4 fColour;		// fragment out (declared, never written)

uniform sampler2D Tex0;
uniform float Saturation;

void main(void)
{
	vec4 tex0 = texture2D(Tex0, sTexcoord.st) * sColour;
	float luminance = tex0.r * 0.2126 + tex0.g * 0.7152 + tex0.b * 0.0772;
	vec3 grey = vec3( luminance, luminance, luminance );
	gl_FragColor = vec4( mix( grey, tex0.rgb, Saturation ), tex0.a );
	gl_FragColor.a *= 0.5;
}
//####
'''


def section(text):
    """The one section of a single-marker source: exactly the bytes the game passes for that stage"""
    got = gl_shaders.darkest_sections(text.encode())
    assert len(got) == 1, got
    return got[0][0].decode()


VERT, FRAG = section(VERT_FILE), section(FRAG_FILE)


def key_of(src):
    return hashlib.sha256(src).hexdigest()[:16]


def interface(src, stage):
    """The names a stage declares as its side of the inter-stage interface: the vertex shader's outputs (its attributes
    are its own input, and they arrive as `in` after the rewrite too), the fragment shader's inputs. Both spellings are
    accepted, so the same helper reads a source before and after the rewrite."""
    want = ('out', 'varying') if stage == 'vert' else ('in', 'varying')
    names = []
    for line in src.splitlines():
        f = line.split('//')[0].split(';')[0].split()
        if len(f) == 3 and f[0] in want: names.append(f[2])
    return names


class VertexLegacy(unittest.TestCase):
    def test_moves_version_and_qualifiers(self):
        t, err = gl_shaders.legacy(VERT, 'vert')
        self.assertIsNone(err)
        self.assertIn('#version 140\n', t)
        self.assertNotIn('#version 120', t)
        self.assertNotIn('attribute ', t)
        self.assertNotIn('varying ', t)
        self.assertEqual(['sColour', 'sTexcoord'], interface(t, 'vert'))
        # gl_Position, the uniforms and the body are untouched: 1.20 and 1.40 agree on them
        self.assertIn('gl_Position = modelviewProjection * vec4(vPosition, 1.0);', t)
        self.assertIn('uniform mat4 modelviewProjection;', t)

    def test_declares_no_fragment_output(self):
        t, _ = gl_shaders.legacy(VERT, 'vert')
        self.assertNotIn(gl_shaders.FRAG_OUT, t)

    def test_keeps_line_numbers(self):
        t, _ = gl_shaders.legacy(VERT, 'vert')
        self.assertEqual(t.count('\n'), VERT.count('\n'))


class FragmentLegacy(unittest.TestCase):
    def test_moves_version_and_varying_to_in(self):
        t, err = gl_shaders.legacy(FRAG, 'frag')
        self.assertIsNone(err)
        self.assertIn('#version 140\n', t)
        self.assertEqual(['sColour', 'sTexcoord', 'fColour'], interface(t, 'frag'))
        self.assertIn(f'out vec4 {gl_shaders.FRAG_OUT};', t)

    def test_declares_the_colour_output_exactly_once(self):
        t, _ = gl_shaders.legacy(FRAG, 'frag')
        self.assertEqual(t.count(f'out vec4 {gl_shaders.FRAG_OUT};'), 1)
        self.assertNotIn('gl_FragColor', t)
        self.assertIn(f'{gl_shaders.FRAG_OUT} = vec4( mix( grey, tex0.rgb, Saturation ), tex0.a );', t)
        self.assertIn(f'{gl_shaders.FRAG_OUT}.a *= 0.5;', t)   # a component write, not just the whole value

    def test_output_declaration_lands_in_the_header(self):
        t, _ = gl_shaders.legacy(FRAG, 'frag')
        lines = t.splitlines()
        decl = next(i for i, l in enumerate(lines) if l.startswith('out vec4'))
        first_decl = next(i for i, l in enumerate(lines) if l.startswith('in vec4 sColour'))
        self.assertLess(decl, first_decl, 'the output must be declared before the code that writes it')
        self.assertEqual(t.count('\n'), FRAG.count('\n'), 'the rewrite keeps the line count: glslang errors still point at the file')

    def test_texture_functions_become_texture(self):
        t, err = gl_shaders.fixups(FRAG, 'frag')
        self.assertIsNone(err)
        self.assertNotIn('texture2D', t)
        self.assertIn('texture(Tex0, sTexcoord.st)', t)

    def test_texture3d_becomes_texture(self):
        src = FRAG.replace('uniform sampler2D Tex0;', 'uniform sampler3D Tint;').replace(
            'texture2D(Tex0, sTexcoord.st)', 'texture3D(Tint, vec3(sTexcoord, 0.5))')
        t, err = gl_shaders.legacy(src, 'frag')
        self.assertIsNone(err)
        self.assertIn('texture(Tint, vec3(sTexcoord, 0.5))', t)


class Interface(unittest.TestCase):
    """The two stages must still agree on their varyings: GL links them by name, and spirv-cross names Metal's by the same
    names, so a stage pair that stops matching here draws nothing at run time even though both compile."""

    def test_stages_pair_by_name(self):
        v, _ = gl_shaders.legacy(VERT, 'vert')
        f, _ = gl_shaders.legacy(FRAG, 'frag')
        outs, ins = set(interface(v, 'vert')), set(interface(f, 'frag'))
        self.assertEqual({'sColour', 'sTexcoord'}, outs & ins)
        self.assertEqual({'fColour'}, ins - outs)   # declared but never written: dead in the fragment stage too

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_metal_names_the_varyings_the_same_in_both_stages(self):
        """What actually pairs them at run time: the [[user(...)]] of the vertex stage's out struct and of the fragment
        stage's in struct, which the host's table leaves to the translator."""
        with tempfile.TemporaryDirectory() as tmp:
            v = Path(gl_shaders.one((VERT.encode(), 'vert', '/x'), tmp)[0][3]).read_text()
            f = Path(gl_shaders.one((FRAG.encode(), 'frag', '/x'), tmp)[0][3]).read_text()
        for name in ('sColour', 'sTexcoord'):
            self.assertIn(f'[[user({name})]]', v)
            self.assertIn(f'[[user({name})]]', f)


class RewriteIsTextAware(unittest.TestCase):
    """A comment or a longer identifier that contains a legacy keyword is not a use of it."""

    def test_comments_and_identifiers_are_left_alone(self):
        src = '''#version 120
// a varying attribute written to gl_FragColor is legacy
/* gl_FragColor and texture2D in a block comment */
uniform sampler2D Tex0;
varying vec2 myvarying;		// a name, not a qualifier
varying vec2 sTexcoord;
void main(void)
{
	// gl_FragColor = vec4(1.0);
	gl_FragColor = texture2D(Tex0, sTexcoord);
}
'''
        t, err = gl_shaders.legacy(src, 'frag')
        self.assertIsNone(err)
        self.assertIn('// a varying attribute written to gl_FragColor is legacy', t)
        self.assertIn('/* gl_FragColor and texture2D in a block comment */', t)
        self.assertIn('in vec2 myvarying;', t)               # the qualifier is rewritten, the name is not
        self.assertIn('// gl_FragColor = vec4(1.0);', t)
        self.assertIn(f'{gl_shaders.FRAG_OUT} = texture2D(Tex0, sTexcoord);', t)

    def test_a_modern_source_is_returned_unchanged(self):
        """The regression that matters for every other GL game: 130 and later never reach the rewrite."""
        for src in ('#version 320 es\nprecision highp float;\nvoid main() { }\n',
                    '#version 450\nin vec3 vPos;\nvoid main() { gl_Position = vec4(vPos, 1.0); }\n'):
            self.assertEqual((src, None), gl_shaders.legacy(src, 'frag'))

    def test_a_legacy_source_without_a_stage_is_an_error(self):
        t, err = gl_shaders.legacy(VERT, None)
        self.assertIsNone(t)
        self.assertIn('needs its stage', err)

    def test_floatsuffix_and_matrices_are_kept(self):
        src = '#version 120\nvoid main(void) { gl_Position = vec4(1.0f) * mat4(mat2(1.0)); }\n'
        t, err = gl_shaders.legacy(src, 'vert')
        self.assertIsNone(err)
        self.assertIn('1.0f', t)


class RejectedSources(unittest.TestCase):
    """What cannot be expressed is reported, with the source and the stage, rather than translated into something wrong."""

    def test_gl_fragdata(self):
        src = '#version 120\nvoid main(void) { gl_FragData[0] = vec4(1.0); }\n'
        t, err = gl_shaders.legacy(src, 'frag')
        self.assertIsNone(t)
        self.assertIn('gl_FragData', err)

    def test_ftransform(self):
        src = '#version 120\nvoid main(void) { gl_Position = ftransform(); }\n'
        t, err = gl_shaders.legacy(src, 'vert')
        self.assertIsNone(t)
        self.assertIn('ftransform', err)

    def test_attribute_in_a_fragment_shader_is_not_silently_accepted(self):
        """It is left for glslang, whose message names the line; the rewrite must not turn it into an `in`."""
        src = '#version 120\nattribute vec3 a;\nvoid main(void) { gl_FragColor = vec4(a, 1.0); }\n'
        t, err = gl_shaders.legacy(src, 'frag')
        self.assertIsNone(err)
        self.assertIn('attribute vec3 a;', t)

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_glslang_names_the_file_and_stage(self):
        src = '#version 120\nattribute vec3 a;\nvoid main(void) { gl_FragColor = vec4(a, 1.0); }\n'
        with tempfile.TemporaryDirectory() as tmp:
            r = gl_shaders.translate(src.encode(), 'frag', key_of(src.encode()), tmp, '/shaders/x.glsl')
        self.assertIsInstance(r, str)
        self.assertIn("'attribute'", r)
        self.assertIn('on /shaders/x.glsl', r)


class Sections(unittest.TestCase):
    """One RomFS file holds both stages, between `//##Vertex//` / `//##Fragment//` and a closing `//####`. The game hands
    glShaderSource the marker line on and stops at the closer's fifth character; it fills each `#line ....` with the line
    number the following line has in the file. Both details are what the host hashes, so both are reproduced."""

    FILE = VERT_FILE + '\n//\n' + FRAG_FILE

    def test_two_stages(self):
        got = gl_shaders.darkest_sections(self.FILE.encode())
        self.assertEqual(['vert', 'frag'], [st for _, st in got])

    def test_section_starts_at_the_marker_and_stops_short_of_the_closer(self):
        src, _ = gl_shaders.darkest_sections(self.FILE.encode())[0]
        self.assertTrue(src.startswith(b'//##Vertex//'))
        self.assertTrue(src.endswith(b'//###'))
        self.assertFalse(src.endswith(b'//####'))
        self.assertNotIn(b'//##Fragment//', src)

    def test_line_directive_carries_the_files_own_line_number(self):
        raw = self.FILE.encode()
        for src, _ in gl_shaders.darkest_sections(raw):
            text = src.decode()
            self.assertNotIn('#line ....', text)
            body = text.split('\n')
            k = next(i for i, l in enumerate(body) if l.startswith('#line '))
            n = int(body[k].split()[1])
            file_line = raw.decode().split('\n').index(body[0]) + 1   # the marker's own line in the file
            self.assertEqual(file_line + k + 1, n, 'the directive names the line the next line has in the file')
            self.assertEqual(f'#line {n:<4}', body[k])                # '%-4d', as the engine writes it

    def test_a_section_without_a_closer_is_an_error(self):
        with self.assertRaises(ValueError) as c:
            gl_shaders.darkest_sections(VERT_FILE.replace('//####\n', '').encode())
        self.assertIn('//####', str(c.exception))

    def test_foreign_glsl_is_not_read(self):
        """Another engine's .glsl file has no markers and must not be taken for one of these."""
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'other.glsl').write_text('#version 330 core\nvoid main() { }\n')
            self.assertEqual([], list(gl_shaders.sources([d])))


class NsoStrings(unittest.TestCase):
    """The engine's built-in shaders live in main as C strings. Some begin with the newline that opens the literal, and one
    of Darkest Dungeon's follows a float array's last byte with no terminator before it, so a scan for a string that starts
    at a NUL boundary finds only some of them."""

    def nso(self, blobs):
        img = b''.join(blobs)
        d = bytearray(0x100 + len(img))
        d[0:4] = b'NSO0'
        struct.pack_into('<I', d, 0xc, 0)                          # uncompressed read-only segment
        struct.pack_into('<III', d, 0x20, 0x100, 0, len(img))
        struct.pack_into('<I', d, 0x64, len(img))
        d[0x100:] = img
        f = tempfile.NamedTemporaryFile(suffix='.nso', delete=False)
        f.write(bytes(d)); f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_reads_both_readings_of_a_literal_that_opens_with_a_newline(self):
        shader = b'\n#version 120\n\nvoid main(void) { gl_Position = vec4(0.0); }\n'
        got = gl_shaders.nso_strings(self.nso([b'junk\0', shader, b'\0']))
        self.assertEqual([shader, shader[1:]], got)   # the literal, then the same text from '#version' on

    def test_reads_a_string_that_follows_data_without_a_terminator(self):
        shader = b'\n#version 120\n\nvoid main(void) { gl_Position = vec4(0.0); }\n'
        got = gl_shaders.nso_strings(self.nso([b'\x00\x00\x80?\x00\x80\xbb\x47', shader, b'\0']))
        self.assertIn(shader, got)

    def test_a_message_is_not_a_shader(self):
        got = gl_shaders.nso_strings(self.nso([b'#version: 320 es is not supported\0',
                                               b'#version 140\nvoid main(void) { }\n\0']))
        self.assertEqual([b'#version 140\nvoid main(void) { }\n'], got)


class Identity(unittest.TestCase):
    """The key is the original source's hash, whatever the rewrite did to it — the translation never reaches the key."""

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_key_survives_the_rewrite(self):
        item = (FRAG.encode(), 'frag', '/shaders/sprite.glsl')
        with tempfile.TemporaryDirectory() as tmp:
            (key, stage, fields, msl, where), = gl_shaders.one(item, tmp)
            self.assertEqual(key_of(item[0]), key)
            self.assertEqual('frag', stage)
            self.assertEqual('/shaders/sprite.glsl', where)
            self.assertEqual(f'{key}_f', Path(msl).stem)          # the .metal file the library is built from
            self.assertIn(f'fragment gl_{key}_f_out gl_{key}_f(', Path(msl).read_text())

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_fields_describe_what_the_host_needs(self):
        with tempfile.TemporaryDirectory() as tmp:
            (key, stage, fields, msl, where), = gl_shaders.one((FRAG.encode(), 'frag', '/x'), tmp)
            msl = Path(msl).read_text()
        self.assertIn('o:dm_fragcolor=0', fields)                   # the colour output spirv-cross gives [[color(0)]]
        self.assertIn('t:Tex0=0:sampler2D', fields)
        self.assertTrue(any(f.startswith('b:') for f in fields), fields)
        self.assertIn('u:Saturation=0:float:0:0', fields)
        self.assertIn('[[color(0)]]', msl)


class Stages(unittest.TestCase):
    def test_a_vertex_section_translates_as_a_vertex_shader(self):
        if not HAVE_TOOLS: self.skipTest('glslangValidator and spirv-cross translate the source')
        with tempfile.TemporaryDirectory() as tmp:
            rows = gl_shaders.one((VERT.encode(), 'vert', '/shaders/sprite.glsl'), tmp)
            msl = Path(rows[0][3]).read_text()
        self.assertEqual(1, len(rows))
        self.assertEqual('vert', rows[0][1])
        self.assertTrue(any(f.startswith('a:vPosition=') for f in rows[0][2]), rows[0][2])
        self.assertIn('[[position]]', msl)

    def test_a_source_without_a_stage_is_tried_as_both(self):
        """A string in main says nothing of its stage: one of the two fails (its keywords belong to the other), which is
        not a failure of the build."""
        if not HAVE_TOOLS: self.skipTest('glslangValidator and spirv-cross translate the source')
        with tempfile.TemporaryDirectory() as tmp:
            rows = gl_shaders.one((FRAG.encode(), None, 'main#3'), tmp)
        self.assertEqual(['frag'], [r[1] for r in rows if r[1]])
        self.assertEqual(1, len(rows))


class Table(unittest.TestCase):
    """The table the host reads back: key <TAB> stage <TAB> fields <TAB> where, and a row per stage."""

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_library_from_a_romfs_like_tree(self):
        with tempfile.TemporaryDirectory() as d:
            romfs = Path(d, 'RomFS', 'shaders'); romfs.mkdir(parents=True)
            Path(romfs, 'sprite.glsl').write_text(VERT_FILE + '\n//\n' + FRAG_FILE)
            out = Path(d, 'out')
            r = subprocess.run([sys.executable, str(Path(gl_shaders.__file__)), str(Path(d, 'RomFS')), str(out)],
                               capture_output=True, text=True)
            if 'xcrun: error' in r.stderr or 'metal compile failed' in r.stderr:
                self.skipTest('no Metal toolchain here')
            self.assertEqual(0, r.returncode, r.stdout + r.stderr)
            rows = [l.split('\t') for l in Path(out, 'gl', 'gl_shaders.tsv').read_text().splitlines() if l and l[0] != '#']
        by_key = {}
        for key, stage, fields, where in rows:
            self.assertEqual(16, len(key))
            self.assertIn(stage, ('vert', 'frag'))
            self.assertEqual('/shaders/sprite.glsl', where)
            by_key.setdefault(key, set()).add(stage)
        # the two sections, keyed by exactly the bytes the game passes to glShaderSource
        self.assertEqual({key_of(src) for src, _ in gl_shaders.darkest_sections((VERT_FILE + '\n//\n' + FRAG_FILE).encode())},
                         set(by_key))
        self.assertEqual({'vert', 'frag'}, {s for v in by_key.values() for s in v})


# The movie player's shader in main is a #version 450 program, not a 1.20 one: NV12 luma and chroma in two textures, bound by
# their declarations rather than by glUniform1i. It is the only program in this game that needs the field below.
BOUND_FRAG = '''#version 450
layout(binding = 0) uniform sampler2D u_textureY;
layout(binding = 1) uniform sampler2D u_textureUV;
uniform float fade;
in vec2 v_texCoord;
out vec4 colorOut;

void main()
{
	vec3 t = texture(u_textureY, v_texCoord).rrr + texture(u_textureUV, v_texCoord).rrg;
	colorOut = vec4(t * fade, 1.0);
}
'''


class SamplerUnits(unittest.TestCase):
    """A sampler's GL texture unit starts at the binding its declaration gives it (GLSL 4.2's `layout(binding = n)`), and
    the table has to carry that unit: a game that never calls glUniform1i for a sampler relies on the initial value. Darkest
    Dungeon's YUV shader does, and with both units at 0 both samplers read the luma plane — the intro movie came out
    luma only, a cyan-green picture, until the host read this field."""

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_declared_bindings_become_the_initial_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = gl_shaders.one((BOUND_FRAG.encode(), 'frag', 'main#13'), tmp)
        (key, stage, fields, msl, where), = [r for r in rows if r[1] == 'frag']
        self.assertIn('t:u_textureY=0:sampler2D', fields)
        self.assertIn('t:u_textureUV=1:sampler2D', fields)
        self.assertIn('s:u_textureY=0', fields)
        self.assertIn('s:u_textureUV=1', fields)

    @unittest.skipUnless(HAVE_TOOLS, 'glslangValidator and spirv-cross translate the source')
    def test_a_sampler_without_a_declared_binding_keeps_gls_default(self):
        """Every 1.20 program of this game declares `uniform sampler2D Tex0;` and sets the unit itself: no field, so the
        host keeps the unit at 0 exactly as before."""
        with tempfile.TemporaryDirectory() as tmp:
            (key, stage, fields, msl, where), = gl_shaders.one((FRAG.encode(), 'frag', '/shaders/sprite.glsl'), tmp)
        self.assertIn('t:Tex0=0:sampler2D', fields)
        self.assertEqual([], [f for f in fields if f.startswith('s:')])


@unittest.skipUnless(os.environ.get('DD_BUILD'), 'set DD_BUILD=<title id>_build to match the captured programs against the RomFS')
class AgainstTheGame(unittest.TestCase):
    """What only the real files can say: the reader finds the sources the game compiled, and every captured program
    translates in the stage it was captured in."""

    def setUp(self):
        self.b = Path(os.environ['DD_BUILD'])
        self.romfs = self.b / 'extract/v0/RomFS'
        self.main = self.b / 'extract/v0/ExeFS/main'
        self.capture = self.b / 'capture'
        for p in (self.romfs, self.main, self.capture):
            if not p.exists(): self.skipTest(f'{p} is not there')

    def pool(self):
        got = {}
        for src, stage, where in gl_shaders.sources([str(self.romfs), str(self.main)]):
            got.setdefault(key_of(src), []).append((src, stage, where))
        return got

    def test_every_glsl_file_holds_two_stages(self):
        files = sorted(self.romfs.glob('shaders/*.glsl'))
        self.assertTrue(files)
        for p in files:
            got = gl_shaders.darkest_sections(p.read_bytes())
            self.assertEqual(['vert', 'frag'], [st for _, st in got], p.name)

    def test_every_captured_program_is_in_the_sources(self):
        pool = self.pool()
        missing = [n for n in sorted(os.listdir(self.capture)) if key_of(open(self.capture / n, 'rb').read()) not in pool]
        self.assertEqual([], missing)

    def test_every_captured_program_translates_in_its_stage(self):
        if not HAVE_TOOLS: self.skipTest('glslangValidator and spirv-cross translate the source')
        pool = self.pool()
        bad = []
        with tempfile.TemporaryDirectory() as tmp:
            for n in sorted(os.listdir(self.capture)):
                stage = n.rsplit('.', 1)[1]
                src = open(self.capture / n, 'rb').read()
                key = key_of(src)
                self.assertIn(key, pool, n)
                r = gl_shaders.translate(src, stage, key, tmp, n)
                if isinstance(r, str): bad.append((n, r))
        self.assertEqual([], bad)

    def test_the_yuv_shader_carries_its_declared_units(self):
        """The movie player's shader in main binds u_textureUV to unit 1 by declaration; its row must say so, or the host
        hands both samplers the luma plane."""
        if not HAVE_TOOLS: self.skipTest('glslangValidator and spirv-cross translate the source')
        yuv = [s for s in gl_shaders.nso_strings(str(self.main)) if b'u_textureUV' in s]
        self.assertEqual(1, len(yuv), yuv)
        src = yuv[0]
        with tempfile.TemporaryDirectory() as tmp:
            rows = gl_shaders.one((src, 'frag', 'main'), tmp)
        fields = [f for _, st, f, _, _ in rows if st == 'frag']
        self.assertEqual(1, len(fields), rows)
        self.assertIn('s:u_textureUV=1', fields[0])
        self.assertIn('s:u_textureY=0', fields[0])


if __name__ == '__main__':
    unittest.main()
