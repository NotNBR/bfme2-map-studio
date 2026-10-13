import struct
import unittest

from mapworkshop.formats.map import Chunk, Map, string
from mapworkshop.formats.terrain import terrain_records
from mapworkshop.mapkit.blank import create
from mapworkshop.mapkit.checks.analyze import records, blend_details


class LegacySectionTests(unittest.TestCase):
    def test_legacy_plane_boundaries(self):
        import numpy as np
        for version in (8,9,10,11,12,13,14,15,16,17):
            m=create(64,64,3)
            n=70*70; packed_row=9
            index_width=4 if version>=14 else 2
            planes=[('impassable',8),('impassable_players',10),('passage_widths',11),
                    ('taintable',14),('extra_passable',15),('flammability',16),('visible',17)]
            tail=m.chunk('BlendTileData').data[m.blend()['tail_offset']:]
            data=bytearray(struct.pack('<I',n)+bytes(n*(2+3*index_width)))
            expected={}
            for name,minimum in planes:
                if version>=minimum:
                    raw=bytes([1])*(n if name=='flammability' else packed_row*70)
                    expected[name]=len(data);data+=raw
            data+=tail
            m.chunk('BlendTileData').data=bytes(data);m.chunk('BlendTileData').version=version
            b=m.blend(inspection=True)
            for name,offset in expected.items():self.assertEqual(b['offsets'][name],offset)
            self.assertEqual(b['arrays']['blends'].dtype,np.dtype('<u4' if version>=14 else '<u2'))
            self.assertEqual(terrain_records(m)['blends'],[])

    def test_v14_inspection_does_not_enable_legacy_editing(self):
        m = create(64, 64, 3)
        modern = m.blend()
        chunk = m.chunk('BlendTileData')
        chunk.data = chunk.data[:modern['offsets']['extra_passable']] + chunk.data[modern['tail_offset']:]
        chunk.version = 14
        before = m.encode()
        with self.assertRaisesRegex(ValueError, 'v18'):
            m.blend()
        inspected = m.blend(inspection=True)
        self.assertEqual(len(inspected['arrays']), 8)
        self.assertNotIn('visible', inspected['arrays'])
        self.assertEqual(terrain_records(m)['blends'], [])
        self.assertEqual(before, m.encode())

    def test_unusual_palette_index_is_reported_without_clamping(self):
        m = create(64, 64, 3)
        chunk = m.chunk('BlendTileData')
        chunk.data = chunk.data[:4] + struct.pack('<H', 31501) + chunk.data[6:]
        before = m.encode()
        with self.assertRaisesRegex(ValueError, 'Tile index'):
            m.blend()
        self.assertEqual(blend_details(m)['record_issues']['tiles_outside_palette'], 1)
        self.assertEqual(m.blend(inspection=True)['arrays']['tiles'][0, 0], 31501)
        self.assertEqual(before, m.encode())

    def test_nonempty_legacy_polygon_layout(self):
        m = create(64, 64, 3)
        data = struct.pack('<I', 1) + string('LegacyWater') + string('Layer')
        data += struct.pack('<IBBI', 7, 1, 0, 0)
        data += b''.join(string(t) for t in ('river', 'noise', 'alpha', 'sparkle', 'bump', 'sky'))
        data += struct.pack('<5B3fI', 1, 10, 20, 30, 0, .25, .5, .75, 3)
        points = [(-10, 20, 7), (20, 20, 7), (20, 50, 7)]
        data += b''.join(struct.pack('<3i', *p) for p in points)
        c = Chunk(m.intern('PolygonTriggers'), 5, data)
        m.chunks.append(c)
        parsed = records(m, 'PolygonTriggers')[0]
        self.assertEqual(parsed['points'], points)
        self.assertEqual(parsed['river_rgb'], (10, 20, 30))
        c.data = data[:-1]
        with self.assertRaises(ValueError):
            records(m, 'PolygonTriggers')


if __name__ == '__main__':
    unittest.main()
