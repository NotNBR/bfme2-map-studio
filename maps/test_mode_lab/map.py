"""Test Mode Lab: two small armies to select and order in the viewer's Test mode.

A flat, open map, 1600 x 1600. Your army (Player_1, Men) stands in the south
facing north, Mordor's (Player_2) in the north facing south, 800 apart. Between
them a small wood on the west side and a few large rocks on the east, so a move
order has something to walk around. No script moves anyone: the orders come
from whoever tests (the viewer's Test mode, or a game: `mw play`); the map is
revealed to Player_1 at the start.

  south, y 400 (Player_1):  GondorFighterHorde x 2, GondorArcherHorde, RohanRohirrimHorde, GondorAragorn
  north, y 1200 (Player_2): MordorFighterHorde x 2, MordorArcherHorde, MordorMountainTroll

    mw build test-mode-lab
    mw view test-mode-lab
"""
import math

import numpy as np

from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.script_writer import Writer, arg
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

WIDTH = HEIGHT = 160                     # cells; the map is 1600 x 1600 units
BORDER = 30
GROUND = 100.0
PALETTE = ['GrassMediumType40']
# (template, x, y) per side; each side faces the other
ARMIES = {
    1: (math.pi/2, [('GondorFighterHorde', 600, 400), ('GondorFighterHorde', 1000, 400), ('GondorArcherHorde', 800, 300),
                    ('RohanRohirrimHorde', 1250, 350), ('GondorAragorn', 800, 420)]),
    2: (-math.pi/2, [('MordorFighterHorde', 600, 1200), ('MordorFighterHorde', 1000, 1200), ('MordorArcherHorde', 800, 1300),
                     ('MordorMountainTroll', 1200, 1180)]),
}
WOOD, TREE = (450, 800, 110), 'TreeHopea'     # a wood: centre x, y and radius
ROCKS, ROCK = [(1050, 760), (1130, 840), (1200, 770)], 'DarkRockGrey07'


def owner(n):
    return ('originalOwner', 3, f'Player_{n}/teamPlayer_{n}')


def build(b):
    m = create(WIDTH, HEIGHT, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    size = (HEIGHT + 2 * BORDER, WIDTH + 2 * BORDER)
    set_heights(m, np.full(size, GROUND))
    set_materials(m, PALETTE, np.zeros(size, 'u2'), cell_sizes=terrain_cell_sizes(PALETTE))
    starts(m, [(150, 150), (1450, 1450)])
    for player, (angle, units) in ARMIES.items():
        for template, x, y in units:
            add_object(m, template, x, y, angle=angle, layer='Armies', extra=[owner(player)])
    rng = np.random.default_rng(7)
    cx, cy, r = WOOD
    for _ in range(14):
        a, d = rng.uniform(0, 2 * math.pi), r * math.sqrt(rng.uniform())
        add_object(m, TREE, cx + d * math.cos(a), cy + d * math.sin(a), angle=float(rng.uniform(0, 2 * math.pi)),
                   layer='Wood')
    for x, y in ROCKS:
        add_object(m, ROCK, x, y, angle=float(rng.uniform(0, 2 * math.pi)), layer='Rocks')
    w = Writer(m)
    reveal = w.operation('action', 'MAP_REVEAL_ALL_PERM', [arg(11, text='Player_1')])
    w.install([w.script('TM_Reveal', [[w.operation('condition', 'CONDITION_TRUE')]], [reveal])], side_index=2)
    add_sky(m, b.project.weather, WIDTH * 10, HEIGHT * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather))
