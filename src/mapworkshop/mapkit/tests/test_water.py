import unittest

from mapworkshop.formats.water import standing_water
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.blank import create


class WaterTests(unittest.TestCase):
    def area(self):
        return dict(id=7,name='Original pond',layer='Water',uv_speed=.125,additive=0,
            bump_texture='bump.tga',sky_texture='sky.tga',points=[(0.,0.),(40.,0.),(40.,30.),(0.,30.)],
            water_height=101,shader='water.w3d',depth_colors='depth.tga')

    def test_nonempty_water_roundtrip_and_bad_geometry(self):
        m=create(64,64,3);value=self.area()
        m.chunk('StandingWaterAreas').data=standing_water([value])
        self.assertEqual(records(m,'StandingWaterAreas'),[value])
        with self.assertRaisesRegex(ValueError,'Duplicate'):standing_water([value,value])
        value['points']=[(0.,0.),(1.,1.),(2.,2.)]
        with self.assertRaisesRegex(ValueError,'Degenerate'):standing_water([value])
        value['points']=[(0.,0.),(1.,1.),(2.,float('inf'))]
        with self.assertRaisesRegex(ValueError,'finite'):standing_water([value])


if __name__=='__main__':unittest.main()
