import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest
from unittest import mock

import numpy as np

from mapworkshop.mapkit import memo

calls = []


@memo.pure
def scaled(a, factor=2.0):
    calls.append(factor)
    return a*factor, a+factor


PROJECT = '''
import numpy as np
LEVEL = 10.0
UNUSED = 1
OUT = None

def helper(n):
    return np.full((4, 4), LEVEL + n)

def terrain(n=1):
    return dict(z=helper(n), names=['a', 'b'])

def scenery(t):
    return UNUSED

def sets_out():
    global OUT
    OUT = 1
    return 0
'''


class MemoTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(memo, 'FOLDER', Path(self.folder.name)/'memo'),
                   mock.patch.object(memo, '_sizes', None), mock.patch.dict(memo._sources, clear=True),
                   mock.patch.dict(os.environ, {'MW_NO_CACHE': ''})]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.folder.cleanup)
        calls.clear()

    def test_pure_reuses_an_identical_call(self):
        a = np.arange(memo.SMALLEST, dtype=float).reshape(-1, 100)
        first = scaled(a, 3.0)
        again = scaled(a, factor=3.0)       # the same call, as a keyword
        self.assertEqual(calls, [3.0])
        for x, y in zip(first, again):
            np.testing.assert_array_equal(x, y)
            self.assertEqual(x.dtype, y.dtype)
        scaled(a, 4.0)
        b = a.copy(); b[0, 0] = -1
        scaled(b, 3.0)
        self.assertEqual(calls, [3.0, 4.0, 3.0])

    def test_pure_calculates_small_calls_and_without_the_cache(self):
        small = np.ones((10, 10))
        scaled(small); scaled(small)
        self.assertEqual(len(calls), 2)
        big = np.ones((memo.SMALLEST,))
        with mock.patch.dict(os.environ, {'MW_NO_CACHE': '1'}):
            scaled(big); scaled(big)
        self.assertEqual(len(calls), 4)
        self.assertFalse(memo.FOLDER.exists())

    def load(self, source, name='memo_project'):
        root = Path(self.folder.name)/'project'
        root.mkdir(exist_ok=True)
        (root/'map.py').write_text(textwrap.dedent(source), encoding='utf-8')
        spec = importlib.util.spec_from_file_location(name, root/'map.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.addCleanup(sys.modules.pop, name, None)
        return module, root

    def test_stage_key_follows_what_the_stage_reaches(self):
        m, root = self.load(PROJECT)
        key = memo.stage_key(m.terrain, root=root)
        self.assertEqual(key, memo.stage_key(m.terrain, root=root))
        m.UNUSED = 2                       # only scenery names it
        m.scenery = lambda t: None
        self.assertEqual(key, memo.stage_key(m.terrain, root=root))
        m.LEVEL = 11.0                     # helper, which terrain calls, names it
        self.assertNotEqual(key, memo.stage_key(m.terrain, root=root))
        m.LEVEL = 10.0
        self.assertNotEqual(key, memo.stage_key(m.terrain, (2,), root=root))
        (root/'heightmap.png').write_bytes(b'new reference')
        self.assertNotEqual(key, memo.stage_key(m.terrain, root=root))

    def test_stage_key_follows_edited_code(self):
        m, root = self.load(PROJECT)
        key = memo.stage_key(m.terrain, root=root)
        edited, _ = self.load(PROJECT.replace('LEVEL + n', 'LEVEL - n'), 'memo_project_edited')
        self.assertNotEqual(key, memo.stage_key(edited.terrain, root=root))

    def test_stage_returns_a_copy_and_refuses_global_assignment(self):
        m, root = self.load(PROJECT)
        notes = []
        first = memo.stage(m.terrain, root=root, note=notes.append)
        first['z'][:] = 0                  # a build changes what it got
        again = memo.stage(m.terrain, root=root, note=notes.append)
        np.testing.assert_array_equal(again['z'], np.full((4, 4), 11.0))
        self.assertEqual(again['names'], ['a', 'b'])
        self.assertIn('Reused', notes[-1])
        self.assertEqual(memo.stage(m.sets_out, root=root, note=notes.append), 0)
        self.assertIn('assigns the module global OUT', notes[-1])

    def test_prune_keeps_the_most_recently_used(self):
        entry = 2*8*memo.SMALLEST           # two float arrays per result
        with mock.patch.object(memo, 'BUDGET', int(3.5*entry)):
            for n in range(5):
                scaled(np.full(memo.SMALLEST, float(n)))
            kept = list(memo.FOLDER.glob('*/*.npz'))
            self.assertLessEqual(len(kept), 3)
            self.assertLessEqual(sum(p.stat().st_size for p in kept), memo.BUDGET)
            calls.clear()
            scaled(np.full(memo.SMALLEST, 4.0))   # the newest is kept
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
