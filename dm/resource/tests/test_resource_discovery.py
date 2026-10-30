"""Resource discovery across both Apple launchers (dm/apple/ResourceDiscovery.swift).

The module is compiled once into a small harness and driven over synthetic
folders, so every rule is exercised without a 15 GB dump: names, nesting, tags,
title IDs, keys in their own folder, several games, conflicts, a renamed
container, a mismatched build, symlinks and the legacy Documents/resources
layout. The real containers are covered by test_nxrom.py / test_mac_packaging.py.

Run: python3 test_resource_discovery.py [-v]
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SWIFT = REPO / 'dm/apple/ResourceDiscovery.swift'
HARNESS = HERE / 'discovery_cli/main.swift'
NXROM_C = REPO / 'dm/resource/nxrom.c'

sys.path.insert(0, str(HERE))
from fixture import (BUILD_ID, HEADER_KEY, AREA_KEY, TITLE, nca, pfs, romfs, with_code,  # noqa: E402
                     patch_nca, xci, gamecard, hfs0)

OTHER = 0x01002B00111A2000      # another game (a Koei Tecmo title), never this one
UPDATE_BUILD = bytes(range(0x60, 0x70))   # the update's ExeFS build id: what a prepared update matches
BASE_BUILD = BUILD_ID

FILES = {'small': b'hello', 'nested/big': bytes(range(256)) * 40}


def base_nsp(files=None, title=TITLE, build=BASE_BUILD):
    return pfs([('program.nca', with_code(nca(romfs(files or FILES), title=title), build=build))])


def update_nsp(files=None, title=TITLE, build=UPDATE_BUILD):
    new = dict(files or FILES)
    new['nested/big'] = new['nested/big'][:-400] + b'UPDATED!' * 50
    patch = patch_nca(romfs(files or FILES), romfs(new), title=title)
    return pfs([('patch.nca', with_code(patch, build=build))])


def keys_text():
    return 'header_key = ' + HEADER_KEY.hex() + '\nkey_area_key_application_00 = ' + AREA_KEY.hex() + '\n'


class Harness(unittest.TestCase):
    """Builds the harness once, then runs it over fixture folders."""

    @classmethod
    def setUpClass(cls):
        cls.build = HERE / 'build'
        if not cls.build.is_dir(): cls.build.mkdir(parents=True)
        cls.binary = cls.build / 'discovery_cli'
        obj = cls.build / 'discovery_cli_nxrom.o'
        subprocess.run(['clang', '-O1', '-c', str(NXROM_C), '-o', str(obj)], check=True)
        subprocess.run(['xcrun', 'swiftc', '-swift-version', '5', '-O', '-target', 'arm64-apple-macos26.0',
                        '-module-cache-path', str(cls.build / 'swift-cache'),
                        str(SWIFT), str(HARNESS), str(obj), '-o', str(cls.binary)],
                       check=True, capture_output=True)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=self.build, prefix='discovery-')
        self.root = Path(self.tmp.name)
        self.modules = self.root / 'App.app/Contents/Resources/program'
        self.modules.mkdir(parents=True)
        self.prepared(BASE_BUILD)     # an App prepared from the base game by default

    def tearDown(self):
        self.tmp.cleanup()

    # -- fixtures ---------------------------------------------------------
    def prepared(self, *builds, names=None):
        names = names or ['main'] * len(builds)
        for name, build in zip(names, builds):
            (self.modules / (name + '.fixups.tsv')).write_text('# BUILD_ID\t' + bytes(build).hex() + '\n')

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def put_keys(self, relative='prod.keys'):
        return self.put(relative, keys_text().encode())

    def scan(self, preferred=None, title=TITLE):
        """preferred: (base path, update path or None) - a combination the player picked."""
        cmd = [str(self.binary), str(self.root), '%016X' % title, str(self.modules)]
        if preferred: cmd += [str(preferred[0]), str(preferred[1] or '')]
        done = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def selected(self, report):
        return report.get('selection', {})

    def boot(self, documents=None, env=None):
        """Run the entry dm/ios/Sources/main.m calls, from a copy that looks like an App.

        The harness is copied next to a profile/ folder so Bundle.main resolves the
        prepared module list the way the packaged App does.
        """
        app = self.root / 'Documents/../IOS.app'
        if not app.is_dir():
            app.mkdir(parents=True)
            shutil.copyfile(self.binary, app / 'discovery_cli')
            os.chmod(app / 'discovery_cli', 0o755)
            shutil.copytree(self.modules, app / 'profile')
        cmd = [str(app / 'discovery_cli'), '--boot', str(documents or self.root), '%016X' % TITLE]
        done = subprocess.run(cmd, capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    # -- the iOS boot entry: the same call main.m makes before UIApplicationMain
    def test_boot_entry_sets_the_paths_itself(self):
        base = self.put('Super Mario Bros Wonder [010015100B514000][v0].nsp', base_nsp())
        keys = self.put_keys('keys/prod.keys')
        booted = self.boot()
        self.assertTrue(booted['ready'], booted)
        self.assertEqual(booted['env'].get('DM_RESOURCE_BACKEND'), 'nsp')
        self.assertEqual(booted['env'].get('DM_RESOURCE_NSP'), str(base))
        self.assertEqual(booted['env'].get('DM_RESOURCE_KEYS'), str(keys))
        # No update: an explicit empty value, so a path left by an earlier run of the
        # same App cannot be picked up as this game's update.
        self.assertEqual(booted['env'].get('DM_RESOURCE_UPDATE'), '')

    def test_boot_entry_explains_a_folder_without_game_files(self):
        booted = self.boot()
        self.assertFalse(booted['ready'], booted)
        self.assertIn('No NSP or XCI file', booted['message'])
        self.assertNotIn('DM_RESOURCE_NSP', booted['env'])

    def test_boot_entry_leaves_paths_an_env_file_already_set(self):
        # env.txt stays a diagnostic override: a value already in the environment wins,
        # so a stale hand-written path is reported by the host instead of being replaced.
        self.put('base.nsp', base_nsp())
        self.put_keys()
        env = dict(os.environ, DM_RESOURCE_NSP='/stale/path/base.nsp')
        booted = self.boot(env=env)
        self.assertTrue(booted['ready'], booted)
        self.assertEqual(booted['env']['DM_RESOURCE_NSP'], '/stale/path/base.nsp')

    # -- 1/2: a gamecard dump, at the root and nested ----------------------
    def test_fifa_xci_at_root(self):
        self.put('EA SPORTS FIFA 23 Nintendo Switch™ Legacy Edition [01001C8016B4E000] (US).xci',
                 xci(FILES, code=True, title=0x01001C8016B4E000))
        self.put_keys()
        report = self.scan(title=0x01001C8016B4E000)
        self.assertTrue(report['ready'], report)
        self.assertTrue(self.selected(report)['base'].endswith('™ Legacy Edition [01001C8016B4E000] (US).xci'))
        self.assertEqual(self.selected(report)['update'], '')

    def test_unusual_name_in_deep_folder(self):
        self.put('Games/Switch/2023/FIFA 23 [01001C8016B4E000]/card.xci', xci(FILES, code=True, title=0x01001C8016B4E000))
        self.put_keys('keys/prod.keys')
        report = self.scan(title=0x01001C8016B4E000)
        self.assertTrue(report['ready'], report)
        self.assertTrue(self.selected(report)['base'].endswith('Games/Switch/2023/FIFA 23 [01001C8016B4E000]/card.xci'))
        self.assertEqual(report['bases'][0]['format'], 'xci')

    # -- 3/4/5/6: the naming forms in the brief ---------------------------
    def test_base_and_update_with_version_tags(self):
        self.put('Super Mario Bros Wonder [010015100B514000][v0].nsp', base_nsp())
        self.put('Super Mario Bros. Wonder v1.2.0[010015100B514800][v262144][UPD].nsp', update_nsp())
        self.put_keys()
        self.prepared(UPDATE_BUILD)   # prepared from the update: only the pair matches
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertTrue(self.selected(report)['base'].endswith('[010015100B514000][v0].nsp'))
        self.assertTrue(self.selected(report)['update'].endswith('[010015100B514800][v262144][UPD].nsp'))
        self.assertEqual(report['updates'][0]['version'], 262144)

    def test_app_upd_prefix_names_in_different_folders(self):
        self.put('base/[APP][0100152000022000][1.0.0][US][1.0.0].nsp', base_nsp(title=0x0100152000022000))
        self.put('updates/2022/[UPD][0100152000022800][4.0.1][US][22.5.0].nsp', update_nsp(title=0x0100152000022000))
        self.put_keys('keys/2022/prod.keys')
        self.prepared(UPDATE_BUILD)
        report = self.scan(title=0x0100152000022000)
        self.assertTrue(report['ready'], report)
        self.assertIn('/updates/2022/', self.selected(report)['update'])
        self.assertIn('/keys/2022/prod.keys', self.selected(report)['keys'])

    def test_chinese_names_and_special_characters(self):
        # The brief's own examples carry spaces, brackets and ™; a Chinese dump names the
        # files and folders in Chinese too. Nothing here may depend on the byte spelling.
        base = self.put('游戏/任天堂/超级马力欧兄弟 惊奇 [010015100B514000] (简体中文).nsp', base_nsp())
        update = self.put('游戏/更新/惊奇 v1.2.0 [010015100B514800][v262144][UPD] ＆特殊字符.nsp', update_nsp())
        self.put_keys('游戏/密钥/prod.keys')
        self.prepared(UPDATE_BUILD)
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(self.selected(report)['base'], str(base))
        self.assertEqual(self.selected(report)['update'], str(update))
        self.assertEqual(report['updates'][0]['tags'], ['UPD'])

    # -- 7/8: only this game's files --------------------------------------
    def test_mixed_folder_selects_only_this_game(self):
        self.put('wonder [010015100B514000].nsp', base_nsp())
        self.put('other/Hyrule Warriors [01002B00111A2000].nsp', base_nsp(title=OTHER))
        self.put('other/Hyrule Warriors update [01002B00111A2800].nsp', update_nsp(title=OTHER))
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(len(report['bases']), 1)
        self.assertEqual(len(report['updates']), 0)
        self.assertTrue(any('01002B00111A2000' in note for note in report['notes']), report['notes'])

    # -- 9: several usable updates -----------------------------------------
    def test_two_matching_updates_are_a_conflict_and_a_choice_wins(self):
        self.put('game/base [010015100B514000].nsp', base_nsp())
        self.put('game/updates/a [010015100B514800].nsp', update_nsp())
        self.put('game/updates/b [010015100B514800].nsp', update_nsp())
        self.put_keys()
        self.prepared(UPDATE_BUILD)
        report = self.scan()
        self.assertEqual(report['state'], 'conflict', report)
        self.assertIsNone(report.get('selection'))
        self.assertEqual(len(report['combinations']), 2)
        chosen = report['combinations'][1]
        again = self.scan((chosen['base'], chosen['update']))     # the player's pick is passed back in
        self.assertTrue(again['ready'], again)
        self.assertEqual(self.selected(again)['update'], chosen['update'])

    def test_same_file_twice_is_not_a_conflict(self):
        first = self.put('game/base [010015100B514000].nsp', base_nsp())
        os.link(first, self.root / 'game/base link.nsp')
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(len(report['bases']), 1)
        self.assertTrue(any('same file' in note for note in report['notes']), report['notes'])

    # -- 10/11/12/13/14: refusals and odd inputs ---------------------------
    def test_other_title_only_is_missing_base(self):
        self.put('other [01002B00111A2000].nsp', base_nsp(title=OTHER))
        self.put_keys()
        report = self.scan()
        self.assertEqual(report['state'], 'missingBase', report)
        self.assertIn('010015100B514000', report['message'])

    def test_container_with_a_wrong_extension_is_judged_by_its_content(self):
        self.put('mislabelled.nsp', xci(FILES, code=True))          # an XCI named .nsp
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(report['bases'][0]['format'], 'xci')

    def test_file_that_is_not_a_container_is_ignored(self):
        self.put('game [010015100B514000].nsp', b'not a container at all' * 100)
        self.put('game/base.nsp', base_nsp())
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(len(report['bases']), 1)

    def test_missing_keys(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        report = self.scan()
        self.assertEqual(report['state'], 'missingKeys', report)
        self.assertIn('prod.keys', report['message'])

    def test_unusable_keys_say_what_is_missing(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put('prod.keys', b'header_key = ' + HEADER_KEY.hex().encode() + b'\n')   # no key_area_key
        report = self.scan()
        self.assertEqual(report['state'], 'missingKeys', report)
        self.assertIn('key_area_key', report['message'])

    def test_keys_content_is_never_echoed(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        report = self.scan()
        blob = json.dumps(report)
        self.assertNotIn(HEADER_KEY.hex(), blob)
        self.assertNotIn(AREA_KEY.hex(), blob)

    def test_missing_base_but_update_present(self):
        self.put('update [010015100B514800].nsp', update_nsp())
        self.put_keys()
        report = self.scan()
        self.assertEqual(report['state'], 'missingBase', report)
        self.assertIn('base game', report['message'])

    def test_nonstandard_name_is_accepted(self):
        # Wrong name and wrong extension, but container-sized: the bytes decide.
        path = self.put('stuff/backup.bin', base_nsp())
        with open(path, 'r+b') as handle:
            handle.truncate(6 << 20)      # a sparse tail: the table and NCA header stay at the front
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertTrue(self.selected(report)['base'].endswith('backup.bin'))

    def test_small_unknown_file_is_not_opened(self):
        # The scan looks into containers by name, and into anything else only when it is
        # large enough to be game data - a folder of unrelated files stays cheap.
        self.put('notes/data.bin', base_nsp())
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(len(report['bases']), 1)

    def test_compressed_container_is_reported_not_guessed(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put('update [010015100B514800].nsz', b'not decompressed' * 100)
        self.put_keys()
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertTrue(any('compressed' in note for note in report['notes']), report['notes'])

    # -- 19: the build check ------------------------------------------------
    def test_base_from_another_build_is_refused(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        self.prepared(bytes(range(0x90, 0xa0)))
        report = self.scan()
        self.assertEqual(report['state'], 'versionMismatch', report)
        self.assertIn('prepared module', report['message'])

    def test_update_that_does_not_match_is_reported_not_dropped(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put('update [010015100B514800].nsp', update_nsp())
        self.put_keys()
        self.prepared(BASE_BUILD)     # App prepared from the base game
        report = self.scan()
        self.assertEqual(report['state'], 'updateMismatch', report)
        self.assertEqual(len(report['combinations']), 1)      # the base-only fallback
        self.assertIsNone(report.get('selection'))

    def test_no_prepared_metadata_refuses_to_guess(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        for stale in self.modules.iterdir():
            stale.unlink()
        report = self.scan()
        self.assertEqual(report['state'], 'unavailable', report)

    # -- 15: the layout older builds used -----------------------------------
    def test_legacy_documents_resources_layout(self):
        self.put('resources/base.nsp', base_nsp())
        self.put('resources/update.nsp', update_nsp())
        self.put('resources/prod.keys', keys_text().encode())
        self.prepared(UPDATE_BUILD)                # the IPA was packed from that update
        report = self.scan()
        self.assertTrue(report['ready'], report)   # same files, found by content

    # -- 17: a restart finds them again -------------------------------------
    def test_scan_is_repeatable_and_ordered(self):
        self.put('b [010015100C000000].nsp', base_nsp(title=0x010015100C000000))
        self.put('a [010015100B514000].nsp', base_nsp())
        self.put_keys()
        first = self.scan()
        second = self.scan()
        self.assertEqual(first, second)
        self.assertEqual([b['name'] for b in first['bases']], ['a [010015100B514000].nsp'])

    # -- performance and file safety ---------------------------------------
    def test_scan_reads_headers_only_and_writes_nothing(self):
        self.put('game [010015100B514000].nsp', base_nsp())
        self.put('game/update [010015100B514800].nsp', update_nsp())
        self.put_keys()
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.scan()
        after = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)   # no copy, no rewrite, no new file

    def test_symlinked_folders_do_not_loop(self):
        self.put('real/base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        os.symlink(self.root / 'real', self.root / 'real/loop')            # a cycle through a folder link
        os.symlink(self.root / 'real/base [010015100B514000].nsp', self.root / 'linked.nsp')
        report = self.scan()
        self.assertTrue(report['ready'], report)
        self.assertEqual(len(report['bases']), 1)
        self.assertTrue(any('symbolic link' in note for note in report['notes']), report['notes'])

    def test_unreadable_folder_is_skipped(self):
        self.put('base [010015100B514000].nsp', base_nsp())
        self.put_keys()
        secret = self.root / 'secret'
        secret.mkdir()
        (secret / 'x').write_text('x')
        os.chmod(secret, 0o000)
        try:
            report = self.scan()
            self.assertTrue(report['ready'], report)
        finally:
            os.chmod(secret, 0o755)

    def base_with_metadata(self, version=0):
        from fixture import metadata_nca
        program = with_code(nca(romfs(FILES)))
        return self.put('base.nsp', pfs([('program.nca',program),('meta.cnmt.nca',metadata_nca(version=version))]))

    def test_dlc_multiple_owned_indices_and_boot_environment(self):
        from fixture import aoc_nsp
        self.base_with_metadata(); self.put_keys()
        one=self.put('DLC/one.nsp',aoc_nsp(files={'marker':b'one'}));two=self.put('two.nsp',aoc_nsp(index=2,files={'marker':b'two'}))
        result=self.scan(); self.assertTrue(result['ready'],result)
        self.assertEqual([d['index'] for d in result['selection']['dlcs']],[1,2])
        boot=self.boot();self.assertEqual(boot['env']['DM_AOC_NSP_1'],str(one))
        self.assertEqual(boot['env']['DM_AOC_NSP_2'],str(two))

    def test_dlc_foreign_title_never_advertised(self):
        from fixture import aoc_nsp
        self.base_with_metadata();self.put_keys();self.put('foreign.nsp',aoc_nsp(application=OTHER))
        result=self.scan();self.assertTrue(result['ready'],result)
        self.assertEqual(result['selection']['dlcs'],[])

    def test_dlc_identical_duplicate_once_conflict_stops(self):
        from fixture import aoc_nsp
        self.base_with_metadata();self.put_keys()
        blob=aoc_nsp();self.put('one.nsp',blob);self.put('copy.nsp',blob)
        result=self.scan();self.assertTrue(result['ready'],result)
        self.assertEqual(len(result['selection']['dlcs']),1)
        self.put('copy.nsp',aoc_nsp(version=65536))
        result=self.scan();self.assertFalse(result['ready'],result)
        self.assertIn('conflicting',result['message'])

    def test_dlc_nonempty_payload_is_accepted_but_required_version_still_checked(self):
        from fixture import aoc_nsp
        self.base_with_metadata();self.put_keys();p=self.put('dlc.nsp',aoc_nsp(required=65536))
        result=self.scan();self.assertFalse(result['ready'],result)
        p.write_bytes(aoc_nsp(files={'shader.bin':b'unknown'}))
        result=self.scan();self.assertTrue(result['ready'],result)
        self.assertEqual(len(result['selection']['dlcs']),1)

    def test_update_and_multiple_nonempty_dlc_keep_program_selection(self):
        from fixture import aoc_nsp,metadata_nca
        self.base_with_metadata();self.put_keys();self.prepared(UPDATE_BUILD)
        patch=with_code(patch_nca(romfs(FILES),romfs(FILES)),build=UPDATE_BUILD)
        update=self.put('update.nsp',pfs([('patch.nca',patch),('patch.cnmt.nca',
            metadata_nca(title=TITLE+0x800,application=TITLE,version=65536,meta_type=0x81))]))
        self.put('one.nsp',aoc_nsp(required=65536,files={'shared':b'one'}))
        self.put('two.nsp',aoc_nsp(index=2,required=65536,files={'shared':b'two'}))
        report=self.scan();self.assertTrue(report['ready'],report)
        self.assertEqual(report['selection']['update'],str(update))
        self.assertEqual([d['index'] for d in report['selection']['dlcs']],[1,2])

    def test_adding_and_replacing_nonempty_dlc_needs_no_app_rebuild(self):
        from fixture import aoc_nsp
        self.base_with_metadata();self.put_keys()
        self.assertEqual(self.scan()['selection']['dlcs'],[])
        before={p.name:p.read_bytes() for p in self.modules.iterdir()}
        dlc=self.put('imported.nsp',aoc_nsp(files={'payload':b'first'}))
        self.assertEqual(len(self.scan()['selection']['dlcs']),1)
        dlc.write_bytes(aoc_nsp(files={'payload':b'replacement data'}))
        self.assertEqual(len(self.scan()['selection']['dlcs']),1)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.modules.iterdir()})

    def test_dlc_removal_and_rescan_clear_old_environment(self):
        from fixture import aoc_nsp
        self.base_with_metadata();self.put_keys();p=self.put('dlc.nsp',aoc_nsp())
        self.assertEqual(len(self.scan()['selection']['dlcs']),1)
        p.unlink();self.assertEqual(self.scan()['selection']['dlcs'],[])
        result=self.boot(env=dict(os.environ,DM_AOC_NSP_1='/stale/dlc.nsp'))
        self.assertNotIn('DM_AOC_NSP_1',result['env'])

    def test_dlc_missing_application_metadata_never_guesses_version(self):
        from fixture import aoc_nsp
        self.put('base.nsp',base_nsp());self.put_keys();self.put('dlc.nsp',aoc_nsp())
        result=self.scan();self.assertFalse(result['ready'],result)
        self.assertIn('CNMT',result['message'])


if __name__ == '__main__':
    unittest.main()
