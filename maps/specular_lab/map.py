"""Specular Lab: what does the High terrain shine like on ground textures
without a normal map, in the game and in the renderer?

terrain.fx's Default technique adds sun x N.H^1200 x B x 0.9, B the composited
normal texture's blue channel. Textures with a `_nrm` map bring their own
normals and B; for those without one the renderer assumes a flat normal with
B = 255, so flat ground there mirrors the sun over a wide patch seen from far
(docs/rendering.md). Which is the game's?

The map is flat ground at 150, west half (x < 800) GrassShire01 (no _nrm),
east half GrassOldForest04 (with one). The clear preset's sun stands in the
south-west, 33 degrees up; cameraYawAngle 130 turns the game's camera to face
it, so the sun's mirror point lies in front of the camera, near what it looks
at from height 300.

Shots (`mw capture specular-lab --graphics High`):
  plain   500, 800  the half without a normal map
  mapped 1100, 800  the half with one
"""
import numpy as np

from mapworkshop.mapkit.blank import create, set_heights, set_materials, set_world, starts, terrain_cell_sizes
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

SIZE, BORDER = 160, 30           # cells; the map is 1600 x 1600 units
GROUND = 150.0
SPLIT = 800                      # x: GrassShire01 west of it, GrassOldForest04 east
PALETTE = ['GrassShire01', 'GrassOldForest04']
YAW = 130.0                      # degrees: the camera faces the south-west sun


def build(b):
    m = create(SIZE, SIZE, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    rows = cols = SIZE + 2 * BORDER
    y, x = (np.mgrid[0:rows, 0:cols] - BORDER) * 10.0
    set_heights(m, np.full((rows, cols), GROUND))
    labels = (x >= SPLIT).astype('u2')
    set_materials(m, PALETTE, labels, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    set_world(m, cameraYawAngle=YAW)
    starts(m, [(200, 1400), (1400, 1400)])
    add_sky(m, b.project.weather, SIZE * 10, SIZE * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather))
