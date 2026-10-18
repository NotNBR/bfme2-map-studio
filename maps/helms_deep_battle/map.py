"""Battle of Helm's Deep: the Hornburg and the Deeping Wall held against the
host of Isengard.

The War of the Ring map `map wor helms deep` from the game's archives, its
fortress, coomb and props as they are, staged as a skirmish of two
(map.toml's [play]: you hold the fortress with Men, Isengard is a hard AI).
Player_2's start moves behind the coomb (ISENGARD_START), where the game
builds Isengard's fortress; the other two starts go, and so do the map's own
War of the Ring scripts (a command point limit, starting cash, build limits).

- Defenders, owned by Player_1 like every piece of the fortress: about 5,000
  command points. Archers stand on the walls (WALLS): one battalion every
  SPACING along the middle of each piece's walkway (its WallBoundsMesh, read
  from the model), facing out: Lothlorien archers on the Deeping Wall and the
  culvert, Men's archers on the Hornburg's outer walls and gatehouse and on
  the keep's walls. The heroes on the walls (ON_WALLS) take the place nearest
  their spot. Each stands at its walkway's height (a map object's Z is over
  the ground under it), so the game puts it on the wall's layer. Behind the
  walls (POSTS): Galadhrim and spearmen in the Deep behind the culvert,
  spearmen in the bailey behind the main gate, the Rohirrim and peasants with
  Theoden in the keep.
- Attackers, owned by Player_2: about 25,000 command points of Uruk-hai,
  pikemen and swordsmen 3 to 1 (HOST), facing north on an even grid: the
  same gap between neighbours along a row and between rows (a battalion is
  BATTALION), as wide as still holds them all in the northern TOP of the
  Deeping Coomb, no nearer the walls than FRONT (out of bowshot: Men's
  archers reach 300), off the causeway (CAUSEWAY) and Isengard's base
  (BASE_CLEAR). The northern rows are pikes, the rear quarter swords. A
  siege ladder stands one row before the front of every LADDER_EVERY column
  facing the Deeping Wall, and battering rams at the causeway's foot
  (RAM_SPOTS); about 25,100 command points in all. None is recruitable by
  the AI, so the scripts alone move them.
- Scripts, on PlyrCivilian: at CHARGE seconds each battalion attacks the
  piece of the defences straight ahead of it (TARGETS: the main gate, the
  culvert or a section of the Deeping Wall), the rams the main gate. The
  ladders dock against the section ahead of them (their
  SpecialAbilitySiegeDeploy takes any STRUCTURE +WALK_ON_TOP_OF_WALL); the
  Deeping Wall's swords make for the Deep, up the ladders, while its pikes
  batter the wall. Once the culvert or a section falls, the Deeping
  Wall's attackers pour into the Deep, and DEEP_ONWARD later make for the
  keep; once the main gate falls, its attackers storm the bailey, GATE_ONWARD
  later attack the keep's gate, and when that falls the keep. Each assault's
  stage is a counter (HD_Deep, HD_Gate); its orders are given again every
  DRIVE seconds. Your units follow your orders only.

Untested in the game. OpenBFME (mw play --godot) has no wall layer and no
ladder docking yet (its docs/STOPS.md S-161, S-1103): there the archers
cannot stand on the walls nor the ladders scale them.

    mw build helms-deep-battle; mw play helms-deep-battle
"""
import io
import math
import re

import numpy as np
from PIL import Image

from mapworkshop.formats import sections
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.blank import add_object, set_world
from mapworkshop.mapkit.pathing import polygon_cells, template_data
from mapworkshop.mapkit.script_writer import Writer, arg
from mapworkshop.render.terrain import TerrainData
from mapworkshop.render.w3d import ModelCache
from mapworkshop.render.water import inside
from maps.nanduhirion_battle.map import Ground, check_templates, owner

SOURCE = 'maps/map wor helms deep/'     # in the game's Maps.big
YOU, ENEMY = 1, 2
ISENGARD_START = (1940, 500)            # Player_2's start: the map's Player_4 start, behind the coomb

# The walkways and who stands on them: per group its pieces, its archers and the point its archers face away from
DEEPING = ('HelmsDeepSectionAi', 'HelmsDeepSectionB', 'HelmsDeepSectionC', 'HelmsDeepCulvert')
HORNBURG = ('HelmsDeepdoSectionA2', 'HelmsDeepdoSectionA5', 'HelmsDeepdoSectionB1', 'HelmsDeepdoSectionD',
            'HelmsDeepGatehouseLeft', 'HelmsDeepGatehouseRight')
KEEP = ('HelmsDeepdiSectionA6', 'HelmsDeepdiSectionA7', 'HelmsDeepdiSectionA8', 'HelmsDeepkiSectionA3',
        'HelmsDeepkiSectionA5', 'HelmsDeepkiSectionB', 'HelmsDeepRampart02', 'HelmsDeepRampart03')
WALLS = {'deeping': (DEEPING, 'ElvenLorienArcherHorde', (1600, 3900)),
         'hornburg': (HORNBURG, 'GondorArcherHorde', (2900, 3250)),
         'keep': (KEEP, 'GondorArcherHorde', (2900, 3250))}
SPACING = 92                    # between the archer battalions along a walkway
END = 20                        # kept clear at each end of a piece
NARROWEST = 60                  # a walkway narrower than this takes no battalion
RANKS_AHEAD = 30                # a horde's ranks stand 10 to 50 ahead of it (RankInfo): it stands this far back of the walkway's middle
SOLID = ('HelmsDeepGatehouseCenter', 'HelmsDeepTower', 'HelmsDeepRampart04', 'WOR_HelmsDeepArcade')   # no walking mesh: ground units keep 110 off
# Heroes on the walls, each at the walkway place nearest its spot
ON_WALLS = [('ElvenLegolas', (1645, 2938)),     # on the culvert
            ('ElvenHaldir', (1977, 2903)),      # Deeping Wall Right, by the Hornburg
            ('GondorAragornMP', (2721, 2612)),  # on the gatehouse, either side of the main gate
            ('DwarvenGimli', (2971, 2612))]
# Behind the walls: template, how many, the middle of the front rank, facing (degrees: 0 east, 90 north), per rank
POSTS = [('ElvenLorienWarriorHorde', 12, (1640, 3110), -90, 6),    # in the Deep, behind the culvert
         ('RohanSpearmenHorde', 8, (1640, 3330), -90, 4),
         ('RohanPeasantHorde', 10, (1250, 3540), -90, 5),          # the Deep's far end, before the caves
         ('RohanSpearmenHorde', 9, (2770, 2860), -90, 5),          # in the bailey, behind the main gate
         ('RohanRohirrimHorde', 6, (2830, 3250), -90, 3),          # in the keep's courtyard, for the last ride
         ('RohanTheoden', 1, (2830, 3390), -90, 1)]
POST_ACROSS, POST_BACK = 100, 80

PIKE, SWORD = 'IsengardPikemanHorde', 'IsengardFighterHorde'
HOST = {PIKE: 294, SWORD: 98}   # 3 to 1; 24,990 command points at 60 and 75
BATTALION = 90, 50              # a battalion's frontage and depth (5 abreast 20 apart, 3 ranks)
FRONT = 480                     # the host stands no nearer the walls than this: out of bowshot (Men's archers reach 300)
TOP = 2/3                       # and in the field's northern two thirds, from its southern edge (SOUTH) to the walls
SOUTH = 100
ROOM = 28                       # a battalion's spot must be open, walkable ground over this radius
CAUSEWAY = (2690, 1880, 2970, 2660)     # x0, y0, x1, y1: kept clear
BASE_CLEAR = 450                # and this round Isengard's start
# The siege: siege ladders (4 command points) dock against a walk-on-top wall (their SpecialAbilitySiegeDeploy takes
# STRUCTURE +WALK_ON_TOP_OF_WALL), and Uruk battalions (CAN_USE_SIEGE_TOWER) climb them; battering rams (25) break gates
LADDER, RAM = 'IsengardSiegeLadder', 'IsengardBatteringRam'
LADDER_EVERY = 1                # a ladder one row before the front, every this many columns facing the Deeping Wall
RAM_SPOTS = [(2790, 1930), (2870, 1930), (2790, 2010), (2870, 2010)]   # at the causeway's foot
# What each battalion attacks: the destructible piece straight ahead of it (nearest west to east); the gate's attackers form
# one assault, the rest the Deeping Wall's
TARGETS = ('Main Gate', 'Culvert', 'Deeping Wall Far Left', 'Deeping Wall Center Left', 'Deeping Wall Near Left',
           'Deeping Wall Right')
DEEP_TARGETS = TARGETS[1:]
WAYPOINTS = {'HD_Deep': (1640, 3350), 'HD_Bailey': (2850, 2860), 'HD_Keep': (2850, 3330)}
CHARGE = 20                     # seconds into the game the host attacks
DEEP_ONWARD, GATE_ONWARD = 90, 60
DRIVE = 40                      # every assault's orders again this often


def prop(o, key, default=''):
    return next((v for k, _, v in o['properties'] if k == key), default)


def command_points(templates, name):
    n = name.lower()
    while n in templates:
        found = re.search(r'(?im)^\s*CommandPoints\s*=\s*(\d+)', templates[n]['body'])
        if found:
            return int(found.group(1))
        n = templates[n]['parent']
    return 0


def seat(m):
    """Two starts: Player_1's in the keep as the map has it, Player_2's at ISENGARD_START; and no War of the Ring scripts."""
    objs = []
    for o in m.objects():
        name = prop(o, 'waypointName')
        if name in ('Player_3_Start', 'Player_4_Start'):
            continue
        if name == 'Player_2_Start':
            o['x'], o['y'] = ISENGARD_START
        objs.append(o)
    m.set_objects(objs)
    sides = [dict((k, v) for k, _, v in p['properties']).get('playerName') for p in sections.read(m, 'SidesList')['players']]
    lists = sections.read(m, 'PlayerScriptsList')
    for i, name in enumerate(sides):
        if name == f'Player_{YOU}':
            lists[i] = dict(lists[i], children=[])
    sections.write(m, 'PlayerScriptsList', lists)
    return sides.index('PlyrCivilian')


def walkway(o, assets, models, cache):
    """A walk-on-top piece's meshes in map units: (its walkway's triangles, all its walking triangles), each a (3, 3)
    array of x, y and height over the ground under the piece's origin."""
    data = template_data(assets.templates, o['template'], cache)
    info = assets.template_model(o['template'])
    model = models.load(info['model']) if info else None
    names = {k: v.lower() for k, v in data['meshes'].items()}
    c, s = math.cos(o['angle']), math.sin(o['angle'])
    rotation = np.array([[c, s], [-s, c]])
    walk, every = [], []
    for part in (model or {}).get('collision', []):
        name = part['name'].lower()
        if name not in names.values():
            continue
        xy = part['positions'][:, :2]*data['scale'] @ rotation + [o['x'], o['y']]
        z = part['positions'][:, 2]*data['scale'] + o['z']
        for tri in np.asarray(part['indices']).reshape(-1, 3):
            t = np.column_stack([xy[tri], z[tri]])
            every.append(t)
            if name == names.get('wallboundsmesh'):
                walk.append(t)
    return walk, every


def height(tris, x, y):
    """The walkway's height at x, y: in the triangle holding it, or the nearest triangle's middle."""
    for t in tris:
        (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = t
        det = (y2 - y3)*(x1 - x3) + (x3 - x2)*(y1 - y3)
        if abs(det) < 1e-6:
            continue
        a = ((y2 - y3)*(x - x3) + (x3 - x2)*(y - y3))/det
        b = ((y3 - y1)*(x - x3) + (x1 - x3)*(y - y3))/det
        if min(a, b, 1 - a - b) >= -1e-3:
            return a*z1 + b*z2 + (1 - a - b)*z3
    return float(min(tris, key=lambda t: math.dist(t[:, :2].mean(0), (x, y)))[:, 2].mean())


def cells(tris, step=10):
    """The points every `step` inside a walkway's triangles."""
    out = []
    for t in tris:
        lo, hi = t[:, :2].min(0), t[:, :2].max(0)
        xs, ys = np.meshgrid(np.arange(math.floor(lo[0]), hi[0] + step, step), np.arange(math.floor(lo[1]), hi[1] + step, step))
        keep = inside(t[:, :2], xs, ys)
        out += list(zip(xs[keep], ys[keep]))
    return np.unique(np.array(out, float).reshape(-1, 2), axis=0)


def stations(tris, middle):
    """Places one SPACING apart along the middle of a walkway: (x, y, facing angle away from `middle`, height)."""
    pts = cells(tris)
    if len(pts) < 10:
        return []
    c = pts.mean(0)
    u = np.linalg.eigh(np.cov((pts - c).T))[1][:, -1]      # the walkway's long axis
    v = np.array([-u[1], u[0]])
    t, w = (pts - c) @ u, (pts - c) @ v
    n = int((t.max() - t.min() - 2*END)//SPACING) + 1
    if n < 1:
        return []
    out = []
    for k in range(n):
        tk = (t.max() + t.min())/2 + (k - (n - 1)/2)*SPACING
        cut = np.abs(t - tk) <= 10
        if cut.sum() < 3 or np.ptp(w[cut]) < NARROWEST:
            continue
        p = c + u*tk + v*(w[cut].min() + w[cut].max())/2
        out_v = v if np.dot(p - middle, v) > 0 else -v
        out.append((float(p[0]), float(p[1]), math.atan2(out_v[1], out_v[0]), height(tris, *p)))
    return out


def defenders(m, assets, ground):
    """The defenders, (template, x, y, angle, z over the ground, role), and the points every 10 on the fortress's walking
    meshes, which it marks as blocked ground."""
    models, cache = ModelCache(assets), {}
    terrain = lambda x, y, t=TerrainData(m): float(t.height_at(np.array([x]), np.array([y]))[0])   # as the game interpolates it
    places = {group: [] for group in WALLS}
    shape = (ground.z.shape[0] - 2*ground.border, ground.z.shape[1] - 2*ground.border)
    outline = set()
    for o in m.objects():
        if o['template'] in SOLID:
            ground.taken.append((o['x'], o['y'], 110))
        data = template_data(assets.templates, o['template'], cache)
        if not data or 'WALK_ON_TOP_OF_WALL' not in data['kinds']:
            continue
        walk, every = walkway(o, assets, models, cache)
        for t in every:                                    # ground units keep off the walls and stairs
            ys, xs = polygon_cells(t[:, :2], shape)
            ground.blocked[ys + ground.border, xs + ground.border] = True
            outline.update(zip(xs*10 + 5, ys*10 + 5))
        base = terrain(o['x'], o['y'])
        for group, (pieces, _, middle) in WALLS.items():
            if o['template'] in pieces:
                places[group] += [(x, y, a, base + z) for x, y, a, z in stations(walk, np.array(middle))]
    out, free = [], [(group, p) for group in WALLS for p in places[group]]
    for template, spot in ON_WALLS:
        group, (x, y, a, z) = min(free, key=lambda gp: math.dist(gp[1][:2], spot))
        free.remove((group, (x, y, a, z)))
        out.append((template, x, y, a, z - terrain(x, y), 'hero'))
    for group, (x, y, a, z) in free:
        x, y = x - RANKS_AHEAD*math.cos(a), y - RANKS_AHEAD*math.sin(a)
        out.append((WALLS[group][1], x, y, a, z - terrain(x, y), group))
    for template, count, (cx, cy), facing, per_rank in POSTS:
        f = math.radians(facing)
        fx, fy = math.cos(f), math.sin(f)
        level = ground.height(cx, cy)
        for i in range(count):
            r, c = divmod(i, per_rank)
            across = (c - (min(per_rank, count - r*per_rank) - 1)/2)*POST_ACROSS
            x, y = cx - fx*r*POST_BACK + fy*across, cy - fy*r*POST_BACK - fx*across
            x, y = ground.spot(x, y, 45, 40, reach=300, level=level)
            out.append((template, x, y, f, 0, 'post'))
    return out, np.array(sorted(outline), float)


def host(m, ground, walls):
    """The Uruk host (HOST) and its siege: (template, x, y, angle, target, role) per unit, the role pike, sword, ladder
    or ram; and the grid's (column spacing, row spacing, gap). The battalions stand on an even grid, the same gap between
    neighbours along a row and between rows, as wide as still holds the host in the open field (open_at)."""
    W = walls[::2]
    x0, y0, x1, y1 = CAUSEWAY

    def south(x):
        """How far north the host may stand at x: short of the southernmost wall there (past the walls' ends, at the end)."""
        x = min(max(x, W[:, 0].min()), W[:, 0].max())
        return W[np.abs(W[:, 0] - x) < 40, 1].min() - 40

    def ahead(x, y):
        return 100 < x < 3900 and 100 < y < south(x)

    targets = {prop(o, 'objectName'): (o['x'], o['y']) for o in m.objects() if prop(o, 'objectName') in TARGETS}
    missing = set(TARGETS) - set(targets)
    if missing:
        raise ValueError(f'The map lacks the named pieces {sorted(missing)}')
    def ahead_of(x, among=TARGETS):
        """The piece straight ahead of x: the defences run west-east."""
        return min(among, key=lambda t: abs(targets[t][0] - x))

    def open_at(x, y):
        return (ahead(x, y) and y >= ymin and math.dist((x, y), ISENGARD_START) > BASE_CLEAR
                and not (x0 < x < x1 and y0 < y < y1) and ground.fits(x, y, ROOM, 40)
                and math.sqrt(((W - (x, y))**2).sum(1).min()) >= FRONT)

    ymin = SOUTH + (1 - TOP)*(max(south(x) for x in range(200, 3800, 100)) - SOUTH)

    def grid(gap):
        """Every open spot of the grid with `gap` between battalions, by row (north first) and column."""
        dx, dy = BATTALION[0] + gap, BATTALION[1] + gap
        top = max(south(x) for x in np.arange(100, 3900, dx))
        return [(x, y) for y in np.arange(top, ymin - 1, -dy) for x in np.arange(2000 - dx*(1900//dx), 3900, dx)
                if open_at(x, y)], dx, dy

    total = sum(HOST.values())
    lo, hi = 0., 300.                                      # the widest gap that still holds the host
    for _ in range(30):
        mid = (lo + hi)/2
        lo, hi = (mid, hi) if len(grid(mid)[0]) >= total else (lo, mid)
    spots, dx, dy = grid(lo)
    while len(spots) > total:                              # the rear row's surplus, from its ends in turn
        rear = [k for k, p in enumerate(spots) if p[1] == spots[-1][1]]
        spots.pop(rear[-1] if len(spots) % 2 else rear[0])
    out = []
    for k, (x, y) in enumerate(spots):                     # north first: the front three quarters pikes, the rear swords
        template = PIKE if k < HOST[PIKE] else SWORD
        out.append((template, float(x), float(y), math.pi/2, ahead_of(x), 'pike' if template == PIKE else 'sword'))
    # ladders one row before the front of the Deeping Wall's columns, rams at the causeway's foot
    columns = sorted({p[0] for p in spots})
    for c, x in enumerate(columns):
        y = max(p[1] for p in spots if p[0] == x) + dy
        if c % LADDER_EVERY == 0 and ahead_of(x) != 'Main Gate' and ahead(x, y) and ground.fits(x, y, 25, 40):
            out.append((LADDER, float(x), float(y), math.pi/2, ahead_of(x, DEEP_TARGETS), 'ladder'))
    for x, y in RAM_SPOTS:
        x, y = ground.spot(x, y, 25, 60, reach=100)
        gx, gy = targets['Main Gate']
        out.append((RAM, x, y, math.atan2(gy - y, gx - x), 'Main Gate', 'ram'))
    return out, (round(dx), round(dy), round(lo))


def scripts(m, side, units):
    """The assaults' scripts (see the module docstring), on PlyrCivilian."""
    w = Writer(m)
    text = lambda kind, value: arg(kind, text=value)
    op = lambda kind, name, *args: w.operation(kind, name, list(args))
    timer = lambda name, seconds: op('action', 'SET_MILLISECOND_TIMER', text(4, name), arg(1, real=float(seconds)))
    expired = lambda name: op('condition', 'TIMER_EXPIRED', text(4, name))
    stage = lambda group, n: op('condition', 'COUNTER', text(4, f'HD_{group}'), arg(6, integer=2), arg(0, integer=n))
    set_stage = lambda group, n: op('action', 'SET_COUNTER', text(4, f'HD_{group}'), arg(0, integer=n))
    destroyed = lambda name: op('condition', 'NAMED_DESTROYED', text(14, name))
    attack = lambda unit, target: op('action', 'NAMED_ATTACK_NAMED', text(14, unit), text(14, target))
    move = lambda unit, waypoint: op('action', 'ATTACK_MOVE_NAMED_UNIT_TO', text(14, unit), text(7, waypoint))
    dock = lambda unit, target: op('action', 'NAMED_FIRE_SPECIAL_POWER_AT_NAMED', text(14, unit),
                                   text(31, 'SpecialAbilitySiegeDeploy'), text(14, target))
    # the ladders dock once, at the charge; the battalions and rams follow their assault's stage
    groups = {'Deep': [(n, t, r) for n, t, r in units if t != 'Main Gate' and r != 'ladder'],
              'Gate': [(n, t, r) for n, t, r in units if t == 'Main Gate']}
    orders = {('Deep', 1): lambda n, t, r: move(n, 'HD_Deep') if r == 'sword' else attack(n, t),   # the swords up the ladders
              ('Deep', 2): lambda n, t, r: move(n, 'HD_Deep'), ('Deep', 3): lambda n, t, r: move(n, 'HD_Keep'),
              ('Gate', 1): lambda n, t, r: attack(n, 'Main Gate'), ('Gate', 2): lambda n, t, r: move(n, 'HD_Bailey'),
              ('Gate', 3): lambda n, t, r: attack(n, 'Inner Keep Gate'), ('Gate', 4): lambda n, t, r: move(n, 'HD_Keep')}
    setup = [op('action', 'MAP_REVEAL_ALL_PERM', text(11, f'Player_{YOU}')), timer('HD_Charge', CHARGE)]
    setup += [timer(f'HD_{group}{n}', .1) for group, n in orders]
    charge = [set_stage('Deep', 1), set_stage('Gate', 1)] + [dock(n, t) for n, t, r in units if r == 'ladder']
    out = [w.script('HD_Setup', [[op('condition', 'CONDITION_TRUE')]], setup),
           w.script('HD_Charge', [[expired('HD_Charge')]], charge),
           w.script('HD_DeepBreached', [[stage('Deep', 1), destroyed(t)] for t in DEEP_TARGETS],
                    [set_stage('Deep', 2), timer('HD_DeepOnward', DEEP_ONWARD)]),
           w.script('HD_DeepOnward', [[stage('Deep', 2), expired('HD_DeepOnward')]], [set_stage('Deep', 3)]),
           w.script('HD_GateBroken', [[stage('Gate', 1), destroyed('Main Gate')]],
                    [set_stage('Gate', 2), timer('HD_GateOnward', GATE_ONWARD)]),
           w.script('HD_GateOnward', [[stage('Gate', 2), expired('HD_GateOnward')]], [set_stage('Gate', 3)]),
           w.script('HD_KeepGateBroken', [[destroyed('Inner Keep Gate')]], [set_stage('Gate', 4), set_stage('Deep', 3)])]
    for (group, n), order in orders.items():               # each stage's orders, at once and every DRIVE seconds
        name = f'HD_{group}{n}'
        actions = [order(*u) for u in groups[group]] + [timer(name, DRIVE)]
        out.append(w.script(name, [[stage(group, n), expired(name)]], actions, deactivate=False))
    w.install(out, side_index=side)
    return len(out)


def build(b):
    m = Map(b.assets.read(SOURCE + 'map wor helms deep.map'))
    set_world(m, mapName=b.project.title, mapDescription=b.project.description)
    side = seat(m)
    ground = Ground(m, m.heightmap()['border'])
    people, walls = defenders(m, b.assets, ground)
    uruks, spacing = host(m, ground, walls)
    check_templates(b.assets, [t for t, *_ in people] + list(HOST) + [LADDER, RAM])
    first = max([v for o in m.objects() for k, _, v in o['properties'] if k == 'waypointID'], default=0) + 1
    for i, (name, (x, y)) in enumerate(WAYPOINTS.items()):
        add_object(m, '*Waypoints/Waypoint', x, y, layer='Battle', extra=[
            ('originalOwner', 3, '/team'), ('uniqueID', 3, name), ('waypointID', 1, first + i),
            ('waypointName', 3, name), ('waypointTypeOption', 3, '')])
    for i, (template, x, y, a, z, role) in enumerate(people):
        name = f'HD_D{i:03d}'
        add_object(m, template, x, y, a, layer=f'Defenders {role}', z=z,
                   extra=[owner(YOU), ('uniqueID', 3, name), ('objectName', 3, name)])
    named = []
    for i, (template, x, y, a, target, role) in enumerate(uruks):
        name = f'HD_U{i:03d}'
        add_object(m, template, x, y, a, layer=f'Host {target}',
                   extra=[owner(ENEMY), ('uniqueID', 3, name), ('objectName', 3, name), ('objectRecruitableAI', 0, 0)])
        named.append((name, target, role))
    count = scripts(m, side, named)
    cp = lambda units: sum(command_points(b.assets.templates, u[0]) for u in units)
    tally = lambda units, key: {k: sum(1 for u in units if key(u) == k) for k in dict.fromkeys(map(key, units))}
    b.report.update(defenders=dict(command_points=cp(people), by_role=tally(people, lambda u: u[5]),
                                   by_template=tally(people, lambda u: u[0])),
                    host=dict(command_points=cp(uruks), spacing=spacing, by_template=tally(uruks, lambda u: u[0]),
                              by_target=tally(uruks, lambda u: u[4]), by_role=tally(uruks, lambda u: u[5])),
                    scripts=count, waypoints=WAYPOINTS)
    print(f'Defenders: {len(people)} ({cp(people)} command points); host: {len(uruks)} units '
          f'({cp(uruks)} command points), columns, rows and gap {spacing}; {count} scripts')
    ini = b.assets.read(SOURCE + 'map.ini').decode('cp1252').replace('\r\n', '\n')
    minimap = Image.open(io.BytesIO(b.assets.read(SOURCE + 'map wor helms deep_art.tga')))
    b.save(m, ini=ini, minimap=minimap)
