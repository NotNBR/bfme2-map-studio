"""Static BFME2 walkability, without a game process or a GPU.

Terrain follows Open-BFME-2 classifyMapCell (0x52E11A) and classifyMap
(0x52F2EC). Footprint sampling follows the partial 0x530212 reconstruction
supplied in the c742 Open-BFME-2 worktree (build/footprint/current.cpp).
The two water limits were read from BFME2 1.06 AIData: 5 and 6 units.

This is an editor estimate of the initial map, not a simulation: spawned
fortresses, moving units, scripts, gate states and destructible walls can
change routes in game. Footprints and bridge connections remain subject to
comparison with native captures. Unknown templates/geometry are reported.
"""
import copy
import math
import re
from pathlib import Path

import numpy as np

from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.mapkit.lines import inside

CELL = 10
NUMBER = r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'


def number(text, default=0.):
    """The number a value starts with, as the game's INI reader takes it:
    '177.0+' and '8.0CA' (both in the retail INI) read 177.0 and 8.0."""
    match = re.match(NUMBER, text.strip())
    return float(match.group(0)) if match else default


def template_data(templates, name, cache=None, visiting=None):
    """Inherited KindOf, geometry and walking meshes from object INI entries."""
    cache = {} if cache is None else cache
    visiting = set() if visiting is None else visiting
    name = name.lower()
    if name in cache:
        return cache[name]
    entry = templates.get(name)
    if entry is None or name in visiting:
        return None
    visiting.add(name)
    parent = template_data(templates, entry['parent'], cache, visiting) if entry.get('parent') else None
    result = copy.deepcopy(parent) if parent else dict(kinds=set(), shapes=[], small=False, scale=1., meshes={})
    shape = result['shapes'][0] if result['shapes'] else None
    # INI nesting matters: module-local Geometry/Scale must not replace object data.
    # A bare word opens a block (DefaultModelConditionState, ArmorSet, ...);
    # statements with arguments (ParticleSysBone bone system, script calls
    # such as CurDrawableHideSubObject(...)) do not, and the lines of a
    # BeginScript ... EndScript region are skipped.
    depth, script = 0, False
    for raw in entry['body'].splitlines():
        line = raw.split(';', 1)[0].split('//', 1)[0].strip()
        if not line:
            continue
        if script:
            script = not re.match(r'^EndScript\b', line, re.I)
            continue
        if re.match(r'^BeginScript\b', line, re.I):
            script = True
            continue
        if re.match(r'^End\b', line, re.I):
            depth = max(0, depth - 1)
            continue
        match = re.match(r'(\w+)\s*=\s*(.*)', line)
        if not match:
            if not line.startswith('#') and re.fullmatch(r'\w+', line):
                depth += 1
            continue
        key, value = match.group(1).lower(), match.group(2).strip()
        if key in ('draw', 'behavior', 'body', 'clientupdate', 'clientbehavior', 'locomotorset',
                   'armorset', 'weaponset', 'modelconditionstate', 'animationstate', 'transitionstate', 'animation'):
            depth += 1
            continue
        if key in ('wallboundsmesh', 'rampmesh1', 'rampmesh2'):
            result['meshes'][key] = value
        if depth:
            continue
        if key == 'kindof':
            tokens = value.upper().split()
            if not any(t.startswith(('+', '-')) for t in tokens):
                result['kinds'] = set(tokens)
            else:
                for token in tokens:
                    if token.startswith('-'):
                        result['kinds'].discard(token[1:])
                    else:
                        result['kinds'].add(token.lstrip('+'))
        elif key in ('geometry', 'additionalgeometry', 'othergeometry'):
            shape = dict(type=value.upper(), major=0., minor=0., offset=(0., 0., 0.), enabled=key != 'othergeometry')
            if key == 'geometry':
                result['shapes'] = [shape]
            else:
                result['shapes'].append(shape)
        elif key in ('geometrymajorradius', 'geometryminorradius') and shape is not None:
            shape['major' if key == 'geometrymajorradius' else 'minor'] = number(value)
        elif key == 'geometryoffset' and shape is not None:
            xyz = {k.upper(): float(v) for k, v in re.findall(r'([XYZ]):\s*('+NUMBER+')', value)}
            shape['offset'] = tuple(xyz.get(k, 0.) for k in 'XYZ')
        elif key == 'geometryissmall':
            result['small'] = value.lower() == 'yes'
        elif key == 'scale':
            result['scale'] = number(value, 1.)
        elif key == 'fencewidth':
            result['fence'] = number(value)
    visiting.remove(name)
    cache[name] = result
    return result


def _neighbours(mask, diagonal=True):
    """Number of matching neighbours, with no wraparound at map edges."""
    padded = np.pad(mask.astype(np.uint8), 1)
    h, w = mask.shape
    count = np.zeros(mask.shape, np.uint8)
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))[:8 if diagonal else 4]:
        count += padded[1+dy:1+dy+h, 1+dx:1+dx+w]
    return count


def terrain_grid(m, water_depth=5., deep_water_depth=6.):
    """Classify corners in the native order, then expand cliffs into clear neighbours."""
    hm = m.heightmap()
    border = hm['border']
    h, w = hm['height']-2*border, hm['width']-2*border
    heights = hm['elevations'] * .0390625
    yy, xx = np.indices((h+1, w+1))
    z = heights[np.minimum(yy+border, hm['height']-1), np.minimum(xx+border, hm['width']-1)]
    level = np.full(z.shape, -np.inf)
    for area in records(m, 'StandingWaterAreas'):
        wet = inside(area['points'], xx*CELL, yy*CELL)
        level[wet] = np.maximum(level[wet], int(area['water_height']))
    depth = level-z
    ground = np.zeros((h, w), np.uint32)
    # Deliberately not max(depth): a later shallow corner replaces deep water.
    for y, x in ((0, 0), (1, 0), (1, 1), (0, 1)):
        d = depth[y:y+h, x:x+w]
        ground[d > water_depth] = 1
        ground[d > deep_water_depth] = 7
    cliffs = m.blend(inspection=True)['arrays']['impassable'][border:border+h, border:border+w].astype(bool)
    ground[cliffs] = 2
    ground[(ground == 0) & (_neighbours(cliffs) > 0)] = 2
    return ground


def footprint_cells(shape, obj, size):
    """Native 5-unit box sampling and circle expansion, as clipped (y, x) arrays."""
    c, s = math.cos(obj['angle']), math.sin(obj['angle'])
    ox, oy, _ = shape['offset']
    x, y = obj['x']+ox*c-oy*s, obj['y']+ox*s+oy*c
    major, minor = shape['major'], shape['minor']
    if shape['type'] == 'BOX':
        iy, ix = np.indices((max(0, math.ceil(2*minor/5)), max(0, math.ceil(2*major/5))))
        xx = x-major*c-minor*s + ix*5*c+iy*5*s
        yy = y+minor*c-major*s + ix*5*s-iy*5*c
        xs, ys = np.floor((xx+.5)*.1).astype(int), np.floor((yy+.5)*.1).astype(int)
    elif shape['type'] in ('SPHERE', 'CYLINDER'):
        radius = major*.1+.4
        x0, y0 = math.floor((x-major)*.1+.5)-1, math.floor((y-major)*.1+.5)-1
        ys, xs = np.mgrid[y0:int(y0+2*radius+2), x0:int(x0+2*radius+2)]
        keep = (xs+.5-x*.1)**2 + (ys+.5-y*.1)**2 <= radius**2
        ys, xs = ys[keep], xs[keep]
    else:
        return np.array([], int), np.array([], int)
    keep = (xs >= 0) & (ys >= 0) & (xs < size[1]-1) & (ys < size[0]-1)
    flat = np.unique(ys[keep]*size[1]+xs[keep])
    return flat//size[1], flat % size[1]


def _pinch(ground, ys, xs):
    if not len(xs):
        return
    # The native footprint pass only touches its bounds, plus one cell.
    y0, y1 = max(0, ys.min()-2), min(ground.shape[0], ys.max()+3)
    x0, x1 = max(0, xs.min()-2), min(ground.shape[1], xs.max()+3)
    area = ground[y0:y1, x0:x1]
    clear = area == 0
    pinched = clear & ((_neighbours(clear) < 4) | (_neighbours(clear, False) < 2))
    # Ignore the window's artificial edge.
    pinched[[0, -1], :] = False
    pinched[:, [0, -1]] = False
    area[pinched] = 5


def polygon_cells(points, shape):
    """Cells with a corner inside a walking polygon; only examine its bounding box."""
    p = np.asarray(points)
    lo = np.maximum(np.floor(p.min(axis=0)/CELL).astype(int)-1, 0)
    hi = np.minimum(np.ceil(p.max(axis=0)/CELL).astype(int)+1, (shape[1], shape[0]))
    if np.any(hi <= lo):
        return np.array([], int), np.array([], int)
    ys, xs = np.mgrid[lo[1]:hi[1], lo[0]:hi[0]]
    keep = np.zeros(xs.shape, bool)
    for dx, dy in ((0, 0), (0, 1), (1, 1), (1, 0)):
        keep |= inside(points, (xs+dx)*CELL, (ys+dy)*CELL)
    return ys[keep], xs[keep]


def compute(m, *, assets=None, map_ini='', models=None):
    """A grid compatible with walkable.analyse; no native dump is loaded or written."""
    from mapworkshop.assets.library import GameAssets
    from mapworkshop.assets.models import ModelCache
    from mapworkshop.mapkit.bridges import bridge_types
    from mapworkshop.mapkit.bridges import endpoint_pairs, pieces

    assets = assets if assets is not None else GameAssets()
    # Isolate map overrides: never leave one map's templates in a shared asset cache.
    if map_ini:
        assets = copy.copy(assets)
        assets._templates = dict(assets.templates)
        # Map-local `Object ExistingName` patches inherit omitted base fields.
        base = dict(assets.templates)
        assets.add_map_templates(map_ini)
        for name, entry in list(assets.templates.items()):
            if name in base and entry is not base[name] and not entry.get('parent'):
                inherited = '__walkable_base_'+name
                assets.templates[inherited] = base[name]
                assets.templates[name] = dict(entry, parent=inherited)
    models = models or ModelCache(assets)
    ground = terrain_grid(m)
    cache, warnings = {}, set()
    objects = m.objects()
    for obj in objects:
        if obj['flags'] & 0x30 or obj['template'].startswith('*'):
            continue
        data = template_data(assets.templates, obj['template'], cache)
        if data is None:
            warnings.add('Unknown object template: '+obj['template'])
            continue
        kinds = data['kinds']
        if kinds & {'PROJECTILE', 'BRIDGE_TOWER', 'DO_NOT_CLASSIFY'}:
            continue
        if data.get('fence', 0) > 0 and not kinds & {'WALK_ON_TOP_OF_WALL', 'DEFENSIVE_WALL'}:
            warnings.add('Fence footprint is not yet supported: '+obj['template'])
        if 'STRUCTURE' not in kinds or 'IMMOBILE' not in kinds or data['small']:
            continue
        if 'WALK_ON_TOP_OF_WALL' in kinds:
            warnings.add('Walking mesh coverage is approximate: '+obj['template'])
            model_info = assets.template_model(obj['template'])
            model = models.load(model_info['model']) if model_info else None
            found = False
            if model:
                c, s = math.cos(obj['angle']), math.sin(obj['angle'])
                rotation = np.array([[c, s], [-s, c]])
                names = {v.lower() for v in data['meshes'].values()}
                scale = data['scale'] * next((float(v) for k, _, v in obj['properties']
                                               if k == 'objectPrototypeScale' and float(v) > 0), 1.)
                for part in model.get('collision', []):
                    if part['name'].lower() not in names:
                        continue
                    found = True
                    points = part['positions'][:, :2] * scale @ rotation + [obj['x'], obj['y']]
                    for triangle in np.asarray(part['indices']).reshape(-1, 3):
                        ys, xs = polygon_cells(points[triangle], ground.shape)
                        ground[ys, xs] = 8
            if not found:
                warnings.add('Missing walking mesh: '+obj['template'])
            continue
        if obj['z'] > 10:
            continue
        all_y, all_x = [], []
        for shape in data['shapes']:
            if not shape['enabled'] or shape['offset'][2] > 10:
                continue
            if shape['type'] not in ('BOX', 'CYLINDER', 'SPHERE'):
                warnings.add('Unsupported geometry: '+obj['template']+' '+shape['type'])
                continue
            ys, xs = footprint_cells(shape, obj, ground.shape)
            ground[ys, xs] = 4
            all_y.extend(ys)
            all_x.extend(xs)
        _pinch(ground, np.asarray(all_y, int), np.asarray(all_x, int))
        if kinds & {'BLOCKING_GATE', 'WALL_UPGRADE'}:
            warnings.add('Dynamic gate/wall state is not simulated: '+obj['template'])
    layers = []
    pairs = endpoint_pairs(objects)
    types = {k.lower(): v for k, v in bridge_types(assets.ini_text('roads.ini')+'\n'+map_ini).items()} if pairs else {}
    for a, b in pairs:
        warnings.add('Bridge deck edges and bank connections are approximate: '+a['template'])
        kind = types.get(a['template'].lower())
        model = models.load(kind['model'].lower()) if kind and kind['model'] else None
        left = pieces(model).get('BRIDGE_LEFT') if model else None
        if not left:
            warnings.add('Missing spanned bridge model: '+a['template'])
            continue
        vertices = np.concatenate([p['positions'] for p in left])
        width = (vertices[:, 1].max()-vertices[:, 1].min())*kind['scale']
        start, end = np.array([a['x'], a['y']]), np.array([b['x'], b['y']])
        axis = end-start
        length = np.linalg.norm(axis)
        if length < .001:
            continue
        across = np.array([-axis[1], axis[0]])/length*width/2
        points = [start+across, end+across, end-across, start-across]
        ys, xs = polygon_cells(points, ground.shape)
        if len(xs):
            x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()+1), int(ys.max()+1)
            cells = np.full((y1-y0, x1-x0), 5, np.uint32)
            cells[ys-y0, xs-x0] = 0
            layers.append(dict(index=len(layers)+2, x0=x0, y0=y0, width=x1-x0, height=y1-y0, bridge=True, cells=cells))
        if a['z'] > 10 or b['z'] > 10:
            warnings.add('Raised bridge endpoints may not connect to terrain: '+a['template'])
    return dict(ground=ground, layers=layers,
                info=dict(source='computed', water_depth=5., deep_water_depth=6., warnings=sorted(warnings)))


def from_file(map_file, *, assets=None):
    from mapworkshop.formats.map import Map
    path = Path(map_file)
    ini = path.with_name('map.ini')
    return compute(Map(path.read_bytes()), assets=assets,
                   map_ini=ini.read_text(encoding='cp1252') if ini.is_file() else '')
