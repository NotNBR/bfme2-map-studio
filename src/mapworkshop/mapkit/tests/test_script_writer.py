"""Scripts written with the catalogue round-trip through the map's script reader."""

import unittest

from mapworkshop.formats.map import Map
from mapworkshop.formats.scripts import player_scripts
from mapworkshop.mapkit.blank import create
from mapworkshop.mapkit.script_writer import Writer, arg


class ScriptWriterTests(unittest.TestCase):
    def test_script_round_trips(self):
        m = create(64, 64, 4, player_count=2)
        w = Writer(m)
        go = w.operation('action', 'MOVE_NAMED_UNIT_TO', [arg(14, text='Scout'), arg(7, text='Hill')])
        hurt = w.operation('condition', 'UNIT_HEALTH', [arg(14, text='Scout'), arg(6, integer=0), arg(0, integer=100)])
        w.install([w.script('Go', [[hurt]], [go])], side_index=2)
        lists = player_scripts(Map(m.encode()))
        script = lists[2]['children'][0]
        self.assertTrue(lists[2]['payload_decoded'])
        self.assertEqual(script['children'][0]['children'][0]['internal_name'], 'UNIT_HEALTH')
        self.assertEqual(script['children'][1]['internal_name'], 'MOVE_NAMED_UNIT_TO')
        self.assertEqual([a['string_value'] for a in script['children'][1]['arguments']], ['Scout', 'Hill'])

    def test_wrong_signature_is_refused(self):
        w = Writer(create(64, 64, 4, player_count=2))
        with self.assertRaises(ValueError):
            w.operation('action', 'MOVE_NAMED_UNIT_TO', [arg(14, text='Scout')])
        with self.assertRaises(ValueError):
            w.operation('action', 'NO_SUCH_ACTION')


if __name__ == '__main__':
    unittest.main()
