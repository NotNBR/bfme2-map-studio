"""Battle of Helm's Deep: the Hornburg and the Deeping Wall held against the
host of Isengard.

The War of the Ring map `map wor helms deep` from the game's archives, its
fortress, coomb and props as they are, staged as a skirmish of two
(map.toml's [play]: you hold the fortress with Men, Isengard is a hard AI).
Player_2's start moves behind the coomb (ISENGARD_START), where the game
builds Isengard's fortress; the other two starts go, and so do the map's own
War of the Ring scripts (a command point limit, starting cash, build limits).
The night is the map's own (GlobalLighting's time of day: Night); map.toml's
weather (rain) dims it and adds rain and lightning (mapkit.weather), but not
the rain's fog, which would hide the stars. In place of the map's sky dome
stands a starry night over black, as the cinematic maps place their skies:
at the map's centre. Three templates that map.ini redefines draw the night
sky model's layers (sky_ini; the game hangs on a map.ini that adds an object
type): its stars (SKY), enlarged and sunk (SKY_SCALE, SKY_SINK) so that they
also fill the void below the map's edge, with the far plane pushed out
(CLIP_DEPTH) to reach them; its dark night clouds and moon (CLOUDS) at the
model's own size, a little lower (CLOUDS_SINK); and its ring of distant
mountains (MOUNTAINS) at its own height. Its purple glows and backdrop and
orange flares stay hidden.

The forces stand as Peter Jackson's The Two Towers (2002) has them on the
night of the battle:

- Defenders, owned by Player_1 like every piece of the fortress: about 5,000
  command points. Archers stand on the walls (WALLS): one battalion every
  SPACING along each piece's walkway (its WallBoundsMesh, read from the
  model), facing out, its front rank at the parapet (PARAPET): Haldir's
  Lothlorien archers along the Deeping Wall and the culvert, Men's archers on
  the Hornburg's outer walls and gatehouse and on the keep's walls. Each
  stands at its walkway's height (a map object's Z is over the ground under
  it), so the game puts it on the wall's layer. The heroes (ON_WALLS) take
  the walkway place nearest their spot: Aragorn over the culvert, Haldir
  among his Elves, Legolas and Gimli side by side on the Deeping Wall, Theoden
  on the gatehouse. Behind the walls (POSTS): Galadhrim and spearmen in the
  Deep behind the culvert, spearmen bracing the main gate in the bailey, the
  Rohirrim in the keep's courtyard for the last ride, the women and children
  at the back of the keep by the caves' arcade (the film puts the Glittering
  Caves' entrance inside the Hornburg).
- Attackers, owned by Player_2: about 40,100 command points of Uruk-hai,
  pikemen and swordsmen (HOST), facing north on an even grid: the
  gaps GAP between neighbours along a row and ROW_GAP between rows (a battalion
  is BATTALION), at most as wide as still holds HOST in the northern TOP of
  the Deeping Coomb, no nearer the walls than FRONT (out of bowshot: Men's
  archers reach 300), off the causeway (CAUSEWAY) and Isengard's base
  (BASE_CLEAR); behind them REAR_ROWS more rows of pikes on the same grid.
  Each battalion stands a little off its spot and off north (JITTER).
  The film's order of battle (TESTUDO): at the causeway's foot
  the battering rams inside a column of shield-bearing swordsmen; before the
  Deeping Wall the rest of the swordsmen in the front rows, a siege ladder
  one row before every LADDER_EVERY column; before the culvert, instead of a
  ladder, the bomb: a mine carrier (MINE) and the torch-bearing berserker
  (BERSERKER); the pikes the mass behind them and before the Hornburg. About
  40,100 command points in all. None is recruitable by the AI, so the
  scripts alone move them.
- Scripts, on PlyrCivilian: at CHARGE seconds each battalion attacks the
  piece of the defences straight ahead of it (TARGETS: the main gate, the
  culvert or a section of the Deeping Wall), the rams the main gate. The
  ladders dock against the section ahead of them (DEPLOY_SIEGE_ON_NAMED_WALL:
  their SpecialAbilitySiegeDeploy takes any STRUCTURE +WALK_ON_TOP_OF_WALL);
  the Deeping Wall's swords make for the Deep, up the ladders, while its
  pikes batter the wall. The mine carrier plants its charge against the
  culvert and the berserker lights his torch and runs after it; once the
  carrier has dropped the charge (BOMB), the charge, named HD_Bomb, burns
  (its Detonate: a script cannot set the berserker's torch on his own side's
  charge; its UnpackTime, 20 seconds, is the fuse) and takes the culvert. Once
  the culvert or a section falls, the Deeping Wall's attackers pour into the
  Deep, and DEEP_ONWARD later make for the keep; once the main gate falls,
  its attackers storm the bailey, GATE_ONWARD later attack the keep's gate,
  and when that falls the keep. Each assault's stage is a counter (HD_Deep,
  HD_Gate); its orders are given again every DRIVE seconds. At DAWN Theoden
  and the keep's Rohirrim (RIDE) ride out into the coomb, and Gandalf and
  Eomer come over the eastern ridge with ten battalions of Rohirrim
  (DAWN_FORCE, made by the script). Your units otherwise follow your orders
  only.

In OpenBFME (mw play --godot) the archers stand on the walls' layers, the
ladders deploy onto the sections and their climbs enter the pathfinder
(its lanes WALL-1, WALL-2, SIEGE-1), the charge drops and the culvert falls
(its tests test_wall1_battle.cpp and test_siege1_deploy.cpp).

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
from mapworkshop.mapkit.weather import apply_weather, ini_block
from mapworkshop.render.terrain import TerrainData
from mapworkshop.assets.models import ModelCache
from mapworkshop.mapkit.lines import inside
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
PARAPET = 8                     # an archer battalion's front rank stands this far inside its walkway's outer edge, at the parapet
RANKS = 10, 50                  # a horde's ranks stand this far ahead of it (RankInfo)
SOLID = ('HelmsDeepGatehouseCenter', 'HelmsDeepTower', 'HelmsDeepRampart04', 'WOR_HelmsDeepArcade')   # no walking mesh: ground units keep 110 off
# Heroes on the walls as the film has them, each at the walkway place nearest its spot
ON_WALLS = [('GondorAragornMP', (1645, 2938)),  # the Deeping Wall over the culvert, commanding the Elves
            ('ElvenHaldir', (1312, 2917)),      # among his archers
            ('ElvenLegolas', (1977, 2903)),     # Legolas and Gimli side by side
            ('DwarvenGimli', (2060, 2900)),
            ('RohanTheoden', (2721, 2612))]     # on the gatehouse, over the main gate
# Behind the walls: template, how many, the middle of the front rank, facing (degrees: 0 east, 90 north), per rank
POSTS = [('ElvenLorienWarriorHorde', 12, (1640, 3110), -90, 6),    # in the Deep, behind the culvert
         ('RohanSpearmenHorde', 8, (1640, 3330), -90, 4),
         ('RohanSpearmenHorde', 10, (2770, 2860), -90, 5),         # in the bailey, bracing the main gate
         ('RohanRohirrimHorde', 6, (2830, 3250), -90, 3),          # in the keep's courtyard, for the last ride
         ('RohanPeasantHorde', 5, (2700, 3415), -90, 5)]           # the women and children, at the back of the keep by the caves' arcade
RIDE = ('RohanRohirrimHorde', 'RohanTheoden')   # at DAWN these ride out of the keep, down the causeway into the coomb
# At DAWN Gandalf and Eomer come over the eastern ridge with the Rohirrim (the film's 2,000 riders): template, how many
DAWN_FORCE = [('GondorGandalfWhite', 1), ('RohanEomer', 1), ('RohanRohirrimHorde', 10)]
POST_ACROSS, POST_BACK = 100, 80

PIKE, SWORD = 'IsengardPikemanHorde', 'IsengardFighterHorde'
HOST = {PIKE: 294, SWORD: 98}   # 3 to 1; 24,990 command points at 60 and 75
REAR_ROWS = 9                   # and this many more rows of pikes behind the rear row, past the field's TOP
BATTALION = 90, 50              # a battalion's frontage and depth (5 abreast 20 apart, 3 ranks)
GAP, ROW_GAP = 15, 25           # between neighbouring battalions along a row, and between rows (at most what fits HOST)
JITTER = 6, 3                   # each battalion up to this far off its grid spot (map units) and off north (degrees)
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
# The film's order of battle: the ram goes up the causeway inside a column of shield-bearing swordsmen (a testudo), at the
# causeway's foot (TESTUDO: its files and ranks, the rams in the middle file's front ranks); the rest of the swordsmen form
# the front rows before the Deeping Wall, behind the ladders, to scale it; the pikes are the mass behind and before the
# Hornburg. Before the culvert, instead of a ladder, the bomb: a mine carrier, which plants its charge against what it
# attacks, and the torch-bearing berserker who lights it (the charge burns off: IsengardDeployedExplosiveMine)
CAUSEWAY_FOOT = (2830, 1840)
TESTUDO = 3, 6
RAMS = 4
MINE, BERSERKER = 'IsengardExplosiveMine', 'IsengardBeserker'
BOMB = 'IsengardDeployedExplosiveMine'          # what the carrier's IsengardExplosiveMineDroppingWeapon leaves
TORCH, DETONATE = 'Command_SpecialAbilityLightTorch', 'Command_IsengardMineDetonate'
# What each battalion attacks: the destructible piece straight ahead of it (nearest west to east); the gate's attackers form
# one assault, the rest the Deeping Wall's
TARGETS = ('Main Gate', 'Culvert', 'Deeping Wall Far Left', 'Deeping Wall Center Left', 'Deeping Wall Near Left',
           'Deeping Wall Right')
DEEP_TARGETS = TARGETS[1:]
WAYPOINTS = {'HD_Deep': (1640, 3350), 'HD_Bailey': (2850, 2860), 'HD_Keep': (2850, 3330), 'HD_Culvert': (1645, 2860),
             'HD_Ridge': (3620, 1650), 'HD_Coomb': (2000, 1500)}   # the ridge: where the dawn force comes in, on the east side
CHARGE = 20                     # seconds into the game the host attacks
DEEP_ONWARD, GATE_ONWARD = 90, 60
DRIVE = 40                      # every assault's orders again this often
DAWN = 600                      # seconds into the game the sun comes up
# The starry night: the SkyBoxNight model (unlit, about 10,000 round), drawn by three templates that map.ini redefines
# (sky_ini), each keeping some of its meshes and hiding the rest as CINE_DwarvenCatapult hides its crew: by its idle
# state's script. The rest stay hidden everywhere: purple glows, orange flares and a violet backdrop.
NIGHT_MESHES = {'SPHERE02': 'the stars, 578 to 4,059 up, 9,500 out', 'CYLINDER10': 'dark night clouds, 66 to 1,684 up',
                'SPHERE03': 'the moon, 3,700 up over the middle', 'SPHERE01': 'violet backdrop (vertex colours)',
                'CYLINDER16': 'purple glow', 'MESH01': 'purple glow', 'CYLINDER14': 'warm horizon glow',
                'PLANE01': 'orange flare', 'PLANE02': 'orange flare', 'CYLINDER02': 'mountain ring, 6,800 out'}
# The stars, enlarged and sunk so that they reach below the map's edge (atan(sink / radius) below the horizon): at
# SKY_SCALE the star sphere is 19,000 out, sunk SKY_SINK under the lowest ground its foot 3,800 below it (11 degrees) and
# its top 3,100 over it, 2,400 over the highest peak (709). Its far side needs the far plane pushed out (CLIP_DEPTH, as
# the cin maps do). CINE_DomeSkyboxNight is placed on no stock map.
SKY, SKY_KEPT = 'CINE_DomeSkyboxNight', ('SPHERE02',)
SKY_SCALE, SKY_SINK = 2.0, 5000
CLIP_DEPTH = 10
# The moonlight (GlobalLighting light 0 of terrain and objects), bluer than the map's own (0.28, 0.29, 0.42); the rain
# preset then scales it by (0.55, 0.62, 0.72) to about (0.12, 0.17, 0.40), as bright as the map's own came out
MOON = (0.22, 0.28, 0.55)
# The clouds and the moon at the model's own size, its foot CLOUDS_SINK under the lowest ground: the cloud band (9,400
# out) then runs from about 4.5 degrees below the horizon to 5.5 above it; sunk with the stars it would sit wholly below.
# CaHero_MorSky is placed only on the Create-a-Hero map (createahero).
CLOUDS, CLOUDS_KEPT = 'CaHero_MorSky', ('CYLINDER10', 'SPHERE03')
CLOUDS_SINK = 800
# The mountain ring at the model's own size and height, its foot at the lowest ground (sunk with the clouds it would sit
# below the horizon): a dark blue range 3,900 to 6,900 out, up to 734 high. No third template draws SkyBoxNight, so
# map.ini points CINE_DomeSkyboxMorning (placed on no stock map) at it.
MOUNTAINS, MOUNTAINS_KEPT = 'CINE_DomeSkyboxMorning', ('CYLINDER02',)


def sky_ini(template, kept):
    """map.ini's override of `template`: its draw module (ModuleTag_01 in all three) replaced by one drawing the
    SkyBoxNight model with only the `kept` meshes. The game hangs on a map.ini that adds an object type, and in an
    override a module must come by ReplaceModule, the same module type under a new tag (the game stops loading
    the map otherwise); the template's other modules and fields stay as the game defines them."""
    hide = ''.join(f'          CurDrawableHideSubObject("{mesh}")\n' for mesh in NIGHT_MESHES if mesh not in kept)
    return f'''Object {template}
  ReplaceModule ModuleTag_01
    Draw = W3DScriptedModelDraw ModuleTag_HD_Sky
      DefaultModelConditionState
        Model = SkyBoxNight
      End
      IdleAnimationState
        BeginScript
{hide}        EndScript
      End
    End
  End
End
'''


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
    data = template_data(assets, o['template'], cache)
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
    """Places one SPACING apart along the middle of a walkway: (x, y, facing angle away from `middle`, height, half
    the walkway's width there)."""
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
        out.append((float(p[0]), float(p[1]), math.atan2(out_v[1], out_v[0]), height(tris, *p), float(np.ptp(w[cut]))/2))
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
        data = template_data(assets, o['template'], cache)
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
                places[group] += [(x, y, a, base + z, half) for x, y, a, z, half in stations(walk, np.array(middle))]
    out, free = [], [(group, p) for group in WALLS for p in places[group]]
    for template, spot in ON_WALLS:
        place = min(free, key=lambda gp: math.dist(gp[1][:2], spot))
        free.remove(place)
        x, y, a, z, half = place[1]
        out.append((template, x, y, a, z - terrain(x, y), 'hero'))
    for group, (x, y, a, z, half) in free:
        back = RANKS[1] - (half - PARAPET)                  # the front rank at the parapet, the horde behind it
        back = min(back, RANKS[0] + half)                   # and the rear rank still on the walkway
        x, y = x - back*math.cos(a), y - back*math.sin(a)
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
    neighbours along a row and between rows: GAP, or less if the host would not fit the open field (open_at)."""
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

    def testudo(dx, dy):
        """The ram column's spots at the causeway's foot, front rank first, for the grid's spacing."""
        files, ranks = TESTUDO
        return [(CAUSEWAY_FOOT[0] + (f - (files - 1)/2)*dx, CAUSEWAY_FOOT[1] - r*dy, f, r)
                for r in range(ranks) for f in range(files)]

    def open_at(x, y, dx, dy, field=True):
        """`field`: within the field's northern TOP."""
        column = testudo(dx, dy)
        return (ahead(x, y) and (y >= ymin or not field) and math.dist((x, y), ISENGARD_START) > BASE_CLEAR
                and not (x0 < x < x1 and y0 < y < y1) and ground.fits(x, y, ROOM, 40)
                and not any(abs(x - cx) < dx*.9 and abs(y - cy) < dy*.9 for cx, cy, *_ in column)
                and math.sqrt(((W - (x, y))**2).sum(1).min()) >= FRONT)

    ymin = SOUTH + (1 - TOP)*(max(south(x) for x in range(200, 3800, 100)) - SOUTH)

    def grid(gap, row_gap=None):
        """Every open spot of the grid with `gap` between battalions in a row and `row_gap` (default `gap`)
        between rows, by row (north first) and column."""
        dx, dy = BATTALION[0] + gap, BATTALION[1] + (gap if row_gap is None else row_gap)
        top = max(south(x) for x in np.arange(100, 3900, dx))
        return [(x, y) for y in np.arange(top, ymin - 1, -dy) for x in np.arange(2000 - dx*(1900//dx), 3900, dx)
                if open_at(x, y, dx, dy)], dx, dy

    shields = TESTUDO[0]*TESTUDO[1] - RAMS                  # the ram column's swordsmen
    total = sum(HOST.values()) - shields
    lo, hi = 0., 300.                                      # the widest gap that still holds the host
    for _ in range(30):
        mid = (lo + hi)/2
        lo, hi = (mid, hi) if len(grid(mid)[0]) >= total else (lo, mid)
    spots, dx, dy = grid(min(lo, GAP), min(lo, ROW_GAP))
    while len(spots) > total:                              # the rear row's surplus, from its ends in turn
        rear = [k for k, p in enumerate(spots) if p[1] == spots[-1][1]]
        spots.pop(rear[-1] if len(spots) % 2 else rear[0])
    rear = min(p[1] for p in spots)                        # REAR_ROWS more rows behind, on the same grid
    for k in range(1, REAR_ROWS + 1):
        spots += [(x, rear - k*dy) for x in np.arange(2000 - dx*(1900//dx), 3900, dx)
                  if open_at(x, rear - k*dy, dx, dy, field=False)]
    # the swordsmen not in the ram column: the front rows of the Deeping Wall's columns, row by row; the rest pikes
    depth = {}                                             # each spot's place in its column, the front 0
    for x, y in spots:
        depth[(x, y)] = sum(1 for px, py in spots if px == x and py > y)
    deep = sorted((p for p in spots if ahead_of(p[0]) != 'Main Gate'), key=lambda p: (depth[p], p[0]))
    assault = set(deep[:HOST[SWORD] - shields])
    # the grid a little uneven (JITTER), the same on every build
    shake = np.random.default_rng(1).uniform(-1, 1, (len(spots), 3))*[JITTER[0], JITTER[0], math.radians(JITTER[1])]
    out = [(SWORD if (x, y) in assault else PIKE, float(x+jx), float(y+jy), math.pi/2+ja, ahead_of(x),
            'sword' if (x, y) in assault else 'pike') for (x, y), (jx, jy, ja) in zip(spots, shake)]
    gx, gy = targets['Main Gate']
    for x, y, f, r in testudo(dx, dy):                     # the ram column, facing up the causeway to the gate
        x, y = ground.spot(x, y, 25, 60, reach=60)
        ram = f == (TESTUDO[0] - 1)//2 and r < RAMS
        out.append((RAM if ram else SWORD, x, y, math.atan2(gy - y, gx - x), 'Main Gate', 'ram' if ram else 'sword'))
    # one row before the front of the Deeping Wall's columns: a ladder each, and before the culvert the bomb
    columns = sorted({p[0] for p in spots if ahead_of(p[0]) != 'Main Gate'})
    culvert = min(columns, key=lambda x: abs(x - targets['Culvert'][0]))
    for c, x in enumerate(columns):
        y = max(p[1] for p in spots if p[0] == x) + dy
        if not (ahead(x, y) and ground.fits(x, y, 25, 40)):
            continue
        if x == culvert:
            out.append((MINE, float(x - dx/4), float(y), math.pi/2, 'Culvert', 'mine'))
            out.append((BERSERKER, float(x + dx/4), float(y), math.pi/2, 'Culvert', 'berserker'))
        elif c % LADDER_EVERY == 0:
            out.append((LADDER, float(x), float(y), math.pi/2, ahead_of(x, DEEP_TARGETS), 'ladder'))
    return out, (round(dx), round(dy), round(dx - BATTALION[0]), round(dy - BATTALION[1]))


def scripts(m, side, units, riders):
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
    dock = lambda unit, target: op('action', 'DEPLOY_SIEGE_ON_NAMED_WALL', text(14, unit), text(14, target))
    button = lambda unit, name: op('action', 'NAMED_USE_COMMANDBUTTON_ABILITY', text(14, unit), text(34, name))
    # the charge the mine carrier drops is a new, unnamed object: named as the one nearest the host's centre (there is one)
    name_bomb = op('action', 'SET_REF_TO_NEREST_TEAM_OF_TYPE_OWNED_BY_PLAYER', text(61, BOMB), text(11, f'Player_{ENEMY}'),
                   text(3, f'Player_{ENEMY}/teamPlayer_{ENEMY}'), text(54, 'HD_Bomb'))
    create = lambda unit, template, waypoint: op('action', 'CREATE_NAMED_ON_TEAM_AT_WAYPOINT', text(14, unit),
                                                 text(15, template), text(3, f'Player_{YOU}/teamPlayer_{YOU}'),
                                                 text(7, waypoint))
    # the ladders dock once and the bomb goes in once, at the charge; the battalions and rams follow their assault's stage
    once = ('ladder', 'mine', 'berserker')
    groups = {'Deep': [(n, t, r) for n, t, r in units if t != 'Main Gate' and r not in once],
              'Gate': [(n, t, r) for n, t, r in units if t == 'Main Gate' and r not in once]}
    orders = {('Deep', 1): lambda n, t, r: move(n, 'HD_Deep') if r == 'sword' else attack(n, t),   # the swords up the ladders
              ('Deep', 2): lambda n, t, r: move(n, 'HD_Deep'), ('Deep', 3): lambda n, t, r: move(n, 'HD_Keep'),
              ('Gate', 1): lambda n, t, r: attack(n, 'Main Gate'), ('Gate', 2): lambda n, t, r: move(n, 'HD_Bailey'),
              ('Gate', 3): lambda n, t, r: attack(n, 'Inner Keep Gate'), ('Gate', 4): lambda n, t, r: move(n, 'HD_Keep')}
    setup = [op('action', 'MAP_REVEAL_ALL_PERM', text(11, f'Player_{YOU}')), timer('HD_Charge', CHARGE), timer('HD_Dawn', DAWN),
             op('action', 'SET_CAMERA_CLIP_DEPTH_MULTIPLIER', arg(1, real=float(CLIP_DEPTH)))]   # the sunk sky's far side
    setup += [timer(f'HD_{group}{n}', .1) for group, n in orders]
    charge = [set_stage('Deep', 1), set_stage('Gate', 1)] + [dock(n, t) for n, t, r in units if r == 'ladder']
    charge += [attack(n, t) for n, t, r in units if r == 'mine']             # it plants its charge against the culvert
    charge += [button(n, TORCH) for n, t, r in units if r == 'berserker']    # the torch-bearer lights his torch
    charge += [move(n, 'HD_Culvert') for n, t, r in units if r == 'berserker']   # and runs after it
    # once the carrier has dropped its charge (it fades as it does) the charge burns: its Detonate (the torch's work; a script cannot set the
    # berserker's torch on his own side's charge), whose UnpackTime is its fuse
    carriers = [n for n, t, r in units if r == 'mine']
    bomb = [name_bomb, button('HD_Bomb', DETONATE)]
    # dawn: the keep's riders charge down the causeway, Gandalf and Eomer come over the eastern ridge with the Rohirrim
    dawn = [move(n, 'HD_Coomb') for n in riders]
    for i, template in enumerate(t for t, count in DAWN_FORCE for _ in range(count)):
        dawn += [create(f'HD_Dawn{i:02d}', template, 'HD_Ridge'), move(f'HD_Dawn{i:02d}', 'HD_Coomb')]
    out = [w.script('HD_Setup', [[op('condition', 'CONDITION_TRUE')]], setup),
           w.script('HD_Charge', [[expired('HD_Charge')]], charge),
           w.script('HD_DeepBreached', [[stage('Deep', 1), destroyed(t)] for t in DEEP_TARGETS],
                    [set_stage('Deep', 2), timer('HD_DeepOnward', DEEP_ONWARD)]),
           w.script('HD_DeepOnward', [[stage('Deep', 2), expired('HD_DeepOnward')]], [set_stage('Deep', 3)]),
           w.script('HD_GateBroken', [[stage('Gate', 1), destroyed('Main Gate')]],
                    [set_stage('Gate', 2), timer('HD_GateOnward', GATE_ONWARD)]),
           w.script('HD_GateOnward', [[stage('Gate', 2), expired('HD_GateOnward')]], [set_stage('Gate', 3)]),
           w.script('HD_KeepGateBroken', [[destroyed('Inner Keep Gate')]], [set_stage('Gate', 4), set_stage('Deep', 3)]),
           w.script('HD_Dawn', [[expired('HD_Dawn')]], dawn)]
    if carriers:
        out.append(w.script('HD_Bomb', [[destroyed(n)] for n in carriers], bomb))
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
    check_templates(b.assets, [t for t, *_ in people] + list(HOST) + [LADDER, RAM, MINE, BERSERKER] + [t for t, _ in DAWN_FORCE])
    first = max([v for o in m.objects() for k, _, v in o['properties'] if k == 'waypointID'], default=0) + 1
    for i, (name, (x, y)) in enumerate(WAYPOINTS.items()):
        add_object(m, '*Waypoints/Waypoint', x, y, layer='Battle', extra=[
            ('originalOwner', 3, '/team'), ('uniqueID', 3, name), ('waypointID', 1, first + i),
            ('waypointName', 3, name), ('waypointTypeOption', 3, '')])
    for i, (template, x, y, a, z, role) in enumerate(people):
        name = f'HD_D{i:03d}'
        add_object(m, template, x, y, a, layer=f'Defenders {role}', z=z,
                   extra=[owner(YOU), ('uniqueID', 3, name), ('objectName', 3, name)])
    riders = [f'HD_D{i:03d}' for i, (template, *_) in enumerate(people) if template in RIDE]
    named = []
    for i, (template, x, y, a, target, role) in enumerate(uruks):
        name = f'HD_U{i:03d}'
        add_object(m, template, x, y, a, layer=f'Host {target}',
                   extra=[owner(ENEMY), ('uniqueID', 3, name), ('objectName', 3, name), ('objectRecruitableAI', 0, 0)])
        named.append((name, target, role))
    count = scripts(m, side, named, riders)
    cp = lambda units: sum(command_points(b.assets.templates, u[0]) for u in units)
    tally = lambda units, key: {k: sum(1 for u in units if key(u) == k) for k in dict.fromkeys(map(key, units))}
    b.report.update(defenders=dict(command_points=cp(people), by_role=tally(people, lambda u: u[5]),
                                   by_template=tally(people, lambda u: u[0])),
                    host=dict(command_points=cp(uruks), spacing=spacing, by_template=tally(uruks, lambda u: u[0]),
                              by_target=tally(uruks, lambda u: u[4]), by_role=tally(uruks, lambda u: u[5])),
                    dawn=dict(seconds=DAWN, riders=len(riders), force=dict(DAWN_FORCE),
                              command_points=sum(command_points(b.assets.templates, t)*n for t, n in DAWN_FORCE)),
                    scripts=count, waypoints=WAYPOINTS)
    print(f'Defenders: {len(people)} ({cp(people)} command points); host: {len(uruks)} units '
          f'({cp(uruks)} command points), column and row spacing, gap and row gap {spacing}; {count} scripts')
    # the night of the battle in map.toml's weather (rain and lightning over the map's own night, no fog) under SKY
    m.set_objects([o for o in m.objects() if not o['template'].startswith('WaterReflectionSkydome')])
    terrain, border = TerrainData(m), m.heightmap()['border']*10
    xs, ys = np.meshgrid(np.arange(-border, 4000 + border, 40.), np.arange(-border, 4000 + border, 40.))
    lowest = float(terrain.height_at(xs.ravel(), ys.ravel()).min())
    centre = float(terrain.height_at(np.array([2000.]), np.array([2000.]))[0])
    add_object(m, SKY, 2000, 2000, layer='Sky', z=lowest - centre - SKY_SINK,
               extra=[('objectPrototypeScale', 2, SKY_SCALE)])
    add_object(m, CLOUDS, 2000, 2000, layer='Sky', z=lowest - centre - CLOUDS_SINK)
    add_object(m, MOUNTAINS, 2000, 2000, layer='Sky', z=lowest - centre - 10)
    apply_weather(m, b.project.weather, sun={'diffuse': MOON})
    ini = b.assets.read(SOURCE + 'map.ini').decode('cp1252').replace('\r\n', '\n')
    ini = (ini.rstrip() + '\n\n' + ini_block(b.project.weather, fog=None) + '\n' + sky_ini(SKY, SKY_KEPT) + '\n'
           + sky_ini(CLOUDS, CLOUDS_KEPT) + '\n' + sky_ini(MOUNTAINS, MOUNTAINS_KEPT))
    minimap = Image.open(io.BytesIO(b.assets.read(SOURCE + 'map wor helms deep_art.tga')))
    b.save(m, ini=ini, minimap=minimap)
