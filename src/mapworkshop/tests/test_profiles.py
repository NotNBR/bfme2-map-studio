"""Profile isolation and BFME2 + ROTWK archive overlays without retail data."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from mapworkshop import config, game
from mapworkshop.render.assets import GameAssets


def write_big(path, entries):
    names = [name.encode('ascii') + b'\0' for name in entries]
    offset = end = 16 + sum(8 + len(name) for name in names)
    directory = b''
    for name, payload in zip(names, entries.values()):
        directory += struct.pack('>II', offset, len(payload)) + name
        offset += len(payload)
    path.write_bytes(b'BIG4' + struct.pack('<I', offset) + struct.pack('>II', len(names), end)
                     + directory + b''.join(entries.values()))


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.base, self.expansion, self.data = (self.root/p for p in ('bfme2', 'rotwk', 'data'))
        self.base.mkdir()
        self.expansion.mkdir()
        write_big(self.base/'INI.big', {'data/ini/object/base.ini': b'Object BaseOnly\nEnd\n',
                                      'data/ini/shared.ini': b'base'})
        write_big(self.base/'Textures1.big', {'art/shared.tga': b'base', 'art/base.tga': b'base-only'})
        write_big(self.base/'Maps.big', {'maps/base/base.map': b'base-map'})
        write_big(self.expansion/'INI.big', {'data/ini/object/angmar.ini': b'Object AngmarOnly\nEnd\n',
                                           'data/ini/shared.ini': b'expansion'})
        write_big(self.expansion/'Textures1.big', {'art/shared.tga': b'expansion', 'art/angmar.tga': b'angmar'})
        write_big(self.expansion/'_patch201.big', {'data/ini/shared.ini': b'201', 'art/shared.tga': b'201'})
        write_big(self.expansion/'__patch202.big', {'data/ini/shared.ini': b'202', 'art/shared.tga': b'202'})
        write_big(self.expansion/'__HD.big', {'art/shared.tga': b'HD'})
        write_big(self.expansion/'Maps.big', {'maps/angmar/angmar.map': b'angmar-map'})

    def test_combined_library_keeps_both_games_and_patch_priority(self):
        assets = GameAssets(self.base, self.data, self.expansion)
        self.assertEqual(assets.read('art/base.tga'), b'base-only')
        self.assertEqual(assets.read('art/angmar.tga'), b'angmar')
        self.assertEqual(assets.read('art/shared.tga'), b'201')
        self.assertEqual(assets.read('data/ini/shared.ini'), b'201')
        self.assertNotIn('__patch202.big', [p.name for p in assets.archive_paths])
        self.assertNotIn('__HD.big', [p.name for p in assets.archive_paths])
        base = GameAssets(self.base, self.data)
        self.assertFalse(base.exists('art/angmar.tga'))
        self.assertEqual(base.read('art/shared.tga'), b'base')

    def test_extraction_matches_render_overlays_and_invalidates_on_base_change(self):
        with patch.object(game, 'PROFILE', 'rotwk'), patch.object(game, 'GAME_DATA', self.data), \
             patch.object(game, 'base_game_dir', return_value=self.base):
            game.extract(self.expansion, progress=None)
            self.assertTrue(game.extracted(self.expansion))
            assets = GameAssets(self.base, self.data, self.expansion)
            self.assertEqual(set(assets.templates), {'baseonly', 'angmaronly'})
            self.assertEqual(assets.ini_text('shared.ini'), '201')
            self.assertEqual((self.data/'maps/base/base.map').read_bytes(), b'base-map')
            self.assertEqual((self.data/'maps/angmar/angmar.map').read_bytes(), b'angmar-map')
            write_big(self.base/'INI.big', {'data/ini/shared.ini': b'base changed'})
            self.assertFalse(game.extracted(self.expansion))

    def test_loose_map_data_wins(self):
        (self.data/'art').mkdir(parents=True)
        (self.data/'art/shared.tga').write_bytes(b'loose')
        self.assertEqual(GameAssets(self.base, self.data, self.expansion).read('art/shared.tga'), b'loose')

    def test_runtime_uses_the_same_clean_archives_and_excludes_injection_dlls(self):
        from mapworkshop.native import rotwk
        (self.expansion/'game.dat').write_bytes(b'engine')
        (self.expansion/'dinput8.dll').write_bytes(b'foreign-hook')
        (self.expansion/'lang').mkdir()
        (self.expansion/'lang/englishpatch201.big').touch()
        (self.expansion/'lang/englishpatch202.big').touch()
        wanted = rotwk.runtime_files(self.expansion, self.base)
        names = {p.as_posix() for p in wanted}
        self.assertIn('_patch201.big', names)
        self.assertIn('game.dat', names)
        self.assertIn('lang/englishpatch201.big', names)
        for name in ('__patch202.big', '__HD.big', 'dinput8.dll', 'lang/englishpatch202.big'):
            self.assertNotIn(name, names)
        self.assertEqual({p for key, p in wanted.items() if key.name.startswith('zz_bfme2_')},
                         set(config.archive_paths(self.base)))

    def test_detection_does_not_mistake_expansion_for_base_game(self):
        (self.expansion/'game.dat').touch()
        (self.expansion/'lotrbfme2ep1.exe').touch()
        self.assertFalse(game.is_game(self.expansion))
        self.assertTrue(game.is_game(self.expansion, 'rotwk'))


class ProfileTests(unittest.TestCase):
    def snapshot(self, profile):
        script = ('import json; from mapworkshop import config as c; '
                  'print(json.dumps({k:str(getattr(c,k)) for k in '
                  "('PROFILE','GAME_DATA','BUILD','HISTORY','CACHE','MARKS','USER_MAPS','GAME_EXE')}))")
        output = subprocess.check_output([sys.executable, '-c', script],
                                         env=dict(os.environ, MW_GAME_PROFILE=profile), text=True)
        return json.loads(output)

    def test_profiles_isolate_data_and_outputs(self):
        base, expansion = self.snapshot('bfme2'), self.snapshot('rotwk')
        self.assertEqual(Path(base['GAME_DATA']), config.LOCAL/'game')
        for key in ('GAME_DATA', 'BUILD', 'HISTORY', 'CACHE', 'MARKS', 'USER_MAPS'):
            self.assertNotEqual(base[key], expansion[key], key)
        self.assertEqual(expansion['GAME_EXE'], 'lotrbfme2ep1.exe')

    def test_cli_selects_profile_before_command_import(self):
        script = ('from mapworkshop import cli; '
                  'cli.cmd_config = lambda args: print(__import__("mapworkshop.config", fromlist=["PROFILE"]).PROFILE); '
                  'cli.main(["--profile", "rotwk", "config"])')
        output = subprocess.run(
            [sys.executable, '-c', script],
            env=dict(os.environ, MW_GAME_PROFILE='bfme2'), text=True, capture_output=True)
        self.assertEqual(output.returncode, 0)
        self.assertEqual(output.stdout.strip(), 'rotwk')

    def test_native_runtime_rejects_unknown_rotwk_before_copying(self):
        from mapworkshop.native import rotwk
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'game.dat').write_bytes(b'not-the-verified-engine')
            with patch.object(rotwk, 'game_dir', return_value=root), \
                 patch.object(rotwk, 'base_game_dir', return_value=root), \
                 patch.object(rotwk, 'runtime_files') as files:
                with self.assertRaisesRegex(RuntimeError, 'no verified studio launch hooks'):
                    rotwk.prepare()
                files.assert_not_called()


class SkirmishTests(unittest.TestCase):
    def test_rotwk_slots_use_random_factions_and_easy_ai(self):
        from mapworkshop.native import rotwk
        engine = Mock(base=0x400000, res={})
        engine.u32.side_effect = [0x10000, 0x20000, 0x30000]
        self.assertFalse(rotwk.skirmish_setup(engine, 1, None))
        self.assertEqual(engine.write.call_args_list[0].args,
                         (engine.base + rotwk.GAME_INFO, struct.pack('<I', 0x10000)))
        engine.write.assert_any_call(0x20018, struct.pack('<i', -1))
        engine.write.assert_any_call(0x30018, struct.pack('<i', -1))
        engine.write.assert_any_call(0x30004, struct.pack('<I', 2))
        engine.write.assert_any_call(0x30008, b'\x01\x01')
        self.assertTrue(engine.res['skirmish_setup'])
        engine.stop.assert_not_called()

    def test_rotwk_missing_slots_stops_before_slot_writes(self):
        from mapworkshop.native import rotwk
        engine = Mock(base=0x400000, res={})
        engine.u32.side_effect = [0x10000, 0x20000, 0]
        rotwk.skirmish_setup(engine, 1, None)
        engine.stop.assert_called_once_with('missing-skirmish-slots')
        self.assertEqual(engine.write.call_count, 1)
        self.assertNotIn('skirmish_setup', engine.res)


if __name__ == '__main__':
    unittest.main()
