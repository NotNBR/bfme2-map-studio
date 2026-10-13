"""Independent geometry and classification checks for read-only diagnostics."""
import tempfile
import unittest
from pathlib import Path
import numpy as np

from mapworkshop.mapkit.graphics import Scene, Templates, spacing, viewport, water_mask, resolve
from mapworkshop.mapkit.blank import create


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


if __name__=='__main__':
    unittest.main()
