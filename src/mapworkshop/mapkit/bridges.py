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
docs/game/roads-and-bridges.md):
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

The renderer and viewer draw them as the game builds them (W3DBridge::load and
getIndicesNVertices, BFME2 1.06 via Open-BFME-2; pieces, layout, place): the
model's BRIDGE_LEFT piece starts at the first point, BRIDGE_SPAN repeats as
often as fits and BRIDGE_RIGHT ends at the second; the whole is scaled along
its axis to fit exactly, and by BridgeScale across and up. A model without a
span piece draws its left piece alone, stretched end to end. Each end lies
FLOAT above the terrain plus the object's z (loadBridges).
"""
import math
import re

import numpy as np

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
            from mapworkshop.assets.library import GameAssets
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
        m.add_object(o)


# Geometry -------------------------------------------------------------------
FLOAT = 0.25          # BRIDGE_FLOAT_AMT


def pieces(model):
    """{piece: [parts]} of a loaded model (assets.models.ModelCache), by mesh name."""
    found = {}
    for part in model['parts']:
        name = (part.get('name') or '').upper()
        for piece in SECTIONS:
            if name.startswith(piece) or '.' + piece in name:
                found.setdefault(piece, []).append(part)
    return found


def _extent(parts):
    x = np.concatenate([p['positions'][:, 0] for p in parts])
    return float(x.min()), float(x.max())


def layout(found, start, end, scale):
    """The pieces to draw as (piece, x offset), the axis vectors (vec, across,
    up) and how many spans; None if the model has no left piece."""
    if 'BRIDGE_LEFT' not in found:
        return None
    start, end = np.asarray(start, float), np.asarray(end, float)
    left_min, left_max = _extent(found['BRIDGE_LEFT'])
    sectional = 'BRIDGE_SPAN' in found and 'BRIDGE_RIGHT' in found
    if sectional:
        span_min, span_max = _extent(found['BRIDGE_SPAN'])
        right_min, right_max = _extent(found['BRIDGE_RIGHT'])
    else:
        span_min = span_max = right_min = right_max = left_max
    length = max(right_max - left_min, 1.0)
    fixed = not sectional or left_max > span_min + .05*length or right_min < span_max - .05*length
    axis = end - start
    desired = float(np.linalg.norm(axis))
    if desired < 1e-6:
        return None
    across = np.array([-axis[1], axis[0], 0.0])
    across = across/max(np.linalg.norm(across), 1e-9)*scale
    dz = (end[2] - start[2])/desired
    up = np.array([-dz, 0.0, math.sqrt(max(1 - dz*dz, 0.0))])*scale
    offset = -left_min
    if not sectional:
        return dict(draw=[('BRIDGE_LEFT', offset)], vec=axis/length, across=across, up=up, spans=0)
    span = right_min - left_max
    spans = 1
    if not fixed and span > 0:
        spans = max(int(math.floor((desired - (length - span) + span/2)/span)), 0)
    total = length + (spans - 1)*span
    draw = [('BRIDGE_LEFT', offset)] + [('BRIDGE_SPAN', offset + i*span) for i in range(spans)]
    draw.append(('BRIDGE_RIGHT', offset + (spans - 1)*span))
    return dict(draw=draw, vec=axis/total, across=across, up=up, spans=spans)


def place(part, offset, plan, start):
    """A part's positions and normals laid along the bridge (world coordinates)."""
    p = part['positions'].astype(np.float64)
    basis = np.stack([plan['vec'], plan['across'], plan['up']])          # rows: model x, y, z
    positions = (p + [offset, 0.0, 0.0]) @ basis + np.asarray(start, float)
    normals = part['normals'].astype(np.float64) @ basis
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    return positions.astype(np.float32), normals.astype(np.float32)


def endpoint_pairs(objects):
    """(first, second) objects of each bridge: a START object directly followed by an END one."""
    pairs = []
    for a, b in zip(objects, objects[1:]):
        if a['flags'] & START and b['flags'] & END:
            pairs.append((a, b))
    return pairs
