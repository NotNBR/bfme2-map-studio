"""Horde Spacing Lab: where does the game put the second of two battalions sent to one point?

A flat, open map. Each row holds a pair of your battalions of one template,
200 apart north to south at x 400, facing east; at the start the map's script
orders each of them on its own (MOVE_NAMED_UNIT_TO) to the row's waypoint at
x 900, between the two. The first row is OpenBFME's own test scene (its
engine test "move3 retail: two allied hordes sent to one point", FB-0006),
moved onto this map:

  y  700  GondorArcherHorde         (HS_A1, HS_A2 to HS_A)
  y 1400  GondorFighterHorde        (B)
  y 2100  ElvenMirkwoodArcherHorde  (C)
  y 2800  ElvenLorienArcherHorde    (D)
  y 3500  DwarvenAxeThrowerHorde    (E)
  y 4200  MordorArcherHorde         (F)
  y 4900  GoblinArcherHorde         (G)
  y 5600  IsengardUrukCrossbowHorde (H)
  y 6300  AngmarDarkRangerHorde     (I)
  y 7000  RohanArcherHorde          (J)

The second battalion's destination is adjusted when the first one's member
goals hold the point: RotWK tests a rectangle of the battalion's size around
each candidate cell (Pathfinder::checkDestination RW 0x6F1584, the rectangle
RW 0x6F0195), searched in a spiral around the point (RW 0x6FA2A4).

Answer (ROTWK 2.01, `mw battle horde-spacing-lab --rotwk --seconds 1`, 20
October 2026): the first of each pair takes the point's cell, the second
stops one formation length on, side by side with it along the march:
Gondor archers and fighters 60 east, Lorien archers and Dwarf axe throwers
50, Mirkwood archers 40, Angmar dark rangers 40 west; the hordes with a
RandomOffset (Mordor and Goblin archers, Uruk crossbows) change side from run
to run. The members stand centred on their battalion (the slot table, the
banner carrier's slot included, less its mean: RW 0x86C4EA), not ahead of it
as the RankInfo X values would put them. OpenBFME had them ahead, and two
battalions sent to one point overlapped once its destination search was
corrected; its fix follows these numbers ([battalions](../../docs/game/battalions.md)).

A torch every 50 along x (700 .. 1000), 110 north of each point, is a ruler
for reading the members' positions off a straight-down screenshot.

    mw build horde-spacing-lab
    mw battle horde-spacing-lab --rotwk --seconds 1 [--cells]     # the destinations and goals, from the game
    mw capture horde-spacing-lab --view a 850 750 500 89 0 --at 300 --view b 850 1450 500 89 0 --at 300
"""
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.script_writer import Writer, arg
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

import numpy as np

WIDTH, HEIGHT, BORDER = 150, 760, 30     # cells; the map is 1500 x 7600 units
GROUND = 100.0
PALETTE = ['GrassMediumType40']
START, GOAL_X, APART = 400, 900, 200     # the pair at x START, 200 apart north to south; their point at x GOAL_X between them
ROWS = [('A', 'GondorArcherHorde', 700), ('B', 'GondorFighterHorde', 1400), ('C', 'ElvenMirkwoodArcherHorde', 2100),
        ('D', 'ElvenLorienArcherHorde', 2800), ('E', 'DwarvenAxeThrowerHorde', 3500), ('F', 'MordorArcherHorde', 4200),
        ('G', 'GoblinArcherHorde', 4900), ('H', 'IsengardUrukCrossbowHorde', 5600), ('I', 'AngmarDarkRangerHorde', 6300),
        ('J', 'RohanArcherHorde', 7000)]
OWNER = 'Player_1/teamPlayer_1'
# A ruler to read positions off a straight-down screenshot: a small torch every 50 from x 700 to 1000, RULER_OFF north of each row's point
MARKER, RULER, RULER_OFF = 'GenericTorch2', (700, 1000, 50), 110


def text(kind, value):
    return arg(kind, text=value)


def build(b):
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    set_heights(m, np.full((HEIGHT + 2 * BORDER, WIDTH + 2 * BORDER), GROUND))
    set_materials(m, PALETTE, np.zeros((HEIGHT + 2 * BORDER, WIDTH + 2 * BORDER), 'u2'),
                  cell_sizes=terrain_cell_sizes(PALETTE))
    starts(m, [(150, 150), (1350, 7450)])
    w = Writer(m)
    orders = [w.operation('action', 'MAP_REVEAL_ALL_PERM', [text(11, 'Player_1')])]
    for i, (row, template, y) in enumerate(ROWS):
        point = f'HS_{row}'
        add_object(m, '*Waypoints/Waypoint', GOAL_X, y, layer='Lab', extra=[
            ('originalOwner', 3, '/team'), ('uniqueID', 3, point), ('waypointID', 1, 3 + i),
            ('waypointName', 3, point), ('waypointTypeOption', 3, '')])
        for k, dy in ((1, -APART / 2), (2, APART / 2)):
            name = f'HS_{row}{k}'
            add_object(m, template, START, y + dy, angle=0, layer='Lab',
                       extra=[('originalOwner', 3, OWNER), ('objectName', 3, name)])
            orders.append(w.operation('action', 'MOVE_NAMED_UNIT_TO', [text(14, name), text(7, point)]))
        for x in range(RULER[0], RULER[1] + 1, RULER[2]):   # the ruler: a torch every 50 along x, beside the pair's point
            add_object(m, MARKER, x, y + RULER_OFF, layer='Ruler')
    w.install([w.script('HS_Orders', [[w.operation('condition', 'CONDITION_TRUE')]], orders)], side_index=2)
    add_sky(m, b.project.weather, WIDTH * 10, HEIGHT * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather))
