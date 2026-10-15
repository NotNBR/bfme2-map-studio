"""viewer.toolbar and viewer.palette: menu layout and hit-testing, without a GPU."""
import unittest

from mapworkshop.viewer.palette import Palette
from mapworkshop.viewer.toolbar import Toolbar


class Fake:
    """Stands in for the GL context, its constants and textures."""
    def __getattr__(self, name):
        return Fake()

    def __call__(self, *args, **kwargs):
        return Fake()


def toolbar():
    bar = Toolbar.__new__(Toolbar)
    Toolbar.__init__(bar, Fake(), [dict(kind='dropdown', id='lod', label='Detail')])
    bar.mgl = Fake()
    bar._upload = lambda image, old: image
    bar.drawn = []
    bar._blit = lambda texture, rect, size, alpha=1.0: bar.drawn.append(rect)
    return bar


class MenuTests(unittest.TestCase):
    def test_reopening_the_same_menu_lays_it_out_again(self):
        bar = toolbar()
        entries = [('low', 'Low', False), ('medium', 'Medium', True)]
        for _ in range(2):
            bar.open_menu = ('lod', entries)
            bar.draw_menu((800, 600), 1.0)
            self.assertIsNotNone(bar.menu_rect)
            self.assertEqual(len(bar.menu_boxes), 2)
            bar.open_menu = None
            bar.draw_menu((800, 600), 1.0)
        self.assertEqual(len(bar.drawn), 2)
        self.assertNotIn(None, bar.drawn)

    def test_menu_headings_take_no_clicks(self):
        bar = toolbar()
        bar.open_menu = ('preview', [(None, 'Detail', None), ('lod:low', 'Low', False), ('lod:high', 'High', True)])
        bar.draw_menu((800, 600), 1.0)
        self.assertEqual([b[4] for b in bar.menu_boxes], [('menu', 'preview', 'lod:low'), ('menu', 'preview', 'lod:high')])


class PaletteTests(unittest.TestCase):
    def test_clicks_find_the_tool_or_button_under_them(self):
        palette = Palette.__new__(Palette)
        Palette.__init__(palette, Fake(), top=36)
        palette.mgl = Fake()
        palette._upload = lambda image, old: image
        palette._blit = lambda texture, rect, size: None
        palette.draw((800, 600), 1.0, 'pin')
        centre = lambda target: next(((x0+x1)//2, (y0+y1)//2) for x0, y0, x1, y1, t in palette.boxes if t == target)
        self.assertEqual(palette.target_at(*centre(('tool', 'circle'))), ('tool', 'circle'))
        self.assertEqual(palette.target_at(*centre(('button', 'copy'))), ('button', 'copy'))
        self.assertEqual(len(palette.boxes), 9)
        x0, y0, x1, y1 = palette.rect
        self.assertEqual(palette.target_at(x0+1, y0+1), 'palette')
        self.assertIsNone(palette.target_at(x1+5, y0+5))
        self.assertGreaterEqual(y0, 36)


if __name__ == '__main__':
    unittest.main()
