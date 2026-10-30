"""Build-tool streams compared with native files and an updated logical view."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import io
from pathlib import Path
import random
import sys
import tempfile
import threading
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from tools.nxrom.resourcefs import ResourceFS, build_library
from fixture import write_fixture, pfs, romfs, patch_nca, xci, TITLE


class ResourceStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (HERE / 'build').mkdir(exist_ok=True)
        cls.work = tempfile.TemporaryDirectory(prefix='streams-', dir=HERE / 'build')
        cls.root = Path(cls.work.name)
        cls.library = build_library(cls.root / 'reader.dylib')
        cls.data = write_fixture(cls.root)
        cls.updated = dict(cls.data)
        cls.updated['nested/big'] = b'patched!' + cls.data['nested/big'][8:]
        (cls.root / 'update.nsp').write_bytes(pfs([('patch.nca', patch_nca(romfs(cls.data), romfs(cls.updated)))]))
        (cls.root / 'base.xci').write_bytes(xci(cls.data))
        cls.directory = cls.root / 'directory'
        (cls.directory / 'nested').mkdir(parents=True)
        (cls.directory / 'empty').mkdir()
        for path, data in cls.data.items():
            (cls.directory / path).write_bytes(data)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def mount(self, update=False, directory=False):
        if directory:
            return ResourceFS(self.library, directory=self.directory)
        return ResourceFS(self.library, base=self.root / 'base.nsp',
                          keys=self.root / 'test.keys', title=TITLE,
                          update=self.root / 'update.nsp' if update else None)

    def test_listing_and_all_bytes(self):
        for update, directory, expected in ((False, False, self.data),
                                           (False, True, self.data),
                                           (True, False, self.updated)):
            with self.subTest(update=update, directory=directory), self.mount(update, directory) as fs:
                self.assertEqual({e.path: e.size for e in fs.files()},
                                 {p: len(b) for p, b in expected.items()})
                self.assertTrue(fs.stat('nested').is_dir)
                self.assertEqual(list(fs.iterdir('empty')), [])
                for path, blob in expected.items():
                    with fs.open(path) as stream:
                        self.assertEqual(stream.read(), blob)
                        self.assertEqual(stream.read(1), b'')

    def test_random_seek_read_and_readinto(self):
        rng = random.Random(41)
        with self.mount(True) as fs:
            for buffering in (0, 65536):
                with fs.open('nested/big', buffering=buffering) as stream:
                    oracle = io.BytesIO(self.updated['nested/big'])
                    for _ in range(120):
                        whence = rng.choice((0, 1, 2))
                        offset = rng.randrange(len(self.updated['nested/big']) + 100)
                        if whence == 2:
                            offset = -min(offset, len(self.updated['nested/big']))
                        self.assertEqual(stream.seek(offset, whence), oracle.seek(offset, whence))
                        size = rng.randrange(17000)
                        target = bytearray(size)
                        n = stream.readinto(target)
                        self.assertEqual(target[:n], oracle.read(size))
                        self.assertEqual(stream.tell(), oracle.tell())
                    stream.seek(0)
                    self.assertEqual(stream.read(5), self.updated['nested/big'][:5])

    def test_concurrent_independent_streams(self):
        with self.mount(True) as fs:
            def read_at(offset):
                with fs.open('nested/big') as stream:
                    stream.seek(offset)
                    return stream.read(12000)
            offsets = [0, 4090, 65520, 200000] * 30
            with ThreadPoolExecutor(max_workers=4) as pool:
                actual = list(pool.map(read_at, offsets))
            self.assertEqual(actual, [self.updated['nested/big'][o:o+12000] for o in offsets])

    def test_invalid_paths_modes_and_lifetimes(self):
        fs = self.mount()
        with fs:
            for path in ('../small', '/small', 'nested//big', 'missing'):
                with self.assertRaises(OSError):
                    fs.open(path)
            with self.assertRaises(ValueError): fs.open('small\0ignored')
            with self.assertRaises(ValueError): fs.open('small', mode='wb')
            with self.assertRaises(IsADirectoryError): fs.open('nested')
            with self.assertRaises(NotADirectoryError): fs.iterdir('small')
            with fs.open('small', buffering=0) as stream:
                for offset, origin in ((-1, 0), (1 << 63, 0), (0, 3)):
                    with self.assertRaises(ValueError): stream.seek(offset, origin)
                with self.assertRaises(TypeError): stream.readinto(b'readonly')
                with self.assertRaises(io.UnsupportedOperation): stream.write(b'x')
            with self.assertRaises(ValueError): stream.read(1)
            raw = fs.open('small', buffering=0)
        fs.close()
        with self.assertRaises(ValueError): raw.read(1)
        raw.close()
        with self.assertRaises(ValueError): fs.stat('small')

    def test_failed_mount_and_compressed_input(self):
        with self.assertRaises(OSError):
            ResourceFS(self.library, base=self.root/'base.nsp', keys=self.root/'absent.keys')
        (self.root/'compressed.nsp').write_bytes(pfs([('content.ncz', b'compressed')]))
        with self.assertRaises(OSError):
            ResourceFS(self.library, base=self.root/'compressed.nsp', keys=self.root/'test.keys')

    def test_gamecard_base_matches_nsp_and_update(self):
        with ResourceFS(self.library, base=self.root/'base.xci', keys=self.root/'test.keys', title=TITLE) as gamecard:
            self.assertEqual({e.path: e.size for e in gamecard.files()},
                             {p: len(b) for p, b in self.data.items()})
            with gamecard.open('nested/big', buffering=0) as stream:
                self.assertEqual(stream.read(70000), self.data['nested/big'][:70000])
        with ResourceFS(self.library, base=self.root/'base.xci', keys=self.root/'test.keys', title=TITLE,
                        update=self.root/'update.nsp') as gamecard:
            with gamecard.open('nested/big', buffering=0) as stream:
                stream.seek(4090)
                self.assertEqual(stream.read(12000), self.updated['nested/big'][4090:4090+12000])
        with self.assertRaises(OSError):
            ResourceFS(self.library, base=self.root/'base.xci', keys=self.root/'test.keys', title=TITLE+1)

    def test_close_waits_for_active_native_lease(self):
        fs = self.mount()
        entered = threading.Event()
        def close():
            entered.set()
            fs.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with fs._lease():
                future = pool.submit(close)
                self.assertTrue(entered.wait(2))
                with self.assertRaises(TimeoutError): future.result(timeout=.05)
            future.result(timeout=2)
        self.assertTrue(fs.closed)


if __name__ == '__main__':
    unittest.main()
