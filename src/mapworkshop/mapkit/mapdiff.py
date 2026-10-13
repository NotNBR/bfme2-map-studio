"""What changed between two maps, in a few lines: terrain, textures, objects,
every other section and map.ini. `mw diff` (cli.py) shows it.

Objects are matched by template and position, not by uniqueID: builds number
their objects in order, so one inserted object would renumber all after it.
An unmatched object of the same template and layer within MOVE_REACH of a
missing one counts as moved. Every `mw build` prints this against the
previous build and keeps it in its build.json (`changes`).
"""
from collections import Counter, defaultdict
import difflib
import math
from pathlib import Path

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map

MOVE_REACH = 300.0       # map units: farther apart is a removal plus an addition
HEIGHT_STEP = 0.0390625  # map units per stored height step
OWN_SECTIONS = ('HeightMapData', 'BlendTileData', 'ObjectsList')


# Comparing --------------------------------------------------------------------
def compare(before, after, before_ini=None, after_ini=None):
    """A dict of what changed from map `before` to map `after` (formats.map.Map),
    and from map.ini text `before_ini` to `after_ini` when both are given."""
    result = dict(terrain=_terrain(before, after), objects=_objects(before, after), sections={})
    names = [n for n in _section_names(before, after) if n not in OWN_SECTIONS]
    for name in names:
        change = _section(before, after, name)
        if change:
            result['sections'][name] = change
    if before_ini is not None and after_ini is not None and before_ini != after_ini:
        result['map_ini'] = [line for line in difflib.unified_diff(
            before_ini.splitlines(), after_ini.splitlines(), lineterm='', n=0)
            if line[:1] in '+-' and not line.startswith(('+++', '---'))]
    return result


def _section_names(before, after):
    seen = []
    for m in (before, after):
        for c in m.chunks:
            name = m.names[c.name_id]
            if name not in seen:
                seen.append(name)
    return seen


def _area(mask, border):
    """The map-unit box of the True cells of a sample grid."""
    rows, cols = np.nonzero(mask)
    x0, x1 = (cols.min() - border) * 10, (cols.max() - border) * 10
    y0, y1 = (rows.min() - border) * 10, (rows.max() - border) * 10
    return [int(x0), int(y0), int(x1), int(y1)]


def _terrain(before, after):
    a, b = before.heightmap(), after.heightmap()
    if a['elevations'].shape != b['elevations'].shape:
        return dict(resized=[[a['width'] - 2 * a['border'], a['height'] - 2 * a['border']],
                             [b['width'] - 2 * b['border'], b['height'] - 2 * b['border']]])
    border = b['border']
    result = {}
    delta = (b['elevations'].astype(np.int32) - a['elevations'].astype(np.int32)) * HEIGHT_STEP
    moved = delta != 0
    if moved.any():
        result['heights'] = dict(samples=int(moved.sum()), area=_area(moved, border),
                                 raised=max(round(float(delta.max()), 2), 0.), lowered=max(round(float(-delta.min()), 2), 0.))
    try:
        ta, tb = before.blend(inspection=True), after.blend(inspection=True)
    except ValueError as error:
        result['textures_unreadable'] = str(error)
        return result
    names_a, names_b = _texture_names(ta), _texture_names(tb)
    painted = names_a != names_b
    if painted.any():
        pairs = Counter(zip(names_a[painted].tolist(), names_b[painted].tolist()))
        result['textures'] = dict(cells=int(painted.sum()), area=_area(painted, border),
                                  changes=[[x, y, n] for (x, y), n in pairs.most_common()])
    blended = (ta['arrays']['blends'] != 0) != (tb['arrays']['blends'] != 0)
    if blended.any() and not painted.any():
        result['blends'] = dict(cells=int(blended.sum()), area=_area(blended, border))
    palette_a, palette_b = [t['name'] for t in ta['textures']], [t['name'] for t in tb['textures']]
    if palette_a != palette_b:
        result['palette'] = dict(added=[n for n in palette_b if n not in palette_a],
                                 removed=[n for n in palette_a if n not in palette_b])
    for plane in ('impassable', 'impassable_players', 'passage_widths', 'taintable', 'extra_passable',
                  'flammability', 'visible'):
        if plane in ta['arrays'] and plane in tb['arrays']:
            pa, pb = ta['arrays'][plane], tb['arrays'][plane]
            if (pa != pb).any():
                result[plane] = dict(set=int(((pb != 0) & (pa == 0)).sum()), cleared=int(((pa != 0) & (pb == 0)).sum()),
                                     area=_area(pa != pb, border))
    return result


def _texture_names(blend):
    """The texture name of every cell's primary tile ('' outside the palette)."""
    names = np.array([t['name'] for t in blend['textures']] + [''], dtype=object)
    owner = np.full(blend['arrays']['tiles'].shape, len(blend['textures']))
    for i, t in enumerate(blend['textures']):
        tiles = blend['arrays']['tiles']
        owner[(tiles >= t['tile_start']) & (tiles < t['tile_start'] + t['tile_count'])] = i
    return names[owner]


def _layer(o):
    return next((v for k, _, v in o['properties'] if k == 'objectLayer'), '')


def _rest(o):
    """What else describes an object, apart from its position and uniqueID."""
    return (o['z'], o['angle'], o['flags'], tuple(p for p in o['properties'] if p[0] != 'uniqueID'))


def _objects(before, after):
    a, b = before.objects(), after.objects()
    key = lambda o: (o['template'], round(o['x'], 1), round(o['y'], 1))
    waiting = defaultdict(list)
    for o in a:
        waiting[key(o)].append(o)
    changed, added = [], []
    for o in b:
        pending = waiting.get(key(o))
        if pending:
            old = pending.pop(0)
            if _rest(old) != _rest(o):
                changed.append((old, o))
        else:
            added.append(o)
    removed = [o for group in waiting.values() for o in group]
    moved = []
    by_kind = defaultdict(list)
    for o in removed:
        by_kind[o['template'], _layer(o)].append(o)
    still_added = []
    for o in added:
        candidates = by_kind.get((o['template'], _layer(o)), [])
        best = min(candidates, key=lambda c: math.dist((c['x'], c['y']), (o['x'], o['y'])), default=None)
        if best is not None and math.dist((best['x'], best['y']), (o['x'], o['y'])) <= MOVE_REACH:
            candidates.remove(best)
            moved.append((best, o))
        else:
            still_added.append(o)
    removed = [o for group in by_kind.values() for o in group]
    return dict(before=len(a), after=len(b), added=_groups(still_added), removed=_groups(removed),
                moved=[_move(old, new) for old, new in moved], changed=[_change(old, new) for old, new in changed])


def _groups(objects):
    """Objects by template and layer: count, centre and box."""
    groups = defaultdict(list)
    for o in objects:
        groups[o['template'], _layer(o)].append(o)
    result = []
    for (template, layer), items in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        xs, ys = [o['x'] for o in items], [o['y'] for o in items]
        result.append(dict(template=template, layer=layer, count=len(items),
                           at=[round(sum(xs) / len(xs)), round(sum(ys) / len(ys))],
                           area=[round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]))
    return result


def _move(old, new):
    return dict(template=new['template'], layer=_layer(new), before=[round(old['x']), round(old['y'])],
                after=[round(new['x']), round(new['y'])], distance=round(math.dist((old['x'], old['y']), (new['x'], new['y']))))


def _change(old, new):
    fields = [f for f, i in (('z', 0), ('angle', 1), ('flags', 2)) if _rest(old)[i] != _rest(new)[i]]
    props_a = {k: v for k, _, v in old['properties'] if k != 'uniqueID'}
    props_b = {k: v for k, _, v in new['properties'] if k != 'uniqueID'}
    fields += sorted(k for k in set(props_a) | set(props_b) if props_a.get(k) != props_b.get(k))
    return dict(template=new['template'], layer=_layer(new), at=[round(new['x']), round(new['y'])], fields=fields)


def _section(before, after, name):
    present = [any(m.names[c.name_id] == name for c in m.chunks) for m in (before, after)]
    if present != [True, True]:
        return dict(added=True) if present[1] else dict(removed=True)
    ca, cb = before.chunk(name), after.chunk(name)
    if ca.version != cb.version:
        return dict(version=[ca.version, cb.version])
    try:
        va, vb = sections.read(before, name), sections.read(after, name)
    except ValueError:
        return None if ca.data == cb.data else dict(bytes_changed=True)
    if va == vb:
        return None
    leaves = list(_leaves(va, vb, ''))
    return dict(changes=[dict(path=p, before=_plain(x), after=_plain(y)) for p, x, y in leaves])


def _is_props(value):
    return isinstance(value, list) and value and all(
        isinstance(p, tuple) and len(p) == 3 and isinstance(p[0], str) and isinstance(p[1], int) for p in value)


def _keyed(items):
    """Items keyed by their name when every item has a distinct one."""
    def name(item):
        if isinstance(item, dict):
            return item.get('name')
        if _is_props(item):
            return next((v for k, _, v in item if k in ('teamName', 'playerName')), None)
        return None
    names = [name(i) for i in items]
    if items and all(isinstance(n, str) and n for n in names) and len(set(names)) == len(names):
        return dict(zip(names, items))
    return None


MISSING = object()


def _leaves(a, b, path):
    """(path, before, after) for each differing value; MISSING where one side has none."""
    if a == b:
        return
    if _is_props(a) and _is_props(b):
        da, db = {k: v for k, _, v in a}, {k: v for k, _, v in b}
        for k in list(da) + [k for k in db if k not in da]:
            if da.get(k, MISSING) != db.get(k, MISSING):
                yield f'{path}.{k}' if path else k, da.get(k, MISSING), db.get(k, MISSING)
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for k in list(a) + [k for k in b if k not in a]:
            yield from _leaves(a.get(k, MISSING), b.get(k, MISSING), f'{path}.{k}' if path else str(k))
        return
    if isinstance(a, list) and isinstance(b, list):
        ka, kb = _keyed(a), _keyed(b)
        if ka is not None and kb is not None:
            for k in list(ka) + [k for k in kb if k not in ka]:
                yield from _leaves(ka.get(k, MISSING), kb.get(k, MISSING), f"{path}['{k}']")
            return
        if len(a) != len(b) and not (a and isinstance(a[0], (dict, list))) and not (b and isinstance(b[0], (dict, list))):
            yield path, a, b     # a list of plain values (points, names): report it whole
            return
        for i in range(max(len(a), len(b))):
            yield from _leaves(a[i] if i < len(a) else MISSING, b[i] if i < len(b) else MISSING, f'{path}[{i}]')
        return
    yield path, a, b


def _plain(value):
    if value is MISSING:
        return None
    if isinstance(value, bytes):
        return f'<{len(value)} bytes>'
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


# Text ---------------------------------------------------------------------------
def _number(v):
    if isinstance(v, float):
        return f'{v:.6g}'
    return str(v)


def _short(value):
    if value is None:
        return '(none)'
    if isinstance(value, str):
        return repr(value) if len(value) <= 60 else repr(value[:57] + '...')
    if isinstance(value, list):
        if value and all(isinstance(v, (int, float)) for v in value) and len(value) <= 4:
            return '(' + ', '.join(_number(v) for v in value) + ')'
        return f'[{len(value)} items]'
    if isinstance(value, dict):
        return repr(value.get('name') or value.get('chunk') or '{...}')
    return _number(value)


def _box(area):
    x0, y0, x1, y1 = area
    return f'({x0}, {y0})' if (x0, y0) == (x1, y1) else f'x {x0}..{x1}, y {y0}..{y1}'


def _tag(layer):
    return f' [{layer}]' if layer else ''


def _object_line(sign, g):
    where = f'at ({g["at"][0]}, {g["at"][1]})' if g['count'] == 1 else f'around ({g["at"][0]}, {g["at"][1]}), {_box(g["area"])}'
    return f'  {sign}{g["count"]} {g["template"]}{_tag(g["layer"])} {where}'


def lines(result, limit=12):
    """The comparison as short text lines; `limit` lines per part at most."""
    out = []
    t = result['terrain']
    if 'resized' in t:
        (w0, h0), (w1, h1) = t['resized']
        out.append(f'Terrain resized: {w0} x {h0} -> {w1} x {h1} cells.')
    if 'heights' in t:
        h = t['heights']
        extent = ', '.join(s for s in (f'+{h["raised"]:g}' if h['raised'] else '',
                                        f'-{h["lowered"]:g}' if h['lowered'] else '') if s)
        out.append(f'Heights: {h["samples"]:,} samples changed, {_box(h["area"])} (up to {extent}).')
    if 'textures' in t:
        x = t['textures']
        out.append(f'Textures: {x["cells"]:,} cells repainted, {_box(x["area"])}: '
                   + ', '.join(f'{a or "?"} -> {b or "?"} {n:,}' for a, b, n in x['changes'][:4])
                   + (f', {len(x["changes"]) - 4} more' if len(x['changes']) > 4 else '') + '.')
    if 'blends' in t:
        out.append(f'Texture blends: {t["blends"]["cells"]:,} cells changed, {_box(t["blends"]["area"])}.')
    if 'palette' in t:
        p = t['palette']
        out.append('Texture palette:' + (f' added {", ".join(p["added"])}' if p['added'] else '')
                   + (f' removed {", ".join(p["removed"])}' if p['removed'] else '') + '.')
    for plane in ('impassable', 'impassable_players', 'passage_widths', 'taintable', 'extra_passable',
                  'flammability', 'visible'):
        if plane in t:
            v = t[plane]
            out.append(f'{plane.replace("_", " ").capitalize()}: +{v["set"]:,} / -{v["cleared"]:,} cells, {_box(v["area"])}.')
    o = result['objects']
    added, removed = sum(g['count'] for g in o['added']), sum(g['count'] for g in o['removed'])
    counts = [text for n, text in ((added, f'+{added:,}'), (removed, f'-{removed:,}'),
                                   (len(o['moved']), f'{len(o["moved"]):,} moved'),
                                   (len(o['changed']), f'{len(o["changed"]):,} changed')) if n]
    if o['added'] or o['removed'] or o['moved'] or o['changed']:
        out.append(f'Objects: {o["before"]:,} -> {o["after"]:,} ({", ".join(counts)}).')
        # (layer, objects, line): layers with the fewest changes first, so a
        # deliberate edit shows above the scatter it shifted.
        detail = [(g['layer'], g['count'], _object_line('+', g)) for g in o['added']]
        detail += [(g['layer'], g['count'], _object_line('-', g)) for g in o['removed']]
        moved = defaultdict(list)
        for m in o['moved']:
            moved[m['layer'], m['template']].append(m)
        for (layer, template), group in moved.items():
            if len(group) == 1:
                m = group[0]
                line = (f'  moved {template}{_tag(layer)} ({m["before"][0]}, {m["before"][1]}) -> '
                        f'({m["after"][0]}, {m["after"][1]}), {m["distance"]} units')
            else:
                xs, ys = [m['after'][0] for m in group], [m['after'][1] for m in group]
                line = (f'  moved {len(group)} {template}{_tag(layer)}, up to {max(m["distance"] for m in group)} units, '
                        f'{_box([min(xs), min(ys), max(xs), max(ys)])}')
            detail.append((layer, len(group), line))
        changed = Counter((c['layer'], c['template'], tuple(c['fields'])) for c in o['changed'])
        detail += [(layer, n, f'  changed {n} {template}{_tag(layer)}: {", ".join(fields)}')
                   for (layer, template, fields), n in changed.items()]
        per_layer = Counter()
        for layer, n, _ in detail:
            per_layer[layer] += n
        detail.sort(key=lambda d: (per_layer[d[0]], d[0], d[1]))
        if len(per_layer) > 1:
            order = sorted(per_layer, key=lambda layer: (per_layer[layer], layer))
            out.append('  by layer: ' + ', '.join(f'{layer or "(none)"} {per_layer[layer]:,}' for layer in order[:10])
                       + (f', {len(order) - 10} more' if len(order) > 10 else ''))
        out += [line for _, _, line in detail[:limit]]
        if len(detail) > limit:
            out.append(f'  ... {len(detail) - limit} more (`--limit`, or --json for all)')
    for name, change in result['sections'].items():
        if change.get('added'):
            out.append(f'{name}: added.')
        elif change.get('removed'):
            out.append(f'{name}: removed.')
        elif 'version' in change:
            out.append(f'{name}: version {change["version"][0]} -> {change["version"][1]}.')
        elif change.get('bytes_changed'):
            out.append(f'{name}: changed (not readable as values).')
        else:
            items = change['changes']
            shown = [f'{c["path"] or "value"}: {_short(c["before"])} -> {_short(c["after"])}' for c in items[:3]]
            more = f'; {len(items) - 3} more' if len(items) > 3 else ''
            out.append(f'{name}: ' + '; '.join(shown) + more + '.')
    if result.get('map_ini'):
        ini = result['map_ini']
        out.append(f'map.ini: {len(ini)} lines changed.')
        out += ['  ' + line for line in ini[:limit]] + ([f'  ... {len(ini) - limit} more'] if len(ini) > limit else [])
    return out or ['No changes.']


# Files ------------------------------------------------------------------------------
def _ini(map_file):
    path = Path(map_file).with_name('map.ini')
    return path.read_text(encoding='ascii', errors='replace') if path.exists() else None


def compare_files(before, after):
    """compare() for two .map files, with the map.ini beside each."""
    before, after = Path(before), Path(after)
    return compare(Map(before.read_bytes()), Map(after.read_bytes()), _ini(before), _ini(after))
