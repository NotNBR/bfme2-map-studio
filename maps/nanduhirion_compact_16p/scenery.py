"""Small cave-side tree groups, based on rough marks with a varied opposite side."""
import math

import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.pathing import template_data, terrain_grid
from mapworkshop.mapkit.variety import spot_random


# Pins 2–8 describe the small cave's southern flanks, approximately
# (4379, 5142)..(4584, 5249). The cave is MoriarGoblinLair, despite the
# conversational "troll cave" label. Mark 1 and pins 9–15 describe the
# dragon's back and sides: (4320, 4737)..(4646, 4853).
# Treat the marks as rough scenery regions; don't reproduce a ring of pins.
NORMAL_GROUP = ((4330, 5230), (4350, 5105), (4610, 5250), (4610, 5125))
SCORCHED_GROUP = ((4340, 4800), (4410, 4865), (4515, 4880), (4595, 4825), (4640, 4755))
# Related southern scenes: offset clumps, a smaller scorched group and open
# gaps instead of rotating every northern trunk through exactly 180 degrees.
SOUTH_NORMAL_GROUP = ((4690, 650), (4635, 783), (4385, 630), (4415, 765))
SOUTH_SCORCHED_GROUP = ((4685, 1100), (4605, 975), (4505, 1015), (4385, 1105))
# Original green trees conflicting with the new scene: three evergreens
# inside the dragon's scorched patch and two crowded south-west broadleaves.
# Leave the outer groves intact so the scenes blend into the existing map.
PRUNE_TREES = ((4464.3, 4965.1), (4435.7, 4860.4), (4519.9, 4892.2),
               (4277.3, 5069.5), (4341.4, 5130.6), (4406.9, 1147.0))
MOUTHS = {'MoriarGoblinLair': -math.pi/2, 'CaveTrollLair': -math.pi/2, 'FireDrakeLair': 0}


def marked_cave_trees(m, assets):
    """Add varied flank groups while retaining cave and resource-site access."""
    ground = terrain_grid(m)
    hm = m.heightmap()
    border = hm['border']
    z = hm['elevations']*.0390625
    objects = m.objects()
    removed = [o for o in objects if o['template'].startswith('Tree')
               and any(math.dist((o['x'], o['y']), p) < 1 for p in PRUNE_TREES)]
    assert len(removed) == len(PRUNE_TREES), 'Marked scene donor trees changed'
    removed_ids = {o['index'] for o in removed}
    objects = [o for o in objects if o['index'] not in removed_ids]
    m.set_objects(objects)
    trees = [(o['x'], o['y']) for o in objects if o['template'].startswith('Tree')]
    farms = [(o['x'], o['y']) for o in objects if o['template'] == 'FarmTemplate']
    structures = [o for o in objects if 'STRUCTURE' in
                  (template_data(assets, o['template']) or {}).get('kinds', set())]
    report = []
    groups = (('north', 'normal', NORMAL_GROUP), ('north', 'scorched', SCORCHED_GROUP),
              ('south', 'normal', SOUTH_NORMAL_GROUP), ('south', 'scorched', SOUTH_SCORCHED_GROUP))
    for side, group, targets in groups:
        for n, target in enumerate(targets):
            species = ('TreeForlindon01', 'TreeForlindon02', 'TreeForlindon03') if group == 'normal' else ('TreeDead01', 'TreeDead02')
            template = species[(n+(side == 'south')) % len(species)]
            rng = spot_random(5325, template, *target)
            tx, ty = target[0]+rng.uniform(-13, 13), target[1]+rng.uniform(-13, 13)
            candidates = [(tx+dx, ty+dy) for dx in range(-60, 61, 10) for dy in range(-60, 61, 10)]
            candidates.sort(key=lambda p: math.dist(p, (tx, ty)))
            for x, y in candidates:
                spacing = 80 if group == 'normal' else 48
                if any(math.dist((x, y), p) < spacing for p in trees):
                    continue
                if any(math.dist((x, y), p) < 125 for p in farms):
                    continue
                if any(math.dist((x, y), (o['x'], o['y'])) < 105 for o in structures):
                    continue
                obstructs = False
                for cave in structures:
                    if cave['template'] not in MOUTHS:
                        continue
                    mouth = cave['angle']+MOUTHS[cave['template']]
                    dx, dy = x-cave['x'], y-cave['y']
                    along = dx*math.cos(mouth)+dy*math.sin(mouth)
                    across = -dx*math.sin(mouth)+dy*math.cos(mouth)
                    if 40 < along < 330 and abs(across) < 95:
                        obstructs = True
                        break
                if obstructs:
                    continue
                gy, gx = round(y/10), round(x/10)
                if not np.isin(ground[gy-1:gy+2, gx-1:gx+2], (0, 1, 8)).all():
                    continue
                if np.ptp(z[gy+border-1:gy+border+2, gx+border-1:gx+border+2]) > 5:
                    continue
                scale = rng.uniform(.78, 1.07) if group == 'normal' else rng.uniform(.8, 1.18)
                add_object(m, template, x, y, angle=rng.uniform(0, math.tau),
                           layer='Marked cave trees', extra=[('objectPrototypeScale', 2, scale)])
                trees.append((x, y))
                report.append(dict(side=side, group=group, template=template, position=[x, y], scale=scale))
                break
            else:
                raise ValueError(f'No clear tree position near rough cave mark {target}')
    return dict(removed=[dict(template=o['template'], position=[o['x'], o['y']]) for o in removed],
                added=report)
