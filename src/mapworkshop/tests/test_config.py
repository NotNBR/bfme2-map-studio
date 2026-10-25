"""config.save_setting keeps every other setting as it was, whatever its type."""
from datetime import date
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from mapworkshop import config


class SaveSettingTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp())/'config.toml'
        self.addCleanup(lambda: __import__('shutil').rmtree(self.path.parent, True))
        patcher = mock.patch.object(config, 'CONFIG', self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_other_settings_survive_with_their_types(self):
        self.path.write_text('game = "C:\\\\Games\\\\BFME2"\nfps = 60\nscale = 1.5\nfog = true\nsince = 2026-10-19\n'
                             'maps = ["a", "b"]\n"odd key" = "x\\ty"\n\n[viewer]\nsize = "1600x900"\n'
                             '\n[viewer.photo]\nev = -0.5\n', encoding='utf-8')
        before = tomllib.loads(self.path.read_text(encoding='utf-8'))
        config.save_setting('last_map', 'greywater-marches')
        after = tomllib.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(after, dict(before, last_map='greywater-marches'))
        self.assertEqual(after['since'], date(2026, 10, 19))

    def test_a_bool_or_number_is_saved_as_one_anything_else_as_text(self):
        config.save_setting('fps', 120)
        config.save_setting('game', Path('C:/Games/BFME2'))
        values = tomllib.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(values, dict(fps=120, game=str(Path('C:/Games/BFME2'))))

    def test_new_nested_settings_round_trip_as_tables(self):
        chosen = dict(resolution='2560x1440', grass=False, display=dict(modes=['windowed', 'borderless']))
        config.save_setting('test_settings', chosen)
        config.save_setting('last_map', 'blend-lab')
        self.assertEqual(config.setting('test_settings'), chosen)
        chosen['grass'] = True
        config.save_setting('test_settings', chosen)
        self.assertEqual(config.settings(), dict(test_settings=chosen, last_map='blend-lab'))


if __name__ == '__main__':
    unittest.main()
