"""Placement plans: map coordinates, generic sites, flag geometry and read-only exports."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from PIL import Image

from mapworkshop import cli
from mapworkshop.assets.library import GameAssets
from mapworkshop.mapkit import blank
from mapworkshop.render import placements


def assets():
    result=GameAssets.__new__(GameAssets)
    result._templates={}
    for name,kinds,major,minor in [('Outpost','STRUCTURE IMMOBILE LINKED_TO_FLAG',40,20),
                                   ('CustomCaptureTower','STRUCTURE IMMOBILE LINKED_TO_FLAG',40,20),
                                   ('CaptureFlag','STRUCTURE IMMOBILE CAPTUREFLAG',8,8),
                                   ('DecorativeHouse','STRUCTURE IMMOBILE',40,20)]:
        result._templates[name.lower()]=dict(name=name,parent=None,
            body=f'KindOf = {kinds}\nGeometry = BOX\nGeometryMajorRadius = {major}\nGeometryMinorRadius = {minor}\nEnd\n')
    return result


class PlacementTests(unittest.TestCase):
    def temporary(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_rotated_generic_buildings_link_flags_once_and_leave_distant_flags_unmatched(self):
        m=blank.create(64,80,3)
        blank.add_object(m,'CustomCaptureTower',200,200,math.pi/2)
        blank.add_object(m,'Outpost',250,200)
        blank.add_object(m,'CaptureFlag',200,230)
        blank.add_object(m,'CaptureFlag',600,700)
        blank.add_object(m,'DecorativeHouse',400,500)
        blank.add_object(m,'FarmTemplate',500,500)
        plan=placements.analyse(m,'Generic',assets=assets())
        self.assertEqual([s['template'] for s in plan.data['sites']],['CustomCaptureTower','Outpost'])
        first,second=plan.data['sites']
        self.assertEqual(first['flag']['distance'],30)
        self.assertTrue(first['flag']['centre_inside'])
        self.assertGreater(first['flag']['overlap_cells'],0)
        self.assertIsNone(second['flag'])
        self.assertEqual(plan.data['missing_flags'],[2])
        self.assertEqual(plan.data['unmatched_flags'],[dict(x=600,y=700)])
        expanded=placements.analyse(m,'Generic',assets=assets(),scenery=True,farms=True)
        self.assertEqual(len(expanded.data['sites']),4)
        self.assertEqual(plan.data['counts']['FarmTemplate'],1) # inventory keeps hidden categories too

    def test_clear_flag_and_numeric_sixteen_start_order(self):
        m=blank.create(64,80,3)
        blank.starts(m,[(40+(i%4)*150,40+(i//4)*150) for i in range(16)])
        blank.add_object(m,'Outpost',300,300,math.pi/2)
        blank.add_object(m,'CaptureFlag',300,390)
        plan=placements.analyse(m,'Sixteen',assets=assets())
        self.assertEqual([s['number'] for s in plan.data['starts']],list(range(1,17)))
        self.assertFalse(plan.data['sites'][0]['flag']['centre_inside'])
        self.assertEqual(plan.data['sites'][0]['flag']['overlap_cells'],0)
        self.assertEqual(plan.data['size'],[640,800])

    def test_map_local_geometry_patches_inherit_the_base_without_leaking(self):
        root=self.temporary()
        m=blank.create(64,80,3)
        blank.add_object(m,'Outpost',300,300)
        blank.add_object(m,'CaptureFlag',325,300)
        source=root/'custom.map'
        source.write_bytes(m.encode())
        source.with_name('map.ini').write_text('Object Outpost\nGeometryMajorRadius = 10\nEnd\n')
        base=assets()
        plan=placements.load(str(source),assets=base)
        site=plan.data['sites'][0]
        self.assertEqual(site['geometry'][0]['major'],10)
        self.assertEqual(site['geometry'][0]['minor'],20)
        self.assertFalse(site['flag']['centre_inside'])
        other=placements.analyse(m,'Base',assets=base)
        self.assertEqual(other.data['sites'][0]['geometry'][0]['major'],40)
        self.assertTrue(other.data['sites'][0]['flag']['centre_inside'])

    def test_north_is_up_and_maps_without_sites_have_a_valid_plan(self):
        m=blank.create(64,80,3)
        heights=np.full((86,70),100.)
        heights[43:,:]=200.
        blank.set_heights(m,heights)
        image=placements.draw([placements.analyse(m,'Empty')],details=True)
        north=image.getpixel((200,200))
        south=image.getpixel((200,650))
        self.assertGreater(sum(north),sum(south))
        self.assertEqual(image.width,placements.PANEL[0])

    def test_cli_single_and_comparison_exports_preserve_map_and_ini(self):
        root=self.temporary()
        sources=[]
        for name,size in [('wide',(80,64)),('tall',(64,80))]:
            path=root/(name+'.map')
            m=blank.create(*size,3)
            blank.starts(m,[(100,100),(500,500)])
            path.write_bytes(m.encode())
            sources.append(path)
        ini=root/'map.ini'
        ini.write_bytes(b'; unchanged\r\n')
        before={p:hashlib.sha256(p.read_bytes()).digest() for p in [*sources,ini]}
        with mock.patch.object(placements,'GameAssets',return_value=assets()):
            self.assertEqual(cli.main(['placements',str(sources[0]),'--out',str(root/'single.png')]),0)
            self.assertEqual(cli.main(['placements',*(str(p) for p in sources),'--out',str(root/'both.png')]),0)
        with Image.open(root/'single.png') as single, Image.open(root/'both.png') as both:
            self.assertEqual(both.width,2*single.width)
        metadata=json.loads((root/'both.json').read_text())
        self.assertEqual(len(metadata['maps']),2)
        self.assertTrue(all(len(p['starts'])==2 for p in metadata['maps']))
        for path,digest in before.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),digest)
        with self.assertRaisesRegex(ValueError,'.png'):
            placements.export([str(sources[0])],sources[0],assets=assets())


if __name__=='__main__':
    unittest.main()
