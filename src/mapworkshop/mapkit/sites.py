"""Neutral sites with their capture flags, creep lairs and Gollum's spawn points.

Stock evidence (local/game/maps, the 13 multiplayer and 38 War of the Ring
maps, measured):

- Outposts, inns, signal fires and shipwrights are LINKED_TO_FLAG: each
  stands with a neutral CaptureFlag beside it, which is what a player
  captures (236 flags for 234 such structures; one flag stands alone). The
  flag's median distance and its direction from the structure's facing
  (map angle) are in LINKED. None of the stock maps links them any other way:
  the link is by nearness. Open-BFME-2 has the kinds, not yet the linking code.
- Every multiplayer and War of the Ring map has 4 to 8 waypoints named
  SpawnPoint_SkirmishGollum_<n>, where skirmish Gollum appears, about 770 to
  2,000 from the starts.
- Creep lairs (WargLair, CaveTrollLair, ...) belong to PlyrCreeps and have no
  flag.

    from mapworkshop.mapkit.sites import neutral_site, creep_lair, gollum_spawns
    neutral_site(m, 'Outpost', 1290, 2710, angle=2.4)        # with its flag
    creep_lair(m, 'WargLair', 650, 3850)
    gollum_spawns(m, [(1400, 2000), (3390, 2790)])
"""
import math

# Template: (flag distance, flag direction from the structure's angle, radians).
LINKED = {'Outpost': (105, 0.0), 'Inn': (109, math.radians(225)), 'SignalFire': (76, 0.0),
          'ShipWright': (145, math.pi)}
LAIRS = ('WargLair', 'CaveTrollLair', 'CaveTrollLairSnow', 'BarrowWightLair', 'SpiderLair', 'FireDrakeLair',
         'MoriarGoblinLair', 'MoriarGoblinLairSnow')
FLAG = 'CaptureFlag'
GOLLUM = 'SpawnPoint_SkirmishGollum_'


def flag_position(template, x, y, angle=0.0):
    """Where the stock maps put a linked structure's flag."""
    distance, turn = LINKED[template]
    return x+distance*math.cos(angle+turn), y+distance*math.sin(angle+turn)


def neutral_site(m, template, x, y, angle=0.0, flag=None, layer='Objectives', extra=()):
    """A neutral outpost, inn, signal fire or shipwright with its capture flag,
    at `flag` (x, y) or where the stock maps put it (flag_position). Returns
    the flag's position. Keep both clear: the flag is a structure too."""
    from mapworkshop.mapkit.blank import add_object
    if template not in LINKED:
        raise ValueError(f'{template} is not linked to a flag; use one of {", ".join(LINKED)}')
    neutral = [('originalOwner', 3, 'PlyrNeutral/teamPlyrNeutral')]
    add_object(m, template, x, y, angle, layer=layer, extra=neutral+list(extra))
    fx, fy = flag if flag is not None else flag_position(template, x, y, angle)
    add_object(m, FLAG, fx, fy, angle, layer=layer, extra=neutral)
    return fx, fy


def creep_lair(m, template, x, y, angle=0.0, layer='Objectives'):
    """A creep lair, owned by the creeps."""
    from mapworkshop.mapkit.blank import add_object
    if template not in LAIRS:
        raise ValueError(f'{template} is not a creep lair; use one of {", ".join(LAIRS)}')
    add_object(m, template, x, y, angle, layer=layer, extra=[('originalOwner', 3, 'PlyrCreeps/teamPlyrCreeps')])


def _waypoint_ids(m):
    return [v for o in m.objects() for k, _, v in o['properties'] if k == 'waypointID']


def gollum_spawns(m, points, layer='Waypoints'):
    """Waypoints named SpawnPoint_SkirmishGollum_1, _2, ... at the points, with
    waypoint IDs after the map's existing ones."""
    from mapworkshop.mapkit.blank import add_object
    if not points:
        raise ValueError('Gollum needs at least one spawn point')
    first = max(_waypoint_ids(m), default=0)+1
    for i, (x, y) in enumerate(points):
        name = f'{GOLLUM}{i+1}'
        add_object(m, '*Waypoints/Waypoint', x, y, layer=layer, extra=[
            ('originalOwner', 3, '/team'), ('uniqueID', 3, name), ('waypointID', 1, first+i),
            ('waypointName', 3, name), ('waypointTypeOption', 3, '')])


def spread(candidates, count, avoid=(), clear=0.0, apart=0.0):
    """Up to `count` of the candidate points, each at least `clear` from every
    point of `avoid` and `apart` from the others, taken farthest first from
    what is already chosen (farthest-point sampling), so they cover the area
    evenly. Deterministic: the same candidates give the same choice."""
    pool = [(float(x), float(y)) for x, y in candidates
            if all(math.dist((x, y), a) >= clear for a in avoid)]
    chosen = []
    while pool and len(chosen) < count:
        anchors = chosen or list(avoid)
        best = max(pool, key=lambda p: min((math.dist(p, a) for a in anchors), default=0.0)) if anchors else pool[0]
        chosen.append(best)
        pool = [p for p in pool if math.dist(p, best) >= max(apart, 1e-9)]
    return chosen
