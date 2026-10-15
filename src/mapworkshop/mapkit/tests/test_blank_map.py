"""Independent invariants for the from-scratch native document writer."""
import struct
import unittest
import numpy as np
from mapworkshop.mapkit.blank import create, starts, set_materials, set_heights, set_world, water_plane
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.weather import apply_weather, weather_code
from mapworkshop.formats.map import Map, Reader, chunks
from mapworkshop.formats.terrain import terrain_records
from mapworkshop.mapkit.checks.analyze import analyze


class BlankDocumentTests(unittest.TestCase):
    def test_large_grid_requires_opt_in_and_roundtrips_at_reader_boundary(self):
        # Thin documents exercise both large axes without huge allocations.
        for width, height in [(4090, 64), (64, 4090)]:
            with self.assertRaises(ValueError):
                create(width, height, 3)
            m = create(width, height, 3, experimental_large=True)
            z = np.full((height+6, width+6), 120.)
            z[-4, -4] = 1650.
            set_heights(m, z)
            blocked = np.zeros(z.shape, bool)
            blocked[-4, -4] = True
            set_materials(m, ['A'], np.zeros(z.shape, dtype='u2'), blocked=blocked)
            loaded = Map(m.encode())
            self.assertEqual(loaded.heightmap()['borders'], [(width, height)])
            self.assertEqual(loaded.heightmap()['elevations'][-4, -4]*.0390625, 1650.)
            np.testing.assert_array_equal(loaded.blend()['arrays']['impassable'], blocked)
        for width, height in [(4091, 64), (64, 4091)]:
            with self.assertRaises(ValueError):
                create(width, height, 3, experimental_large=True)

    def test_new_plane_is_empty_and_all_supported_sections_decode(self):
        m=create(71,83,3)
        data=m.encode(); report=analyze(data)
        self.assertEqual(report['height_range'],[100,100])
        self.assertEqual(report['objects'],0)
        self.assertEqual(report['dimensions']['samples'],[77,89])
        self.assertEqual(report['unresolved_sections'],{})
        self.assertEqual(Map(data).encode(),data)
        self.assertEqual(len(m.chunk('GlobalLighting').data),1360)
        self.assertEqual(m.chunk('PostEffectsChunk').data,b'\0')

    def test_starts_preserve_plane_and_use_distinct_native_ids(self):
        m=create(71,83,3); original=m.chunk('HeightMapData').data
        starts(m,[(200,250),(500,550)])
        objects=Map(m.encode()).objects()
        self.assertEqual(len(objects),2)
        self.assertEqual(m.chunk('HeightMapData').data,original)
        self.assertEqual([dict((k,v) for k,_,v in o['properties'])['waypointID'] for o in objects],[1,2])

    def test_non_byte_aligned_bit_planes_and_blend_ranges(self):
        m=create(71,83,3); labels=np.zeros((89,77),dtype='u2');labels[:,38:]=1
        blocked=np.zeros_like(labels);blocked[8,76]=1;blocked[88,0]=1
        set_materials(m,['A','B'],labels,blocked)
        b=Map(m.encode()).blend()
        np.testing.assert_array_equal(b['arrays']['impassable'],blocked)
        self.assertTrue((b['arrays']['visible']==1).all())
        self.assertEqual(int(b['arrays']['blends'][30,37])>0,True)
        # First tile of each 2x2 cell row increments by four, not two.
        self.assertEqual(list(b['arrays']['tiles'][0,:4]),[0,1,4,5])
        self.assertLess(int(b['arrays']['tiles'].max()),128)
        self.assertTrue(analyze(m.encode())['blend_details']['tail_fully_consumed'])

    def test_corner_blends_fill_enclosed_cells_and_use_the_three_way_layer(self):
        def blend(labels):
            m=create(64,64,3)
            set_materials(m,['A','B','C'],labels,cell_sizes=[1,1,1],corner_blends=True)
            doc=Map(m.encode()); b=doc.blend(); b['blend_records']=terrain_records(doc,b)['blends']
            texture=lambda tile:next(i for i,t in enumerate(b['textures']) if t['tile_start']<=tile<t['tile_start']+t['tile_count'])
            return b,texture
        # A lone cell has no blend that covers it: it takes its neighbours' texture.
        labels=np.zeros((70,70),dtype="u2");labels[9:12,9:12]=1;labels[10,10]=0
        b,texture=blend(labels)
        self.assertEqual(texture(int(b['arrays']['tiles'][10,10])),1)
        self.assertEqual(int(b['arrays']['blends'][10,10]),0)
        # Where two higher textures meet a cell, the lower one is the primary blend, the higher one on top.
        labels=np.zeros((70,70),dtype="u2");labels[:,12:]=1;labels[12:,:]=2
        b,texture=blend(labels)
        records={r['index']:r for r in b['blend_records']}
        primary,extra=int(b['arrays']['blends'][11,11]),int(b['arrays']['three_way'][11,11])
        self.assertTrue(primary and extra)
        self.assertEqual((texture(records[primary]['tile']),texture(records[extra]['tile'])),(1,2))
        self.assertFalse(any(r['flags']&2 for r in b['blend_records']))
        self.assertFalse(((b['arrays']['three_way']>0)&(b['arrays']['blends']==0)).any())
        # One texture on opposite corners: a single-corner blend in each layer.
        labels=np.zeros((70,70),dtype="u2");labels[9,9]=1;labels[11,11]=1
        b,_=blend(labels)
        self.assertTrue(int(b['arrays']['blends'][10,10]) and int(b['arrays']['three_way'][10,10]))

    def test_invalid_elevations_are_rejected_before_writing(self):
        m=create(64,64,3)
        for bad in [float('nan'),-1,2600]:
            with self.assertRaises(ValueError):set_heights(m,np.full((70,70),bad))


    def test_eight_player_document_has_matching_sides_scripts_and_starts(self):
        m=create(100,100,3,player_count=8)
        starts(m,[(100+i*90,400) for i in range(8)])
        report=analyze(m.encode())
        self.assertEqual(len(report['waypoints']),8)
        sides=Reader(m.chunk('SidesList').data)
        self.assertEqual(sides.get('BI'),(1,18))
        for chunk_name in ['PlayerScriptsList','LibraryMapLists']:
            self.assertEqual(len(chunks(m.chunk(chunk_name).data,m.names)),18)
        self.assertEqual(len(chunks(m.chunk('MPPositionList').data,m.names)),8)
        with self.assertRaises(ValueError):create(player_count=9)

    def test_world_info_values_change_by_name(self):
        m=create(71,83,3,title='Vale',description='A quiet vale.')
        set_world(m,cameraMaxHeight=30000.)
        world={k:v for k,_,v in m.properties(Reader(m.chunk('WorldInfo').data))}
        self.assertEqual((world['mapName'],world['mapDescription'],world['cameraMaxHeight']),('Vale','A quiet vale.',30000.))
        with self.assertRaises(KeyError):set_world(m,cameraMaxHight=1.)

    def test_water_plane_covers_the_playable_area_by_default(self):
        m=create(71,83,3);water_plane(m,'Lake',140.7)
        lake,=records(m,'StandingWaterAreas')
        self.assertEqual(lake['points'],[(-300,-300),(1010,-300),(1010,1130),(-300,1130)])
        self.assertEqual((lake['name'],lake['water_height']),('Lake',140))

    def test_weather_sets_the_code_and_the_light_rig(self):
        m=create(71,83,3)
        apply_weather(m,'rain',sun=dict(diffuse=(1.,.5,.25)),fill=dict(direction=(0.,0.,-1.)))
        self.assertIn(('weather',1,weather_code('rain')),m.properties(Reader(m.chunk('WorldInfo').data)))
        lights=[l for c in records(m,'GlobalLighting')['configurations'] for l in c]
        self.assertTrue(all(l['direction']==(0.,0.,-1.) for l in lights if l['light_index']==1))
        sun=[l['diffuse'] for l in lights if l['light_index']==0]
        self.assertTrue(sun and all(d[0]>d[1]>d[2] for d in sun))   # the rig, then the rain's dimming

if __name__=='__main__':unittest.main()
