"""Author original modern BFME2 scripts using explicit typed arguments.

Ported from bfme-workshop's mapkit.script_writer (same author). Catalogue
signatures (mapkit/data/bfme2-1.06-scripts.json, docs/game/scripts.md)
validate storage shape, not gameplay semantics. No runtime enum is inferred
from an argument's Python value. Unknown signatures are refused.

    w = Writer(m)
    go = w.operation('action', 'MOVE_NAMED_UNIT_TO', [arg(14, text='Scout'), arg(7, text='Hill')])
    w.install([w.script('Go', [[w.operation('condition', 'CONDITION_TRUE')]], [go])], side_index=2)

Comparisons (argument type 6) store 0 less than, 1 less or equal, 2 equal,
3 greater or equal, 4 greater, as the stock maps' scripts do.
"""

import json
import math
import struct
from pathlib import Path

from mapworkshop.formats.map import Chunk, chunks, string


CATALOG = Path(__file__).parent/'data'/'bfme2-1.06-scripts.json'


def load_catalog(path=None):
    return json.loads(Path(path or CATALOG).read_text(encoding='utf-8'))


def arg(type_id, *, integer=0, real=0., text='', position=None):
    if not isinstance(type_id, int) or not 0 <= type_id <= 0xffffffff:
        raise ValueError('Invalid argument type')
    if type_id == 16:
        if position is None or len(position) != 3 or not all(math.isfinite(v) for v in position):
            raise ValueError('Coordinate argument needs three finite values')
        return dict(type_id=16, position=tuple(position))
    if position is not None or not math.isfinite(real):
        raise ValueError('Invalid scalar argument')
    if not isinstance(integer, int) or not -0x80000000 <= integer < 0x80000000:
        raise ValueError('Integer argument exceeds int32')
    string(text)  # Validate native string encoding and length now.
    return dict(type_id=type_id, int_value=integer, float_value=real, string_value=text)


def encode_argument(value):
    kind = value['type_id']
    checked = arg(kind, position=value.get('position')) if kind == 16 else arg(
        kind, integer=value['int_value'], real=value['float_value'], text=value['string_value'])
    if kind == 16:
        return struct.pack('<I3f', kind, *checked['position'])
    return struct.pack('<Iif', kind, checked['int_value'], checked['float_value']) + string(checked['string_value'])


class Writer:
    def __init__(self, map_file, catalog=None):
        if catalog is None:
            catalog = load_catalog()
        if catalog.get('game') != 'BFME2 1.06' or catalog.get('schema') != 1:
            raise ValueError('Expected BFME2 1.06 catalogue schema 1')
        self.map = map_file
        self.catalog = catalog

    def chunk(self, name, version, payload):
        return Chunk(self.map.intern(name), version, payload)

    def operation(self, kind, name, arguments=(), *, enabled=True, condition_flag=0, opcode=None):
        if kind not in ('condition', 'action', 'false_action'):
            raise ValueError('Unknown operation kind')
        table = self.catalog['condition' if kind == 'condition' else 'action']['templates']
        matches = [r for r in table if r['name'] == name and (opcode is None or r['opcode'] == opcode)]
        if len(matches) != 1:
            raise ValueError(f'Name must resolve to exactly one template: {name}')
        selected = matches[0]
        types = selected['argument_types']
        if types is None or any(t is None for t in types):
            raise ValueError(f'Unresolved argument signature: {name}')
        if [a['type_id'] for a in arguments] != types:
            raise ValueError(f'{name} expects argument types {types}')
        if enabled not in (False, True) or condition_flag not in (0, 1):
            raise ValueError('Flags must be boolean')
        if condition_flag and kind != 'condition':
            raise ValueError('Only conditions have the second raw flag')
        key = b'\3' + self.map.intern(name).to_bytes(3, 'little')
        data = struct.pack('<I', selected['opcode']) + key + struct.pack('<I', len(arguments))
        data += b''.join(encode_argument(a) for a in arguments)
        data += struct.pack('<I', enabled)
        if kind == 'condition':
            return self.chunk('Condition', 6, data + struct.pack('<I', condition_flag))
        return self.chunk('ScriptActionFalse' if kind == 'false_action' else 'ScriptAction', 3, data)

    def script(self, name, condition_groups, actions, false_actions=(), *, active=True,
               deactivate=True, interval=0, subroutine=False, easy=True, medium=True,
               hard=True, sequential=False, loop=False, loop_count=1,
               target_type_raw=0, target_name='', player_mask_text='ALL', comment='',
               conditions_comment='', actions_comment=''):
        if not name or not isinstance(interval, int) or not 0 <= interval <= 0xffffffff:
            raise ValueError('Script needs a name and uint32 interval')
        if not condition_groups or any(not group for group in condition_groups):
            raise ValueError('Supply explicit nonempty condition groups')
        if any(v not in (False, True) for v in (active, deactivate, subroutine, easy,
                                               medium, hard, sequential, loop)):
            raise ValueError('Script flags must be boolean')
        if not isinstance(loop_count, int) or not -0x80000000 <= loop_count < 0x80000000:
            raise ValueError('Loop count exceeds int32')
        if not isinstance(target_type_raw, int) or not 0 <= target_type_raw <= 255:
            raise ValueError('Target type must fit its raw byte')
        data = b''.join(string(s) for s in (name, comment, conditions_comment, actions_comment))
        data += struct.pack('<6BI', active, deactivate, easy, medium, hard, subroutine, interval)
        data += struct.pack('<BBiB', sequential, loop, loop_count, target_type_raw)
        data += string(target_name) + string(player_mask_text)
        for conditions in condition_groups:
            if any(self.map.names[c.name_id] != 'Condition' or c.version != 6 for c in conditions):
                raise ValueError('Expected Condition v6')
            data += self.chunk('OrCondition', 1, b''.join(c.encode() for c in conditions)).encode()
        for expected, items in (('ScriptAction', actions), ('ScriptActionFalse', false_actions)):
            if any(self.map.names[c.name_id] != expected or c.version != 3 for c in items):
                raise ValueError(f'Expected {expected} v3')
            data += b''.join(c.encode() for c in items)
        return self.chunk('Script', 4, data)

    def _children(self, items):
        from mapworkshop.formats.scripts import node
        items = list(items)
        for child in items:
            if (self.map.names.get(child.name_id), child.version) not in (('Script', 4), ('ScriptGroup', 3)):
                raise ValueError('Expected Script v4 or ScriptGroup v3')
            decoded = node(self.map, child, depth=1)
            if not decoded['payload_decoded']:
                raise ValueError('Invalid script/group payload or nesting depth')
        return items

    def group(self, name, children=(), *, active=True, subroutine=False):
        """Create a nested ScriptGroup v3; active/subroutine behavior needs native evidence."""
        if not name or any(v not in (False, True) for v in (active, subroutine)):
            raise ValueError('Group needs a name and boolean flags')
        data = string(name) + struct.pack('<2B', active, subroutine)
        data += b''.join(child.encode() for child in self._children(children))
        result = self.chunk('ScriptGroup', 3, data)
        self._children([result])  # Check the additional nesting level as installed.
        return result

    def install(self, scripts, *, side_index=0):
        outer = self.map.chunk('PlayerScriptsList')
        if outer.version != 1:
            raise ValueError('Expected PlayerScriptsList v1')
        lists = chunks(outer.data, self.map.names)
        if not 0 <= side_index < len(lists):
            raise ValueError('Script side index outside list')
        target = lists[side_index]
        if target.version != 1 or self.map.names[target.name_id] != 'ScriptList':
            raise ValueError('Expected ScriptList v1')
        if target.data:
            raise ValueError('Install requires an empty script list; existing scripts are not overwritten')
        target.data = b''.join(c.encode() for c in self._children(scripts))
        outer.data = b''.join(c.encode() for c in lists)
