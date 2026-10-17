"""Battle of Nanduhirion v2 (film): the v2 battle with a scripted camera, cut
as a trailer, for recording in OpenBFME.

The Battle of Nanduhirion v2 (maps/nanduhirion_v2_battle/, its staged():
the same armies, units as tough), its lines charging at the film's CHARGE,
not the battle's, with a film over it (mapkit.cinematics): the interface
hidden, health bars and icons off, the far plane pushed out, and the shots
played in turn on the battle's own clock. The battle: four battle lines fill
the arena's bowl, the Men (players 1 and 4) facing Angmar and Mordor (8 and
5) across no-man's land, and in each strip beyond the mesas the Elves and the
Dwarves (2, 3) face the Wild and Isengard (7, 6); every line charges at
CHARGE. The whole battle line runs along x 6,900, from the map's south edge
to its north one: the south strip's clash, the arena's no-man's land, the
north strip's. The film shows its scale, not single units: wide and high
shots of whole armies, long lenses stacking the lines, reveals over the rims,
cut in three acts:

    I, the armies waiting: from the sky a tilt down over the arena's south
    rim to the bowl and its four lines; a high truck behind the Men's north
    line, both armies in depth; another behind the Elves' line in the north
    strip, the Wild's across the mesa; and straight down on the arena, all
    four lines turning slowly, cut as they charge.
    II, the charge: down no-man's land from the south rim as the south lines
    rush in; a crane up and back as all four meet along their fronts; and
    the north strip's lines charging at each other across the mesa.
    III, the fight: one flight along the whole battle line, south strip to
    north strip, banking gently; and up and back from the north strip's
    fight, the last to end, to hold.

The shots take the lines from the battle's waypoints (NB_Line_n, the middle
of each line's front), so they follow the battle when it is drawn up anew.

Every move eases in and out. A shot is a list of poses (camera, target, field of view, roll); its keys
(EASE a second) run through them. Heights: `up` puts a point that far above
the ground under it, `over` above the mesas' tops (MESA), whichever is
higher. Fields of view are horizontal (OpenBFME's; mw render's too), and the
keys carry them and the roll, so a shot can zoom and bank (OpenBFME plays
both, openbfme-cinematics.patch, which also gives a film a sky and a haze).
The build checks every key: the camera CLEARANCE above the ground, no tree
right in front of it (tree_in_view()), and the top corners and top middle of
its picture (ASPECT) not seeing where the map's terrain stops (edge_seen()).
The map keeps a skybox as ROTWK's
cinematic maps have one (SKYBOX: a CINE_skybox_* model in the middle of the
map at ground level, scaled with objectPrototypeScale) for ROTWK, which draws
it.

The scripts stand on PlyrCreeps, which a skirmish keeps and the battle leaves
empty (its own are on PlyrCivilian). Play it as the battle:

    mw build nanduhirion-v2; mw build nanduhirion-v2-battle-film; mw play nanduhirion-v2-battle-film --godot

and record the game window (OBS, the Xbox Game Bar); F11 hides OpenBFME's
frame-rate counter.
"""
import math

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.mapkit import cinematics
from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.script_writer import Writer
from maps.nanduhirion_v2.map import BORDER, CENTRE
from maps.nanduhirion_v2_battle.map import staged

START = 0.5                     # seconds into the game the film starts
CLEARANCE = 25                  # the camera stays at least this above the ground
ASPECT = 16/9                   # the recording's picture, for the edge check
HORIZON = 2                     # degrees below level the edge check takes for the horizon, the haze's
TILTS = {'Rim'}                 # shots tilting down from the sky: their top sweeps every angle below the horizon, the far edge in the haze for a moment
TREE = 90, 300                  # a tree blocks up to this high, and the check follows a sight line this far
CROWNS = {'TreeForlindon': 75, 'TreeEttenmoors': 50, 'TreeEvergreen': 30}   # a tree's crown, its reach from the trunk (mw item NAME --footprint)
MESA = 125                      # the mesas between the arena and the strips (and the arena's terraces)
ARENA_Y = 5500                  # y of the arena's middle, between its two pairs of lines (they stand from 3,630 to 7,420)
SKYBOX, SKYBOX_SCALE = 'CINE_skybox_day', 1.6  # the sky for ROTWK, as the cin maps place it (cin fornost, cin gundabad: 0.5 / 0.64)
CHARGE = 39                     # seconds into the game every line charges: the film's first act shows them waiting
CLIP_DEPTH = 12                 # the far plane, times the game's
EASE = 4                        # keys per second of a move


def eased(t):
    """Smoothstep: 0 to 1 with no jolt at either end."""
    return t*t*(3 - 2*t)


def catmull(points, u):
    """The point at u (0 to 1) along a Catmull-Rom curve through points (tuples of numbers)."""
    n = len(points) - 1
    s = min(max(u, 0.0), 1.0)*n
    i = min(int(s), n - 1)
    t = s - i
    p0, p1, p2, p3 = (points[max(0, min(n, k))] for k in (i - 1, i, i + 1, i + 2))
    return tuple(.5*(2*b + (c - a)*t + (2*a - 5*b + 4*c - d)*t*t + (3*b - a - 3*c + d)*t*t*t) for a, b, c, d in zip(p0, p1, p2, p3))


def move(poses, seconds, ease=True):
    """Keys through poses (camera, target, fov degrees[, roll degrees]), evenly in time or easing in and out."""
    steps = max(2, round(seconds*EASE))
    cams = [p[0] for p in poses]
    targets = [p[1] for p in poses]
    lens = [(p[2], p[3] if len(p) > 3 else 0.0) for p in poses]
    keys = []
    for i in range(steps + 1):
        u = eased(i/steps) if ease else i/steps
        fov, roll = catmull(lens, u)
        keys.append((seconds*i/steps, catmull(cams, u), catmull(targets, u), math.radians(fov), math.radians(roll)))
    return keys


def orbit(centre, radius, height, start, sweep, seconds, fov, radius_to=None, height_to=None, fov_to=None, look=None):
    """Keys circling `centre` (x, y, z) from `start` degrees (0 east, counter-clockwise) through `sweep`, easing in and out, looking at
    `look` (the centre without one); radius, height and field of view may change on the way, a spiral."""
    radius_to, height_to, fov_to = radius_to or radius, height_to or height, fov_to or fov
    steps = max(2, round(seconds*EASE))
    cx, cy, cz = centre
    keys = []
    for i in range(steps + 1):
        e = eased(i/steps)
        a = math.radians(start + sweep*e)
        r, h = radius + (radius_to - radius)*e, height + (height_to - height)*e
        keys.append((seconds*i/steps, (cx + r*math.cos(a), cy + r*math.sin(a), cz + h), look or centre, math.radians(fov + (fov_to - fov)*e), 0.0))
    return keys


def edge_seen(camera, target, fov, roll, ground, size):
    """Where the picture's top corners or top middle see the map's edge, where its terrain stops (None if they do not): each ray marched
    until it meets the ground; one still descending when it leaves the map sees the cut below the horizon. A rising one reaches the sky,
    and one within HORIZON of level the haze (OpenBFME's film sky, openbfme-cinematics.patch), whose horizon colour hides a far edge."""
    sub = lambda a, b: tuple(p - q for p, q in zip(a, b))
    unit = lambda a: tuple(p/math.sqrt(sum(q*q for q in a)) for p in a)
    cross = lambda a, b: (a[1]*b[2] - a[2]*b[1], a[2]*b[0] - a[0]*b[2], a[0]*b[1] - a[1]*b[0])
    f = unit(sub(target, camera))
    r = unit(cross(f, (0, 0, 1)))
    u = cross(r, f)
    r, u = (tuple(math.cos(roll)*a - math.sin(roll)*b for a, b in zip(r, u)),
            tuple(math.cos(roll)*b + math.sin(roll)*a for a, b in zip(r, u)))   # banked right: the picture's right edge dips
    th = math.tan(fov/2)
    tv = th/ASPECT
    for sx, side in ((-1, 'top left'), (0, 'top'), (1, 'top right')):
        d = unit(tuple(fc + sx*th*rc + tv*uc for fc, rc, uc in zip(f, r, u)))
        if d[2] >= -math.sin(math.radians(HORIZON)):
            continue
        x, y, z = camera
        while z >= ground(x, y):
            x, y, z = x + d[0]*15, y + d[1]*15, z + d[2]*15
            if not (0 <= x < size[0] and 0 <= y < size[1]):
                return f'its {side} at ({x:.0f}, {y:.0f})'
    return None


def tree_in_view(camera, target, ground, trees):
    """Whether a tree stands in front of the camera: in a tree's crown (CROWNS, up to TREE's height) at the camera or along the first stretch of its line of
    sight to the target, unless that is above the trees. `trees`: x, y and crown reach of each."""
    top, length = TREE
    d = np.subtract(target, camera)
    d /= np.linalg.norm(d)
    points = np.array(camera) + np.outer(np.arange(0, length + 1, 25), d)
    low = np.array([p[2] - ground(p[0], p[1]) < top for p in points])
    if not low.any() or not len(trees):
        return False
    near = np.hypot(points[low, None, 0] - trees[None, :, 0], points[low, None, 1] - trees[None, :, 1]) < trees[None, :, 2]
    return bool(near.any())


def problems(film, ground, size, trees):
    """What keeps each key of the film's shots from being drawn: the camera under CLEARANCE above the ground, a tree in front of it
    (tree_in_view()), its picture seeing the map's edge (edge_seen(); not checked for TILTS)."""
    out = []
    for name, _, keys, _ in film.shots:
        for t, camera, target, fov, roll in keys:
            if camera[2] < ground(*camera[:2]) + CLEARANCE:
                out.append(f'{name} at {t:.1f} s: the camera is under {CLEARANCE} above the ground')
            elif tree_in_view(camera, target, ground, trees):
                out.append(f'{name} at {t:.1f} s: a tree stands in front of the camera')
            elif name not in TILTS and (edge := edge_seen(camera, target, fov, roll, ground, size)):
                out.append(f'{name} at {t:.1f} s: the picture sees the map\'s edge, {edge}')
    return out


def shots(ground, wp):
    """The film: its shots over the ground (x, y -> height) and the battle's waypoints (its report's)."""
    up = lambda x, y, h: (x, y, ground(x, y) + h)                 # a point h above the ground
    over = lambda x, y, h: (x, y, max(ground(x, y), MESA) + h)    # a point h above the mesas' tops, wherever it is
    north, south = wp['NB_Line_1'], wp['NB_Line_4']               # the Men's two arena lines' fronts (their middles)
    gap = (north[0] + wp['NB_Line_8'][0])/2                       # x of no-man's land in the arena, between the Men and Angmar / Mordor
    strip_n = wp['NB_Line_2'][1]                                   # y of the north strip's line
    meet = (wp['NB_Line_2'][0] + wp['NB_Line_7'][0])/2            # x where the strips' lines meet, on the mesa

    film = cinematics.Film(prefix='NBV', clip_depth=CLIP_DEPTH)
    centre = up(gap, ARENA_Y, 0)                                  # the middle of the arena's four lines
    # I. The armies waiting, CHARGE seconds.
    # The reveal: from the sky over the arena, a tilt down as the camera rises over its south rim, to the bowl and its four lines.
    film.shot('Rim', move([((gap + 100, 2850, MESA + 60), (gap, 6500, 1100), 54),
                           ((gap + 50, 2900, MESA + 300), (gap, 5600, 100), 56),
                           ((gap - 150, 3000, MESA + 750), up(gap, 4700, 0), 58)], seconds=9))
    # Across: a high truck north behind the Men's north line, from beyond its south end to beyond its north one, looking east over it and
    # no-man's land to Angmar's, both armies in depth.
    film.shot('Across', move([(up(5300, north[1] - 1250, 800), up(7200, north[1] - 850, 0), 56),
                              (up(5300, north[1] + 1050, 800), up(7300, north[1] + 1100, 0), 56)], seconds=11.5))
    # The north strip: a high truck north from well behind the Elves' line, looking east, a little towards the map's middle, over it, the
    # mesa and the Wild's line beyond.
    film.shot('Strips', move([(up(3850, strip_n - 1300, 950), up(5500, strip_n - 1200, 100), 58),
                              (up(3850, strip_n - 350, 950), up(5500, strip_n - 500, 100), 58)], seconds=9))
    # The wait: high over the arena, the four lines in one picture, slowly turning and sinking, cut as they charge.
    seconds = CHARGE - START - sum(keys[-1][0] for _, _, keys, _ in film.shots)
    film.shot('Wait', orbit(centre, 400, 3200, 0, 25, seconds, 72, height_to=2400))
    # II. The charge.
    # The charge: down no-man's land from the south rim, wide, the two south lines rushing in from either side, pushing in.
    film.shot('Charge', move([((gap, 3250, MESA + 180), up(gap, 5000, 0), 64),
                              ((gap, 3700, 220), up(gap, 5600, 0), 58)], seconds=12), start=CHARGE)
    # The clash: a crane up and back from the south-west as the four lines meet along their whole fronts.
    film.shot('Clash', move([(up(gap - 900, 4900, 300), up(gap, 5600, 0), 55),
                             (up(gap - 1500, 4400, 1400), up(gap, 5800, 0), 62)], seconds=8))
    # The north strip: its two lines charging at each other across the mesa, seen down its no-man's land from above its south end.
    film.shot('North', move([(over(meet, 7700, 500), over(meet, 9800, 0), 66),
                             (over(meet, 7950, 600), over(meet, 9900, 0), 62)], seconds=9))
    # III. The fight.
    # The line: one flight along the whole battle line, south strip, arena, north strip, weaving and banking gently.
    fly = [(over(gap + dx, y, h), up(gap + dx*.4, y + lead, 0), 60, roll)
           for dx, y, h, lead, roll in [(-100, 400, 600, 1600, -1.5), (80, 2600, 550, 1600, 1.5), (-80, 4600, 600, 1500, -1.5),
                                        (80, 6600, 600, 1200, 1.5), (0, 8500, 650, 800, 0)]]
    film.shot('Line', move(fly, seconds=16))
    # The end: from where the flight ends, up and back from the north strip's fight (the arena's, its lines closer, is over first),
    # turning, to the whole strip and the arena's rim, to hold.
    film.shot('End', move([(over(meet - 300, strip_n - 700, 600), up(meet, strip_n - 100, 0), 56),
                           (over(meet + 200, strip_n - 1400, 1100), up(meet, strip_n - 450, 0), 58),
                           (over(meet + 400, strip_n - 2200, 2000), up(meet - 100, strip_n - 650, 0), 60)], seconds=14))
    return film


def build(b):
    m, ini, minimap = staged(b, CHARGE)       # the battle, its lines charging at the film's CHARGE, its units tougher
    wp = b.report['waypoints']
    z = m.heightmap()['elevations']*.0390625
    rows, cols = z.shape
    size = ((cols - 2*BORDER)*10, (rows - 2*BORDER)*10)
    ground = lambda x, y: float(z[min(rows - 1, max(0, int(y//10) + BORDER)), min(cols - 1, max(0, int(x//10) + BORDER))])
    film = shots(ground, wp)
    # Every key: the camera clear of the ground and of trees, and its picture within the map.
    trees = np.array([(o['x'], o['y'], reach) for o in m.objects() for kind, reach in CROWNS.items() if o['template'].startswith(kind)])
    if found := problems(film, ground, size, trees):
        raise ValueError('Shots the game cannot draw: ' + '; '.join(found))
    # The skybox, as ROTWK's cinematic maps place theirs: one model in the middle of the map at ground level, scaled.
    add_object(m, SKYBOX, *CENTRE, layer='Film', extra=[('objectPrototypeScale', 2, SKYBOX_SCALE), ('objectName', 3, 'NBV_Skybox')])
    w = Writer(m)
    sides = [dict((k, v) for k, _, v in p['properties']) for p in sections.read(m, 'SidesList')['players']]
    side = next(i for i, s in enumerate(sides) if s.get('playerName') == 'PlyrCreeps')
    w.install(film.install(m, w, start=START), side_index=side)
    b.report.update(shots=[dict(name=n, start=round(s, 1), end=round(e, 1)) for n, s, e in film.timeline(START)],
                    keys={n: [dict(t=round(t, 2), camera=[round(v) for v in c], target=[round(v) for v in g], fov=round(math.degrees(f), 1),
                                   roll=round(math.degrees(r), 1)) for t, c, g, f, r in keys] for n, _, keys, _ in film.shots})
    b.save(m, ini=ini, minimap=minimap)
