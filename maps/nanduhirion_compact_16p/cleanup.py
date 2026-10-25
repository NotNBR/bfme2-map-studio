"""Gameplay clearance and scenery-density repairs for Compact Nanduhirion.

Static checks use installed INI geometry, not a running skirmish. Resource
sites reserve space for the available factions' buildings and starting bases;
later construction, enemy threats and resource yield remain game decisions.
"""
import math
from collections import Counter

import numpy as np

from mapworkshop.mapkit import pathing
from mapworkshop.mapkit.sites import LINKED, flag_position
from mapworkshop.render.godot import starting_positions


RESOURCE_BUILDINGS = ('GondorFarm', 'ElvenMallornTree', 'DwarvenMineShaft',
                      'IsengardFurnace', 'MordorSlaughterHouse', 'WildMineShaft', 'AngmarMill')
FARM_SPACING = 350
# Measured from the original 5,500 x 4,500 community 2.02 Nanduhirion.
ORIGINAL_AMBIENCE = {
    'Crow': 25, 'Rabbit': 22, 'Boar': 8, 'Dog': 3, 'Dog1': 3, 'Wolf': 2,
    'AnimalWanderPoint': 25, 'Amb_WindMT': 8, 'Amb_BirdsDesert1': 4,
    'Amb_BirdsFalcon1': 4, 'Amb_CreaksMetal1': 1, 'Amb_BirdsIthilien2Loop': 3,
    'Amb_BirdsAmonHen1': 21, 'Amb_CreakTree1': 19, 'AmbStream_PlainsOfRohan': 1,
    'BirdEmitter': 13,
}
TROLLS = ((5703.1220703125, 4834.2939453125), (3316.514404296875, 1037.7060546875))


def cells(obj, shapes, size):
    return {(int(y), int(x)) for shape in shapes if shape['enabled']
            for ys, xs in [pathing.footprint_cells(shape, obj, size)] for y, x in zip(ys, xs)}


def repair_flags_and_caves(m, assets):
    """Restore safe flag offsets and pull two cave mouths back from cliffs."""
    objects = m.objects()
    terrain = pathing.terrain_grid(m)
    flags = [o for o in objects if o['template'] == 'CaptureFlag']
    report = {'flags': [], 'caves': []}
    for obj in objects:
        if obj['template'] not in LINKED:
            continue
        flag = min(flags, key=lambda f: math.dist((f['x'], f['y']), (obj['x'], obj['y'])))
        flags.remove(flag)
        old = flag['x'], flag['y']
        flag['x'], flag['y'] = flag_position(obj['template'], obj['x'], obj['y'], obj['angle'])
        if obj['template'] == 'Inn':
            # Its doorway is local -Y. Keep the contested capture point on
            # the starts' shared centreline instead of favouring the west.
            starts = starting_positions(m)
            flag['x'] = sum(s['x'] for s in starts)/len(starts)
            flag['y'] = obj['y']-109
        own = cells(obj, pathing.template_data(assets, obj['template'])['shapes'], terrain.shape)
        fc = cells(flag, pathing.template_data(assets, 'CaptureFlag')['shapes'], terrain.shape)
        assert not own & fc, f'{obj["template"]}: flag overlaps building'
        assert all(terrain[y, x] in (0, 1, 8) for y, x in fc), 'Flag on blocked terrain'
        report['flags'].append(dict(building=obj['template'], position=[flag['x'], flag['y']],
                                    moved=math.dist(old, (flag['x'], flag['y']))))
    assert not flags, 'Unpaired capture flags'
    yy, xx = np.indices(terrain.shape)
    wx, wy = (xx+.5)*10, (yy+.5)*10
    for source in TROLLS:
        obj = next(o for o in objects if o['template'] == 'CaveTrollLair'
                   and math.dist((o['x'], o['y']), source) < 1)
        # Four-direction model inspection: troll mouths face local -Y.
        mouth = obj['angle']-math.pi/2
        obj['x'] -= 120*math.cos(mouth)
        obj['y'] -= 120*math.sin(mouth)
        footprint = cells(obj, pathing.template_data(assets, obj['template'])['shapes'], terrain.shape)
        assert all(terrain[y, x] in (0, 1, 8) for y, x in footprint), 'Cave on blocked terrain'
        dx, dy = wx-obj['x'], wy-obj['y']
        along = dx*math.cos(mouth)+dy*math.sin(mouth)
        across = -dx*math.sin(mouth)+dy*math.cos(mouth)
        front = (along >= 80) & (along <= 250) & (np.abs(across) <= 50)
        assert np.isin(terrain[front], (0, 1, 8)).all(), 'Cave approach still blocked'
        report['caves'].append(dict(position=[obj['x'], obj['y']], retreat=120))
    m.set_objects(objects)
    return report


def clean_farm_sites(m, assets):
    """Reject crowded, obstructed, steep or base-overlapping resource plots."""
    ground = pathing.compute(m, assets=assets)['ground']
    objects = m.objects()
    farms = [o for o in objects if o['template'] == 'FarmTemplate']
    starts = starting_positions(m)
    hm = m.heightmap()
    b = hm['border']
    z = hm['elevations'][b:b+ground.shape[0], b:b+ground.shape[1]].astype(float)*.0390625
    buildings = {name: pathing.template_data(assets, name) for name in RESOURCE_BUILDINGS
                 if name.lower() in assets.templates}
    assert len(buildings) >= 6, 'Resource-building geometry missing'
    bases = [(s['x'], s['y']) for s in starts]
    nearest = lambda o: min(math.dist((o['x'], o['y']), p) for p in bases)
    # Prioritise useful base-side sites over remote filler, deterministically.
    farms.sort(key=lambda o: (nearest(o), o['index']))
    kept, reasons = [], Counter()
    for obj in farms:
        x, y = obj['x'], obj['y']
        if min(x, y, ground.shape[1]*10-x, ground.shape[0]*10-y) < 100:
            reasons['map_edge'] += 1
            continue
        if nearest(obj) < 350:
            reasons['starting_base_reservation'] += 1
            continue
        footprint = set().union(*(cells(obj, data['shapes'], ground.shape) for data in buildings.values()))
        if any(ground[cy, cx] not in (0, 1, 8) for cy, cx in footprint):
            reasons['terrain_or_structure'] += 1
            continue
        if np.ptp([z[cy, cx] for cy, cx in footprint]) > 10:
            reasons['slope'] += 1
            continue
        if any(math.dist((x, y), (o['x'], o['y'])) < FARM_SPACING for o in kept):
            reasons['spacing'] += 1
            continue
        kept.append(obj)
    ids = {o['index'] for o in kept}
    m.set_objects([o for o in objects if o['template'] != 'FarmTemplate' or o['index'] in ids])
    nearby = [{**s, 'hints_within_900': sum(math.dist((s['x'], s['y']), (o['x'], o['y'])) <= 900 for o in kept)}
              for s in starts]
    assert all(s['hints_within_900'] >= 2 for s in nearby), 'Insufficient base-side farm choices'
    return dict(before=len(farms), after=len(kept), removed_by_reason=dict(reasons),
                minimum_spacing=FARM_SPACING, checked_templates=list(buildings), starts=nearby,
                note='Static footprint checks; 350 spacing is not a promise of full income for adjacent farms.')


def spread_subset(objects, count):
    """Keep spatial coverage when thinning repeated decorative objects."""
    if len(objects) <= count:
        return objects
    points = np.array([(o['x'], o['y']) for o in objects])
    centre = np.mean(points, axis=0)
    selected = [int(np.argmin(np.sum((points-centre)**2, axis=1)))]
    distances = np.sum((points-points[selected[0]])**2, axis=1)
    for _ in range(1, count):
        distances[selected] = -1
        k = int(np.argmax(distances))
        selected.append(k)
        distances = np.minimum(distances, np.sum((points-points[k])**2, axis=1))
    return [objects[i] for i in selected]


def thin_ambience(m):
    """Match original per-area density, retaining each ambience type's coverage."""
    hm = m.heightmap()
    area = (hm['width']-2*hm['border'])*(hm['height']-2*hm['border'])*100
    ratio = area/(5500*4500)
    objects = m.objects()
    removed, report = set(), {}
    for template, baseline in ORIGINAL_AMBIENCE.items():
        group = [o for o in objects if o['template'] == template]
        budget = max(1, round(baseline*ratio))
        kept = {o['index'] for o in spread_subset(group, budget)}
        removed.update(o['index'] for o in group if o['index'] not in kept)
        report[template] = dict(before=len(group), after=len(kept))
    m.set_objects([o for o in objects if o['index'] not in removed])
    return report


def validate(m, assets):
    """Check all site access and the deduplicated farm inventory after repair."""
    ground = pathing.compute(m, assets=assets)['ground']
    objects = m.objects()
    flags = [o for o in objects if o['template'] == 'CaptureFlag']
    sites = [o for o in objects if o['template'] in LINKED]
    assert len(flags) == len(sites) == 11
    for site in sites:
        flag = min(flags, key=lambda f: math.dist((f['x'], f['y']), (site['x'], site['y'])))
        flags.remove(flag)
        assert math.dist((flag['x'], flag['y']), (site['x'], site['y'])) <= 150
        footprint = cells(flag, pathing.template_data(assets, 'CaptureFlag')['shapes'], ground.shape)
        # The flag itself occupies its own cells. Check for nearby open
        # approach space; whole-map connectivity is checked by mw walkable.
        gy, gx = int(flag['y']/10), int(flag['x']/10)
        assert np.isin(ground[gy-5:gy+6, gx-5:gx+6], (0, 1, 8)).any()
        assert footprint
    yy, xx = np.indices(ground.shape)
    wx, wy = (xx+.5)*10, (yy+.5)*10
    mouths = {'CaveTrollLair': -math.pi/2, 'MoriarGoblinLair': -math.pi/2, 'FireDrakeLair': 0}
    cave_count = 0
    for obj in objects:
        if obj['template'] not in mouths:
            continue
        mouth = obj['angle']+mouths[obj['template']]
        dx, dy = wx-obj['x'], wy-obj['y']
        along = dx*math.cos(mouth)+dy*math.sin(mouth)
        across = -dx*math.sin(mouth)+dy*math.cos(mouth)
        front = (along >= 80) & (along <= 250) & (np.abs(across) <= 50)
        assert np.isin(ground[front], (0, 1, 8)).all(), f'{obj["template"]}: obstructed approach'
        cave_count += 1
    assert cave_count == 8
    farms = [o for o in objects if o['template'] == 'FarmTemplate']
    assert all(math.dist((a['x'], a['y']), (b['x'], b['y'])) >= FARM_SPACING
               for i, a in enumerate(farms) for b in farms[i+1:])
    assert len(starting_positions(m)) == 16
    return dict(capture_flags=11, clear_lair_approaches=8, starts=16, farm_hints=len(farms))


def repair(m, assets):
    report = repair_flags_and_caves(m, assets)
    report['farms'] = clean_farm_sites(m, assets)
    report['ambience'] = thin_ambience(m)
    report['verification'] = validate(m, assets)
    return report
