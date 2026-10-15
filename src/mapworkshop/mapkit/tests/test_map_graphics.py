"""Independent geometry and classification checks for read-only diagnostics."""
import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image

from mapworkshop.mapkit.graphics import (Scene, Templates, spacing, viewport, water_mask,
                                        resolve, elevation_colors, elevation_limits,
                                        elevation_plan, main)
from mapworkshop.mapkit.blank import create, set_heights


class MapGraphicsTests(unittest.TestCase):
    def temporary(self):
        from mapworkshop.config import ROOT
        base=ROOT/'local/cache/tests/map-graphics'
        base.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def test_world_origin_and_north_match_flipped_raster(self):
        z=np.array([[10.,10.],[100.,100.]])
        scene=Scene('Orientation','test',z,np.zeros((2,2),bool),np.zeros((2,2),bool),
                    np.zeros((2,2,3),dtype=np.uint8),[],[],[],{}, {})
        image,pixel,scale=viewport(scene,20,20,'relief')
        self.assertEqual(pixel((0,0)),(0,19))
        self.assertEqual(pixel((10,10)),(10,9))
        self.assertGreater(image.getpixel((0,0))[0],image.getpixel((0,19))[0])

    def test_water_polygon_does_not_flood_higher_ground(self):
        from unittest.mock import patch
        m=create(64,64,3)
        z=np.full((64,64),100.)
        z[1,1]=150.
        def decoded(map_object,name):
            return [dict(points=[(0,0),(40,0),(40,30),(0,30)],water_height=110)] if name=='StandingWaterAreas' else []
        with patch(water_mask.__module__+'.records',decoded):
            mask=water_mask(m,z)
        self.assertTrue(mask[0,0])
        self.assertFalse(mask[1,1])
        self.assertFalse(mask[10,10])

    def test_classification_follows_inheritance_and_keeps_deadwood_separate(self):
        with self.temporary() as folder:
            p=Path(folder)
            (p/'naturetrees.ini').write_text('Object Base\n KindOf = TREE IMMOBILE\nEnd\nObjectReskin Living Base\nEnd\nChildObject TreeDead01 Living\nEnd\n')
            templates=Templates(p)
            self.assertEqual(templates.category(dict(template='Living',flags=0)),'tree')
            self.assertEqual(templates.category(dict(template='TreeDead01',flags=0)),'deadwood')
            self.assertEqual(templates.category(dict(template='Unknown',flags=0)),'gameplay/other')

    def test_small_tree_sets_have_defined_statistics(self):
        a=[dict(template='A',x=0,y=0),dict(template='A',x=30,y=40)]
        self.assertIsNone(spacing([],[],True))
        self.assertIsNone(spacing(a[:1],a[:1],True))
        stats=spacing(a,a,True)
        self.assertEqual(stats['nearest_p10_p50_p90'],[50.,50.,50.])
        self.assertIsNone(stats['median_fifth_neighbor'])
        a[1]['x']=a[1]['y']=0
        self.assertEqual(spacing(a,a,True)['nearest_p10_p50_p90'],[0.,0.,0.])

    def test_config_paths_normalize_parent_directory(self):
        with self.temporary() as folder:
            p=Path(folder);(p/'config').mkdir();(p/'input.map').write_bytes(b'test')
            self.assertEqual(resolve('../input.map',p/'config'),p/'input.map')

    def test_elevation_scale_is_shared_clipped_and_handles_flat_maps(self):
        scenes = [SimpleNamespace(z=np.array([100.,200.])),
                  SimpleNamespace(z=np.array([200.,500.]))]
        limits = elevation_limits(scenes)
        self.assertEqual(limits, (100.,500.))
        first, second = [elevation_colors(s.z, limits) for s in scenes]
        np.testing.assert_array_equal(first[1], second[0])
        clipped = elevation_colors(np.array([0,100,500,600]), limits)
        np.testing.assert_array_equal(clipped[0], clipped[1])
        np.testing.assert_array_equal(clipped[2], clipped[3])
        self.assertEqual(elevation_limits([SimpleNamespace(z=np.full((2,2),200.))]),
                         (199.5,200.5))
        for invalid in ((1,1),(2,1),(0,float('inf')),(float('nan'),1)):
            with self.assertRaises(ValueError):
                elevation_limits(scenes, invalid)

    def test_elevation_keeps_riverbed_height_and_north_up(self):
        z = np.array([[100.,100.],[300.,300.]])
        scene = Scene('Elevation', 'test', z, np.ones((2,2),bool),
                      np.zeros((2,2),bool), np.zeros((2,2,3),np.uint8), [],[],[],{}, {})
        plan = elevation_plan(scene, (100,300))
        expected = elevation_colors(np.array([100,300]), (100,300))
        self.assertEqual(plan.getpixel((plan.width//2,71)), tuple(expected[1]))
        self.assertEqual(plan.getpixel((plan.width//2,1168)), tuple(expected[0]))

    def test_cli_exports_elevation_scale_and_gallery_without_changing_map(self):
        with self.temporary() as folder:
            root = Path(folder)
            m = create(64,64,3)
            shape = m.heightmap()['elevations'].shape
            heights = np.full(shape, 200.)
            heights[3,3], heights[4,4] = 100., 300.
            set_heights(m, heights)
            source = m.encode()
            path = root/'input.map'
            path.write_bytes(source)
            ini = root/'ini'
            ini.mkdir()
            (ini/'object.ini').write_text('Object Test\n KindOf = IMMOBILE\nEnd\n')
            out = root/'output'
            self.assertEqual(main(['--map',str(path),'--name','Elevation test','--ini',str(ini),
                                   '--out',str(out),'--height-range','150','250','--columns','1']),0)
            metrics = json.loads((out/'metrics.json').read_text())
            self.assertEqual(metrics['options']['height_range'],[150,250])
            self.assertEqual(metrics['maps'][0]['height_range'],[100,300])
            self.assertEqual(metrics['maps'][0]['elevation_scale'],dict(range=[150,250],
                             units='map units',below_range_samples=1,above_range_samples=1))
            with Image.open(out/'elevation-test/elevation.png') as image:
                self.assertEqual(image.mode,'RGB')
            page = (out/'index.html').read_text(encoding='utf-8')
            self.assertIn('value="elevation-test/elevation.png"',page)
            self.assertIn('value="elevation-test/slope.png"',page)
            self.assertEqual(path.read_bytes(),source)


if __name__=='__main__':
    unittest.main()
