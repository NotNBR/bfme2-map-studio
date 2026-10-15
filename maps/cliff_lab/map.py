"""Cliff Lab: how does BFME2 draw cliff-mapped terrain (mapkit.cliffs)?

Steep faces in a brick texture (HelmsDeepBrick04), whose courses show the
texture's orientation, scale and every seam, on grass. The game's camera
looks north, so every panel turns a face south, towards it:

  plain   400, 1500  a straight wall 300 high, rising 3 per unit run: not mapped
  mapped 1200, 1500  the same wall, cliff-mapped
  hill   2000, 1500  a round hill 300 high, cliff-mapped: its facing turns
                     through every direction
  rough  1200,  600  a wall with the noise of a real mountain face, cliff-mapped

Shots: `mw capture cliff-lab --shot NAME X Y 400` at each panel's foot
(y 1250 for the top row, 350 for the rough wall).
"""
import math

import numpy as np

from mapworkshop.mapkit.blank import create, set_heights, set_materials, starts, terrain_cell_sizes
from mapworkshop.mapkit.cliffs import steep_cells
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

SIZE, BORDER = 240, 30           # cells; the map is 2400 x 2400 units
GROUND, HEIGHT = 150.0, 300.0
PALETTE = ['GrassMediumType40', 'HelmsDeepBrick04']


def block(x, y, x0, x1, y0, y1, rise=3.0):
    """A plateau HEIGHT high over x0..x1, y0..y1, its faces rising `rise` per unit run."""
    inside = np.minimum(np.minimum(x-x0, x1-x), np.minimum(y-y0, y1-y))
    return HEIGHT*np.clip(inside*rise/HEIGHT, 0, 1)


def build(b):
    m = create(SIZE, SIZE, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    rows = cols = SIZE+2*BORDER
    y, x = (np.mgrid[0:rows, 0:cols]-BORDER)*10.0
    plain = block(x, y, 200, 600, 1350, 1850)
    mapped = block(x, y, 1000, 1400, 1350, 1850)
    hill = HEIGHT*np.clip((260-np.hypot(x-2000, y-1650))*3/HEIGHT, 0, 1)
    rough = block(x+40*fbm(x, y, scale=120, seed=7, octaves=3), y+50*fbm(x+500, y, scale=150, seed=8, octaves=3),
                  800, 1600, 450, 900)
    rough *= 1+.15*fbm(x, y, scale=90, seed=9, octaves=3)
    z = GROUND+np.maximum.reduce([plain, mapped, hill, rough])
    set_heights(m, z)
    steep = steep_cells(z, 1.0)
    labels = steep.astype('u2')
    cliffs = steep & (x > 700)            # everything but the plain wall
    set_materials(m, PALETTE, labels, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True, cliffs=cliffs)
    starts(m, [(250, 250), (2150, 250)])
    add_sky(m, b.project.weather, SIZE*10, SIZE*10, BORDER*10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather))
