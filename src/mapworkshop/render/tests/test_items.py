"""mw item / mw items: the parts that run without a GPU."""
import unittest

import numpy as np

from mapworkshop.render.items import _background, _perspective, bar_length, collage, draw_scale_bar, fit, parse_views, select


class ItemTests(unittest.TestCase):
    def test_views(self):
        self.assertEqual(parse_views('3q, side,top,135/20'), ['3q', 'side', 'top', '135/20'])
        with self.assertRaises(ValueError):
            parse_views('3q,diagonal')

    def test_backgrounds(self):
        self.assertEqual(_background('white'), (1., 1., 1.))
        self.assertIsNone(_background('transparent'))
        self.assertEqual(_background('#ff8000'), (1., 128 / 255, 0.))

    def test_shadow_projection_maps_the_corners(self):
        target = [(10, 20), (300, 40), (280, 200), (5, 180)]
        source = [(0, 0), (256, 0), (256, 256), (0, 256)]
        a, b, c, d, e, f, g, h = _perspective(target, source)
        for (x, y), (u, v) in zip(target, source):
            w = g * x + h * y + 1
            self.assertAlmostEqual((a * x + b * y + c) / w, u, places=6)
            self.assertAlmostEqual((d * x + e * y + f) / w, v, places=6)

    def test_fit_crops_to_the_content_and_keeps_its_aspect(self):
        image = np.full((400, 400, 4), 255, np.uint8)
        content = np.zeros((400, 400), bool)
        image[100:120, 50:250, :3] = 0                # a dark bar 200 wide, 20 high
        content[100:120, 50:250] = True
        tile, zoom = fit(image, content, 100, (1., 1., 1.))
        self.assertEqual(tile.shape, (100, 100, 4))
        self.assertAlmostEqual(zoom, 100 / round(200 / (1 - 2 * .06)))
        dark = np.nonzero(tile[..., 0] < 128)
        self.assertLessEqual(dark[1].min(), 8)        # fills the width, within the margin
        self.assertGreaterEqual(dark[1].max(), 91)
        self.assertTrue(40 <= dark[0].min() and dark[0].max() <= 60)   # centred, still flat

    def test_scale_bars_are_round_and_about_a_quarter_wide(self):
        self.assertEqual(bar_length(1.0, 400), 100)
        self.assertEqual(bar_length(0.05, 400), 2000)
        self.assertEqual(bar_length(4.0, 400), 20)
        tile = np.full((200, 200, 4), 255, np.uint8)
        draw_scale_bar(tile, 1.0, (1., 1., 1.))
        self.assertTrue((tile[150:, :, 0] < 200).any())

    def test_collage_grid(self):
        tile = np.full((64, 64, 4), 255, np.uint8)
        sheet = collage([(tile, ['Tree', '10 x 10 x 30'])] * 5, columns=3, tile=64, background=(1., 1., 1.), title='trees')
        rows = 2
        self.assertEqual(sheet.width, 16 * 2 + 3 * 64 + 2 * 12)
        self.assertGreater(sheet.height, rows * 64)
        self.assertEqual(sheet.getpixel((0, 0)), (255, 255, 255, 255))
        clear = collage([(tile, ['Tree'])], columns=1, tile=64, background=None)
        self.assertEqual(clear.getpixel((0, 0))[3], 0)


class SelectionTests(unittest.TestCase):
    def setUp(self):
        try:
            from mapworkshop.assets.library import GameAssets
            self.assets = GameAssets()
            self.assets.templates
        except Exception as error:   # no game data: `mw setup`
            self.skipTest(f'game data not available: {error}')

    def test_wildcards_names_and_what_is_left_out(self):
        names, skipped = select(self.assets, ['*treebridge*', 'shirebridge', 'NoSuchThing'])
        self.assertEqual(names, ['GenericTreeBridge', 'ShireBridge'])
        self.assertEqual(skipped, [('NoSuchThing', 'no such template')])


if __name__ == '__main__':
    unittest.main()
