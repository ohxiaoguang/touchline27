"""Both resource modes of the build: the macOS packaging step and the packaging roots.

Synthetic inputs only - no game files, no Xcode, no Swift compiler: the launcher is
stubbed, so what is checked is the bundle layout, the Info.plist and the guards that
keep the wrong game data out of an App.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest

REPO = Path(__file__).resolve().parents[3]
CHAIN = 'a1b2c3d4e5f6'
TITLE = '010015100B514000'
MARKER = 'System/Resource/ResourceSizeTable.product.rsizetable'
BUILD_ID = 'c0ffee00d15ea5e0c0ffee00d15ea5e0'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mac_app = load_module('nx_build_mac_app', REPO / 'scripts/build_mac_app.py')
ipa = load_module('nx_build_ipa_from_nsp', REPO / 'scripts/build_ipa_from_nsp.py')


def write(path, data=b'x'):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())
    return path


def make_inputs(root, romfs=True):
    """Every input the packaging step takes, in the shape the pipeline produces it."""
    inputs = types.SimpleNamespace()
    inputs.host = write(root / 'tools/dmhost', b'#!/bin/sh\n# chain ' + CHAIN.encode() + b'\n')
    inputs.host.chmod(0o755)
    inputs.patched = root / 'patched_v0'
    write(inputs.patched / 'main.patched.bin', b'program')
    write(inputs.patched / 'main.fixups.tsv', '# BUILD_ID\t' + BUILD_ID + '\n')
    inputs.shaders = root / 'shader/cache' / ('b-' + CHAIN)
    write(inputs.shaders / 'abc_b.metallib', b'metallib')
    write(inputs.shaders / 'abc_b.json', b'{}')
    write(inputs.shaders / 'inputs.tsv', 'game\t' + TITLE + '\ninputs\tfixture\n')
    inputs.profile = root / 'profile'
    # The chain version header belongs to the source tree (one for every game), not to a game profile.
    inputs.chain_header = write(root / 'gfx/nvn/dmsh_chain.h', '#define DMSH_CHAIN "' + CHAIN + '"\n')
    for table in ('shader_map.tsv', 'pso_manifest.tsv', 'c1_full.tsv', 'cb_extent.tsv'):
        write(inputs.profile / table, '# table\n')
    write(inputs.profile / 'game.tsv', 'modules\tmain\ndisplay\t1.0\nromfs_marker\t' + MARKER + '\n')
    inputs.font = root / 'font'
    for name in ('standard.ttf', 'nintendo_ext.ttf'):
        write(inputs.font / name, b'ttf')
    inputs.settings = write(root / 'launcher.json', '{"settings": []}\n')
    inputs.romfs = root / 'RomFS'
    if romfs:
        write(inputs.romfs / MARKER, b'rsizetable')
        write(inputs.romfs / 'Model/model.bfres', b'bfres')
    return inputs


def args_for(inputs, output, backend, romfs=None):
    return types.SimpleNamespace(
        output=output, resource_backend=backend, title_id=TITLE, name='Test Game', version='1.0',
        settings=inputs.settings, profile=inputs.profile, shaders=inputs.shaders, host=inputs.host,
        patched=inputs.patched, font=inputs.font, romfs=romfs, chain_header=inputs.chain_header, icon=None)


def stub_launcher(path):
    """The real one runs swiftc; the bundle layout is what these tests check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'#!/bin/sh\nexit 0\n')
    path.chmod(0o755)


class MacAppDirectoryMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'work'
        self.inputs = make_inputs(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_shader_stamp_is_rejected_before_packaging(self):
        (self.inputs.shaders / 'inputs.tsv').unlink()
        with self.assertRaisesRegex(ValueError, 'has no inputs.tsv'):
            self.package(Path(self.tmp.name) / 'MissingStamp.app')

    def package(self, output, romfs=None, inputs=None):
        inputs = inputs or self.inputs
        args = args_for(inputs, output, 'directory', romfs if romfs is not None else inputs.romfs)
        return mac_app.package(args, launcher=stub_launcher)

    def test_bundles_the_game_romfs_and_says_so(self):
        out = Path(self.tmp.name) / 'Game.app'
        summary = self.package(out)
        self.assertTrue(summary['romfs_bundled'])
        self.assertEqual(summary['backend'], 'directory')
        res = out / 'Contents/Resources'
        self.assertTrue((res / 'romfs' / MARKER).is_file())
        self.assertEqual((res / 'romfs/Model/model.bfres').read_bytes(), b'bfres')
        self.assertIn('inside this App', (res / 'Readme.txt').read_text())
        plist = (out / 'Contents/Info.plist').read_bytes()
        self.assertIn(b'NXResourceBackend', plist)

    def test_runtime_parts_are_the_same_as_the_external_mode(self):
        out = Path(self.tmp.name) / 'Game.app'
        self.package(out)
        res = out / 'Contents/Resources'
        self.assertTrue((res / 'program/main.patched.bin').is_file())
        self.assertEqual((res / 'profile/prepared_builds.tsv').read_text(), 'main\t' + BUILD_ID + '\n')
        self.assertTrue((res / 'msl' / ('b-' + CHAIN) / 'abc_b.metallib').is_file())
        self.assertTrue((res / 'profile/shader_map.tsv').is_file())
        self.assertTrue((res / 'font/standard.ttf').is_file())

    def test_rejects_a_folder_that_is_not_this_games_romfs(self):
        other = Path(self.tmp.name) / 'NotRomFS'
        write(other / 'readme.txt', b'')
        with self.assertRaisesRegex(ValueError, 'not this game'):
            self.package(Path(self.tmp.name) / 'Game.app', romfs=other)
        self.assertFalse((Path(self.tmp.name) / 'Game.app').exists())

    def test_refuses_to_bundle_a_container_inside_the_romfs(self):
        write(self.inputs.romfs / 'leftover.nsp', b'PFS0')
        with self.assertRaisesRegex(ValueError, 'container or key material'):
            self.package(Path(self.tmp.name) / 'Game.app')

    def test_needs_a_romfs(self):
        args = args_for(self.inputs, Path(self.tmp.name) / 'Game.app', 'directory', None)
        with self.assertRaisesRegex(ValueError, 'needs --romfs'):
            mac_app.package(args, launcher=stub_launcher)


class MacAppExternalMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inputs = make_inputs(Path(self.tmp.name) / 'work')

    def tearDown(self):
        self.tmp.cleanup()

    def test_carries_no_game_data(self):
        out = Path(self.tmp.name) / 'Game.app'
        summary = mac_app.package(args_for(self.inputs, out, 'nsp'), launcher=stub_launcher)
        self.assertFalse(summary['romfs_bundled'])
        self.assertFalse((out / 'Contents/Resources/romfs').exists())
        # The launcher finds the container itself, so the Readme says what it looks for
        # instead of naming the file the player has to copy in.
        readme = (out / 'Contents/Resources/Readme.txt').read_text()
        self.assertIn('base game', readme)
        self.assertIn('sub-folder', readme)

    def test_refuses_a_romfs_argument(self):
        out = Path(self.tmp.name) / 'Game.app'
        with self.assertRaisesRegex(ValueError, 'belongs to directory mode'):
            mac_app.package(args_for(self.inputs, out, 'nsp', romfs=self.inputs.romfs), launcher=stub_launcher)

    def test_bundles_the_modules_a_game_loads_with_nn_ro(self):
        # FC 27 loads its render NRO at boot: without the table the host cannot match the
        # SHA-256 the game registers, LoadModule fails and the export resolves to 0.
        write(self.inputs.patched / 'render.patched.bin', b'nro program')
        write(self.inputs.patched / 'render.fixups.tsv', '# BUILD_ID\t' + BUILD_ID + '\n')
        table = 'render\t' + 'ab' * 32 + '\t4096\n'
        write(self.inputs.patched / 'nro.tsv', table)
        out = Path(self.tmp.name) / 'Game.app'
        mac_app.package(args_for(self.inputs, out, 'nsp'), launcher=stub_launcher)
        res = out / 'Contents/Resources'
        self.assertEqual((res / 'program/render.patched.bin').read_bytes(), b'nro program')
        self.assertEqual((res / 'program/nro.tsv').read_text(), table)

    def test_refuses_an_nro_row_without_its_rewritten_module(self):
        write(self.inputs.patched / 'nro.tsv', 'render\t' + 'ab' * 32 + '\t4096\n')
        out = Path(self.tmp.name) / 'Game.app'
        with self.assertRaisesRegex(ValueError, 'no rewritten module'):
            mac_app.package(args_for(self.inputs, out, 'nsp'), launcher=stub_launcher)
        self.assertFalse(out.exists())

    def test_prepared_manifest_keeps_nro_modules_out(self):
        # The launcher compares the manifest's Build IDs against the container's ExeFS, which
        # has no entry for a module the game loads with nn::ro: listing "render" refused every
        # matching base and update ("does not match prepared module render").
        write(self.inputs.patched / 'render.patched.bin', b'nro program')
        write(self.inputs.patched / 'render.fixups.tsv', '# BUILD_ID\t' + 'cd' * 16 + '\n')
        write(self.inputs.patched / 'nro.tsv', 'render\t' + 'ab' * 32 + '\t4096\n')
        out = Path(self.tmp.name) / 'Game.app'
        mac_app.package(args_for(self.inputs, out, 'nsp'), launcher=stub_launcher)
        self.assertEqual((out / 'Contents/Resources/profile/prepared_builds.tsv').read_text(),
                         'main\t' + BUILD_ID + '\n')


class MacAppPlist(unittest.TestCase):
    def test_backend_is_recorded_for_the_launcher(self):
        for backend in ('directory', 'nsp'):
            info = mac_app.info_plist('Test Game', TITLE, '1.0', backend)
            self.assertEqual(info['NXResourceBackend'], backend)
            self.assertEqual(info['NXTitleID'], TITLE)
            self.assertEqual(info['CFBundleExecutable'], 'launch')
        self.assertNotEqual(mac_app.info_plist('G', TITLE, '1', 'directory')['CFBundleIdentifier'],
                            mac_app.info_plist('G', TITLE, '1', 'nsp')['CFBundleIdentifier'])

    def test_readme_follows_the_mode(self):
        self.assertIn('romfs', mac_app.readme('directory', TITLE))
        self.assertIn('NSP', mac_app.readme('nsp', TITLE))


class BackendResolution(unittest.TestCase):
    def test_default_stays_external(self):
        # Every packaging command written before the option existed passes no backend.
        self.assertEqual(mac_app.resolve_backend(None, None, None), 'nsp')
        self.assertEqual(mac_app.resolve_backend('nsp', None, None), 'nsp')
        self.assertEqual(mac_app.resolve_backend(None, None, Path('/games/RomFS')), 'directory')
        self.assertEqual(mac_app.resolve_backend(None, Path('/prepared'), None), 'nsp')
        self.assertEqual(mac_app.resolve_backend('nsp', Path('/prepared'), Path('/romfs')), 'nsp')

    def test_ipa_pipeline_default_is_directory(self):
        self.assertEqual(ipa.RESOURCE_BACKEND, 'directory')
        self.assertIsNone(ipa.parse_args([]).resource_backend)
        self.assertIsNone(ipa.parse_args([]).mac_app)
        self.assertEqual(ipa.parse_args(['--mac-app']).mac_app, '')
        self.assertEqual(ipa.parse_args(['--mac-app', '/tmp/A.app']).mac_app, '/tmp/A.app')
        self.assertEqual(ipa.parse_args(['--resource-backend', 'nsp']).resource_backend, 'nsp')


class BuildRoots(unittest.TestCase):
    def test_each_mode_gets_its_own_packaging_state(self):
        work = Path('/games/010015100B514000_build')
        self.assertEqual(ipa.backend_build_root(work, 'directory'), work)
        self.assertEqual(ipa.backend_build_root(work, 'nsp'), work / 'nsp')
        # The extracted files, the rewritten modules and the Shader caches stay shared:
        # both modes build them from the same inputs, so only the packaging state moves.
        self.assertNotEqual(ipa.backend_build_root(work, 'nsp') / 'ipa', ipa.backend_build_root(work, 'directory') / 'ipa')

    def test_a_root_keeps_one_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'build'
            ipa.stamp_backend(root, 'directory')
            self.assertEqual((root / '.resource-backend').read_text().strip(), 'directory')
            ipa.stamp_backend(root, 'directory')   # the same mode again is fine
            with self.assertRaisesRegex(ipa.BuildError, 'holds a directory mode build'):
                ipa.stamp_backend(root, 'nsp')
            self.assertTrue(root.is_dir())   # nothing removed on the refusal


class MacAppArguments(unittest.TestCase):
    def run_main(self, *argv):
        return ipa.main(ipa.parse_args(list(argv)))

    def test_mac_app_is_directory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = write(Path(tmp) / 'prod.keys', b'x')
            with self.assertRaisesRegex(ipa.BuildError, 'directory mode App'):
                self.run_main(tmp, '-k', str(keys), '--resource-backend', 'nsp', '--mac-app')

    def test_mac_app_is_not_an_ipa(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = write(Path(tmp) / 'prod.keys', b'x')
            with self.assertRaisesRegex(ipa.BuildError, 'names the IPA'):
                self.run_main(tmp, '-k', str(keys), '--mac-app', '--out', str(Path(tmp) / 'x.ipa'))

    def test_mac_app_excludes_the_xcode_and_nsp_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            keys = write(Path(tmp) / 'prod.keys', b'x')
            with self.assertRaisesRegex(ipa.BuildError, 'prepare-xcode'):
                self.run_main(tmp, '-k', str(keys), '--mac-app', '--prepare-xcode')
            with self.assertRaisesRegex(ipa.BuildError, 'NSP preparation modes'):
                self.run_main(tmp, '-k', str(keys), '--mac-app', '--use-nsp-prepared', 'x')


if __name__ == '__main__':
    unittest.main()
