"""Shared native CNMT identity and conservative AOC preparation.

Ownership comes from CNMT, not title arithmetic. Index arithmetic is only a
validated compatibility constraint of the current host. Unknown metadata and
multiple revisions are errors, never a silent highest-version preference.
"""
import ctypes as C
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil

from tools.nxrom.resourcefs import ResourceFS


class Content(C.Structure):
    _fields_ = [('title', C.c_uint64), ('application', C.c_uint64),
                ('version', C.c_uint32), ('required_version', C.c_uint32),
                ('type', C.c_uint32), ('index', C.c_uint32)]


def metadata(library, path, keys):
    lib = C.CDLL(str(library), use_errno=True)
    lib.nxrom_content_meta.argtypes = [C.c_char_p, C.c_char_p, C.POINTER(Content), C.c_char_p, C.c_size_t]
    result, error = Content(), C.create_string_buffer(512)
    if lib.nxrom_content_meta(os.fsencode(path), os.fsencode(keys), C.byref(result), error, len(error)):
        raise OSError(C.get_errno(), error.value.decode(), str(path))
    return {name: getattr(result, name) for name, _ in Content._fields_}


@dataclass(frozen=True)
class AddOn:
    path: str
    title: int
    application: int
    version: int
    required_version: int
    index: int
    sha256: str


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def discover(library, root, keys, application, application_version):
    """One content discovery result; never guesses the identity of an unknown file.

    Program classification stays with the existing native Program probe. A
    damaged/metadata-free non-program container fails preflight, even when its
    name does not say DLC. A caller may present warnings but cannot silently
    discard these errors and publish a complete build.
    """
    from tools.nxrom.folder import candidates, probe
    found, warnings, unknown, errors = {}, [], [], []
    for p in candidates(root):
        if p.suffix.lower() in ('.nsz', '.ncz', '.xcz'):
            errors.append(p.name + ': compressed content is unsupported; supply an uncompressed NSP/XCI')
            unknown.append(str(p))
            continue
        try:
            facts = metadata(library, p, keys)
        except OSError as exc:
            try:
                probe(library, p, keys)  # ordinary Program NCA: existing path still works
                continue
            except OSError:
                unknown.append(str(p))
                errors.append(p.name + ': ' + str(exc.strerror))
                continue
        if facts['type'] != 0x82:
            continue
        if facts['application'] != application:
            warnings.append(p.name + ': DLC belongs to another application')
            continue
        if facts['required_version'] > application_version:
            errors.append(p.name + ': DLC requires application version ' + str(facts['required_version']))
            continue
        addon = AddOn(str(p), **{k: facts[k] for k in ('title', 'application', 'version', 'required_version', 'index')}, sha256=digest(p))
        prior = found.get(addon.title)
        if prior:
            if addon.sha256 == prior.sha256:
                warnings.append(p.name + ': duplicate DLC; identical bytes included once')
            else:
                errors.append(p.name + ': conflicting copies/revisions of DLC ' + format(addon.title, '016X'))
        else:
            found[addon.title] = addon
    return dict(dlcs=[asdict(v) for _, v in sorted(found.items())], warnings=warnings,
                unrecognized_content=unknown, errors=errors)


def prepare_inputs(library, addons, keys, application, application_version):
    """Validate real content and retain the native inventory for extraction audit.

    As upstream does, ordinary Data/PublicData RomFS files are packaged as
    resources. Their size says nothing about Shader requirements. The selected
    program's existing Shader cache identity and checks remain authoritative.
    Actual standalone executable modules need the existing module rewriter;
    detect those by their bytes, not by their names or non-empty status.
    """
    for addon in addons:
        facts = metadata(library, addon['path'], keys)
        if any(facts[k] != addon[k] for k in ('title', 'application', 'version', 'required_version', 'index')):
            raise ValueError('DLC identity changed since discovery')
        with ResourceFS(library, base=addon['path'], keys=keys, title=application,
                        aoc=True, application_version=application_version) as fs:
            fs.validate_aoc()
            inventory = {}
            for entry in fs.files():
                h = hashlib.sha256()
                with fs.open(entry.path) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        h.update(block)
                inventory[entry.path] = dict(bytes=entry.size, sha256=h.hexdigest())
            addon['files'] = inventory


def extract(addons, output, command, run):
    """Reuse upstream nx_extract --aoc; publish only a completely checked tree."""
    output = Path(output)
    if not addons:
        raise ValueError('No DLC to extract; leave AOC unset for a base-only build')
    indexes = [d['index'] for d in addons]
    if (any(type(i) is not int or not 1 <= i <= 2047 for i in indexes)
            or len(indexes) != len(set(indexes))
            or any(d['title'] != d['application'] + 0x1000 + d['index'] for d in addons)):
        raise ValueError('Invalid or conflicting AOC index/identity')
    if output.exists() or output.is_symlink():
        raise ValueError('AOC output must be new')
    partial = output.with_name(output.name + '.partial')
    partial.mkdir(parents=True, exist_ok=False)
    try:
        for addon in addons:
            if digest(addon['path']) != addon['sha256']:
                raise ValueError('DLC changed since review: ' + Path(addon['path']).name)
            dest = partial / str(addon['index'])
            run(command + ['--aoc', addon['path'], str(dest), '--aoc-title', format(addon['title'], '016X')])
            if digest(addon['path']) != addon['sha256']:
                raise ValueError('DLC changed during extraction: ' + Path(addon['path']).name)
            if not dest.is_dir() or not any(p.is_file() for p in dest.rglob('*')):
                raise ValueError('DLC extraction produced no files: ' + dest.name)
            if 'files' in addon and tree_inventory(dest) != addon['files']:
                raise ValueError('DLC extraction differs from native RomFS (missing files or path collision)')
        manifest = dict(schema=1, dlcs=[dict(d) for d in addons], files=tree_inventory(partial))
        # Never embed private source paths in the App/IPA.
        for addon in manifest['dlcs']:
            addon.pop('path', None)
        (partial / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True))
        # macOS RENAME_EXCL prevents a competing output from being overwritten.
        libc = C.CDLL(None, use_errno=True)
        rename = libc.renamex_np
        rename.argtypes = [C.c_char_p, C.c_char_p, C.c_uint]
        if rename(os.fsencode(partial), os.fsencode(output), 4):
            code = C.get_errno()
            raise OSError(code, os.strerror(code), str(output))
    except BaseException:
        shutil.rmtree(partial)
        raise


def tree_inventory(root):
    root = Path(root)
    result = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink() or not (p.is_file() or p.is_dir()):
            raise ValueError('AOC tree contains a link or special file')
        if p.is_file() and p != root / 'manifest.json':
            result[p.relative_to(root).as_posix()] = dict(bytes=p.stat().st_size, sha256=digest(p))
    return result


def audit_tree(root, application=None):
    root = Path(root)
    saved = json.loads((root / 'manifest.json').read_text())
    if saved['schema'] != 1 or saved['files'] != tree_inventory(root):
        raise ValueError('AOC resource inventory differs (missing, extra or changed files)')
    indexes = [str(d['index']) for d in saved['dlcs']]
    if not indexes or len(indexes) != len(set(indexes)):
        raise ValueError('Missing or duplicate AOC index')
    actual = {p.name for p in root.iterdir() if p.is_dir()}
    if actual != set(indexes):
        raise ValueError('AOC directory inventory differs')
    for addon in saved['dlcs']:
        if application is not None and addon['application'] != application:
            raise ValueError('AOC application mismatch')
        if not 1 <= addon['index'] <= 0x7ff or addon['title'] != addon['application'] + 0x1000 + addon['index']:
            raise ValueError('AOC index identity mismatch')
        if not any(name.startswith(str(addon['index']) + '/') for name in saved['files']):
            raise ValueError('Empty AOC index')
    return saved
