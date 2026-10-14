"""viewer.toolbar: menu layout, without a GPU."""
import unittest

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


if __name__ == '__main__':
    unittest.main()
