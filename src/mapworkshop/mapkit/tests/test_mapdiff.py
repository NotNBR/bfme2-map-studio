"""What `mw diff` reports between two versions of a small generated map."""
import unittest

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, set_world, starts, water_plane
from mapworkshop.mapkit.mapdiff import compare, lines

H, W = 89, 77   # samples of a 71 x 83 map with a 3-cell border


def build(trees=((300, 300), (350, 300), (400, 320)), extra_first=False, hill=0., paint=False, blocked=False,
          scale=None, description='A vale.', lake=140):
    m = create(71, 83, 3, description=description)
    y, x = np.mgrid[0:H, 0:W]
    set_heights(m, 150 + hill * (np.hypot(x - 40, y - 40) < 6))
    labels = np.zeros((H, W), 'u2')
    if paint:
        labels[10:20, 10:20] = 1
    walls = np.zeros((H, W), bool)
    if blocked:
        walls[50:52, 30:40] = True
    set_materials(m, ['GrassA', 'DirtB'], labels, blocked=walls)
    if extra_first:
        add_object(m, 'Barrel', 600, 600, layer='Yard')
    starts(m, [(100, 100), (600, 700)])
    for i, (tx, ty) in enumerate(trees):
        extra = [('objectPrototypeScale', 2, scale)] if scale and i == 0 else []
        add_object(m, 'TreeA', tx, ty, 1.0, layer='Woods', extra=extra)
    water_plane(m, 'Lake', lake)
    return Map(m.encode())


class MapDiffTests(unittest.TestCase):
    def test_the_same_map_has_no_changes(self):
        self.assertEqual(lines(compare(build(), build())), ['No changes.'])

    def test_renumbered_objects_are_not_changes(self):
        text = '\n'.join(lines(compare(build(), build(extra_first=True))))
        self.assertIn('+1 Barrel [Yard] at (600, 600)', text)
        self.assertNotIn('changed', text)
        self.assertNotIn('TreeA', text)

    def test_moved_removed_and_changed_objects(self):
        result = compare(build(), build(trees=((300, 300), (340, 250)), scale=.5))
        text = '\n'.join(lines(result))
        self.assertIn('moved TreeA [Woods] (350, 300) -> (340, 250), 51 units', text)
        self.assertIn('-1 TreeA [Woods] at (400, 320)', text)
        self.assertIn('changed 1 TreeA [Woods]: objectPrototypeScale', text)
        self.assertEqual((result['objects']['before'], result['objects']['after']), (5, 4))

    def test_far_moves_are_a_removal_and_an_addition(self):
        text = '\n'.join(lines(compare(build(), build(trees=((300, 300), (350, 300), (1400, 1500))))))
        self.assertIn('+1 TreeA [Woods] at (1400, 1500)', text)
        self.assertIn('-1 TreeA [Woods] at (400, 320)', text)

    def test_terrain_heights_textures_and_passability(self):
        text = '\n'.join(lines(compare(build(), build(hill=20., paint=True, blocked=True))))
        self.assertIn('Heights: ', text)
        self.assertIn('(up to +20).', text)
        self.assertIn('Textures: 100 cells repainted, x 70..160, y 70..160: GrassA -> DirtB 100', text)
        self.assertIn('Impassable: +20 / -0 cells, x 270..360, y 470..480', text)

    def test_other_sections_by_name_and_property(self):
        before, after = build(), build(description='A wet vale.', lake=150)
        set_world(after, cameraMaxHeight=30000.)
        cameras = [dict(look_at=(10., 20., 0.), name='Overview', pitch=.5, roll=0., yaw=0., zoom=1.,
                        field_of_view=.75, unknown=0.)]
        sections.write(after, 'NamedCameras', cameras)
        text = '\n'.join(lines(compare(before, after)))
        self.assertIn("WorldInfo: cameraMaxHeight: 300 -> 30000; mapDescription: 'A vale.' -> 'A wet vale.'", text)
        self.assertIn("StandingWaterAreas: ['Lake'].water_height: 140 -> 150", text)
        self.assertIn('NamedCameras: [0]: (none) -> ', text)

    def test_map_ini_lines(self):
        result = compare(build(), build(), 'Weather\n  Fog = No\nEnd\n', 'Weather\n  Fog = Yes\nEnd\n')
        self.assertEqual(lines(result), ['map.ini: 2 lines changed.', '  -  Fog = No', '  +  Fog = Yes'])

    def test_resized_terrain_is_reported_without_cell_details(self):
        small = create(64, 64, 3)
        text = '\n'.join(lines(compare(build(), Map(small.encode()))))
        self.assertIn('Terrain resized: 71 x 83 -> 64 x 64 cells.', text)
        self.assertNotIn('Heights:', text)


if __name__ == '__main__':
    unittest.main()
