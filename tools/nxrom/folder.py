"""Folder inputs for the packager; the native reader owns all container identities."""
import ctypes as C
import os
from pathlib import Path


def candidates(root):
    seen = set()
    root = Path(root)
    scanned = 0
    for directory, dirs, files in os.walk(root, followlinks=False):
        here = Path(directory)
        if len(here.relative_to(root).parts) > 64:
            raise ValueError('Resource folder nesting exceeds 64 levels')
        dirs[:] = sorted(d for d in dirs if not (here / d).is_symlink()
                         and not d.endswith(('.app', '_build', '-work')) and d not in ('.git',))
        for name in sorted(files):
            scanned += 1
            if scanned > 200000:
                raise ValueError('Resource folder exceeds 200000 files; choose a narrower folder')
            p = here / name
            if p.is_symlink() or p.suffix.lower() not in ('.nsp', '.xci', '.nsz', '.xcz', '.ncz'):
                continue
            st = p.stat()
            identity = (st.st_dev, st.st_ino)
            if identity not in seen:
                seen.add(identity)
                yield p


def probe(library, path, keys):
    lib = C.CDLL(str(library), use_errno=True)
    lib.nxrom_probe_container.argtypes = [C.c_char_p, C.c_char_p, C.POINTER(C.c_int), C.POINTER(C.c_int),
                                         C.POINTER(C.c_int), C.POINTER(C.c_uint64), C.c_char_p, C.c_size_t]
    fmt, programs, patched, title = C.c_int(), C.c_int(), C.c_int(), C.c_uint64()
    error = C.create_string_buffer(512)
    if lib.nxrom_probe_container(os.fsencode(path), os.fsencode(keys), C.byref(fmt), C.byref(programs),
                                 C.byref(patched), C.byref(title), error, len(error)):
        raise OSError(C.get_errno(), error.value.decode(), str(path))
    return dict(title=title.value, patched=bool(patched.value))
