"""assets.ini: the one INI reader, on text written to its rules."""
import unittest

from mapworkshop.assets import ini

BODY = '''
  KindOf = STRUCTURE IMMOBILE //UNATTACKABLE
  Scale 1.75
  Shadow = SHADOW_VOLUME
  GeometryName ;= Geom_Orig
  Geometry = CYLINDER
  Draw = W3DTreeDraw ModuleTag_01
    ModelName = PTOak01
    TextureName = PTOak01.tga
  End
  Behavior = AuraBehavior ModuleTag_02
    Shadow = SHADOW_ADDITIVE_DECAL    ; a module's own, not the object's
    Scale = 9
  End
  ArmorSet
    Armor = StructureArmor
  End
  BeginScript
    Scale = 3
  EndScript
  ShadowTexture = ShadowI
'''


class StatementTests(unittest.TestCase):
    def test_the_object_s_own_values_are_its_top_level_lines(self):
        own = ini.top(BODY)
        self.assertEqual(own['kindof'], 'STRUCTURE IMMOBILE')           # // comments are not text
        self.assertEqual(own['scale'], '1.75')                          # `=` is optional, as in the game
        self.assertEqual(own['shadow'], 'SHADOW_VOLUME')                # not the module's decal
        self.assertEqual(own['shadowtexture'], 'ShadowI')               # after the blocks and the script
        self.assertNotIn('armor', own)

    def test_blocks_nest_and_a_field_left_without_its_value_does_not_open_one(self):
        paths = {s.key: s.path for s in ini.statements(BODY)}
        self.assertEqual(paths['geometry'], ())                         # GeometryName ;= ... opened nothing
        self.assertEqual(paths['modelname'], ('draw',))
        self.assertEqual(paths['armor'], ('armorset',))
        self.assertNotIn('3', [s.value for s in ini.statements(BODY)])  # a script's lines are skipped

    def test_a_module_s_lines(self):
        self.assertEqual(ini.in_module(BODY, 'W3DTreeDraw'), dict(modelname='PTOak01', texturename='PTOak01.tga'))
        self.assertEqual(ini.in_module(BODY, 'W3DModelDraw'), {})

    def test_a_template_inherits_from_its_parents_with_their_included_files(self):
        templates = dict(child=dict(body='Scale = 2\n', parent='base', file='a.ini'),
                         base=dict(body='#include "shared.inc"\nShadow = SHADOW_DECAL ; ok\n', parent='child',
                                   file='a.ini'))

        class Assets:
            pass
        source = Assets()
        source.templates = templates
        source.included = lambda text, file: text.replace('#include "shared.inc"', 'ShadowSizeX = 19')
        self.assertEqual([e['parent'] for e in ini.chain(templates, 'Child')], ['base', 'child'])   # a loop ends
        bodies = ini.bodies(source, 'child')
        self.assertEqual(ini.inherited(bodies, 'Scale'), '2')
        self.assertEqual(ini.inherited(bodies, 'Shadow'), 'SHADOW_DECAL')
        self.assertEqual(ini.inherited(bodies, 'ShadowSizeX'), '19')    # from the included file
        self.assertIsNone(ini.inherited(ini.bodies(templates, 'child'), 'ShadowSizeX'))   # a dict: no includes

    def test_numbers_and_words_as_the_game_reads_them(self):
        self.assertEqual(ini.number('177.0+'), 177.0)
        self.assertEqual(ini.number('8.0CA'), 8.0)
        self.assertIsNone(ini.number('none', None))
        self.assertEqual(ini.words('"Bip L Finger2" SoWolf_Ambient_fog FollowBone:YES'),
                         ['Bip L Finger2', 'SoWolf_Ambient_fog', 'FollowBone:YES'])

    def test_an_override_s_module_edits_open_blocks(self):
        paths = {s.key: s.path for s in ini.statements('ReplaceModule ModuleTag_01\n  Draw = W3DModelDraw Tag2\n'
                                                       '  End\nEnd\nKindOf = X\n')}
        self.assertEqual(paths['draw'], ('replacemodule',))
        self.assertEqual(paths['kindof'], ())


if __name__ == '__main__':
    unittest.main()
