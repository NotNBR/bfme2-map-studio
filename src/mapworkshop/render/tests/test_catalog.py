"""render.catalog: classifying templates, searching the index, checking maps."""
import unittest

from mapworkshop.render import catalog
from mapworkshop.assets.library import TEMPLATE


def template(name, file, body, kind='Object', parent=None):
    return dict(name=name, kind=kind, parent=parent, body=body, file=file, line=1)


class Assets:
    """The parts of GameAssets the catalog reads, over a few INI entries."""

    def __init__(self, *entries, ini=None):
        self.templates = {e['name'].lower(): e for e in entries}
        self.ini = dict(ini or {})

    def template_model(self, name):
        body = self.templates[name.lower()]['body']
        kinds = catalog._field(body, 'KindOf') or ''
        model = catalog._field(body, 'Model')
        return dict(model=model.lower(), scale=1.0, kinds={k.upper() for k in kinds.split()}, tree=False) if model else None

    def ini_text(self, name):
        return self.ini.get(name, '')


HALL = template('RohanGoldenHall', 'object/obsolete/rohan/goldenhall.ini',
                '  Side = Obsolete\n  EditorSorting = STRUCTURE\n  KindOf = STRUCTURE FS_FACTORY MADE_OF_WOOD\n'
                '  CommandSet = GoldenHallCommandSet\n  Model = RBGoldHall\n')
HOUSE = template('RohanHouse01', 'object/civilian/rohanbuildings.ini',
                 '  Side = Civilian\n  EditorSorting = STRUCTURE\n  KindOf = STRUCTURE IMMOBILE\n  Model = RBHouse01\n'
                 '  Geometry = BOX\n  GeometryMajorRadius = 45.0\n')
FARM = template('GondorFarm', 'object/goodfaction/structures/men/farm.ini',
                '  Side = Men\n  EditorSorting = STRUCTURE\n  KindOf = STRUCTURE FS_CASH_PRODUCER\n  Model = GBFarm\n')
TORCH = template('GenericTorch2', 'object/civilian/civilianprop.ini',
                 '  EditorSorting = MISC_MAN_MADE\n  KindOf = IMMOBILE\n  Model = PTorch\n'
                 '  Draw = W3DScriptedModelDraw ModuleTag_01\n    ParticleSysBone = None TorchFire\n  End\n')
SNOWY = template('OsgiliathRuin12Snow', 'object/civilian/osgiliathbuildings.ini',
                 '  EditorSorting = STRUCTURE\n  KindOf = STRUCTURE\n  Model = OBRuin12S\n  GeometryMajorRadius = 130\n')
CINE = template('CINE_RohanGate', 'object/cinematic/cinematicprops.ini', '  EditorSorting = STRUCTURE\n  Model = CRGate\n')


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.assets = Assets(HALL, HOUSE, FARM, TORCH, SNOWY, CINE,
                             template('RohanHouse01Snow', 'object/civilian/rohanbuildings.ini', '', 'ObjectReskin', 'rohanhouse01'))

    def facts(self, name):
        return catalog.facts(self.assets, name)

    def test_groups_and_types(self):
        self.assertEqual(catalog.classify(self.facts('RohanHouse01')), ('Built scenery', 'House / building'))
        self.assertEqual(catalog.classify(self.facts('GenericTorch2')), ('Built scenery', 'Light / fire'))
        self.assertEqual(catalog.classify(self.facts('OsgiliathRuin12Snow')), ('Built scenery', 'Ruin'))
        self.assertEqual(catalog.classify(self.facts('GondorFarm')), ('Faction structures', 'Economy'))
        self.assertEqual(catalog.classify(self.facts('RohanGoldenHall')), ('Obsolete / test', 'Obsolete'))
        self.assertEqual(catalog.classify(self.facts('CINE_RohanGate'))[1], 'Cinematic / test / placeholder')

    def test_reskins_inherit_their_parents_fields(self):
        f = self.facts('RohanHouse01Snow')
        self.assertEqual((f['parents'], f['radius'], f['side']), (['RohanHouse01'], 45.0, 'Civilian'))
        self.assertEqual(catalog.variants(f['name']), ['Snow'])

    def test_regions_come_from_the_ini_then_the_name_then_the_side(self):
        self.assertEqual(catalog.region(self.facts('RohanHouse01')), 'Rohan / Edoras')
        self.assertEqual(catalog.region(self.facts('OsgiliathRuin12Snow')), 'Osgiliath')
        self.assertEqual(catalog.region(self.facts('GondorFarm')), 'Gondor / Minas Tirith')
        self.assertEqual(catalog.region(self.facts('GenericTorch2')), '')

    def test_material_names_its_evidence(self):
        hall = self.facts('RohanGoldenHall')
        self.assertEqual(catalog.material(hall, 'Obsolete', 'Rohan / Edoras'), ('Wood', 'game flag'))
        self.assertEqual(catalog.material(self.facts('GenericTorch2'), 'Light / fire', ''), ('Fire / light', 'type'))
        self.assertEqual(catalog.material(self.facts('RohanHouse01'), 'House / building', 'Rohan / Edoras', ['rbhouse.tga']),
                         ('Wood', 'culture guess'))
        self.assertEqual(catalog.material(self.facts('RohanHouse01'), 'House / building', '', ['pwood01.tga']),
                         ('Wood', 'texture'))
        self.assertEqual(catalog.material(self.facts('OsgiliathRuin12Snow'), 'Ruin', 'Osgiliath'), ('Stone', 'name'))

    def test_particles_and_sizes(self):
        self.assertEqual(self.facts('GenericTorch2')['particles'], ['TorchFire'])
        self.assertEqual([catalog.size_class(r) for r in (None, 5, 30, 100, 400)], ['', 'small', 'medium', 'large', 'huge'])

    def test_concerns(self):
        self.assertIn('obsolete by the game; a faction building', catalog.concerns(self.facts('RohanGoldenHall'))[0])
        self.assertIn("faction's gameplay building", catalog.concerns(self.facts('GondorFarm'))[0])
        self.assertIn('cinematics', catalog.concerns(self.facts('CINE_RohanGate'))[0])
        self.assertEqual(catalog.concerns(self.facts('RohanHouse01')), [])

    def test_describe(self):
        text = '\n'.join(catalog.describe(self.assets, 'GenericTorch2'))
        self.assertIn('object/civilian/civilianprop.ini:1', text)
        self.assertIn('Effects:    TorchFire', text)
        with self.assertRaisesRegex(LookupError, 'similar: RohanHouse01'):
            catalog.describe(self.assets, 'RohanHouse')


class IndexTests(unittest.TestCase):
    def entry(self, name, group='Built scenery', type='House / building', placed=0, maps=0, concerns=(), **extra):
        return dict(dict(name=name, group=group, type=type, region='', variants=[], material='', evidence='', radius=None,
                         size='', placed=placed, maps=maps, model=name.lower(), concerns=list(concerns)), **extra)

    def test_every_group_in_order_of_stock_use(self):
        index = dict(objects=[self.entry('ShireGeneric01', placed=3, maps=1, region='Shire'),
                              self.entry('ShireMill', placed=9, maps=4, region='Shire'),
                              self.entry('ShireHouseOld', concerns=['marked obsolete'], placed=50, maps=9, region='Shire'),
                              self.entry('ShireHobbitHorde', group='Faction units', type='Infantry', region='Shire')])
        hits = catalog.find_objects(index, ['shire'])
        self.assertEqual([h['name'] for h in hits], ['ShireHouseOld', 'ShireMill', 'ShireGeneric01', 'ShireHobbitHorde'])
        hits = catalog.find_objects(index, ['shire'], group='Faction units')
        self.assertEqual([h['name'] for h in hits], ['ShireHobbitHorde'])
        hits = catalog.find_objects(index, [], type='house', used=True)
        self.assertEqual({h['name'] for h in hits}, {'ShireMill', 'ShireGeneric01', 'ShireHouseOld'})

    def test_every_word_must_match(self):
        index = dict(objects=[self.entry('DaleBridge', type='Bridge / walkway', material='Wood'),
                              self.entry('MinisBridge1', type='Bridge / walkway', material='Stone')])
        hits = catalog.find_objects(index, ['stone', 'bridge'])
        self.assertEqual([h['name'] for h in hits], ['MinisBridge1'])

    def test_lines(self):
        lines = catalog.object_lines([self.entry('ShireMill', placed=9, maps=1, radius=40.0, concerns=['x'])], 25, '"mill"')
        self.assertIn('! ShireMill', lines[2])
        self.assertIn('1 map, 9x', lines[2])
        self.assertEqual(catalog.object_lines([], 25, '"x"'), ['No template matches "x".'])

    def test_themes_and_road_groups(self):
        self.assertEqual(catalog.fx_theme('CampfireEmbersSmall'), 'fire')
        self.assertEqual(catalog.road_group('DirtRoadTracks2'), 'dirt')
        self.assertEqual(catalog.road_group('EreborRoad01'), 'regional')


class Map:
    def __init__(self, *objects):
        self.list = objects

    def objects(self):
        return [dict(template=t, flags=flags, properties=[('originalOwner', 3, owner), ('objectLayer', 3, layer)])
                for t, flags, owner, layer in self.list]


class CheckMapTests(unittest.TestCase):
    def test_check_map(self):
        assets = Assets(HALL, HOUSE, FARM, ini={'roads.ini': 'Road DirtRoad2\n', 'crate.ini': 'ChildObject TreasureChest100 Crate\n'})
        m = Map(('RohanGoldenHall', 0, 'PlyrCivilian/teamPlyrCivilian', 'Hold'),
                ('RohanGoldenHall', 0, 'PlyrCivilian/teamPlyrCivilian', 'Hold'),
                ('RohanHouse01', 0, 'PlyrCivilian/teamPlyrCivilian', ''),
                ('GondorFarm', 0, 'PlyrCivilian/teamPlyrCivilian', ''),
                ('GondorFarm', 0, 'Player_1/teamPlayer_1', ''),
                ('DirtRoad2', 2, '/team', ''), ('TreasureChest100', 0, '/team', ''), ('Scorch', 0, '/team', ''),
                ('*Waypoints/Waypoint', 0, '/team', ''), ('RohanHouse02', 0, '/team', 'Town'))
        lines = catalog.check_map(assets, m)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith('GondorFarm x1:'))
        self.assertTrue(lines[1].startswith('RohanGoldenHall x2 [Hold]: marked obsolete'))
        self.assertTrue(lines[2].startswith("RohanHouse02 x1 [Town]: the game defines no such template"))


class CheckIniTests(unittest.TestCase):
    def test_check_ini(self):
        assets = Assets(HALL, ini={'crate.ini': 'ChildObject TreasureChest100 Crate\n'})
        assets.texture_key = lambda name: 'art/textures/exwater01.dds' if name.lower() == 'exwater01.tga' else None
        ini = ('Object RohanGoldenHall\n  ReplaceModule ModuleTag_Draw\n  End\nEnd\n\n'
               'Object TreasureChest100\n  AddModule ModuleTag_X\n  End\nEnd\n\n'
               'Object MW_NewThing\n  KindOf = IMMOBILE\nEnd\n\n'
               'FXParticleSystem MWWater\n  System\n    ParticleName = EXWater01.tga\n  End\nEnd\n\n'
               'FXParticleSystem MWMissing\n  System\n    ParticleName = NoSuchTexture.tga\n  End\nEnd\n')
        lines = catalog.check_ini(assets, ini)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith('Object MW_NewThing: adds an object type'))
        self.assertEqual(lines[1], 'FXParticleSystem MWMissing: the game has no texture NoSuchTexture.tga')

    def test_override_modules(self):
        """An override of the game's object replaces a module with ReplaceModule and a new tag; declaring one
        directly, or keeping the old tag, stops the game loading the map."""
        assets = Assets(HALL)
        draw = ('    Draw = W3DScriptedModelDraw {tag}\n      DefaultModelConditionState\n        Model = X\n      End\n'
                '      IdleAnimationState\n        BeginScript\n          CurDrawableHideSubObject("A")\n'
                '        EndScript\n      End\n    End\n')
        good = 'Object RohanGoldenHall\n  ReplaceModule ModuleTag_01\n' + draw.format(tag='ModuleTag_New') + '  End\nEnd\n'
        self.assertEqual(catalog.check_ini(assets, good), [])
        same = 'Object RohanGoldenHall\n  ReplaceModule ModuleTag_01\n' + draw.format(tag='ModuleTag_01') + '  End\nEnd\n'
        self.assertEqual(catalog.check_ini(assets, same),
                         ['Object RohanGoldenHall: ReplaceModule ModuleTag_01 keeps the tag; the game needs a new one'])
        bare = 'Object RohanGoldenHall\n' + draw.format(tag='ModuleTag_01') + '  EditorSorting = SYSTEM\nEnd\n'
        lines = catalog.check_ini(assets, bare)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith('Object RohanGoldenHall: Draw ModuleTag_01 outside AddModule or ReplaceModule'))


class TemplatePatternTests(unittest.TestCase):
    def test_indented_definitions_and_assignments(self):
        text = ('Object A\n  Model = X\nEnd\n   Object B\n  ObjectStatus = Y\n  Object = NotATemplate\nEnd\n'
                'ChildObject C A\nEnd\n')
        found = [(k, n, p) for k, n, p, _ in TEMPLATE.findall(text)]
        self.assertEqual(found, [('Object', 'A', ''), ('Object', 'B', ''), ('ChildObject', 'C', 'A')])


if __name__ == '__main__':
    unittest.main()
