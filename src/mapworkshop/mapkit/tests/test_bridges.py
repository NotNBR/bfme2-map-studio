"""Spanned bridges (mapkit.bridges): types, the section check and the endpoints."""
import unittest

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import create
from mapworkshop.mapkit.bridges import END, START, add_bridge, bridge_type, bridge_types, check_type
from mapworkshop.mapkit.roads import inspect

ROADS = """
Bridge TEST_Arc
  BridgeScale = 0.6
  BridgeModelName = ArcModel
End
Bridge TEST_Plank
  BridgeModelName = PlankModel
End
"""


class Assets:
    """Two models: one with the three bridge pieces, one in one piece."""
    models = {'arcmodel': b'ARCMODEL.BRIDGE_LEFT ARCMODEL.BRIDGE_SPAN ARCMODEL.BRIDGE_RIGHT',
              'plankmodel': b'PLANKMODEL.DECK'}

    def ini_text(self, relative):
        return ROADS

    def model_key(self, model):
        return model.lower() if model.lower() in self.models else None

    def read(self, key):
        return self.models[key]


class BridgeTests(unittest.TestCase):
    def test_types_from_ini_and_written_types_read_back(self):
        self.assertEqual(bridge_types(ROADS)['TEST_Arc'], dict(model='ArcModel', scale=.6, texture=None))
        self.assertEqual(bridge_types(ROADS)['TEST_Plank']['scale'], 1.)
        self.assertEqual(bridge_types(bridge_type('MyBridge', 'ArcModel', scale=.8))['MyBridge'],
                         dict(model='ArcModel', scale=.8, texture='ArcModel.tga'))

    def test_only_sectional_models_pass(self):
        self.assertEqual(check_type(Assets(), 'test_arc')['model'], 'ArcModel')
        with self.assertRaisesRegex(ValueError, 'crashes the game'):
            check_type(Assets(), 'TEST_Plank')
        with self.assertRaisesRegex(ValueError, 'No Bridge type'):
            check_type(Assets(), 'Nothing')
        ini = bridge_type('MapArc', 'ArcModel')
        self.assertEqual(check_type(Assets(), 'MapArc', ini)['model'], 'ArcModel')

    def test_endpoints_are_adjacent_and_not_roads(self):
        m = create(71, 83, 3)
        add_bridge(m, 'TEST_Arc', (100, 200), (500, 200), name='ford', assets=Assets())
        objects = Map(m.encode()).objects()
        self.assertEqual([(o['template'], o['flags'], o['x']) for o in objects],
                         [('TEST_Arc', START, 100.), ('TEST_Arc', END, 500.)])
        self.assertEqual(inspect(objects)['uninterpreted_flags'], [])
        with self.assertRaises(ValueError):
            add_bridge(m, 'TEST_Arc', (100, 300), (500, 300), name='ford', assets=Assets())
        with self.assertRaises(ValueError):
            add_bridge(m, 'TEST_Arc', (100, 300), (105, 300), name='short', assets=Assets())


if __name__ == '__main__':
    unittest.main()
