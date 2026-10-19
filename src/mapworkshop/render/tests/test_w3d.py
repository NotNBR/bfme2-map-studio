"""render.w3d: mesh details that the effects and glows depend on, without game data."""
import struct
import unittest

import numpy as np

from mapworkshop.render.w3d import (CAMERA_MODES, GEOMETRY_TYPE, MESH, SKIN, ModelCache, classic_shader, grid_mapper,
                                    vertex_material)


def chunk(kind, payload):
    return struct.pack('<II', kind, len(payload)) + payload


class MaterialTests(unittest.TestCase):
    def test_grid_mapper(self):
        # GPTOWNLAMP5's flames: a 4x4 sequence at 15 frames per second.
        self.assertEqual(grid_mapper(0x00070000, b'FPS=15\r\nLog2Width=2\0'), (4, 15.0, 16))
        self.assertEqual(grid_mapper(0x00070000, b'FPS=8\nLog2Width=3\nLast=10'), (8, 8.0, 10))
        self.assertIsNone(grid_mapper(0x00040000, b'FPS=15'))           # linear offset, not a grid

    def test_vertex_material_reads_its_mapper(self):
        # W3dVertexMaterialStruct: attributes, 4 RGBA colours, shininess, opacity, translucency.
        info = struct.pack('<I', 0x00070000) + bytes(16) + struct.pack('<3f', 1.0, 1.0, 0.0)
        payload = chunk(0x2b, chunk(0x2d, info) + chunk(0x2e, b'FPS=15\r\nLog2Width=2\0'))
        self.assertEqual(vertex_material(payload)['grid'], (4, 15.0, 16))

    def test_detail_colour_function(self):
        # FIREGLOW: additive, stage 1 multiplies (DetailColorFunc 2, SCALE).
        state = classic_shader(bytes([3, 0, 0, 1, 2, 1, 0, 1, 1, 2, 0, 2, 0, 2, 0, 2]))
        self.assertEqual((state['blend'], state['detail']), (('one', 'one'), 2))


class GeometryTypeTests(unittest.TestCase):
    def test_camera_oriented_is_not_a_skin(self):
        # The geometry type is a field: 0x60000 shares the skin bit 0x20000.
        oriented = 0x00060000 | 0x2000
        self.assertNotEqual(oriented & GEOMETRY_TYPE, SKIN)
        self.assertEqual(CAMERA_MODES.get(oriented & GEOMETRY_TYPE), 2)
        self.assertEqual(CAMERA_MODES.get(0x00010000), 1)
        self.assertIsNone(CAMERA_MODES.get(SKIN))


class ModelCacheTests(unittest.TestCase):
    def test_a_model_that_fails_to_parse_is_unreadable_not_missing(self):
        class Assets:
            def model_key(self, name):
                return None if name == 'gone' else name

            def read(self, key):
                # A mesh chunk whose only sub-chunk claims 100 bytes it does not have.
                return struct.pack('<II', MESH, 0x80000000 | 8) + struct.pack('<II', 0x02, 100)

        cache = ModelCache(Assets())
        self.assertIsNone(cache.load('broken'))
        self.assertIsNone(cache.load_tree('broken'))
        self.assertIsNone(cache.load('gone'))
        self.assertEqual(list(cache.unreadable), ['broken'])


if __name__ == '__main__':
    unittest.main()
