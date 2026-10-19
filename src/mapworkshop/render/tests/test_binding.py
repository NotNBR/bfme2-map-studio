"""MapRenderer._bind_batch sends each pass only the uniforms that change, without a GL context."""
import unittest

from mapworkshop.render.engine import MapRenderer


class Program(dict):
    """An object program that records what is written to it."""
    def __init__(self, names):
        super().__init__()
        self.written = []
        for name in names:
            self[name] = Uniform(self, name)


class Uniform:
    def __init__(self, program, name):
        self.program, self.name = program, name

    @property
    def value(self):
        raise AttributeError

    @value.setter
    def value(self, value):
        self.program.written.append((self.name, value))


class Texture:
    def __init__(self):
        self.bound = []

    def use(self, unit):
        self.bound.append(unit)


NAMES = ('tex', 'has_texture', 'technique', 'alpha_ref', 'texturing', 'camera_mode', 'pivot', 'uv_grid', 'detail_func',
         'mat_diffuse', 'mat_specular')


def batch(texture, diffuse=(1.0, 1.0, 1.0)):
    return dict(texture=texture, technique=0, alpha_ref=None, uniforms=dict(mat_diffuse=diffuse, mat_specular=(0.0, 0.0, 0.0)))


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.r = MapRenderer.__new__(MapRenderer)
        self.op = Program(NAMES)
        self.r._object_uniforms = frozenset(NAMES)

    def test_a_pass_sends_only_what_changes_from_one_batch_to_the_next(self):
        texture = Texture()
        self.r._begin_batches()
        self.r._bind_batch(self.op, batch(texture))
        self.assertEqual(len(self.op.written), len(NAMES))       # the first batch: everything
        self.op.written.clear()
        self.r._bind_batch(self.op, batch(texture, diffuse=(0.5, 0.5, 0.5)))
        self.assertEqual(self.op.written, [('mat_diffuse', (0.5, 0.5, 0.5))])
        self.assertEqual(texture.bound, [0])                     # bound once

    def test_each_pass_starts_again_and_a_changed_batch_is_worked_out_again(self):
        b = batch(Texture())
        self.r._begin_batches()
        self.r._bind_batch(self.op, b)
        self.r._begin_batches()                                  # the next pass: anything may have changed
        self.op.written.clear()
        self.r._bind_batch(self.op, b)
        self.assertEqual(len(self.op.written), len(NAMES))
        b['uniforms']['mat_diffuse'] = (0.2, 0.2, 0.2)           # as _apply_sky changes a sky dome
        b.pop('_binding')
        self.op.written.clear()
        self.r._bind_batch(self.op, b)
        self.assertEqual(self.op.written, [('mat_diffuse', (0.2, 0.2, 0.2))])


if __name__ == '__main__':
    unittest.main()
