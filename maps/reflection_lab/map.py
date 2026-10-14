"""Reflection Lab: how do water reflections look in the game, and in our renderer?

A still lake fills the middle of the map, 1400 x 700 (x 500..1900, y 500..1200),
with ReflectionOn = Yes and the reflection plane at the water's height. At
WaterLOD High the lake's model (wtr_Riv03, BumpSpecular) takes 80% of its
colour from the reflection texture (docs/rendering.md).

What there is to reflect, all seen across the water by the game's camera,
which looks north:

  north-west shore: a grassy hill 250 high centred at (450, 1450)
  north shore, y 1260, west to east:
    x  800  DolGulTower, a dark spire 196 high
    x 1000  GBGHGenTowA, a pale stone tower 129 high
    x 1200  RivRTower, 118 high, its stair facing the lake
    x 1320..1460  a row of TreeEvergreen03c and TreeDiospyros2 (the tree buffer)
    x 1600  Erebortower, 131 high, KindOf CAN_CAST_REFLECTIONS
    x 1740  RockGrey15 at the water's edge, CAN_CAST_REFLECTIONS
    x 1790..1890  24 OptBushLG06, 12 high, at the water's edge (the shrub buffer)
  everywhere: the clear preset's sky dome (CAN_CAST_REFLECTIONS)

Shots (`mw capture reflection-lab --graphics High`), the camera looking at
these points from 300 (cameraMaxHeight; higher is clamped to it):
  hill    650, 1050  the hill's reflection
  towers 1000, 1050  the towers'
  trees  1350, 1050  the trees'
  kinds  1700, 1050  Erebortower's, the rock's and the bushes'

Game screenshots (High, 15 October 2026): the sky dome, the trees, Erebortower
and the rock reflect; the other towers, the hill and the bushes do not. The
renderer's reflection pass draws the same (docs/rendering.md).
"""
import numpy as np

from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes, water_plane
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

SIZE, BORDER = 240, 30           # cells; the map is 2400 x 2400 units
GROUND, BED, WATER = 150.0, 100.0, 140.0
LAKE = (500, 500, 1900, 1200)    # x0, y0, x1, y1 of the water's edge
CORNER = 150                     # the lake's corner radius
BANK = 60                        # the shore slopes down to the bed over this
HILL = (450, 1450, 250, 300)     # x, y, height, radius
PALETTE = ['GrassMediumType40', 'IthilienDirt07']
OBJECTS = [('DolGulTower', 800, 1260), ('GBGHGenTowA', 1000, 1260), ('RivRTower', 1200, 1260),
           ('TreeEvergreen03c', 1320, 1250), ('TreeDiospyros2', 1370, 1270), ('TreeEvergreen03c', 1420, 1245),
           ('TreeDiospyros2', 1460, 1265), ('Erebortower', 1600, 1270), ('RockGrey15', 1740, 1225)]
OBJECTS += [('OptBushLG06', 1790 + 13 * i + 6 * (j % 2), 1210 + 10 * j) for i in range(8) for j in range(3)]


def lake_inside(x, y):
    """How far inside the lake's rounded rectangle each point lies (negative outside)."""
    x0, y0, x1, y1 = LAKE
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    qx = np.abs(x - cx) - ((x1 - x0) / 2 - CORNER)
    qy = np.abs(y - cy) - ((y1 - y0) / 2 - CORNER)
    outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0)
    return CORNER - outside


def build(b):
    m = create(SIZE, SIZE, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    rows = cols = SIZE + 2 * BORDER
    y, x = (np.mgrid[0:rows, 0:cols] - BORDER) * 10.0
    # The lake: the ground meets the water at its edge, then slopes to a flat bed.
    inside = lake_inside(x, y)
    depth = np.clip(inside / BANK, 0, 1)
    z = GROUND - (GROUND - WATER) * np.clip(inside / 10 + 1, 0, 1) - (WATER - BED) * depth
    hx, hy, hh, hr = HILL
    z = z + hh * np.clip(1 - np.hypot(x - hx, y - hy) / hr, 0, 1) ** 2 * (inside < 0)
    set_heights(m, z)
    labels = (inside > -10).astype('u2')
    set_materials(m, PALETTE, labels, blocked=z < WATER - 5, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    water_plane(m, 'Reflection lake', WATER)
    # Angle 0 (local +y north) turns the Rivendell tower's front, its stair on
    # local -y, south: towards the lake and the camera.
    for template, ox, oy in OBJECTS:
        add_object(m, template, ox, oy, 0.0, layer='Reflected')
    starts(m, [(250, 250), (2150, 250)])
    add_sky(m, b.project.weather, SIZE * 10, SIZE * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    ini = ini_block(b.project.weather) + f'WaterTransparency\n  ReflectionPlaneZ = {WATER:g}\n  ReflectionOn = Yes\nEnd\n'
    b.save(m, ini=ini)
