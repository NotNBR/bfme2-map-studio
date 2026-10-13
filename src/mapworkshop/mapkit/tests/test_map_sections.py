"""Source-derived record fixtures and honest coverage reporting; no game assets."""

import struct
import unittest
from unittest.mock import patch

from mapworkshop.formats.map import Map, Chunk, string
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.blank import create, lighting
from mapworkshop.mapkit.checks.coverage import audit, section
from mapworkshop.formats.tests.fixtures import fixture


def put(m,name,version,data):
    chunk=Chunk(m.intern(name),version,data)
    m.chunks=[c for c in m.chunks if c.name_id!=chunk.name_id]+[chunk]


class MapSectionTests(unittest.TestCase):
    def test_nonempty_build_lists_in_both_locations(self):
        m=Map(fixture())
        item=string('Barracks')+string('GondorBarracks')+struct.pack('<4fBI',10,20,30,.5,1,0xffffffff)
        item+=string('OnBuilt')+struct.pack('<i3B',75,1,0,1)
        faction=m.intern('FactionMen')
        put(m,'BuildLists',1,struct.pack('<I',1)+b'\3'+faction.to_bytes(3,'little')+struct.pack('<I',1)+item)
        parsed=records(m,'BuildLists')[0]['items'][0]
        self.assertEqual(parsed['position'],(10,20,30))
        self.assertEqual(parsed['rebuilds'],0xffffffff)
        self.assertEqual(parsed['script'],'OnBuilt')
        self.assertEqual(parsed['health'],75)
        player=m.encode_properties([('playerName',3,'Player_1')])
        put(m,'SidesList',6,struct.pack('<BI',1,1)+player+struct.pack('<I',1)+item)
        self.assertEqual(records(m,'SidesList')['players'][0]['build_list'],[parsed])

    def test_environment_lighting_and_nonempty_posteffects(self):
        m=create(64,64,3)
        self.assertEqual(records(m,'EnvironmentData')['deep_water_alpha'],1)
        lights=records(m,'GlobalLighting')
        self.assertEqual([len(v) for v in lights['configurations']],[9]*4)
        self.assertEqual(lights['shadow_color_raw'],0xFFA0A0A0)
        self.assertEqual(lights['overbright_value'],1.)
        put(m,'GlobalLighting',7,lighting()[:-12])
        self.assertNotIn('final_values',records(m,'GlobalLighting'))
        put(m,'PostEffectsChunk',1,b'\1'+string('LookupTable')+struct.pack('<f',.25)+string('color.tga'))
        self.assertEqual(records(m,'PostEffectsChunk'),[dict(name='LookupTable',blend_factor=.25,lookup_image='color.tga')])

    def test_wave_fields_keep_raw_values(self):
        m=Map(fixture())
        data=struct.pack('<II',1,8)+string('Shore')+string('Water')+struct.pack('<fBI',.5,0,0)
        data+=struct.pack('<10I',0,*range(1,10))+string('wave.tga')+struct.pack('<I',1)
        put(m,'StandingWaveAreas',2,data)
        wave=records(m,'StandingWaveAreas')[0]
        self.assertEqual(wave['wave_parameters']['final_width'],1)
        self.assertEqual(wave['wave_parameters']['distance_from_shore'],9)
        self.assertEqual(wave['wave_parameters_raw'],tuple(range(1,10)))

    def test_free_and_look_camera_records(self):
        m=Map(fixture())
        header=lambda kind: kind[::-1].encode()+string('Track')+struct.pack('<2I',100,4)
        frame=struct.pack('<I',8)+b'enil'+struct.pack('<3f',1,2,3)
        free=header('free')+struct.pack('<I',1)+frame+struct.pack('<5f',0,0,0,1,.8)
        look=header('look')+struct.pack('<I',1)+frame+struct.pack('<2f',.2,.8)+struct.pack('<I',1)+frame
        put(m,'CameraAnimationList',3,struct.pack('<I',2)+free+look)
        result=records(m,'CameraAnimationList')
        self.assertEqual(result[0]['camera_frames'][0]['rotation_raw'],(0,0,0,1))
        self.assertEqual(result[1]['target_frames'][0]['look_at'],(1,2,3))
        self.assertEqual(result[1]['camera_frames'][0]['interpolation'],'line')
        put(m,'CameraAnimationList',3,struct.pack('<I',1)+free[:-1])
        with self.assertRaises(ValueError):records(m,'CameraAnimationList')

    def test_versions_and_opaque_sections_are_not_claimed_as_decoded(self):
        m=Map(fixture())
        self.assertEqual(section(m,m.chunk('MysteryChunk'))['layout'],'opaque')
        put(m,'Teams',99,bytes(4))
        self.assertEqual(section(m,m.chunk('Teams'))['layout'],'unsupported')
        with self.assertRaisesRegex(ValueError,'version'):records(m,'Teams')
        # Failure in one section must not hide other sections in a corpus survey.
        m.chunk('BlendTileData').version=14
        with patch('mapworkshop.mapkit.checks.coverage.BigArchive') as archive:
            archive.return_value.entries={'test.map':None}
            archive.return_value.read_bytes.return_value=m.encode()
            report=audit('unused.big')
        self.assertFalse(report['semantics_complete'])
        statuses={s['name']:s['layout'] for s in report['files'][0]['sections']}
        self.assertEqual(statuses['BlendTileData'],'unsupported')
        self.assertEqual(statuses['HeightMapData'],'decoded')


if __name__=='__main__':unittest.main()
