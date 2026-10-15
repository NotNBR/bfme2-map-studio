"""Inspect BFME2 map scripts without applying another game's opcode enum.

Source provenance and semantic limits: docs/game/scripts.md.
formats.sections reads and writes the script chunks (PlayerScriptsList); this
module labels that tree for inspection: each node's size, whether it decoded,
and why not. It does not apply runtime compatibility migrations.
"""

from collections import Counter

from mapworkshop.formats import sections
from mapworkshop.formats.map import Chunk


VERSIONS = {name: tuple(sections.CHILDREN[name]) for name in
            ('ScriptList', 'ScriptGroup', 'Script', 'OrCondition', 'Condition', 'ScriptAction', 'ScriptActionFalse')}
CHILDREN = {'ScriptList': ('Script', 'ScriptGroup'),
            'ScriptGroup': ('Script', 'ScriptGroup'),
            'Script': ('OrCondition', 'ScriptAction', 'ScriptActionFalse'),
            'OrCondition': ('Condition',)}


def node(m, item, parent=None, depth=0):
    """One script chunk as sections reads it, with its size, payload_decoded
    and, when it stayed raw, the reason and its bytes as hex. `item` may also
    be a raw formats.map.Chunk."""
    if isinstance(item, Chunk):
        item = sections.read_child(item, m)
    name, version = item['chunk'], item['version']
    result = dict(chunk=name, version=version, bytes=len(sections.child_payload(item, m)), payload_decoded=False)
    if 'raw' in item or depth > 64:
        if depth > 64:
            reason = 'Script nesting exceeds tool limit of 64'
        elif parent and (name not in CHILDREN.get(parent[0], ()) or
                         (parent == ('ScriptGroup', 1) or parent == ('ScriptGroup', 2)) and name == 'ScriptGroup'):
            reason = f'Unexpected child of {parent[0]}'
        elif version not in VERSIONS.get(name, ()):
            reason = f'Unsupported {name} version {version}'
        else:
            reason = item.get('error', 'Unreadable')
        result.update(reason=reason, raw_hex=sections.child_payload(item, m).hex())
        return result
    result.update((k, v) for k, v in item.items() if k not in ('chunk', 'version', 'children'))
    if 'children' in item:
        result['children'] = [node(m, child, (name, version), depth + 1) for child in item['children']]
    result['payload_decoded'] = all(c['payload_decoded'] for c in result.get('children', []))
    return result


def player_scripts(m):
    outer = m.chunk('PlayerScriptsList')
    if outer.version not in (1, 5, 6):
        raise ValueError(f'Unsupported PlayerScriptsList version {outer.version}')
    lists = sections.read(m, 'PlayerScriptsList')
    if any(item['chunk'] != 'ScriptList' for item in lists):
        raise ValueError('Expected ScriptList child')
    return [node(m, item) for item in lists]


def inventory(lists):
    versions, argument_types, signatures = Counter(), Counter(), Counter()
    incomplete = []
    coordinates = 0

    def visit(item, path):
        nonlocal coordinates
        path = path + [item.get('name', item['chunk'])]
        versions[f"{item['chunk']} v{item['version']}"] += 1
        if 'reason' in item:
            incomplete.append(dict(path=path, reason=item['reason']))
        if 'arguments' in item:
            types = tuple(a['type_id'] for a in item['arguments'])
            key = (item['chunk'], item['opcode_raw'], item['internal_name'], types)
            signatures[key] += 1
            argument_types.update(str(t) for t in types)
            coordinates += sum('position' in a for a in item['arguments'])
        for child in item.get('children', []):
            visit(child, path)

    for slot, item in enumerate(lists):
        visit(item, [f'list[{slot}]'])
    return dict(versions=dict(versions), argument_types=dict(argument_types),
                coordinate_arguments=coordinates, incomplete=incomplete,
                payloads_decoded=all(v['payload_decoded'] for v in lists),
                semantics_complete=False,
                signatures=[dict(chunk=k[0], opcode_raw=k[1], internal_name=k[2],
                                 argument_types=k[3], occurrences=n)
                            for k, n in sorted(signatures.items())])
