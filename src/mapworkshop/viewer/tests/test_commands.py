"""viewer.commands: keys, scene checks and menu entries, without GLFW."""
import unittest

from mapworkshop.viewer.commands import Command, Commands, parse_key


def registry(ran):
    c = Commands(lambda name: name)         # GLFW key names stand in for key codes
    c.add(Command('border', lambda: ran.append('border'), 'Map border', ('B',), checked=lambda: True),
          Command('build', lambda: ran.append('build'), keys=('Ctrl+B',), needs_scene=False),
          Command('grid', lambda: ran.append('grid'), 'Grid', ('G',), checked=lambda: False),
          Command('delete', lambda: ran.append('delete'), keys=('Del',), when=lambda: False))
    return c


class CommandTests(unittest.TestCase):
    def test_key_names_follow_the_docs(self):
        self.assertEqual(parse_key('Ctrl+B'), ('B', True))
        self.assertEqual(parse_key('Esc'), ('ESCAPE', False))
        self.assertEqual(parse_key('7'), ('7', False))
        with self.assertRaises(ValueError):
            parse_key('Shift+X')

    def test_a_ctrl_binding_takes_its_key_from_the_plain_one(self):
        ran = []
        c = registry(ran)
        c.run(c.for_key('B', ctrl=True), scene=True)
        c.run(c.for_key('B', ctrl=False), scene=True)
        c.run(c.for_key('G', ctrl=True), scene=True)     # no Ctrl+G: G answers
        self.assertEqual(ran, ['build', 'border', 'grid'])
        self.assertIsNone(c.for_key('Q', ctrl=False))

    def test_commands_wait_for_a_scene_and_their_condition(self):
        ran = []
        c = registry(ran)
        self.assertFalse(c.run('border', scene=False))
        self.assertTrue(c.run('build', scene=False))
        self.assertFalse(c.run('delete', scene=True))
        self.assertEqual(ran, ['build'])

    def test_a_key_cannot_be_bound_twice(self):
        c = registry([])
        with self.assertRaises(ValueError):
            c.add(Command('other', lambda: None, keys=('G',)))

    def test_menu_entries_are_checked_only_with_a_scene(self):
        c = registry([])
        layout = ('grid', None, 'border')
        self.assertEqual(c.menu(layout, scene=True),
                         [('grid', 'Grid', False), (None, '', None), ('border', 'Map border', True)])
        self.assertEqual(c.menu(layout, scene=False)[2], ('border', 'Map border', False))


if __name__ == '__main__':
    unittest.main()
