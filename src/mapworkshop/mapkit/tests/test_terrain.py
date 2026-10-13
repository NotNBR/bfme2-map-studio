"""Synthetic terrain tables; no retail map bytes or assets are redistributed."""

import struct
import unittest
from unittest.mock import patch

from mapworkshop.formats.map import Map, string
from mapworkshop.formats.terrain import terrain_records
from mapworkshop.mapkit.checks.analyze import blend_details
from mapworkshop.mapkit.checks.terrain_audit import audit
from mapworkshop.formats.tests.fixtures import fixture


def document(blends=b'', cliffs=b'', edges=b'', edge_count=0, cliff_count=None):
    m = Map(fixture())
    offset = m.blend()['tail_offset']
    tail = struct.pack('<4I', 16, len(blends) // 18 + 1,
                       len(cliffs) // 38 + 1 if cliff_count is None else cliff_count, 1)
    tail += struct.pack('<4I', 0, 16, 4, 0) + string('GrassTest')
    tail += struct.pack('<2I', 16 if edge_count else 0, edge_count) + edges + blends + cliffs
    m.chunk('BlendTileData').data = m.chunk('BlendTileData').data[:offset] + tail
    return m


class TerrainRecordTests(unittest.TestCase):
    def test_directions_flags_and_custom_edge_table(self):
        edges = struct.pack('<3I', 0, 16, 4) + string('EdgeTest')
        # Every cardinal/diagonal direction and both documented flag bits.
        blends = b''.join(struct.pack('<I4sBBiI', i, bytes(int(j == i) for j in range(4)),
                                     i, i % 2, 0, 0x7ada0000) for i in range(4))
        m = document(blends, edges=edges, edge_count=1)
        original = m.encode()
        decoded = terrain_records(m)
        self.assertEqual([r['direction'] for r in decoded['blends']],
                         ['horizontal', 'vertical', 'right_diagonal', 'left_diagonal'])
        self.assertEqual([r['inverted'] for r in decoded['blends']], [False, True, False, True])
        self.assertEqual([r['force_flip'] for r in decoded['blends']], [False, False, True, True])
        self.assertEqual(decoded['edge_textures'][0]['name'], 'EdgeTest')
        self.assertEqual(blend_details(m)['record_issues'], {})
        self.assertEqual(m.encode(), original)

    def test_cliff_uv_order_and_separate_flags(self):
        cliff = struct.pack('<I8fBB', 12, .25, .5, .75, 1., 1.25, 1.5, 1.75, 2., 1, 1)
        m = document(cliffs=cliff)
        r = terrain_records(m)['cliffs'][0]
        self.assertEqual(r['uv'], [[.25, .5], [.75, 1.], [1.25, 1.5], [1.75, 2.]])
        self.assertEqual((r['tile'], r['flip'], r['mutant']), (12, 1, 1))
        self.assertEqual(blend_details(m)['cliff_flags'], {'1,1': 1})

    def test_unusual_records_are_preserved_and_reported(self):
        blend = struct.pack('<I4sBBiI', 999, b'\xdd\0\0\0', 0x81, 9, 7, 123)
        m = document(blend)
        r = terrain_records(m)['blends'][0]
        self.assertIsNone(r['direction'])
        self.assertEqual(r['direction_hex'], 'dd000000')
        self.assertEqual(r['unknown_flag_bits'], 128)
        self.assertEqual(r['custom_edge_class'], 7)
        issues = blend_details(m)['record_issues']
        self.assertEqual(set(issues), {'unrecognized_blend_direction', 'unknown_blend_flag_bits',
                                     'nonboolean_long_diagonal', 'unexpected_blend_marker',
                                     'custom_edge_outside_table', 'blend_tile_outside_palette'})
        self.assertTrue(all(v == 1 for v in issues.values()))

    def test_empty_table_zero_count_and_corrupt_payloads(self):
        self.assertEqual(terrain_records(document(cliff_count=0))['cliffs'], [])
        cliff = struct.pack('<I8fBB', 0, *([0.] * 8), 0, 0)
        m = document(cliffs=cliff)
        m.chunk('BlendTileData').data = m.chunk('BlendTileData').data[:-1]
        with self.assertRaisesRegex(ValueError, 'Truncated'): terrain_records(m)
        m = document(edges=struct.pack('<3I', 0, 16, 4), edge_count=1)
        with self.assertRaisesRegex(ValueError, 'Truncated'): terrain_records(m)
        m = document()
        m.chunk('BlendTileData').data += b'\x00'
        with self.assertRaisesRegex(ValueError, 'trailing'): terrain_records(m)
        cliff = struct.pack('<I8fBB', 0, float('nan'), *([0.] * 7), 0, 0)
        with self.assertRaisesRegex(ValueError, 'Non-finite'): terrain_records(document(cliffs=cliff))

    def test_audit_totals_exclude_unsupported_maps_and_other_files(self):
        blend = struct.pack('<I4sBBiI', 1, b'\0\1\0\0', 2, 0, -1, 0x7ada0000)
        supported = document(blend).encode()
        old = Map(supported)
        old.chunk('BlendTileData').version = 14
        files = {'a.map': supported, 'b.map': supported, 'old.map': old.encode(), 'image.tga': b''}
        with patch('mapworkshop.mapkit.checks.terrain_audit.BigArchive') as archive:
            archive.return_value.entries = files
            archive.return_value.read_bytes.side_effect = files.__getitem__
            report = audit('unused.big')
        self.assertEqual((report['maps_checked'], report['maps_skipped']), (2, 1))
        self.assertEqual(report['blend_records'], 2)
        self.assertEqual(report['totals']['blend_directions'], {'vertical': 2})
        self.assertEqual(report['versions'], {'18': 2, '14': 1})
        self.assertEqual(report['skipped'][0]['map'], 'old.map')
        self.assertTrue(all(r['raw_roundtrip_exact'] for r in report['maps']))


if __name__ == '__main__':
    unittest.main()
