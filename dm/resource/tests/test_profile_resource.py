"""Existing preparation census rules must agree across all resource inputs."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
sys.path.insert(0, str(HERE.parents[1] / 'games'))
import profile_guess as pg
from scripts.inspect_external_nsp import main, survey
from tools.nxrom.resourcefs import ResourceFS, build_library
from fixture import write_fixture, pfs, romfs, nca, patch_nca, with_code, BUILD_ID, TITLE


class ProfileResources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (HERE/'build').mkdir(exist_ok=True)
        cls.work = tempfile.TemporaryDirectory(prefix='profile-resource-', dir=HERE/'build')
        cls.root = Path(cls.work.name)
        cls.library = build_library(cls.root/'nxrom.dylib')
        cls.files = {'nested/example.bfsha': b'BNSH' + bytes(range(64)),
                     'nested/caf\u00e9': b'UnityFS\0' + b'x'*100,
                     'zero': b'', 'root.bin': b'abc'}
        write_fixture(cls.root, cls.files)
        (cls.root/'base.nsp').write_bytes(pfs([('program.nca', with_code(nca(romfs(cls.files))))]))
        cls.updated = dict(cls.files, **{'root.bin': b'Yaz0' + b'u'*80})
        (cls.root/'update.nsp').write_bytes(pfs([('patch.nca', with_code(patch_nca(romfs(cls.files), romfs(cls.updated))))]))
        for name, files in (('base', cls.files), ('updated', cls.updated)):
            directory = cls.root/(name+'-directory')
            directory.mkdir()
            for path, data in files.items():
                target = directory/path
                target.parent.mkdir(exist_ok=True, parents=True)
                target.write_bytes(data)
            (cls.root/(name+'.tsv')).write_text(''.join(
                f'/{path}\t{len(data)}\t{data[:32].hex()}\n' for path, data in files.items()))
        # Minimal uncompressed NSO with an empty valid MOD0 dynamic-symbol table.
        image = bytearray(256)
        struct.pack_into('<I', image, 4, 32)
        image[32:36] = b'MOD0'; struct.pack_into('<i', image, 36, 32)
        struct.pack_into('<qQqQ', image, 64, 5, 216, 6, 192)
        header = bytearray(256); header[:4] = b'NSO0'; header[64:80] = BUILD_ID
        for i in range(3):
            struct.pack_into('<III', header, 0x10+i*0x10, 256 if not i else 512,
                             0 if not i else 256, 256 if not i else 0)
        struct.pack_into('<III', header, 0x60, 256, 0, 0)
        cls.exefs = cls.root/'ExeFS'; cls.exefs.mkdir()
        (cls.exefs/'main').write_bytes(header+image)

    @classmethod
    def tearDownClass(cls): cls.work.cleanup()

    def mount(self, update=False):
        return ResourceFS(self.library, base=self.root/'base.nsp', keys=self.root/'test.keys',
                          title=TITLE, update=self.root/'update.nsp' if update else None)

    def test_census_facts_and_profile_parity(self):
        for update, name in ((False, 'base'), (True, 'updated')):
            with self.subTest(update=update), self.mount(update) as fs:
                native = pg.facts_of(self.exefs, fs)
                directory = pg.facts_of(self.exefs, self.root/(name+'-directory'))
                manifest = pg.facts_of(self.exefs, self.root/(name+'.tsv'))
                self.assertEqual(native, directory)
                self.assertEqual(native, manifest)
                self.assertEqual(pg.guess(native), pg.guess(directory))
                self.assertEqual(native['romfs']['n'], 4)
                self.assertEqual(native['romfs']['mags']['Yaz0'], int(update))

    def test_census_reads_only_32_bytes(self):
        class Census:
            def files(self):
                from tools.nxrom.resourcefs import Entry
                return [Entry('large', 1 << 40, False)]
            def open(inner, path, buffering):
                self.assertEqual(buffering, 0)
                class Stream(io.BytesIO):
                    def read(inner, count=-1):
                        self.assertEqual(count, 32)
                        return super().read(count)
                return Stream(b'a'*100)
        self.assertEqual(list(pg.romfs_files(Census())), [('/large', 1 << 40, b'a'*32)])

    def test_survey_checks_module_identity(self):
        with self.mount(True) as fs:
            fs.check_build('main', BUILD_ID.hex().upper())
            with self.assertRaises(OSError): fs.check_build('main', '0'*32)
            with self.assertRaises(ValueError): fs.check_build('main', 'invalid')
            wrong = self.root/'wrong-ExeFS'; wrong.mkdir()
            blob = bytearray((self.exefs/'main').read_bytes()); blob[64] ^= 1
            (wrong/'main').write_bytes(blob)
            with self.assertRaises(OSError): survey(wrong, fs)

    def test_inspector_survey_cli_and_conflicting_options(self):
        args = ['--base', str(self.root/'base.nsp'), '--update', str(self.root/'update.nsp'),
                '--keys', str(self.root/'test.keys'), '--title', f'{TITLE:016x}',
                '--work', str(self.root/'cli-work'), '--survey-exefs', str(self.exefs)]
        output = io.StringIO()
        with redirect_stdout(output): self.assertEqual(main(args), 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['romfs']['mags']['Yaz0'], 1)
        self.assertEqual(report['modules']['main']['build_id'], BUILD_ID.hex())
        for line in (self.root/'test.keys').read_text().splitlines():
            self.assertNotIn(line.split('=', 1)[1].strip(), output.getvalue())
        for extra in (['--read', 'root.bin'], ['--verify'], ['--length', '5']):
            with redirect_stdout(io.StringIO()), patch('sys.stderr', io.StringIO()):
                with self.assertRaises(SystemExit): main(args+extra)

    def test_existing_inspector_read_and_verify_modes(self):
        script = HERE.parents[2]/'scripts/inspect_external_nsp.py'
        args = [sys.executable, str(script), '--base', str(self.root/'base.nsp'),
                '--keys', str(self.root/'test.keys'), '--work', str(self.root/'legacy-work')]
        result = subprocess.run(args+['--read', 'root.bin', '--offset', '1', '--length', '2'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'bc')
        result = subprocess.run(args+['--verify'], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'f\t/root.bin\t3\t', result.stdout)


if __name__ == '__main__':
    unittest.main()
