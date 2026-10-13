import contextlib
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from mapworkshop.formats.map import Map, Chunk, sha, differences, string, tile_offset
from mapworkshop.mapkit.author import apply_recipe
from mapworkshop.mapkit import workspace as cli
from mapworkshop.mapkit.checks.analyze import analyze, records
from maps.ithilien_frontier.build import resize
from mapworkshop.mapkit.relief import distance_to, sculpt


from mapworkshop.formats.tests.fixtures import fixture


def recipe(*operations):
    return dict(schema=1, id='test_pass', seed=123, operations=list(operations))


class WorldBuilderTests(unittest.TestCase):
    def test_relief_distance_and_water_protection(self):
        wet=np.zeros((9,9),dtype=bool);wet[4,4]=True
        distance=distance_to(wet)
        self.assertEqual(distance[4,4],0)
        self.assertEqual(distance[4,8],4)
        self.assertAlmostEqual(distance[6,6],2*2**.5)
        m=resize(self.resize_fixture().encode(),160,180)
        m.chunk('BlendTileData').data=m.chunk('BlendTileData').data.replace(string('GrassTest'),string('IthilienCliff03'))
        water=struct.pack('<II',1,7)+string('Pond')+string('Water')
        water+=struct.pack('<fB',.1,0)+string('bump')+string('sky')
        water+=struct.pack('<I6fI',3,100,100,400,100,250,400,100)+string('shader')+string('depth')
        m.chunk('StandingWaterAreas').data=water
        objects=m.chunk('ObjectsList').data
        result=sculpt(m)
        self.assertTrue(result['water_samples_unchanged'])
        self.assertGreater(result['maximum_height'],300)
        self.assertEqual(m.chunk('ObjectsList').data,objects)
        self.assertEqual(m.heightmap()['elevations'][22,22],2560)

    def resize_fixture(self):
        m = Map(fixture())
        for name in ('TriggerAreas','StandingWaveAreas','CameraAnimationList',
                     'WaypointsList','StandingWaterAreas','RiverAreas','NamedCameras'):
            version = {'StandingWaterAreas':2, 'RiverAreas':2, 'StandingWaveAreas':2,
                       'NamedCameras':2, 'CameraAnimationList':3}.get(name,1)
            m.chunks.append(Chunk(m.intern(name),version,bytes(4)))
        m.chunks.append(Chunk(m.intern('PlayerScriptsList'),1,b''))
        # The WorldInfo values resize sets, as every stock map has them.
        m.chunk('WorldInfo').data=m.encode_properties([('cameraMaxHeight',2,800.),('mapName',3,'Stock'),('mapDescription',3,'')])
        return m

    def test_resize_preserves_heights_props_and_unknown_chunks(self):
        source = self.resize_fixture().encode()
        m = resize(source,64,96)
        terrain = m.heightmap()
        self.assertEqual((terrain['width'],terrain['height'],terrain['border']),(68,100,2))
        self.assertTrue(np.all(terrain['elevations']==2560))
        self.assertEqual(m.blend()['arrays']['visible'].shape,(100,68))
        self.assertAlmostEqual(m.objects()[0]['x'],25*64/26,places=4)
        self.assertAlmostEqual(m.objects()[0]['y'],25*96/30,places=4)
        self.assertEqual(m.objects()[0]['properties'],Map(source).objects()[0]['properties'])
        self.assertEqual(m.chunk('MysteryChunk').data,Map(source).chunk('MysteryChunk').data)
        self.assertEqual(Map(m.encode()).encode(),m.encode())

    def test_resize_scales_water_and_rejects_unhandled_coordinates(self):
        m = self.resize_fixture()
        water = struct.pack('<II',1,7)+string('Ford')+string('Water')
        water += struct.pack('<fB',.1,0)+string('bump')+string('sky')
        water += struct.pack('<I6fI',3,10,10,50,10,30,40,25)+string('shader')+string('depth')
        m.chunk('StandingWaterAreas').data=water
        enlarged=resize(m.encode(),78,90)
        pond=records(enlarged,'StandingWaterAreas')[0]
        self.assertEqual(pond['points'],[(30,30),(150,30),(90,120)])
        self.assertEqual(pond['water_height'],25)
        m.chunk('TriggerAreas').data=struct.pack('<I',1)
        with self.assertRaisesRegex(ValueError,'TriggerAreas'):resize(m.encode(),78,90)
        with self.assertRaises(ValueError):resize(self.resize_fixture().encode(),1024,96)

    def test_native_texture_subtiles_follow_cell_order(self):
        self.assertEqual([tile_offset(x,0,4) for x in range(8)], [0,1,4,5,8,9,12,13])
        self.assertEqual([tile_offset(x,1,4) for x in range(4)], [2,3,6,7])
        self.assertEqual(tile_offset(220,210,4),24)  # Observed native Ithilien cell.
    def test_analysis_offsets_cover_file_and_expose_missing_sections(self):
        data = fixture()
        report = analyze(data)
        self.assertEqual(report['chunks'][-1]['end_offset'], len(data))
        self.assertTrue(report['blend_details']['tail_fully_consumed'])
        self.assertEqual(report['blend_details']['textures'], 1)
        self.assertIn('SidesList', report['unresolved_sections'])
        self.assertEqual(report['file_sha256'], sha(data))

    def test_water_geometry_is_decoded_and_truncation_is_rejected(self):
        m = Map(fixture())
        data = struct.pack('<II', 1, 7) + string('Pond') + string('Water')
        data += struct.pack('<fB', 0.1, 0) + string('bump.tga') + string('sky.tga')
        data += struct.pack('<I6fI', 3, 10, 10, 50, 10, 30, 40, 25) + string('shader') + string('depth')
        m.chunks.append(Chunk(m.intern('StandingWaterAreas'), 2, data))
        water = records(m, 'StandingWaterAreas')
        self.assertEqual(water[0]['points'], [(10, 10), (50, 10), (30, 40)])
        self.assertEqual(water[0]['water_height'], 25)
        m.chunk('StandingWaterAreas').data = data[:-1]
        with self.assertRaises(ValueError): records(m, 'StandingWaterAreas')

    def test_lossless_and_row_padded_flags(self):
        data = fixture()
        m = Map(data)
        self.assertEqual(m.encode(), data)
        self.assertTrue(m.report()['raw_roundtrip_exact'])
        self.assertEqual(m.blend()['textures'][0]['name'], 'GrassTest')
        self.assertEqual(m.blend()['arrays']['visible'].shape, (34, 30))

    def test_corrupt_count_and_truncation_rejected(self):
        m = Map(fixture())
        m.chunk('BlendTileData').data = struct.pack('<I', 99) + m.chunk('BlendTileData').data[4:]
        with self.assertRaises(ValueError): m.report()
        with self.assertRaises(ValueError): Map(fixture()[:-1])

    def test_terrain_and_paint_preserve_unrelated_bytes(self):
        data = fixture()
        out, diff = apply_recipe(data, recipe(
            dict(op='raise', x=120, y=120, radius=65, amount=12),
            dict(op='paint', x=120, y=120, radius=30, texture='GrassTest')))
        m, before = Map(out), Map(data)
        self.assertEqual(set(diff['changed_chunks']), {'HeightMapData', 'BlendTileData'})
        self.assertEqual(m.chunk('MysteryChunk').data, before.chunk('MysteryChunk').data)
        self.assertEqual(m.chunk('ObjectsList').data, before.chunk('ObjectsList').data)
        self.assertEqual(m.heightmap()['elevations'][14, 14], round(112 / 0.0390625))
        self.assertTrue(np.array_equal(m.heightmap()['elevations'][:2], before.heightmap()['elevations'][:2]))
        self.assertEqual(m.blend()['arrays']['tiles'][14, 14], 60)

    def test_seeded_scatter_names_spacing_exclusions_and_replay(self):
        data = fixture()
        rec = recipe(dict(op='scatter', template='TreeEvergreen03', count=12, rect=[10, 10, 250, 290], spacing=20))
        rec['exclude_rects'] = [[70, 70, 170, 170]]
        out, _ = apply_recipe(data, rec)
        self.assertEqual(out, apply_recipe(data, rec)[0])
        objs = Map(out).objects()
        self.assertEqual(len(objs), 13)
        identifiers = [v for o in objs for k, _, v in o['properties'] if k == 'uniqueID']
        self.assertEqual(len(set(identifiers)), 13)
        for i, obj in enumerate(objs[1:], 1):
            self.assertFalse(70 <= obj['x'] <= 170 and 70 <= obj['y'] <= 170)
            for earlier in objs[:i]:
                self.assertGreaterEqual((obj['x']-earlier['x'])**2 + (obj['y']-earlier['y'])**2, 399.99)
        with self.assertRaises(ValueError): apply_recipe(out, rec)

    def test_overcrowded_recipe_fails_without_mutating_source(self):
        data = fixture()
        expected = sha(data)
        with self.assertRaises(ValueError):
            apply_recipe(data, recipe(dict(op='scatter', template='TreeEvergreen03', count=20, rect=[10,10,20,20], spacing=100)))
        self.assertEqual(sha(data), expected)

    def test_invalid_brush_and_unsupported_action(self):
        for operation in [dict(op='resize'), dict(op='raise', x=20, y=20, radius=0, amount=1),
                          dict(op='raise', x=20, y=20, radius=20, amount=float('nan'))]:
            with self.assertRaises(ValueError): apply_recipe(fixture(), recipe(operation))

    def test_diff_includes_added_chunk(self):
        a, b = Map(fixture()), Map(fixture())
        b.chunks.append(Chunk(b.intern('AnotherChunk'), 1, b'new'))
        self.assertIn('AnotherChunk', differences(a, b)['changed_chunks'])

    def test_workspace_transactions_reject_stale_hash_and_preserve_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / 'source'; src.mkdir()
            source = src / 'original.map'; source.write_bytes(fixture())
            (src / 'map.ini').write_text('; original sidecar')
            rec = root / 'recipe.json'; rec.write_text(json.dumps(recipe(dict(op='raise', x=120,y=120,radius=50,amount=10))))
            with patch.object(cli, 'WORKSPACES', root / 'workspaces'), contextlib.redirect_stdout(io.StringIO()):
                cli.main(['checkout', str(source), 'demo'])
                target = cli.working_file('demo')
                with self.assertRaises(ValueError): cli.main(['apply', 'demo', str(rec), '--expect-sha', 'stale'])
                self.assertEqual(target.read_bytes(), fixture())
                cli.main(['apply', 'demo', str(rec), '--expect-sha', sha(target.read_bytes())])
                self.assertNotEqual(target.read_bytes(), fixture())
                self.assertEqual(source.read_bytes(), fixture())
                self.assertEqual(len(list((cli.workspace('demo') / 'checkpoints').iterdir())), 3)
                self.assertTrue((cli.workspace('demo') / 'preview.png').exists())
                with self.assertRaises(ValueError): cli.main(['apply', 'demo', str(rec), '--expect-sha', sha(target.read_bytes())])
                with self.assertRaises(ValueError): cli.workspace('../escape')


if __name__ == '__main__':
    unittest.main()
