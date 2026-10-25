"""Nanduhirion Compact: the authored 9,000 x 6,000 map with all sixteen starts.

This imports the validated compact map from the bundled references, so building
and opening it needs no external share ZIP or machine-specific source path.
Compared with Medium (9,900 x 8,100), X is reduced by 9% and Y by 26%.
Terrain heights follow the Y scale; gameplay objects keep their normal size.
All objectives remain; farm hints and ambience are cleaned up for usable space
and density. All four inner outposts sit in locally
carved recesses, using the two-thirds inset approved at viewer pin 2.
All four sit another 25 units toward the cliff, with slight stony crests
following freehand mark 1, adapted to each outpost's local orientation.
Opposite pairs retain matching inset distances. Static terrain and footprint checks
found all starts walkable and connected to the centre; a full match remains
unverified. Requires OpenBFME's sixteen-player support for play.

Derived from the community Nanduhirion map and the locally authored v2 layout.
Original assets remain credited to their respective creators.
"""
import math

import numpy as np
from PIL import Image

from mapworkshop.formats.map import Map
from mapworkshop.formats import sections
from mapworkshop.formats.terrain import decode_blend, encode_blend
from mapworkshop.mapkit.blank import add_object, corner_blend_records, fill_enclosed, set_heights, tile_offset
from mapworkshop.mapkit.cliffs import cliff_uvs, steep_cells
from mapworkshop.mapkit.lines import polyline_distance
from mapworkshop.mapkit.pathing import footprint_cells, template_data, terrain_grid
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.variety import spot_random

from .cleanup import repair
from .scenery import marked_cave_trees


# Viewer marks: pin 1 (3732.8, 1513.2) selects the outpost at
# (3727.6365, 1512); pin 2 (3586, 1625.1) proposes the inset destination.
# Use the building's centre, not the slightly offset selection pin.
INSET_TARGET = (3586.0, 1625.1)
INSET_FRACTION = 2 / 3
INSET_PAIR = ((3727.636474609375, 1512.0), (5292.0, 4360.0))
OTHER_PAIR = ((3675.272705078125, 4376.0), (5344.36376953125, 1496.0))
CLIFF_NUDGE = 25.0
# Open freehand mark 1: a low rocky ridge, not a filled polygon.
STONY_RIDGE = (
    (5473.5, 1840.2), (5476.8, 1825.9), (5484.0, 1813.0), (5493.1, 1802.0),
    (5504.4, 1791.6), (5515.1, 1781.4), (5526.0, 1770.0), (5535.8, 1760.1),
    (5549.5, 1748.8), (5565.9, 1739.6), (5580.0, 1730.0), (5591.2, 1720.8),
    (5606.6, 1708.9), (5616.9, 1699.7), (5625.6, 1688.2), (5635.3, 1675.3),
    (5646.1, 1657.8), (5655.1, 1644.0), (5662.0, 1630.6), (5668.0, 1617.3),
    (5672.0, 1604.2), (5678.5, 1588.7), (5687.3, 1575.8), (5693.4, 1563.8),
    (5694.9, 1549.2), (5696.6, 1529.7), (5698.1, 1515.5),
)


def stony_ridges(z, wx, wy, labels, palette, sites):
    """Carry the marked low crest around all four cliff-side recesses."""
    source = sites[-1]  # The south-east outpost beside freehand mark 1.
    sx, sy = source['position']
    c, s = math.cos(source['angle']), math.sin(source['angle'])
    local = [((x-sx)*c+(y-sy)*s, -(x-sx)*s+(y-sy)*c) for x, y in STONY_RIDGE]
    lines = []
    for site in sites:
        x, y = site['position']
        c, s = math.cos(site['angle']), math.sin(site['angle'])
        lines.append(tuple((x+u*c-v*s, y+u*s+v*c) for u, v in local))
    painted = np.zeros(z.shape, bool)
    raised = np.zeros(z.shape, bool)
    for line in lines:
        distance, along = polyline_distance(line, wx, wy, reach=90)
        length = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
        width = 62 + 8*np.sin(along/73) + 5*np.sin(along/37+.8)
        cross = np.clip(1-(distance/width)**2, 0, 1)**2
        taper = np.sin(np.pi*np.clip(along/length, 0, 1))**2
        addition = (14 + 2*np.sin(along/61)) * cross * taper
        # Let the rise fade before any building or capture-flag foundation.
        for site in sites:
            x, y = site['position']
            clearance = np.clip((np.hypot(wx-x, wy-y)-135)/55, 0, 1)
            addition *= clearance*clearance*(3-2*clearance)
        z += addition
        raised |= addition > .01
        stone = (distance < width*.55) & (addition > 3)
        labels[stone] = palette['RockEregion01']
        painted |= stone
    return raised, painted


def blend_recess_ground(blend, labels, painted):
    """Join local grass and courtyard wear with native corner alpha blends."""
    arrays = blend['arrays']
    region = painted.copy()
    for _ in range(2):
        p = np.pad(region, 1)
        region = np.logical_or.reduce([p[dy:dy+region.shape[0], dx:dx+region.shape[1]]
                                       for dy in range(3) for dx in range(3)])
    ys, xs = np.nonzero(region)
    y0, y1 = max(0, ys.min()-3), min(region.shape[0], ys.max()+4)
    x0, x1 = max(0, xs.min()-3), min(region.shape[1], xs.max()+4)
    patch = np.s_[y0:y1, x0:x1]
    local = fill_enclosed(labels[patch])
    starts = np.array([4*t['cell_start'] for t in blend['textures']])
    sizes = np.array([t['cell_size'] for t in blend['textures']])

    def tile_index(label, y, x):
        # The imported palette uses 4x4 classes throughout.
        assert np.all(sizes[label] == 4)
        return starts[label] + tile_offset(x+x0, y+y0, 4)

    primary, extra, records = corner_blend_records(local, tile_index)
    offset = len(blend['blend_records'])
    blend['blend_records'].extend(records)
    mask = region[patch]
    yy, xx = np.indices(local.shape)
    arrays['tiles'][patch][mask] = tile_index(local, yy, xx)[mask]
    arrays['blends'][patch][mask] = np.where(primary, primary+offset, 0)[mask]
    arrays['three_way'][patch][mask] = np.where(extra, extra+offset, 0)[mask]


def weather_cliff_feet(z, wx, wy, sites, walls, labels, palette):
    """Weathered stone and earth collect below cliffs, tapering into grass."""
    distance = distance_to(walls)*10
    painted = walls.copy()
    for site in sites:
        x, y = site['position']
        angle = site['angle']
        c, s = math.cos(angle), math.sin(angle)
        along = (wx-x)*c+(wy-y)*s
        across = -(wx-x)*s+(wy-y)*c
        local = np.hypot(along, across) < 340
        width = 19+7*np.sin(across/57)+5*np.sin(along/81)
        # Keep courtyard wear distinct and avoid painting an evenly spaced
        # decorative ring: the bands follow the actual cliff and its hollows.
        courtyard = np.hypot((along-30)/125, across/105) < 1
        # Small disconnected deposits, rather than a broad bare-earth skirt.
        deposit = np.sin(across/67+.6)+.55*np.cos(along/91) > .25
        soil = local & (distance < width) & (z < 10) & deposit & ~courtyard & ~walls
        labels[soil] = palette['DirtRhun01a']
        painted |= soil
    labels[walls] = palette['CliffRhun01']
    return painted


def outpost_trees(m, sites, assets):
    """Three irregularly grouped flank trees per outpost; keep entries clear."""
    hm = m.heightmap()
    b = hm['border']
    z = hm['elevations']*.0390625
    ground = terrain_grid(m)
    objects = m.objects()
    trees = [(o['x'], o['y']) for o in objects if o['template'].startswith('Tree')]
    structures = [(o['x'], o['y']) for o in objects
                  if 'STRUCTURE' in (template_data(assets, o['template']) or {}).get('kinds', set())]
    report = []
    for site in sites:
        x, y = site['position']
        c, s = math.cos(site['angle']), math.sin(site['angle'])
        for n, (along, across) in enumerate(((35, 185), (-70, 235), (95, -190))):
            target = (x+along*c-across*s, y+along*s+across*c)
            candidates = [(target[0]+dx, target[1]+dy)
                          for dx in range(-200, 201, 20) for dy in range(-200, 201, 20)]
            candidates.sort(key=lambda p: math.dist(p, target))
            for tx, ty in candidates:
                local_across = -(tx-x)*s+(ty-y)*c
                if abs(local_across) < 145 or math.dist((tx, ty), (x, y)) > 380:
                    continue
                if any(math.dist((tx, ty), p) < 95 for p in trees):
                    continue
                if any(math.dist((tx, ty), p) < 125 for p in structures):
                    continue
                gy, gx = round(ty/10), round(tx/10)
                if not np.isin(ground[gy-2:gy+3, gx-2:gx+3], (0, 1, 8)).all():
                    continue
                if np.ptp(z[gy+b-2:gy+b+3, gx+b-2:gx+b+3]) > 5:
                    continue
                template = ('TreeForlindon01', 'TreeForlindon02', 'TreeForlindon03')[n]
                rng = spot_random(1625, template, tx, ty)
                add_object(m, template, tx, ty, angle=rng.uniform(0, math.tau),
                           layer='Outpost trees', extra=[('objectPrototypeScale', 2, rng.uniform(.85, 1.0))])
                trees.append((tx, ty))
                report.append(dict(template=template, position=[tx, ty], outpost=[x, y]))
                break
            else:
                raise ValueError(f'No clear flank tree position beside outpost {x:.0f},{y:.0f}')
    return report


def inset_outposts(m, assets):
    """Carve paired low-ground pockets and keep their capture approach open."""
    hm = m.heightmap()
    border = hm['border']
    z = hm['elevations'].astype(float) * .0390625
    original_z = z.copy()
    yy, xx = np.indices(z.shape)
    wx, wy = (xx - border) * 10, (yy - border) * 10
    chunk = m.chunk('BlendTileData')
    blend = decode_blend(chunk.data, chunk.version, m)
    # Local weathering layers must blend over the imported grass palette.
    # Reuse the same texture assets at the end of the table; remapping the
    # original table would alter terrain elsewhere on the map.
    for name in ('DirtRhun01a', 'CliffRhun01'):
        texture = next(t for t in blend['textures'] if t['name'] == name)
        blend['textures'].append(dict(texture, cell_start=blend['texture_cells']))
        blend['texture_cells'] += texture['cell_count']
    arrays = blend['arrays']
    original_arrays = {key: value.copy() for key, value in arrays.items()}
    arrays.update({key: value.copy() for key, value in arrays.items()})
    objects = m.objects()
    first = INSET_PAIR[0]
    dx, dy = ((INSET_TARGET[i] - first[i]) * INSET_FRACTION for i in (0, 1))
    changed = np.zeros(z.shape, bool)
    floor = np.zeros(z.shape, bool)
    painted = np.zeros(z.shape, bool)
    starts = np.array([4*t['cell_start'] for t in blend['textures']])
    labels = np.searchsorted(starts, arrays['tiles'], side='right')-1
    palette = {t['name']: i for i, t in enumerate(blend['textures'])}
    moved = []
    # The second pair's original +X direction faces its own cliff. Recess it
    # by the same approved distance, rather than reusing the first diagonal.
    other = next(o for o in objects if o['template'] == 'Outpost'
                 and math.dist((o['x'], o['y']), OTHER_PAIR[0]) < 1)
    distance = math.hypot(dx, dy)
    shifts = ((INSET_PAIR, (dx, dy)),
              (OTHER_PAIR, (distance*math.cos(other['angle']), distance*math.sin(other['angle']))))
    for (old_x, old_y), sx, sy in [
            (position, sign*shift[0], sign*shift[1])
            for pair, shift in shifts for position, sign in zip(pair, (1, -1))]:
        obj = next(o for o in objects if o['template'] == 'Outpost'
                   and math.dist((o['x'], o['y']), (old_x, old_y)) < 1)
        flag = min((o for o in objects if o['template'] == 'CaptureFlag'),
                   key=lambda o: math.dist((o['x'], o['y']), (old_x, old_y)))
        x, y = old_x + sx, old_y + sy
        # Four-direction model inspection: the outpost's courtyard opens on
        # local +X (view heading 270). Turn it toward the original open lane.
        angle = math.atan2(old_y - y, old_x - x)
        c, s = math.cos(angle), math.sin(angle)
        # All four use the approved closer placement, while their recesses
        # stay centred where they were to avoid cutting deeper into the hill.
        nudge = CLIFF_NUDGE
        x, y = x-nudge*c, y-nudge*s
        along = (wx - x) * c + (wy - y) * s
        across = -(wx - x) * s + (wy - y) * c
        # The building and flag stay on a flat pocket. Broad, uneven shoulders
        # form a shallow scallop in the hillside rather than a perfect ellipse.
        # Shape variation is in local coordinates, matching opposite partners.
        pocket_centre = 40+nudge
        radius = np.hypot((along - pocket_centre) / 150, across / 135)
        phi = np.arctan2(across, along - pocket_centre)
        edge = 1 + .035*np.sin(3*phi+.5) + .025*np.sin(5*phi-.8)
        width = 110 + 18*np.sin(3*phi+.7) + 12*np.sin(5*phi-.4)
        shoulder = np.clip((radius - edge) / (width / 135), 0, 1)
        weight = 1 - shoulder * shoulder * (3 - 2 * shoulder)
        level = float(original_z[round(old_y / 10) + border, round(old_x / 10) + border])
        lowered = np.minimum(z, z * (1 - weight) + level * weight)
        patch = (lowered != z) | (radius <= edge)
        changed |= patch
        z = lowered
        pad = radius <= edge
        floor |= pad
        # The closer building can meet the edge of the former flat pocket.
        # Level its measured cells, corners and a two-cell foundation margin.
        # Native cliff expansion must not spill back into the building.
        for shape in template_data(assets, 'Outpost')['shapes']:
            if not shape['enabled']:
                continue
            ys, xs = footprint_cells(shape, dict(obj, x=x, y=y, angle=angle),
                                     (hm['height']-2*border, hm['width']-2*border))
            for oy, ox in ((oy, ox) for oy in range(-2, 4) for ox in range(-2, 4)):
                gy, gx = ys+border+oy, xs+border+ox
                z[gy, gx] = level
                changed[gy, gx] = floor[gy, gx] = True
        # Continuous grass at the foot of the slope, with a worn courtyard
        # and narrow trail out to the flag. Alpha blending replaces the old
        # cut-and-pasted rectangular texture boundary.
        repaint = (radius <= edge+.34) & (z <= level+9)
        labels[repaint] = palette['GrassErebor07']
        courtyard = np.hypot((along-30)/110, across/85) <= 1+.07*np.sin(across/30)
        trail = (along >= 60) & (along <= 215) & (np.abs(across-5*np.sin(along/45)) <= 19)
        labels[repaint & (courtyard | trail)] = palette['DirtHarlindon03']
        painted |= repaint
        obj.update(x=x, y=y, angle=angle)
        flag.update(x=x + 105 * c, y=y + 105 * s, angle=angle)
        moved.append(dict(position=[x, y], angle=angle, flag=[flag['x'], flag['y']], inset=distance+nudge))
    raised, stone = stony_ridges(z, wx, wy, labels, palette, moved)
    changed |= raised
    painted |= stone
    set_heights(m, z)
    # A changed corner also changes the cell to its west/south. Reclassify
    # only this local footprint; preserve authored passability elsewhere.
    affected = changed.copy()
    affected[:-1] |= changed[1:]
    affected[:, :-1] |= changed[:, 1:]
    affected[:-1, :-1] |= changed[1:, 1:]
    steep = steep_cells(z, slope=.75)
    arrays['impassable'][affected] = steep[affected]
    # Raising an existing cliff crest must not turn authored cliff cells into
    # tiny isolated walking shelves merely because their new slope is gentler.
    crest = raised & (z >= original_z) & ~floor
    arrays['impassable'][crest] |= original_arrays['impassable'][crest]
    # Cliff expansion can leave one- or two-cell walkable freckles on a shoulder.
    blocked = arrays['impassable'].astype(bool)
    p = np.pad(blocked, 1, constant_values=True)
    expanded = np.logical_or.reduce([p[dy:dy+z.shape[0], dx:dx+z.shape[1]]
                                    for dy in range(3) for dx in range(3)])
    clear = ~expanded
    p = np.pad(clear, 1)
    neighbours = sum(p[dy:dy+z.shape[0], dx:dx+z.shape[1]].astype(np.uint8)
                     for dy in range(3) for dx in range(3) if (dy, dx) != (1, 1))
    p = np.pad(clear & (neighbours <= 1), 1)
    paired = np.logical_or.reduce([p[dy:dy+z.shape[0], dx:dx+z.shape[1]]
                                  for dy in range(3) for dx in range(3) if (dy, dx) != (1, 1)])
    islands = clear & ((neighbours == 0) | ((neighbours == 1) & paired))
    arrays['impassable'][affected & islands] = 1
    arrays['cliffs'][affected] = 0
    walls = affected & steep & ~floor
    painted |= weather_cliff_feet(z, wx, wy, moved, walls, labels, palette)
    blend_recess_ground(blend, labels, painted)
    # The imported map has no cliff UV records. Add local mapping for the
    # newly cut shoulders instead of stretching the grass texture vertically.
    cliff = next(t for t in reversed(blend['textures']) if t['name'] == 'CliffRhun01')
    tile = cliff['cell_start'] * 4
    arrays['tiles'][walls] = tile + original_arrays['tiles'][walls] % (cliff['cell_count'] * 4)
    arrays['blends'][walls] = arrays['three_way'][walls] = 0
    uv, flip = cliff_uvs(z, walls, cell_size=cliff['cell_size'])
    for gy, gx in zip(*np.nonzero(walls)):
        blend['cliff_records'].append(dict(tile=int(arrays['tiles'][gy, gx]),
            uv=tuple(uv[gy, gx]), flip=int(flip[gy, gx]), mutant=0))
        arrays['cliffs'][gy, gx] = len(blend['cliff_records'])
    chunk.data = encode_blend(blend, chunk.version, m)
    m.set_objects(objects)
    return moved


def build(b):
    source = b.project.folder / 'references'
    m = Map((source / 'compact.map').read_bytes())
    terrain = m.heightmap()
    border = terrain['border']
    assert (terrain['width'] - 2 * border, terrain['height'] - 2 * border) == (900, 600)
    assert len(sections.read(m, 'MPPositionList')) == b.project.players == 16
    b.report['inset_outposts'] = inset_outposts(m, b.assets)
    b.report['outpost_trees'] = outpost_trees(m, b.report['inset_outposts'], b.assets)
    b.report['cleanup'] = repair(m, b.assets)
    b.report['marked_cave_trees'] = marked_cave_trees(m, b.assets)
    with Image.open(source / 'minimap.tga') as minimap:
        b.save(m, ini=(source / 'map.ini').read_text(encoding='ascii'), minimap=minimap)
