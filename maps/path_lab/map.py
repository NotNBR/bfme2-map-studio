"""Path Lab: which way do units go round what stands in their way?

Four lanes run west to east, 450 apart. At each lane's west end (x 250) stand
a single unit (GondorAragorn, 70 south of the lane) and a battalion
(GondorFighterHorde, 70 north); across the middle of the lane (about x 1000)
stands one kind of obstacle:

  y  300  corner:  a wall (Men's kit) folded into a pocket that opens west,
                   towards them: the way round is past one of its corners
  y  750  objects: Fornost buildings and rocks, staggered, with gaps between
  y 1200  hills:   a gentle mound (x 600), a plateau with cliff sides
                   (x 1000, 120 high) and a mountain as high, marked impassable
                   (x 1450): height alone never blocks in BFME2, the impassable
                   plane does (docs/game/navigation.md), so they walk over the
                   first two and go round the third
  y 1650  units:   five of your own battalions standing shoulder to shoulder
                   across the lane

Order each lane's pair to its east end (x 1750) in the viewer's Test mode
with Paths on, and watch the paths their AI plans and follows. All units are
Player_1's; nothing moves until ordered.

Answer (OpenBFME at the pin studio-2026-10-21-3, the viewer's Test mode with
Paths on, 21 October 2026; not checked in the game itself):

- corner: both paths run round the outside of the pocket, along its walls,
  past its far corners;
- objects: both bend through the gaps between the buildings and the rocks;
- hills: both run straight over the mound and the cliff-sided plateau, as
  height does not block, and round the impassable mountain;
- units: the battalion's path runs straight through the line of standing
  battalions, which make way as it marches through (allies are cleared from a
  new path, AIMover clearAlliesFromPath); the single unit's jogs past one.

    mw build path-lab
    mw view path-lab
"""
import math

import numpy as np

from mapworkshop.formats import sections
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.walls import place_wall, wall_line
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

WIDTH, HEIGHT, BORDER = 200, 190, 30     # cells; the map is 2000 x 1900 units
GROUND = 100.0
PALETTE = ['GrassMediumType40']
LANES = dict(corner=300, objects=750, hills=1200, units=1650)
START, GOAL, PAIR = 250, 1750, 70        # the pair's x at the start, the lanes' east end, the pair's offset off the lane
POCKET = 800, 1050, 180                  # the wall's open (west) end, its back, its half width
BUILDINGS = [('FornostBuilding05', 950, -150), ('FornostBuilding07', 950, 0), ('FornostBuilding05', 950, 150),
             ('FornostBuilding07', 1090, -75), ('FornostBuilding05', 1090, 75)]
ROCKS = [(1020, -230), (1020, 230), (1160, 0)]
MOUND, PLATEAU, MOUNTAIN = (600, 150, 60.0), (1000, 220, 120.0), (1450, 140, 120.0)   # centre x, radius, height
BLOCKERS = [-200, -100, 0, 100, 200]      # the standing battalions, off the lane: a closed line


def owner():
    return ('originalOwner', 3, 'Player_1/teamPlayer_1')


def grid():
    """The height map's sample positions in map units, x and y."""
    size = (HEIGHT + 2 * BORDER, WIDTH + 2 * BORDER)
    return np.meshgrid((np.arange(size[1]) - BORDER) * 10.0, (np.arange(size[0]) - BORDER) * 10.0)


def heights():
    """Flat, with the hills lane's mound (smooth), plateau and mountain (cliff-sided)."""
    gx, gy = grid()
    z = np.full(gx.shape, GROUND)
    cy = LANES['hills']
    mx, mr, mh = MOUND
    d = np.hypot(gx - mx, gy - cy)
    z += mh * np.clip(1 - d / mr, 0, 1) ** 2 * (3 - 2 * np.clip(1 - d / mr, 0, 1))   # smoothstep
    for px, pr, ph in (PLATEAU, MOUNTAIN):
        z[np.hypot(gx - px, gy - cy) <= pr] += ph
    return z


def mark_impassable(m):
    """The mountain's samples, and a ring of one sample round it, in the impassable plane."""
    gx, gy = grid()
    px, pr, _ = MOUNTAIN
    texture = sections.read(m, 'BlendTileData')
    arrays = dict(texture['arrays'])
    arrays['impassable'] = arrays['impassable'] | (np.hypot(gx - px, gy - LANES['hills']) <= pr + 10)
    texture['arrays'] = arrays
    sections.write(m, 'BlendTileData', texture)


def build(b):
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    z = heights()
    set_heights(m, z)
    set_materials(m, PALETTE, np.zeros(z.shape, 'u2'), cell_sizes=terrain_cell_sizes(PALETTE))
    mark_impassable(m)
    starts(m, [(100, 100), (1900, 1800)])
    for lane, y in LANES.items():
        add_object(m, 'GondorAragorn', START, y - PAIR, angle=0, layer=lane, extra=[owner()])
        add_object(m, 'GondorFighterHorde', START, y + PAIR, angle=0, layer=lane, extra=[owner()])
    y = LANES['corner']
    west, back, half = POCKET
    place_wall(m, wall_line([(west, y - half), (back, y - half), (back, y + half), (west, y + half)], kit='men'),
               layer='corner')
    y = LANES['objects']
    for template, x, dy in BUILDINGS:
        add_object(m, template, x, y + dy, angle=0, layer='objects')
    for x, dy in ROCKS:
        add_object(m, 'DarkRockGrey07', x, y + dy, angle=0, layer='objects')
    y = LANES['units']
    for dy in BLOCKERS:
        add_object(m, 'GondorFighterHorde', 1000, y + dy, angle=math.pi, layer='units', extra=[owner()])
    add_sky(m, b.project.weather, WIDTH * 10, HEIGHT * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather))
