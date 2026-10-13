"""Section layouts read and write the same bytes (formats.sections, Map objects)."""
import os
from pathlib import Path
import unittest

from mapworkshop.config import GAME_DATA, setting
from mapworkshop.formats.big import BigArchive
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.formats.tests.fixtures import fixture

AREA = dict(id=7, name='Ford', layer='Water', uv_speed=.25, additive=1)
BUILD = dict(building_name='Keep', template='GondorCastle', position=(10., 20., 0.), angle=1.5, initially_built=1,
             rebuilds=0, script='', health=100, whiner=1, unsellable=0, repairable=1)
OPERATION = dict(opcode_raw=900, internal_name_kind=3, internal_name='TEST_ACTION',
                 arguments=[dict(type_id=16, position=(12., 25., 8.)),
                            dict(type_id=77, int_value=-2, float_value=.5, string_value='Keep all fields')])
SCRIPT = dict(chunk='Script', version=4, name='Test', comment='', conditions_comment='', actions_comment='',
              active_raw=1, deactivate_on_success_raw=1, easy_raw=1, medium_raw=0, hard_raw=1, subroutine_raw=0,
              evaluation_interval_raw=15, sequential_raw=1, loop_raw=0, loop_count=-1, target_type_raw=2,
              target_name='ExampleTeam', player_mask_text='ALL', children=[
                  dict(chunk='OrCondition', version=1, children=[
                      dict(OPERATION, chunk='Condition', version=6, enabled_raw=1, condition_flag_4d_raw=1)]),
                  dict(OPERATION, chunk='ScriptAction', version=3, enabled_raw=1),
                  dict(OPERATION, chunk='ScriptActionFalse', version=2),
                  dict(chunk='FutureScript', version=1, raw=b'opaque')])
TRIGGER = dict(name='Ford', layer='', id=2, is_water_raw=1, is_river_raw=0, river_start=0, points=[(0, 0, 0), (5, 0, 0)])
FRAME = dict(frame=0, interpolation='catm')

# One value per layout, in the form decode returns.
SAMPLES = {
    ('StandingWaterAreas', 2): [dict(AREA, bump_texture='bump.tga', sky_texture='sky.tga',
                                     points=[(10., 20.), (30.5, 20.), (25., 40.)], water_height=140,
                                     shader='wtr.W3D', depth_colors='lut.tga')],
    ('RiverAreas', 2): [dict(AREA, texture='river.tga', noise='noise.tga', alpha_edge='edge.tga', sparkle='s.tga',
                             color_bytes=(1, 2, 3, 4), alpha=.5, water_height=100, min_lod='LOW',
                             cross_sections=[(0., 0., 10., 0.), (0., 50., 10., 50.)])],
    ('TriggerAreas', 1): [dict(name='Gate', layer='', id=3, points=[(0., 0.), (5., 0.), (5., 5.)], unknown_u32=0)],
    ('StandingWaveAreas', 1): [dict(AREA, points=[(1., 1.), (2., 2.), (3., 1.)], unknown_u32=9,
                                    wave_parameters_raw=tuple(range(9)), texture='wave.tga')],
    ('StandingWaveAreas', 2): [dict(AREA, points=[(1., 1.), (2., 2.), (3., 1.)], unknown_u32=9,
                                    wave_parameters_raw=tuple(range(9)), texture='wave.tga', enable_pca=1)],
    ('NamedCameras', 2): [dict(look_at=(100., 200., 0.), name='Overview', pitch=.5, roll=0., yaw=1.25,
                               zoom=1., field_of_view=.75, unknown=0.)],
    ('WaypointsList', 1): [dict(start_id=1, end_id=-2)],
    ('EnvironmentData', 2): dict(macro_texture_stretched=1, macro_texture='m.tga', cloud_texture='c.tga'),
    ('EnvironmentData', 3): dict(water_max_alpha_depth=3., deep_water_alpha=1., macro_texture_stretched=0,
                                 macro_texture='m.tga', cloud_texture='c.tga'),
    ('PostEffectsChunk', 1): [dict(name='Bloom', blend_factor=.5, lookup_image='')],
    ('SkyboxSettings', 1): dict(position=(1., 2., 3.), scale=1.5, rotation=0., texture_scheme='Day'),
    ('WorldInfo', 1): [('mapName', 3, 'Vale'), ('cameraMaxHeight', 2, 800.), ('compression', 1, 0),
                       ('isScenarioMultiplayer', 0, 1), ('displayName', 4, 'Vale été')],
    ('MPPositionList', 0): [dict(chunk='MPPositionInfo', version=1, human=1, computer=1, load_ai_script=0,
                                 team=4294967295, side_restrictions=['Men', 'Elves']),
                            dict(chunk='MPPositionInfo', version=0, human=1, computer=0, team=2)],
    ('SidesList', 5): dict(players=[dict(properties=[('playerName', 3, 'Player_1')], build_list=[])]),
    ('SidesList', 6): dict(unknown_boolean=1, players=[dict(properties=[('playerName', 3, 'Player_1'),
                                                                        ('playerIsHuman', 0, 1)], build_list=[BUILD])]),
    ('LibraryMapLists', 1): [dict(chunk='LibraryMaps', version=1, maps=['ai_library'])],
    ('Teams', 1): [[('teamName', 3, 'teamPlayer_1'), ('teamIsSingleton', 0, 1)]],
    ('PlayerScriptsList', 1): [dict(chunk='ScriptList', version=1, children=[
        dict(chunk='ScriptGroup', version=3, name='Group', active_raw=1, subroutine_raw=0, children=[SCRIPT])])],
    ('BuildLists', 1): [dict(property_kind=3, faction='FactionMen', items=[BUILD])],
    ('PolygonTriggers', 4): [TRIGGER],
    ('PolygonTriggers', 5): [dict(TRIGGER, river_texture='r.tga', noise_texture='n.tga', alpha_edge='a.tga',
                                  sparkle='s.tga', bump_texture='b.tga', sky_texture='k.tga', additive_raw=0,
                                  river_rgb=(1, 2, 3), unknown_byte=0, uv_speed=(.5, .25), river_alpha=1.)],
    ('CameraAnimationList', 3): [
        dict(type='free', name='Fly', num_frames=10, start_offset=0, camera_frames=[
            dict(FRAME, position=(1., 2., 3.), rotation_raw=(0., 0., 0., 1.), fov_or_focal_parameter=.75)]),
        dict(type='look', name='Watch', num_frames=5, start_offset=2, camera_frames=[
            dict(FRAME, interpolation='line', position=(1., 2., 3.), roll=0., fov_or_focal_parameter=.5)],
             target_frames=[dict(FRAME, look_at=(4., 5., 6.))])],
}


class SectionTests(unittest.TestCase):
    def test_every_layout_has_a_sample(self):
        covered = {(name, version) for name, version in SAMPLES}
        for name, (versions, _) in sections.LAYOUTS.items():
            self.assertTrue(any((name, v) in covered for v in versions), name)
        self.assertEqual(set(sections.SECTIONS), set(sections.LAYOUTS) | set(sections.codecs()))

    def test_children_that_do_not_parse_stay_raw(self):
        m = Map(fixture())
        data = sections.encode('PlayerScriptsList', 1, SAMPLES['PlayerScriptsList', 1], m)
        damaged = data.replace(m.intern('TEST_ACTION').to_bytes(3, 'little'), bytes([255, 255, 255]), 1)
        lists = sections.decode('PlayerScriptsList', 1, damaged, m)
        script = lists[0]['children'][0]['children'][0]
        condition = script['children'][0]['children'][0]
        self.assertIn('raw', condition)
        self.assertEqual(script['children'][1]['internal_name'], 'TEST_ACTION')   # its siblings still read
        self.assertEqual(sections.encode('PlayerScriptsList', 1, lists, m), damaged)

    def test_values_survive_encode_and_decode(self):
        for (name, version), value in SAMPLES.items():
            with self.subTest(name=name, version=version):
                m = Map(fixture())
                data = sections.encode(name, version, value, m)
                self.assertEqual(sections.decode(name, version, data, m), value)
                self.assertEqual(sections.encode(name, version, sections.decode(name, version, data, m), m), data)

    def test_later_versions_add_their_fields(self):
        v2 = sections.encode('EnvironmentData', 2, SAMPLES['EnvironmentData', 3])
        self.assertEqual(len(sections.encode('EnvironmentData', 3, SAMPLES['EnvironmentData', 3])), len(v2) + 8)
        self.assertNotIn('water_max_alpha_depth', sections.decode('EnvironmentData', 2, v2))

    def test_post_effects_count_is_one_byte(self):
        self.assertEqual(sections.encode('PostEffectsChunk', 1, []), b'\0')

    def test_unknown_versions_and_trailing_bytes_are_refused(self):
        with self.assertRaises(ValueError):
            sections.decode('NamedCameras', 1, bytes(4))
        with self.assertRaises(ValueError):
            sections.decode('WaypointsList', 1, bytes(5))

    def test_objects_rewrite_to_the_same_bytes(self):
        m = Map(fixture())
        before = m.chunk('ObjectsList').data
        m.set_objects(m.objects())
        self.assertEqual(m.chunk('ObjectsList').data, before)


def stock_documents():
    """Every map, base and library in the game's Maps/Bases/Libraries.big when
    the game folder is set (mw setup), else the extracted stock maps."""
    game = setting('game')
    if game and all((Path(game)/big).is_file() for big in ARCHIVES):
        for big in ARCHIVES:
            archive = BigArchive(Path(game)/big)
            for key in sorted(archive.entries):
                if key.endswith(('.map', '.bse')):
                    yield f'{big}/{key}', Map(archive.read_bytes(key))
    elif (GAME_DATA/'maps').is_dir():
        for path in sorted((GAME_DATA/'maps').glob('*/*.map')):
            yield path.parent.name, Map(path.read_bytes())


ARCHIVES = ('Maps.big', 'Bases.big', 'Libraries.big')


def unread(value):
    """Child chunks anywhere in a decoded value that stayed raw."""
    if isinstance(value, dict):
        if 'raw' in value and 'chunk' in value:
            yield value
        for v in value.values():
            yield from unread(v)
    elif isinstance(value, list):
        for v in value:
            yield from unread(v)


@unittest.skipUnless(os.environ.get('MW_CORPUS'), 'stock maps: run `mw test --corpus` after `mw setup`')
class StockMapTests(unittest.TestCase):
    def test_every_section_of_every_stock_document_reads_and_writes_unchanged(self):
        pairs, raw = set(), []
        for label, m in stock_documents():
            for c in m.chunks:
                name = m.names[c.name_id]
                with self.subTest(document=label, section=name):
                    value = sections.decode(name, c.version, c.data, m)
                    self.assertEqual(sections.encode(name, c.version, value, m), c.data)
                    pairs.add((name, c.version))
                    raw += [f'{label}: {name}' for _ in unread(value)]
        self.assertTrue(pairs, 'no stock documents found')
        self.assertEqual(raw, [], 'children left unread')


if __name__ == '__main__':
    unittest.main()
