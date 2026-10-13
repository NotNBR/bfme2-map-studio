"""Synthetic script records; no retail script payloads or opcode-name guesses."""

import struct
import unittest

from mapworkshop.formats.map import Chunk, Map, string
from mapworkshop.formats.scripts import inventory, node, player_scripts
from mapworkshop.formats.tests.fixtures import fixture


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.m = Map(fixture())

    def chunk(self, name, version, data):
        return Chunk(self.m.intern(name), version, data)

    def operand(self, name='ScriptAction', version=3, args=None):
        args = args if args is not None else [struct.pack('<I3f', 16, 12, 25, 8),
            struct.pack('<Iif', 77, -2, .5) + string('Keep all fields')]
        key = b'\3' + self.m.intern('TEST_ACTION').to_bytes(3, 'little')
        data = struct.pack('<I', 900) + key + struct.pack('<I', len(args)) + b''.join(args)
        data += struct.pack('<2I' if name == 'Condition' else '<I',
                            *((1, 1) if name == 'Condition' else (1,)))
        return self.chunk(name, version, data)

    def script(self, children=b''):
        data = b''.join(string(s) for s in ('Test', '', '', ''))
        data += struct.pack('<6BIBBiB', 1, 1, 1, 0, 1, 0, 15, 1, 0, -1, 2)
        data += string('ExampleTeam') + string('ALL') + children
        return self.chunk('Script', 4, data)

    def test_hierarchy_and_both_action_branches(self):
        condition = self.operand('Condition', 6)
        disjunction = self.chunk('OrCondition', 1, condition.encode())
        script = self.script(disjunction.encode() + self.operand().encode()
                             + self.operand('ScriptActionFalse').encode())
        group = self.chunk('ScriptGroup', 3, string('Group') + b'\1\0' + script.encode())
        script_list = self.chunk('ScriptList', 1, group.encode())
        outer = self.chunk('PlayerScriptsList', 1, script_list.encode())
        self.m.chunks.append(outer)
        before = self.m.encode()
        parsed = player_scripts(self.m)
        report = inventory(parsed)
        self.assertTrue(report['payloads_decoded'])
        self.assertFalse(report['semantics_complete'])
        self.assertEqual(report['coordinate_arguments'], 3)
        self.assertEqual(report['versions']['ScriptActionFalse v3'], 1)
        data = parsed[0]['children'][0]['children'][0]
        self.assertEqual(data['evaluation_interval_raw'], 15)
        self.assertEqual(data['player_mask_text'], 'ALL')
        self.assertEqual(self.m.encode(), before)

    def test_argument_storage_does_not_assume_shared_game_enum(self):
        parsed = node(self.m, self.operand())
        self.assertTrue(parsed['payload_decoded'])
        self.assertEqual(parsed['arguments'][0]['position'], (12, 25, 8))
        self.assertEqual(parsed['arguments'][1], dict(type_id=77, int_value=-2,
                         float_value=.5, string_value='Keep all fields'))
        self.assertEqual(parsed['opcode_raw'], 900)
        self.assertEqual(parsed['internal_name'], 'TEST_ACTION')

    def test_truncation_trailing_data_and_unknown_versions_remain_visible(self):
        original = self.operand()
        for data in (original.data[:-1], original.data + b'\0'):
            parsed = node(self.m, self.chunk('ScriptAction', 3, data))
            self.assertFalse(parsed['payload_decoded'])
            self.assertEqual(parsed['raw_hex'], data.hex())
        child = self.chunk('FutureScript', 1, b'opaque')
        parsed = node(self.m, self.script(child.encode()))
        self.assertFalse(parsed['payload_decoded'])
        self.assertIn('Unexpected child', parsed['children'][0]['reason'])
        parsed = node(self.m, self.chunk('Script', 99, b'opaque'))
        self.assertFalse(parsed['payload_decoded'])
        self.assertIn('version 99', parsed['reason'])

    def test_bad_key_and_excessive_nesting_are_reported(self):
        action = self.operand()
        damaged = action.data[:5] + b'\xff\xff\xff' + action.data[8:]
        self.assertFalse(node(self.m, self.chunk('ScriptAction', 3, damaged))['payload_decoded'])
        self.assertFalse(node(self.m, self.script(), depth=65)['payload_decoded'])

    def test_legacy_outer_layout_and_unknown_version(self):
        outer = self.chunk('PlayerScriptsList', 5, self.chunk('ScriptList', 1, b'').encode())
        self.m.chunks.append(outer)
        self.assertTrue(inventory(player_scripts(self.m))['payloads_decoded'])
        outer.version = 99
        with self.assertRaisesRegex(ValueError, 'version 99'):
            player_scripts(self.m)


if __name__ == '__main__':
    unittest.main()
