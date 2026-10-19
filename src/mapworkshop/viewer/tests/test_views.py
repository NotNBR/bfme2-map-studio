"""viewer.views: saved views in a temporary folder, read back as `mw render` reads them."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from mapworkshop.render.camera import parse_view, view_from_dict
from mapworkshop.viewer import views as viewlib
from mapworkshop.viewer.camera import Camera, FlyCamera


def flat(x, y):
    return np.zeros_like(np.asarray(x, float))


class ViewsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patch = mock.patch.object(viewlib, 'VIEWS', Path(self.folder.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.folder.cleanup)

    def test_saved_views_are_a_views_file_mw_render_reads(self):
        views = viewlib.Views('maps/x/my map.map')
        fly = FlyCamera(flat)
        fly.place(np.array([10.0, 20.0, 300.0]), np.array([0.0, 1.0, -0.5]), focus=400)
        fly.aperture, fly.ev, fly.roll = 2.8, 0.5, 4.0
        views.save('photo', viewlib.photo_spec(fly), slot=3, thumbnail=Image.new('RGB', viewlib.THUMBNAIL))
        views.save('edit', viewlib.edit_spec(Camera(flat, (1000, 800))))
        data = json.loads(views.path.read_text())
        self.assertEqual(views.path.name, 'my map.json')
        for name, spec in data['views'].items():
            view_from_dict(spec)                              # what mw render --views does
        self.assertEqual(data['viewer'], {'View 1': dict(slot=3, mode='photo'), 'View 2': dict(slot=1, mode='edit')})
        self.assertTrue(views.thumbnail_path('View 1').exists())
        again = viewlib.Views('maps/x/my map.map')
        self.assertEqual(again.by_slot(3)['spec']['aperture'], 2.8)

    def test_a_slot_holds_one_view_and_names_stay_unique(self):
        views = viewlib.Views('m.map')
        views.save('edit', dict(target=[0, 0]), slot=1)
        views.save('edit', dict(target=[5, 5]), slot=1)
        self.assertEqual(len(views.items), 1)
        self.assertEqual(views.by_slot(1)['spec'], dict(target=[5, 5]))
        views.save('edit', dict(target=[1, 1]), slot=2)
        with self.assertRaises(ValueError):
            views.rename('View 1', 'View 2')
        self.assertTrue(views.rename('View 1', 'Gate'))
        self.assertTrue(views.delete('Gate'))
        self.assertEqual([v['name'] for v in views.items], ['View 2'])
        self.assertEqual(views.free_slot(), 1)

    def test_a_copied_view_is_a_render_command(self):
        spec = dict(eye=[1, 2, 3], target=[4, 5, 6], focal=35, aperture=2.8, focus=500)
        command = viewlib.render_command('helms-deep-battle', 'Gate view', spec)
        self.assertTrue(command.startswith('mw render --map helms-deep-battle --out local/renders/helms-deep-battle-views '
                                           '--view gate-view '))
        words = command.split('--view ', 1)[1].split()[1:]
        self.assertEqual(parse_view(words).describe()['aperture'], 2.8)

    def test_the_command_carries_the_preview_where_it_differs_from_mw_render(self):
        shown = dict(size=(1600, 1200), lod='medium', weather=None, sun=None, time=0.0, normal_maps=None,
                     objects=True, units=True, shadows=True, clouds=True, weather_fx=True, limits=False,
                     markers=False, grid=False, border=False, walkable=False, flow=False)
        self.assertEqual(viewlib.render_flags(shown), [])
        shown.update(size=(1920, 816), lod='high', weather='rain', sun='ember', time=12.34, normal_maps=False,
                     units=False, clouds=False, grid=True)
        self.assertEqual(viewlib.render_flags(shown),
                         ['--size 1920x816', '--lod high', '--weather rain', '--sun ember', '--time 12.3',
                          '--normal-maps off', '--no-units', '--no-clouds', '--grid'])
        command = viewlib.render_command('lab', 'v', dict(target=[1, 2]), shown)
        self.assertIn('-views --size 1920x816 --lod high', command)
        self.assertTrue(command.endswith('--view v target=1,2'))


if __name__ == '__main__':
    unittest.main()
