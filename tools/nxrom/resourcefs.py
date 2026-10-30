"""MIT-licensed, read-only build-tool access to nxnative's resource core.

Build the shared library explicitly with build_library(output) on macOS. No
implicit compilation, extraction, disk cache or key logging occurs at mount.
Use a mount as a context manager and close its streams before closing the mount.
Independent streams have independent cursors; native pread calls may overlap.
Mount close waits for active native calls and rejects subsequent operations.
Per-call native buffers are capped at 1 MiB. As with ordinary Python files,
read() without a size collects a complete file: stream large assets in chunks.
"""
import ctypes as C
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import io
import operator
import os
from pathlib import Path
import subprocess
import threading


def build_library(output):
    """Compile into an explicitly chosen existing work directory, never HOME."""
    output = Path(output).resolve()
    source = Path(__file__).resolve().parents[2] / 'dm/resource/nxrom.c'
    subprocess.run(['xcrun', 'clang', '-dynamiclib', '-O2', '-Wall', '-Wextra',
                    '-Werror', '-Wno-deprecated-declarations', str(source),
                    '-Wl,-install_name,@rpath/nxrom.dylib',
                    '-o', str(output)], check=True)
    return output


class _Info(C.Structure):
    _fields_ = [('path', C.c_char_p), ('size', C.c_uint64), ('directory', C.c_int)]


@dataclass(frozen=True)
class Entry:
    path: str
    size: int
    is_dir: bool


def _path(path):
    value = os.fspath(path)
    if not isinstance(value, str) or '\0' in value:
        raise ValueError('resource paths must be text without NUL characters')
    return value.encode('utf-8')


def _error(path=None, message=None):
    code = C.get_errno() or errno.EIO
    return OSError(code, message or os.strerror(code), path)


class ResourceFS:
    """Immutable directory or base/update NSP view. Paths are relative UTF-8."""
    def __init__(self, library, *, base=None, keys=None, update=None, title=0,
                 directory=None, aoc=False, application_version=0):
        if directory is not None:
            if any(x is not None for x in (base, keys, update)) or title or aoc or application_version:
                raise ValueError('directory and NSP mount options cannot be combined')
        elif base is None or keys is None:
            raise ValueError('NSP mounts require base and keys paths')
        self._condition = threading.Condition()
        self._active = 0
        self._closing = False
        self._ptr = None
        lib = self._lib = C.CDLL(str(Path(library).resolve()), use_errno=True)
        lib.nxrom_open.argtypes = [C.c_char_p, C.c_char_p, C.c_char_p, C.c_uint64,
                                  C.POINTER(C.c_void_p), C.c_char_p, C.c_size_t]
        lib.nxrom_directory.argtypes = [C.c_char_p, C.POINTER(C.c_void_p)]
        lib.nxrom_close.argtypes = [C.c_void_p]
        lib.nxrom_close.restype = None
        lib.nxrom_find.argtypes = [C.c_void_p, C.c_char_p, C.POINTER(C.c_uint64)]
        lib.nxrom_stat.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(_Info)]
        lib.nxrom_next.argtypes = [C.c_void_p, C.c_uint64, C.POINTER(C.c_uint64), C.POINTER(_Info)]
        lib.nxrom_read.argtypes = [C.c_void_p, C.c_uint64, C.c_void_p, C.c_size_t, C.c_int64]
        lib.nxrom_read.restype = C.c_ssize_t
        lib.nxrom_check_build.argtypes = [C.c_void_p, C.c_char_p, C.c_char_p]
        lib.nxrom_title.argtypes = [C.c_void_p]
        lib.nxrom_title.restype = C.c_uint64
        ptr = C.c_void_p()
        if directory is not None:
            result = lib.nxrom_directory(_path(directory), C.byref(ptr))
            message = None
        else:
            title = operator.index(title)
            if not 0 <= title < 1 << 64:
                raise ValueError('title must fit an unsigned 64-bit value')
            error = C.create_string_buffer(512)
            if aoc:
                application_version = operator.index(application_version)
                if not 0 <= application_version <= 0xffffffff:
                    raise ValueError('application_version must fit an unsigned 32-bit value')
                if update is not None:
                    raise ValueError('AOC cannot be mounted as a program update')
                lib.nxrom_open_aoc.argtypes = [C.c_char_p, C.c_char_p, C.c_uint64, C.c_uint32,
                                               C.POINTER(C.c_void_p), C.c_char_p, C.c_size_t]
                result = lib.nxrom_open_aoc(_path(base), _path(keys), title, application_version,
                                            C.byref(ptr), error, len(error))
            else:
                result = lib.nxrom_open(_path(base), _path(update) if update is not None else None,
                                        _path(keys), title, C.byref(ptr), error, len(error))
            message = error.value.decode('utf-8', errors='replace')
        if result:
            raise _error(message=message)
        self._ptr = ptr

    def validate_aoc(self):
        """Refuse corrupt headers and unprocessed executable modules, not data."""
        error = C.create_string_buffer(512)
        self._lib.nxrom_validate_aoc.argtypes = [C.c_void_p, C.c_char_p, C.c_size_t]
        with self._lease() as ptr:
            if self._lib.nxrom_validate_aoc(ptr, error, len(error)):
                raise _error(message=error.value.decode('utf-8', errors='replace'))

    @property
    def closed(self):
        with self._condition:
            return self._closing

    @property
    def title(self):
        """Title ID of the base Program NCA the native reader selected.

        Mounting with title=0 asks the reader to report the container's own
        Program NCA title instead of verifying a caller-supplied one, so a
        caller can identify the game from the resource itself.
        """
        with self._lease() as ptr:
            return self._lib.nxrom_title(ptr)

    @contextmanager
    def _lease(self):
        with self._condition:
            if self._closing:
                raise ValueError('resource filesystem is closed')
            self._active += 1
            ptr = self._ptr
        try:
            yield ptr
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()

    def close(self):
        with self._condition:
            if self._closing:
                while self._ptr is not None:
                    self._condition.wait()
                return
            self._closing = True
            while self._active:
                self._condition.wait()
            if self._ptr is not None:
                self._lib.nxrom_close(self._ptr)
                self._ptr = None
            self._condition.notify_all()

    def __enter__(self):
        if self.closed:
            raise ValueError('resource filesystem is closed')
        return self

    def __exit__(self, *args):
        self.close()

    @staticmethod
    def _entry(info):
        return Entry(info.path.decode('utf-8'), info.size, bool(info.directory))

    def _lookup(self, ptr, path):
        ident = C.c_uint64()
        if self._lib.nxrom_find(ptr, _path(path), C.byref(ident)):
            raise _error(path)
        info = _Info()
        if self._lib.nxrom_stat(ptr, ident, C.byref(info)):
            raise _error(path)
        return ident, self._entry(info)

    def stat(self, path):
        with self._lease() as ptr:
            return self._lookup(ptr, path)[1]

    def check_build(self, module, build_id):
        """Require the selected ExeFS module's first 16 build-ID bytes to match."""
        if not isinstance(build_id, str) or len(build_id) != 32 or any(c not in '0123456789abcdefABCDEF' for c in build_id):
            raise ValueError('build ID must contain exactly 32 hexadecimal digits')
        with self._lease() as ptr:
            if self._lib.nxrom_check_build(ptr, _path(module), build_id.lower().encode('ascii')):
                raise _error(module, 'prepared module does not match selected ExeFS')

    def iterdir(self, path=''):
        # Copy names while leased; do not hold a native pointer across a yield.
        entries = []
        with self._lease() as ptr:
            ident, entry = self._lookup(ptr, path)
            if not entry.is_dir:
                raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), path)
            cursor, info = C.c_uint64(), _Info()
            while True:
                result = self._lib.nxrom_next(ptr, ident, C.byref(cursor), C.byref(info))
                if result < 0:
                    raise _error(path)
                if not result:
                    break
                entries.append(self._entry(info))
        return iter(entries)

    def files(self, path=''):
        pending = [path]
        while pending:
            for entry in self.iterdir(pending.pop()):
                if entry.is_dir:
                    pending.append(entry.path)
                else:
                    yield entry

    def open(self, path, mode='rb', buffering=65536):
        if mode != 'rb':
            raise ValueError('resource files support rb mode only')
        buffering = operator.index(buffering)
        if buffering < 0:
            raise ValueError('buffering must be nonnegative')
        with self._lease() as ptr:
            ident, entry = self._lookup(ptr, path)
            if entry.is_dir:
                raise IsADirectoryError(errno.EISDIR, os.strerror(errno.EISDIR), path)
            raw = _File(self, ident, entry)
        return io.BufferedReader(raw, buffer_size=buffering) if buffering else raw


class _File(io.RawIOBase):
    def __init__(self, fs, ident, entry):
        super().__init__()
        self._fs, self._id, self._size = fs, ident, entry.size
        self.name, self.mode = entry.path, 'rb'
        self._position = 0
        self._lock = threading.RLock()

    def _check(self):
        self._checkClosed()
        if self._fs.closed:
            raise ValueError('resource filesystem is closed')

    def readable(self):
        self._check()
        return True

    def seekable(self):
        self._check()
        return True

    def write(self, data):
        self._check()
        raise io.UnsupportedOperation('resource files are read-only')

    def tell(self):
        with self._lock:
            self._check()
            return self._position

    def seek(self, offset, whence=os.SEEK_SET):
        offset, whence = operator.index(offset), operator.index(whence)
        with self._lock:
            self._check()
            if whence not in (os.SEEK_SET, os.SEEK_CUR, os.SEEK_END):
                raise ValueError('invalid seek origin')
            position = offset + (0 if whence == os.SEEK_SET else self._position if whence == os.SEEK_CUR else self._size)
            if not 0 <= position < 1 << 63:
                raise ValueError('seek position must fit a nonnegative signed 64-bit value')
            self._position = position
            return position

    def readinto(self, buffer):
        with self._lock:
            self._check()
            view = memoryview(buffer).cast('B')
            if view.readonly:
                raise TypeError('readinto requires a writable buffer')
            count = min(len(view), 1024 * 1024, max(0, self._size - self._position))
            with self._fs._lease() as ptr:
                if not count:
                    return 0
                data = (C.c_ubyte * count).from_buffer(view)
                result = self._fs._lib.nxrom_read(ptr, self._id, data, count, self._position)
                if result < 0:
                    raise _error(self.name)
            self._position += result
            return result

    def close(self):
        with self._lock:
            super().close()
