"""OpenBFME's parts that need neither the engine nor the game: the archives
it mounts, the merged map cache, the launcher's pins, gathering game files,
the Godot project's copy, when build() imports it, the viewer's
assembly, and the submodule's cleanliness check (on a small repository of
its own)."""
import hashlib
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from mapworkshop.formats.big import BigArchive
from mapworkshop.config import ROOT
from mapworkshop.native import openbfme
from mapworkshop.native.tests.test_engine_bundle import fixture as runtime_fixture


def md5(data):
    return hashlib.md5(data).hexdigest()


class BigTests(unittest.TestCase):
    def test_written_archive_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)/'map.ini'
            source.write_bytes(b'Weather\nEnd\n')
            path = openbfme.write_big(Path(tmp)/'a.big', [('maps/mapcache.ini', b'; cache\r\n'),
                                                           ('maps/m/map.ini', source)])
            archive = BigArchive(path)
            self.assertEqual(set(archive.entries), {'maps/mapcache.ini', 'maps/m/map.ini'})
            self.assertEqual(archive.read_bytes('maps/mapcache.ini'), b'; cache\r\n')
            self.assertEqual(archive.read_bytes('maps/m/map.ini'), b'Weather\nEnd\n')
            self.assertEqual(path.read_bytes()[:4], b'BIG4')
            self.assertFalse((Path(tmp)/'a.big.part').exists())


class TestModeTests(unittest.TestCase):
    def test_compact_sixteen_player_map_packs_with_all_starts(self):
        from mapworkshop.formats.map import Map
        from mapworkshop.mapkit.cache import cache_entry
        map_file = ROOT/'maps'/'nanduhirion_compact_16p'/'references'/'compact.map'
        name = 'nanduhirion compact 16p'
        with self.assertRaisesRegex(ValueError, r'2\.\.8'):
            cache_entry(map_file, Map(map_file.read_bytes()), name, 'Compact', 'Compact')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            assets = tmp/'assets'
            (assets/'rotwk').mkdir(parents=True)
            openbfme.write_big(assets/'rotwk'/'_patch201maps.big', [('maps/mapcache.ini', b'; retail\r\n')])
            with mock.patch.multiple(openbfme, TEST=tmp/'test', ASSETS=assets):
                archive, cache = openbfme.pack_for_test(map_file, name, 'Compact')
            self.assertIn(f'maps/{name}/{name}.map', BigArchive(archive).entries)
            text = BigArchive(cache).read_bytes('maps/mapcache.ini').decode('cp1252')
            self.assertIn('  numPlayers = 16\r\n', text)
            for number in range(1, 17):
                self.assertIn(f'  Player_{number}_Start = ', text)

    def test_the_map_is_packed_with_its_cache_in_a_folder_of_its_own(self):
        from mapworkshop.mapkit.blank import create, starts
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            folder = tmp/'maps'/'my copy'
            folder.mkdir(parents=True)
            m = create(64, 64, 10, title='Mine', player_count=2)
            starts(m, [(100, 100), (500, 500)])
            (folder/'my copy.map').write_bytes(m.encode())
            (folder/'map.ini').write_bytes(b'Weather\nEnd\n')
            (folder/'notes.txt').write_bytes(b'not packed')
            retail = openbfme.write_big(tmp/'_patch201maps.big', [('maps/mapcache.ini', b'; retail\r\n')])
            (tmp/'test'/'old').mkdir(parents=True)
            with mock.patch.multiple(openbfme, TEST=tmp/'test', ASSETS=tmp/'assets'):
                (tmp/'assets'/'rotwk').mkdir(parents=True)
                retail.rename(tmp/'assets'/'rotwk'/'_patch201maps.big')
                archive, cache = openbfme.pack_for_test(folder/'my copy.map', 'map mp mine', 'Mine')
            self.assertEqual(set(BigArchive(archive).entries), {'maps/map mp mine/map mp mine.map',
                                                               'maps/map mp mine/map.ini'})
            text = BigArchive(cache).read_bytes('maps/mapcache.ini').decode('cp1252')
            self.assertTrue(text.startswith('; retail'))
            self.assertIn('MAP_20MP_20MINE_5CMAP_20MP_20MINE_2EMAP'.lower(), text.lower())
            self.assertFalse((tmp/'test'/'old').exists())                  # no viewer holds it any more
            self.assertEqual(archive.parent, cache.parent)

    def test_the_line_up_plays_with_every_slot_human(self):
        seats = [dict(faction='Elves', team=1), dict(faction=None, team=-1), dict(faction='Wild', team=0)]
        with mock.patch('mapworkshop.native.runtime.lineup', return_value=seats):
            slots = openbfme.world_slots(object())
        self.assertEqual(slots, [
            dict(player='Player_1', faction='FactionElves', human=True, team=1, start_index=0),
            dict(player='Player_2', faction='FactionMordor', human=True, team=1, start_index=1),
            dict(player='Player_3', faction='FactionWild', human=True, team=0, start_index=2)])
        self.assertEqual([s['faction'] for s in openbfme.world_slots(None)], ['FactionMen', 'FactionMordor'])


class CacheTests(unittest.TestCase):
    def test_entries_replace_their_key_and_keep_the_rest(self):
        retail = ('; FILE\r\nMapCache maps_5Ca\r\n  numPlayers = 2\r\nEND\r\n\r\n'
                  'MapCache maps_5Cb\r\n  numPlayers = 4\r\nEND\r\n')
        merged = openbfme.merged_cache(retail, ['MapCache maps_5Cb\n  numPlayers = 8\nEND\n',
                                                'MapCache maps_5Cc\n  numPlayers = 2\nEND\n'])
        self.assertNotIn('\r', merged)
        self.assertIn('MapCache maps_5Ca\n  numPlayers = 2\nEND', merged)
        self.assertEqual(merged.count('MapCache maps_5Cb'), 1)
        self.assertIn('MapCache maps_5Cb\n  numPlayers = 8\nEND', merged)
        self.assertTrue(merged.rstrip().endswith('MapCache maps_5Cc\n  numPlayers = 2\nEND'))


class PinTests(unittest.TestCase):
    def test_packages_owner_and_files(self):
        text = ('const PACKAGES := [\n'
                '\t{"key": "rotwk", "guid": "original-RotWK", "owner": "bdc6bc60-73f9-4833-9069-3076aff26418", "files": [\n'
                '\t\t["Data1.big", "ee5c0791c75a55a5123d0c21b5fd680f", 625668],\n'
                '\t\t["data/cursors/Beam.ani", "bc39ef7ee099e6815ca867b166737e9d", 3458],\n'
                '\t]},\n'
                '\t{"key": "bfme2", "guid": "original-BFME2", "owner": "0000aaaa-0000-0000-0000-000000000000", "files": [\n'
                '\t\t["INI.big", "2f24887ba2b0c1d210bc7bc2d6c62c31", 29034678],\n'
                '\t]},\n]\n')
        found = openbfme.pins(text)
        self.assertEqual(found['rotwk'][0], 'bdc6bc60-73f9-4833-9069-3076aff26418')
        self.assertEqual(found['rotwk'][1][1], ('data/cursors/Beam.ani', 'bc39ef7ee099e6815ca867b166737e9d', 3458))
        self.assertEqual(found['bfme2'][1], [('INI.big', '2f24887ba2b0c1d210bc7bc2d6c62c31', 29034678)])


class GatherTests(unittest.TestCase):
    def test_links_matching_files_and_reports_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            modded, clean, target = tmp/'modded', tmp/'clean', tmp/'assets'
            for folder, data in ((modded, b'mod'), (clean, b'retail')):
                (folder/'apt').mkdir(parents=True)
                (folder/'Data1.big').write_bytes(data)
                (folder/'apt'/'x.big').write_bytes(data)
            files = [('Data1.big', md5(b'retail'), 6), ('apt/x.big', md5(b'retail'), 6), ('Gone.big', md5(b'gone'), 4)]
            hashes = openbfme.Hashes(tmp/'md5.json')
            missing = openbfme.gather(files, target, [modded, clean], hashes)
            self.assertEqual(missing, [('Gone.big', md5(b'gone'), 4)])
            self.assertEqual((target/'Data1.big').read_bytes(), b'retail')
            self.assertEqual((target/'apt'/'x.big').read_bytes(), b'retail')
            fetched = []
            def fetch(path, digest, destination):
                fetched.append(path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b'gone')
            self.assertEqual(openbfme.gather(files, target, [modded], hashes, fetch, progress=lambda *_: None), [])
            self.assertEqual(fetched, ['Gone.big'])              # the others are kept
            hashes.save()
            self.assertEqual(openbfme.Hashes(tmp/'md5.json').known, hashes.known)


class MirrorTests(unittest.TestCase):
    def test_copies_changes_deletes_the_rest_and_keeps_what_godot_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp)/'godot', Path(tmp)/'project'
            files = ['project.godot', 'scripts/a.gd', 'scripts/old/b.gd', 'icon.png', 'icon.png.import']
            mirror = lambda: openbfme.mirror(target, {name: source/name for name in files})
            for name in files:
                (source/name).parent.mkdir(parents=True, exist_ok=True)
                (source/name).write_bytes(name.encode())
            (source/'scripts'/'stray.gd.uid').write_bytes(b'uid://source')     # untracked: not copied
            self.assertEqual(mirror(), 5)
            self.assertEqual(sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()), sorted(files))
            self.assertEqual((target/'scripts'/'a.gd').stat().st_mtime_ns, (source/'scripts'/'a.gd').stat().st_mtime_ns)
            self.assertEqual(mirror(), 0)

            written = ['.godot/uid_cache.bin', 'bin/openbfme.dll', 'scripts/a.gd.uid', 'icon.png.import']   # by Godot and the build
            for name in written:
                (target/name).parent.mkdir(parents=True, exist_ok=True)
                (target/name).write_bytes(b'generated')
            (target/'project.godot').write_bytes(b'project.godot')              # the same bytes, a newer time
            self.assertEqual(mirror(), 1)         # the tracked .import is restored
            self.assertEqual((target/'icon.png.import').read_bytes(), b'icon.png.import')
            self.assertEqual((target/'scripts'/'a.gd.uid').read_bytes(), b'generated')

            (source/'scripts'/'a.gd').write_bytes(b'changed')
            files.remove('scripts/old/b.gd')
            (target/'scripts'/'old'/'b.gd.uid').write_bytes(b'generated')
            self.assertEqual(mirror(), 3)         # a.gd copied, b.gd and its .uid deleted
            self.assertEqual((target/'scripts'/'a.gd').read_bytes(), b'changed')
            self.assertFalse((target/'scripts'/'old').exists())
            self.assertTrue(all((target/name).exists() for name in written))

            (source/'icon.png').unlink()                                        # tracked, gone from the working tree
            (source/'scripts'/'a.gd').unlink()
            (source/'scripts'/'a.gd').mkdir()                                   # a file that became a folder
            (source/'scripts'/'a.gd'/'c.gd').write_bytes(b'c')
            files[files.index('scripts/a.gd')] = 'scripts/a.gd/c.gd'
            self.assertEqual(mirror(), 4)         # icon.png, a.gd and its .uid deleted, c.gd copied
            self.assertFalse((target/'icon.png').exists())
            self.assertEqual((target/'scripts'/'a.gd'/'c.gd').read_bytes(), b'c')


class BuildTests(unittest.TestCase):
    def test_an_import_that_failed_runs_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp, links, imports = Path(tmp), [], []
            (tmp/'src'/'godot').mkdir(parents=True)
            (tmp/'src'/'godot'/'project.godot').write_bytes(b'project')

            def link(llvm, progress):
                links.append(llvm)
                (tmp/'project'/openbfme.DLL).parent.mkdir(parents=True, exist_ok=True)
                (tmp/'project'/openbfme.DLL).write_bytes(b'dll')

            def run(args, **kwargs):                                            # Godot's import, failing the second time
                imports.append(args)
                return subprocess.CompletedProcess(args, int(len(imports) == 2), '', 'error')

            with mock.patch.multiple(openbfme, SOURCE=tmp/'src', PROJECT=tmp/'project', BUILD=tmp/'build', LOGS=tmp/'logs',
                                     APPDATA=tmp/'appdata', source=lambda progress: None,
                                     setting=lambda key, default=None: default,  # source-build test, independent of the user's bundle
                                     toolchain=lambda progress: (tmp, 'gui', 'console'), _stamp=lambda: 'stamp',
                                     _compile=link, _git=lambda *args, **kwargs: 'godot/project.godot'), \
                    mock.patch.object(subprocess, 'run', run):
                build = lambda: openbfme.build(progress=lambda *_: None)
                build()                                                         # compiled and imported
                (tmp/'project'/'project.godot').unlink()                        # the copy changed: imported again, failing
                self.assertRaises(RuntimeError, build)
                build()                                                         # nothing changed since, but the import is due
                build()
            self.assertEqual((len(links), len(imports)), (1, 3))
            self.assertFalse((tmp/'logs'/'import-project.pending').exists())


class AssembleTests(unittest.TestCase):
    def test_the_viewer_gets_the_library_and_its_shaders_and_assembles_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp, imports = Path(tmp), []
            bundle = runtime_fixture(tmp)
            files = {'studio/project.godot': b'studio', 'studio/scripts/viewer.gd': b'extends Node3D',
                     'studio/.godot/uid_cache.bin': b''}
            for name, data in files.items():
                (tmp/name).parent.mkdir(parents=True, exist_ok=True)
                (tmp/name).write_bytes(data)

            def run(args, **kwargs):                                            # Godot's import
                imports.append(args)
                return subprocess.CompletedProcess(args, 0, '', '')

            with mock.patch.multiple(openbfme, SOURCE=tmp/'src', PROJECT=tmp/'project', VIEWER=tmp/'viewer', STUDIO=tmp/'studio',
                                     LOGS=tmp/'logs', APPDATA=tmp/'appdata', build=lambda progress: ('gui', 'console'),
                                     runtime_bundle=lambda *args: bundle), \
                    mock.patch.object(subprocess, 'run', run):
                (tmp/'logs').mkdir()
                self.assertEqual(set(openbfme.viewer_files()),
                                 {'project.godot', 'scripts/viewer.gd', 'studio_runtime.json'} | set(bundle.files('viewer')))
                openbfme.assemble(progress=lambda *_: None)
                before = {p: p.stat().st_mtime_ns for p in (tmp/'viewer').rglob('*')}
                openbfme.assemble(progress=lambda *_: None)                     # the same again: nothing copied or imported
                self.assertEqual({p: p.stat().st_mtime_ns for p in (tmp/'viewer').rglob('*')}, before)
                self.assertEqual(len(imports), 1)
                self.assertEqual((tmp/'viewer'/openbfme.DLL).read_bytes(), b'extension')

                (tmp/'studio'/'shaders').mkdir()
                (tmp/'studio'/'shaders'/'road.gdshader').write_bytes(b'')       # the studio's own file under OpenBFME's name
                self.assertRaises(RuntimeError, openbfme.viewer_files)


class DifferencesTests(unittest.TestCase):
    def test_clean_with_lfs_off_and_each_kind_of_dirt(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, config = Path(tmp)/'repo', Path(tmp)/'gitconfig'
            repo.mkdir()
            config.write_text('')
            alone = dict(GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@t',
                         GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@t')             # neither the user's nor the system's
            with mock.patch.dict(os.environ, alone):
                def git(*args):
                    return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True).stdout
                (repo/'.gitattributes').write_text('*.png filter=lfs diff=lfs merge=lfs -text\n')
                (repo/'.gitignore').write_text('bin/\n')
                (repo/'icon.png').write_bytes(b'\x89PNG stored plain')                  # as upstream's four are
                (repo/'a.gd').write_text('extends Node\n')
                git('init', '-q')
                git('add', '.')
                git('commit', '-qm', 'one')
                head = git('rev-parse', 'HEAD').strip()
                git('config', 'filter.lfs.clean', 'sed s/PNG/LFS/')                    # Git LFS on: the PNG reads as changed
                os.utime(repo/'icon.png', (time.time() + 60,)*2)
                self.assertEqual(git('status', '--porcelain'), ' M icon.png\n')
                self.assertEqual(openbfme.differences(repo, head), [])

                self.assertEqual(openbfme.differences(repo, '0'*40), [f'at {head[:8]} instead of the recorded 00000000'])
                (repo/'bin').mkdir()
                (repo/'bin'/'openbfme.dll').write_bytes(b'')
                (repo/'a.gd.uid').write_text('uid://a')
                (repo/'a.gd').write_text('extends Node3D\n')
                self.assertCountEqual(openbfme.differences(repo, head), [' M a.gd', '?? a.gd.uid', '!! bin/'])
            self.assertEqual(openbfme.differences(Path(tmp)/'elsewhere', head), ['not checked out'])


if __name__ == '__main__':
    unittest.main()


class QuickSettingsTests(unittest.TestCase):
    def test_only_supported_settings_are_accepted(self):
        values = openbfme.test_settings(dict(resolution='--headless', window_mode='bad', quality='bad', grass='false', fog=True, extra='x'))
        self.assertEqual(values, dict(openbfme.TEST_DEFAULTS, fog=True))

    def test_display_choices_preserve_other_game_settings(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(openbfme, 'APPDATA', Path(tmp)):
            path = Path(tmp)/'Godot/app_userdata/OpenBFME/openbfme-display.cfg'
            path.parent.mkdir(parents=True)
            path.write_text('[display]\nresolution="2560x1440"\nvsync="on"\nrender_scale=0.75\n', encoding='utf-8')
            openbfme.apply_test_display(openbfme.test_settings(dict(resolution='1920x1080', window_mode='windowed')))
            text = path.read_text(encoding='utf-8')
            self.assertIn('resolution="1920x1080"', text)
            self.assertIn('render_scale=0.75', text)
            self.assertIn('vsync="on"', text)
            before = path.read_bytes()
            openbfme.apply_test_display(openbfme.test_settings())
            self.assertEqual(before, path.read_bytes())

    def test_quality_preset_replaces_custom_overrides_and_preserves_other_options(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(openbfme, 'APPDATA', Path(tmp)):
            path = Path(tmp)/'Godot/app_userdata/OpenBFME/Options.ini'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'; my settings\r\nStaticGameLOD = Custom\r\nTextureQualityLOD = Low\r\n'
                             b'EffectsLOD = VeryLow\r\nOpenBFMEAntiAliasing = taa\r\nMusicVolume = 47')
            openbfme.apply_test_quality(openbfme.test_settings(dict(quality='UltraHigh')))
            self.assertEqual(path.read_bytes(), b'; my settings\r\nOpenBFMEAntiAliasing = taa\r\n'
                             b'MusicVolume = 47\r\nStaticGameLOD = UltraHigh\r\n')
            before = path.read_bytes()
            openbfme.apply_test_quality(openbfme.test_settings())
            self.assertEqual(path.read_bytes(), before)

    def test_quality_default_does_not_create_options_but_an_explicit_preset_does(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(openbfme, 'APPDATA', Path(tmp)):
            path = Path(tmp)/'Godot/app_userdata/OpenBFME/Options.ini'
            openbfme.apply_test_quality(openbfme.test_settings())
            self.assertFalse(path.exists())
            openbfme.apply_test_quality(openbfme.test_settings(dict(quality='Low')))
            self.assertEqual(path.read_text(), 'StaticGameLOD = Low\n')

    def test_launch_forwards_grass_and_fog_choices(self):
        with mock.patch.object(openbfme, 'prepare', return_value=('godot', 'console', {}, 'maps/test.map')), \
                mock.patch.object(openbfme, 'net_slots', return_value='human::-1:-1;easy::-1:-1'), \
                mock.patch.object(openbfme, 'apply_test_display') as display, \
                mock.patch.object(openbfme, 'apply_test_quality') as quality, \
                mock.patch.object(openbfme.subprocess, 'Popen') as spawn:
            openbfme.play(object(), settings=dict(grass=False, fog=True, resolution='1920x1080', quality='High'))
        args = spawn.call_args.args[0]
        self.assertIn('--ground-cover=off', args)
        self.assertNotIn('--no-shroud', args)
        self.assertEqual(display.call_args.args[0]['resolution'], '1920x1080')
        self.assertEqual(quality.call_args.args[0]['quality'], 'High')
