"""Deterministic, transactional edits for a saved WorldBuilder document."""

import math
import random
import re

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map, differences, tile_offset


def finite(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError('Parameters must be finite')
    return value


def brush(terrain, op):
    x, y, radius = [finite(op[k]) for k in ('x', 'y', 'radius')]
    if radius <= 0:
        raise ValueError('Brush radius must be positive')
    border = terrain['border']
    w, h = terrain['width'], terrain['height']
    if not (0 <= x < (w - 2 * border) * 10 and 0 <= y < (h - 2 * border) * 10):
        raise ValueError('Brush center outside playable area')
    yy, xx = np.ogrid[:h, :w]
    weight = np.clip(1 - np.hypot((xx - border) * 10 - x, (yy - border) * 10 - y) / radius, 0, 1)
    weight = weight * weight * (3 - 2 * weight)
    if border:
        weight[:border, :] = weight[-border:, :] = 0
        weight[:, :border] = weight[:, -border:] = 0
    return weight


def apply_recipe(source, recipe):
    """Produce a new map in memory; no partial edit reaches the source document."""
    if recipe.get('schema') != 1 or not isinstance(recipe.get('operations'), list):
        raise ValueError('Expected recipe schema 1 and operations array')
    if len(recipe['operations']) > 1000:
        raise ValueError('Too many operations')
    m, before = Map(source), Map(source)
    before.report()
    terrain = m.heightmap()
    seed = int(recipe.get('seed', 0))
    rng = random.Random(seed)
    identifier = recipe.get('id', '')
    if not re.fullmatch('[a-z0-9_-]{1,48}', identifier):
        raise ValueError('Recipe id must be 1-48 lowercase letters, digits, underscores or hyphens')
    prefix = 'bfx_' + identifier + '_'
    existing = m.objects()
    if any(str(v).startswith(prefix) for o in existing for k, _, v in o['properties'] if k == 'uniqueID'):
        raise ValueError('This recipe already placed objects; use the base checkpoint to replay')
    protected = recipe.get('exclude_rects', [])
    for rect in protected:
        if len(rect) != 4 or not all(math.isfinite(float(v)) for v in rect) or rect[0] >= rect[2] or rect[1] >= rect[3]:
            raise ValueError('Invalid protected rectangle')
    changed = set()
    results = []
    for op_index, op in enumerate(recipe['operations']):
        action = op['op']
        if action in ('raise', 'flatten'):
            weight = brush(terrain, op)
            heights = terrain['elevations'].astype(float) * 0.0390625
            if action == 'raise':
                heights += weight * finite(op['amount'])
            else:
                strength = finite(op.get('strength', 1))
                if not 0 < strength <= 1:
                    raise ValueError('Flatten strength must be in (0,1]')
                heights += weight * strength * (finite(op['height']) - heights)
            encoded = np.rint(heights / 0.0390625)
            if encoded.min() < 0 or encoded.max() > 65535:
                raise ValueError('Height outside BFME2 uint16 range')
            stored = sections.read(m, 'HeightMapData')
            stored['elevations'] = encoded
            sections.write(m, 'HeightMapData', stored)
            terrain = m.heightmap()
            changed.add('HeightMapData')
            results.append(dict(op=action, samples=int(np.count_nonzero(weight))))
        elif action == 'paint':
            weight = brush(terrain, op)
            b = m.blend()
            matches = [t for t in b['textures'] if t['name'] == op['texture']]
            if len(matches) != 1:
                raise ValueError('Paint texture must already exist in this map palette')
            texture = matches[0]
            # Preserve repeating texture cells; WorldBuilder can feather the brush edge.
            yy, xx = np.indices(weight.shape)
            edge = texture['cell_size'] * 2
            tiles = texture['tile_start'] + tile_offset(xx, yy, texture['cell_size'])
            selection = weight > 0
            stored = sections.read(m, 'BlendTileData')
            arrays = dict(stored['arrays'])
            for name in ('tiles', 'blends', 'three_way', 'cliffs'):
                arrays[name] = arrays[name].copy()
                arrays[name][selection] = tiles[selection] if name == 'tiles' else 0
            stored['arrays'] = arrays
            sections.write(m, 'BlendTileData', stored)
            changed.add('BlendTileData')
            results.append(dict(op=action, samples=int(selection.sum())))
        elif action in ('scatter', 'place'):
            template = op['template']
            donors = [o for o in existing if o['template'] == template and o['flags'] == 0
                      and not any(k == 'objectName' and v for k, _, v in o['properties'])]
            if not donors or template.startswith('*'):
                raise ValueError('Choose an existing, unnamed object template, excluding roads/waypoints')
            if action == 'scatter' and not re.search('tree|rock|grass|bush|shrub|stump|fern|flower', template, re.I):
                raise ValueError('Scatter is restricted to scenery; use place for individual landmarks')
            count = int(op.get('count', 1)) if action == 'scatter' else 1
            if not 1 <= count <= 5000:
                raise ValueError('Object count must be 1-5000 per operation')
            gap = finite(op.get('spacing', 25))
            max_slope = finite(op.get('max_slope', 0.55))
            if gap <= 0 or max_slope < 0:
                raise ValueError('Invalid spacing/slope')
            w = (terrain['width'] - 2 * terrain['border']) * 10
            h = (terrain['height'] - 2 * terrain['border']) * 10
            bounds = [finite(v) for v in op.get('rect', [0, 0, w - 10, h - 10])]
            if len(bounds) != 4 or not (0 <= bounds[0] < bounds[2] < w and 0 <= bounds[1] < bounds[3] < h):
                raise ValueError('Scatter rectangle outside playable area')
            heights = terrain['elevations'].astype(float) * 0.0390625
            dy, dx = np.gradient(heights, 10)
            slope = np.hypot(dx, dy)
            blocked = m.blend()['arrays']['impassable']
            points = [(o['x'], o['y']) for o in existing]
            placed = 0
            for _ in range(max(1, count * 100)):
                if action == 'place':
                    x, y = finite(op['x']), finite(op['y'])
                else:
                    x, y = rng.uniform(bounds[0], bounds[2]), rng.uniform(bounds[1], bounds[3])
                if not (0 <= x < w - 10 and 0 <= y < h - 10):
                    raise ValueError('Object outside playable area')
                tx, ty = round(x / 10) + terrain['border'], round(y / 10) + terrain['border']
                invalid = (any(a <= x <= c and b <= y <= d for a, b, c, d in protected)
                           or slope[ty, tx] > max_slope or blocked[ty, tx]
                           or any((x - px)**2 + (y - py)**2 < gap**2 for px, py in points))
                if invalid:
                    if action == 'place':
                        raise ValueError('Placement violates slope, passability, spacing or protected area')
                    continue
                angle = math.radians(finite(op['angle_degrees'])) if 'angle_degrees' in op else rng.uniform(0, math.tau)
                m.append_object(donors[0], x, y, angle, f'{prefix}{op_index}_{placed}')
                points.append((x, y))
                placed += 1
                if placed == count:
                    break
            if placed != count:
                raise ValueError(f'Could place only {placed}/{count} {template}; expand region or reduce density')
            existing = m.objects()
            changed.add('ObjectsList')
            results.append(dict(op=action, template=template, placed=placed))
        else:
            raise ValueError(f'Unsupported operation: {action}')
    result = m.encode()
    parsed = Map(result)
    parsed.report()
    for a, b in zip(before.chunks, parsed.chunks):
        name = before.names[a.name_id]
        if name not in changed and a.encode() != b.encode():
            raise AssertionError(f'Unexpected modification to {name}')
    diff = differences(before, parsed)
    diff['operations'] = results
    diff['review_required'] = ['WorldBuilder open/save round trip', 'in-game rendering and pathfinding']
    return result, diff
