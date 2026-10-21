import unittest

from mapworkshop.mapkit import vegetation


class Assets:
    """template_model for 'tree N' (model N), 'shrub N' and 'house'."""

    def template_model(self, template):
        kind, _, n = template.partition(' ')
        if kind == 'house':
            return dict(model='house', texture=None, tree=False, editor=False, kinds={'STRUCTURE'})
        return dict(model=f'{kind}{n}', texture='Bark.tga', tree=True, editor=False, kinds={kind.upper()})


def objects(templates, flags=0):
    return [dict(index=i, template=t, flags=flags) for i, t in enumerate(templates)]


class PastBuffersTests(unittest.TestCase):
    def test_trees_past_the_buffer_are_left_out_in_map_order(self):
        placed = objects(['house'] + ['tree 1'] * (vegetation.TREE_BUFFER + 3) + ['shrub 1'] * 5)
        self.assertEqual(vegetation.past_buffers(placed, Assets()),
                         set(range(vegetation.TREE_BUFFER + 1, vegetation.TREE_BUFFER + 4)))

    def test_shrubs_have_their_own_buffer(self):
        placed = objects(['shrub 1'] * (vegetation.SHRUB_BUFFER + 1) + ['tree 1'])
        self.assertEqual(vegetation.past_buffers(placed, Assets()), {vegetation.SHRUB_BUFFER})

    def test_kinds_of_tree_past_the_limit_are_left_out(self):
        placed = objects([f'tree {n}' for n in range(vegetation.TREE_TYPES + 2)] + ['tree 0'])
        self.assertEqual(vegetation.past_buffers(placed, Assets()),
                         {vegetation.TREE_TYPES, vegetation.TREE_TYPES + 1})

    def test_hidden_objects_take_no_place(self):
        placed = objects(['tree 1'] * vegetation.TREE_BUFFER, flags=2) + objects(['tree 1'])
        self.assertEqual(vegetation.past_buffers(placed, Assets()), set())


if __name__ == '__main__':
    unittest.main()
