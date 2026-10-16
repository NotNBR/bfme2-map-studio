"""CPU preparation boundaries and independent map overlays, without a GPU."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np

from mapworkshop.render.assets import GameAssets
from mapworkshop.render.terrain import TerrainData
from mapworkshop.render.engine import MapRenderer, TextureCache


class PreparationTests(unittest.TestCase):
    def test_texture_cache_evicts_old_ownership_without_releasing_live_textures(self):
        from unittest.mock import Mock
        textures = [SimpleNamespace(width=3, height=3, components=4, release=Mock()) for _ in range(3)]
        cache = TextureCache(budget=96)
        cache['a'], cache['b'] = textures[:2]
        self.assertIs(cache['a'], textures[0])
        cache['c'] = textures[2]
        self.assertEqual(list(cache), ['a', 'c'])
        self.assertEqual(cache.bytes, 96)
        for texture in textures:
            texture.release.assert_not_called()

    def test_blend_lookup_handles_missing_ids_cliffs_and_independent_layers(self):
        indices = np.array([[0, 1, 2, 3, 0xffffffff]]*5, dtype=np.uint32)
        cliffs = np.zeros((5, 5), np.uint32)
        cliffs[1, 1] = 1
        arrays = dict(tiles=np.zeros((5, 5), np.uint16), blends=indices,
                      three_way=np.roll(indices, 1, axis=1), cliffs=cliffs)
        m = SimpleNamespace(heightmap=lambda: dict(width=5, height=5, border=0,
                                                  elevations=np.zeros((5, 5), np.uint16)),
                            blend=lambda **kwargs: dict(textures=[dict(tile_start=0, tile_count=16, cell_size=2)],
                                                         arrays=arrays))
        records = [dict(index=1, tile=4, direction_hex='01000000', flags=2,
                        long_diagonal=0, custom_edge_class=-1),
                   dict(index=2, tile=8, direction_hex='00000100', flags=0,
                        long_diagonal=0, custom_edge_class=-1),
                   dict(index=3, tile=1, direction_hex='01000000', flags=0,
                        long_diagonal=0, custom_edge_class=0)]
        with patch('mapworkshop.render.terrain.terrain_records', return_value={'blends': records}):
            t = TerrainData(m)
        first = (2 << 10) | (6 << 20) | (1 << 24)
        second = (2 << 15) | (4 << 20) | (1 << 24)
        np.testing.assert_array_equal(t.cells[0, :, 1], [0, first, second, 0, 0])
        np.testing.assert_array_equal(t.cells[0, :, 2], [0, 0, first, second, 0])
        np.testing.assert_array_equal(t.cells[0, :, 3], [0, 1, 1, 0, 0])
        self.assertEqual(t.cells[1, 1, 1], 0)
        self.assertEqual(t.cells[1, 1, 3], 1)

    def test_map_overrides_do_not_leak_to_base_or_next_map(self):
        base = GameAssets.__new__(GameAssets)
        base._templates = {'tree': dict(name='Tree', parent=None, body='Scale = 1\n', kind='Object')}
        base.image = lambda name: 'shared decoded image'
        first = base.for_map('Object Tree\nScale = 2\nEnd\nObject Extra\nEnd\n')
        second = first.for_map('')
        self.assertIn('Scale = 2', first.templates['tree']['body'])
        self.assertIn('Scale = 1', base.templates['tree']['body'])
        self.assertIn('Scale = 1', second.templates['tree']['body'])
        self.assertNotIn('extra', second.templates)
        self.assertIs(first.image, base.image)
        self.assertIs(second.image, base.image)

    def test_shared_assets_take_map_templates_only_in_copies(self):
        base = GameAssets.__new__(GameAssets)
        base._templates = {'tree': dict(name='Tree', parent=None, body='Scale = 1\n', kind='Object')}
        base.image = lambda name: None
        with patch.object(GameAssets, '_shared', base):
            with self.assertRaises(RuntimeError):
                base.add_map_templates('Object Extra\nEnd\n')
            self.assertIn('extra', base.for_map('Object Extra\nEnd\n').templates)
            self.assertNotIn('extra', base.templates)

    def test_walkability_task_does_not_capture_renderer_gpu_resources(self):
        import weakref
        import gc
        renderer = MapRenderer.__new__(MapRenderer)
        renderer.map, renderer.pathing_assets = object(), object()
        renderer.map_ini, renderer.model_cache = '', object()
        ref = weakref.ref(renderer)
        task = renderer.walkability_task()
        del renderer
        gc.collect()
        self.assertIsNone(ref())
        self.assertFalse(hasattr(task.args[0], 'ctx'))

    def test_world_builder_models_are_editor_markers_unless_they_stand_in(self):
        draw = ('  Draw = W3DScriptedModelDraw ModuleTag_01\n'
                '    DefaultModelConditionState\n      Model = {default}\n    End\n'
                '    ModelConditionState = WORLD_BUILDER\n      Model = {editor}\n    End\n'
                '    ModelConditionState = SNOW\n      Model = {snow}\n    End\n  End\n')
        assets = GameAssets.__new__(GameAssets)
        assets._templates = {
            'farm': dict(name='Farm', parent=None, kind='Object', body='KindOf = TACTICAL_MARKER INERT\n'
                         + draw.format(default='None', editor='GBFarm_WB', snow='None')),
            'horde': dict(name='Horde', parent=None, kind='Object', body='KindOf = SELECTABLE HORDE\n'
                          + draw.format(default='None', editor='HordeBanner', snow='None')),
            'ruin': dict(name='Ruin', parent=None, kind='Object', body='KindOf = IMMOBILE\n'
                         + draw.format(default='None', editor='RuinEditor', snow='RuinSnow'))}
        farm, horde, ruin = (assets.template_model(name) for name in ('Farm', 'Horde', 'Ruin'))
        self.assertEqual((farm['model'], farm['editor']), ('gbfarm_wb', True))
        self.assertEqual((horde['model'], horde['editor']), ('hordebanner', False))
        self.assertEqual((ruin['model'], ruin['editor']), ('ruinsnow', False))


if __name__ == '__main__':
    unittest.main()
