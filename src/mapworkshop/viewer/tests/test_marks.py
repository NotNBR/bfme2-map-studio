"""What `mw marks` reports about the objects under a mark."""
import unittest

from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object, create
from mapworkshop.viewer.marks import describe, text


class NoVegetation:
    def template_model(self, template):
        return None


class MarkTests(unittest.TestCase):
    def test_objects_carry_the_layer_they_were_placed_with(self):
        m = create(71, 83, 3)
        add_object(m, 'Barrel', 300, 300, layer='Yard')
        add_object(m, 'Crate01', 330, 300, layer='Yard')
        add_object(m, 'Cart01', 900, 900, layer='Road')
        data = dict(map='test', map_path='no-such-project.map', updated='now',
                    marks=[dict(id=1, kind='circle', points=[[310, 300]], radius=100)])
        mark, = describe(data, assets=NoVegetation(), m=Map(m.encode()))['marks']
        self.assertEqual([(o['template'], o['layer']) for o in mark['objects']], [('Barrel', 'Yard'), ('Crate01', 'Yard')])
        self.assertEqual(mark['layers'], {'Yard': 2})
        report = text(dict(data, title='Test', playable=[700, 820], marks=[mark]))
        self.assertIn('Barrel at (300, 300) [Yard]', report)
        self.assertIn('layers: Yard 2', report)


if __name__ == '__main__':
    unittest.main()
