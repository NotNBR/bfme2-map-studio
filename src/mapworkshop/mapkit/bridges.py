"""Bridges the game spans between two points: any length, walkable.

A `Bridge` type (roads.ini, or a map's own map.ini) names a model. Two
adjacent map objects carrying the type's name, flagged 0x10 and 0x20, place
one: the game (W3DBridgeBuffer::loadBridges) lays the model's BRIDGE_LEFT
piece at the first point, repeats BRIDGE_SPAN as often as fits, ends with
BRIDGE_RIGHT at the second point and scales the whole along its length to fit
exactly. BridgeScale sets width and height. Units walk a straight line from
one end to the other, 0.25 above the terrain at each end, whatever the model's
shape: put both ends on dry banks, ideally of equal height. Raising the ends
above the terrain breaks this (units then cross on the riverbed beneath).

Native evidence (bfme-workshop, 13 October 2026; see
docs/reference/mapping/navigation/roads-and-bridges.md):
- TEST_EuropeanBridgeWide spans 400 and 700 units cleanly; infantry, cavalry,
  catapults and trolls cross it on the deck as fast as on dry ground.
- A map.ini Bridge type with the same model works the same way.
- A model without the three sections (e.g. GenericTreeBridge's NBTreeBrdge)
  crashes the game while the map loads; add_bridge refuses one.
- TEST_NewBridgeWide (CBBrdge1, an arched stone bridge on piers) is crossed
  the same way, but its deck lies about 40 below the walkable line: it looks
  sunken, units walk above it. With its ends raised 40 it looks right, but
  units then cross on the riverbed.
Of BFME2's 12,751 models only CBWBrdgeArc (TEST_EuropeanBridgeWide, a flat
deck that matches the walkable line) and CBBrdge1 have the sections.

    add_bridge(m, 'TEST_EuropeanBridgeWide', (1040, 1600), (1460, 1600), name='ford')
    ini += bridge_type('MyStoneBridge', 'CBWBrdgeArc', scale=.8)   # wider; then
    add_bridge(m, 'MyStoneBridge', ..., map_ini=ini)

The renderer and viewer draw them the same way (render.bridges).
"""
import math
import re

START, END = 0x10, 0x20
SECTIONS = ('BRIDGE_LEFT', 'BRIDGE_SPAN', 'BRIDGE_RIGHT')


def bridge_types(text):
    """{name: dict(model, scale, texture)} for the Bridge blocks in INI text;
    a later block of the same name replaces an earlier one."""
    found = {}
    for name, body in re.findall(r'(?ms)^Bridge\s+(\S+)\s*\n(.*?)^End\b', text):
        model = re.search(r'(?im)^\s*BridgeModelName\s*=\s*(\S+)', body)
        scale = re.search(r'(?im)^\s*BridgeScale\s*=\s*([\d.]+)', body)
        texture = re.search(r'(?im)^\s*Texture\s*=\s*(\S+)', body)
        found[name] = dict(model=model.group(1) if model else None, scale=float(scale.group(1)) if scale else 1.0,
                           texture=texture.group(1) if texture else None)
    return found


def sections(assets, model):
    """Which of the three bridge pieces a model (a W3D name) has."""
    key = assets.model_key(model)
    if key is None:
        return set()
    data = assets.read(key).upper()
    return {s for s in SECTIONS if b'.' + s.encode() in data}


def check_type(assets, bridge, map_ini=''):
    """The bridge type's definition; raises ValueError if the game would not
    draw it (unknown type, missing model, model without the three sections)."""
    types = {**bridge_types(assets.ini_text('roads.ini')), **bridge_types(map_ini)}
    match = {k.lower(): v for k, v in types.items()}.get(bridge.lower())
    if match is None:
        raise ValueError(f'No Bridge type {bridge!r} in roads.ini or the map.ini; define one with bridge_type()')
    model = match['model'] or ''
    have = sections(assets, model)
    if have != set(SECTIONS):
        raise ValueError(f'Bridge {bridge}: model {model} lacks {", ".join(s for s in SECTIONS if s not in have)}; '
                         'a model without BRIDGE_LEFT/SPAN/RIGHT pieces crashes the game while the map loads')
    return match


def bridge_type(name, model='CBWBrdgeArc', scale=0.6, texture=None, radar_color=(140, 110, 70)):
    """A Bridge block for a map's map.ini: `model` drawn at `scale` width and height."""
    texture = texture or model + '.tga'
    lines = [f'Bridge {name}', f'  BridgeScale                    = {scale:g}',
             '  RadarColor                     = R:{} G:{} B:{}'.format(*radar_color)]
    for state in ('', 'Damaged', 'ReallyDamaged', 'Broken'):
        lines += [f'  BridgeModelName{state:<16}= {model}', f'  Texture{state:<24}= {texture}']
    return '\n'.join(lines + ['End']) + '\n'


def add_bridge(m, bridge, start, end, *, name, assets=None, map_ini='', layer='Bridges'):
    """Append the two endpoints of a spanned bridge of type `bridge`, from
    `start` to `end` (x, y in map units, on dry banks). Checks the type first
    (check_type) unless `assets` is False."""
    if assets is not False:
        if assets is None:
            from mapworkshop.render.assets import GameAssets
            assets = GameAssets()
        check_type(assets, bridge, map_ini)
    (x0, y0), (x1, y1) = start, end
    if not all(math.isfinite(v) for v in (x0, y0, x1, y1)) or math.hypot(x1 - x0, y1 - y0) < 20:
        raise ValueError('A bridge needs two finite points at least 20 units apart')
    identities = {v for o in m.objects() for k, _, v in o['properties'] if k == 'uniqueID'}
    if any(f'{name}_{suffix}' in identities for suffix in ('from', 'to')):
        raise ValueError(f'Bridge endpoint uniqueID {name}_from/_to already exists')
    for (x, y), flag, suffix in (((x0, y0), START, 'from'), ((x1, y1), END, 'to')):
        props = [('originalOwner', 3, '/team'), ('uniqueID', 3, f'{name}_{suffix}'), ('objectLayer', 3, layer)]
        o = dict(template=bridge, x=float(x), y=float(y), z=0., angle=0., flags=flag, properties=props)
        m.chunk('ObjectsList').data += m.encode_object(o).encode()
