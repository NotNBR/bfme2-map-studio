"""Map properties: reading, applying and the map.toml round trip."""
import tempfile
import tomllib
import unittest
from pathlib import Path

from mapworkshop.formats.map import Map
from mapworkshop.mapkit import properties
from mapworkshop.mapkit.blank import create

INI = """; A map
Weather
  HardwareFogEnable = No ; no fog
End
Object Thing
  Draw = W3DModelDraw ModuleTag_01
    HardwareFogEnable = Yes
  End
End
"""


class IniTests(unittest.TestCase):
    def test_fields_of_top_level_blocks_only(self):
        self.assertEqual(properties.ini_fields(INI, 'Weather'), {'HardwareFogEnable': 'No'})
        self.assertEqual(properties.ini_fields(INI, 'WaterTransparency'), {})

    def test_set_replaces_in_place_and_adds_before_end(self):
        text = properties.set_ini_fields(INI, 'Weather', {'HardwareFogEnable': 'Yes', 'HardwareFogStart': '900'})
        self.assertEqual(properties.ini_fields(text, 'Weather'), {'HardwareFogEnable': 'Yes', 'HardwareFogStart': '900'})
        # The nested field of the same name inside the Object stays as it was.
        self.assertIn('    HardwareFogEnable = Yes\n  End\nEnd', text)
        self.assertEqual(text.count('Weather'), 1)

    def test_set_adds_a_missing_block(self):
        text = properties.set_ini_fields(INI, 'WaterTransparency', {'ReflectionOn': 'Yes'})
        self.assertTrue(text.startswith(INI))
        self.assertEqual(properties.ini_fields(text, 'WaterTransparency'), {'ReflectionOn': 'Yes'})


class ApplyTests(unittest.TestCase):
    def test_apply_sets_world_environment_and_ini_and_reads_back(self):
        m = create(71, 83, 3)
        overrides = properties.flatten({
            'world': {'cameraMaxHeight': 25000, 'cameraMinHeight': 150.0, 'isScenarioMultiplayer': True},
            'environment': {'deep_water_alpha': 0.5, 'macro_texture_stretched': False},
            'ini': {'WaterTransparency': {'ReflectionOn': True, 'ReflectionGuard': [10, 20]},
                    'Weather': {'HardwareFogColor': [1, 2, 3]}}})
        ini, changes = properties.apply(m, INI, overrides)
        m = Map(m.encode())
        values = properties.read(m, ini)
        for key, value in overrides.items():
            self.assertEqual(values[key], value, key)
        self.assertIn('HardwareFogColor = R:1 G:2 B:3', ini)
        self.assertIn('ReflectionGuard = X:10 Y:20', ini)
        self.assertEqual(len(changes), len(overrides))
        # Applying the same values again changes nothing.
        self.assertEqual(properties.apply(m, ini, overrides)[1], [])

    def test_unknown_property_is_refused(self):
        with self.assertRaises(ValueError):
            properties.flatten({'world': {'cameraMaxHeigth': 1.0}})
        with self.assertRaises(ValueError):
            properties.flatten({'ini': {'Weather': {'IsSnowing': 'maybe'}}})


class SaveTests(unittest.TestCase):
    def test_map_toml_keeps_comments_and_round_trips(self):
        from mapworkshop.project import Project, save_properties
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'map.toml'
            path.write_text('id = "x"\ntitle = "X"\nnative_name = "map mp x"\n'
                            'weather = "clear"   # clear, haze, rain, snow, dusk\nseed = 4\n', encoding='utf-8')
            project = Project(Path(folder), tomllib.loads(path.read_text(encoding='utf-8')))
            overrides = {('world', 'cameraMaxHeight'): 25000.0, ('ini:WaterTransparency', 'ReflectionOn'): True}
            saved = save_properties(project, overrides, {'weather': 'rain', 'description': 'A "wet" map'})
            text = path.read_text(encoding='utf-8')
            self.assertNotIn(b'\r\n', path.read_bytes())      # the repository's line endings, on Windows too
            self.assertIn('weather = "rain"   # clear, haze, rain, snow, dusk', text)
            self.assertEqual(saved.config['description'], 'A "wet" map')
            self.assertEqual(saved.config['seed'], 4)
            self.assertEqual(properties.flatten(saved.config['properties']), overrides)
            # Saving again with fewer overrides rewrites the tables, once.
            again = save_properties(saved, {('world', 'cameraMaxHeight'): 25000.0})
            text = path.read_text(encoding='utf-8')
            self.assertEqual(text.count('[properties.'), 1)
            self.assertEqual(text.count('# Map properties'), 1)
            self.assertNotIn('ReflectionOn', text)
            self.assertEqual(again.config['weather'], 'rain')
            save_properties(again, {})
            self.assertNotIn('properties', path.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
