"""Bridges the game spans between two map points (mapkit.bridges), as geometry.

Follows W3DBridge::load and getIndicesNVertices (BFME2 1.06 via Open-BFME-2):
the model's BRIDGE_LEFT piece starts at the first point, BRIDGE_SPAN repeats
as often as fits and BRIDGE_RIGHT ends at the second; the whole is scaled
along its axis to fit exactly, and by BridgeScale across and up. A model
without a span piece draws its left piece alone, stretched end to end. Each
end lies 0.25 above the terrain plus the object's z (loadBridges).
"""
import math

import numpy as np

FLOAT = 0.25          # BRIDGE_FLOAT_AMT
PIECES = ('BRIDGE_LEFT', 'BRIDGE_SPAN', 'BRIDGE_RIGHT')


def pieces(model):
    """{piece: [parts]} of a loaded model (render.w3d), by mesh name."""
    found = {}
    for part in model['parts']:
        name = (part.get('name') or '').upper()
        for piece in PIECES:
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
    """(first, second) objects of each bridge: a 0x10 object directly followed by a 0x20 one."""
    pairs = []
    for a, b in zip(objects, objects[1:]):
        if a['flags'] & 0x10 and b['flags'] & 0x20:
            pairs.append((a, b))
    return pairs
