"""Shadow Lab: a fixed Studio map for comparing object shadows.

An 1800 x 1800 test ground under fixed, neutral, raking sunlight.
Pale dirt keeps silhouettes readable; the northern foliage strip is grass.
No lab-specific controls, custom assets, automatic camera or moving scripts.

South to north:
  y  330: friendly infantry, archers and Aragorn for animation/movement tests.
  y  650: three Gondor barracks at x 450, 900 and 1350, rotated 0/90/180 degrees.
  y 1050: an isolated tower at x 400; two at x 800/900 for overlapping shadows;
          a rock on a gentle mound at x 1400 for sloped reception.
  y 1450: spaced broad-leaf trees, a denser pair, and a ground-level rock.
Starts are in the two southern corners; placed units/buildings belong to Player_1.
The map is revealed at startup. Nothing orders the units to move.

Open with `mw view shadow-lab`. Useful render targets are buildings (900,650),
towers (800,1050), slope (1400,1050), and foliage (900,1450).
The map does not change Studio's engine pin: visible shadows depend on the
runtime's shadow support. Infantry and foliage exercise ordinary decal-type
objects as well as buildings' volume types.
"""
import math

import numpy as np

from mapworkshop.formats.lighting import decode as decode_lighting, encode as encode_lighting
from mapworkshop.mapkit.blank import (
    add_object, create, set_heights, set_materials, starts, terrain_cell_sizes,
)
from mapworkshop.mapkit.script_writer import Writer, arg
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

SIZE, BORDER = 180, 30
GROUND = 150.0
PALETTE = ['DirtRhun02', 'GrassMediumType40']
PLAYER = ('originalOwner', 3, 'Player_1/teamPlayer_1')


def build(b):
    m = create(SIZE, SIZE, BORDER, title=b.project.title,
               description=b.project.description, player_count=b.project.players)
    shape = (SIZE + 2 * BORDER, SIZE + 2 * BORDER)
    y, x = (np.mgrid[:shape[0], :shape[1]] - BORDER) * 10.0
    # A smooth 60-unit mound with a 220-unit radius: no impassable cliff rim.
    rise = np.clip(1.0 - np.hypot(x - 1400, y - 1050) / 220, 0, 1)
    z = GROUND + 60.0 * rise * rise * (3.0 - 2.0 * rise)
    set_heights(m, z)
    labels = (y >= 1280).astype('u2')
    set_materials(m, PALETTE, labels, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    starts(m, [(180, 180), (1620, 180)])

    # Four-view inspection: at angle 0 the barracks' plain tower walls face
    # south/west, its entrance courtyard north/east. The rotation series is
    # intentional: it compares the same caster from three orientations.
    for ox, angle in [(450, 0.0), (900, math.pi / 2), (1350, math.pi)]:
        add_object(m, 'GondorBarracks', ox, 650, angle=angle,
                   layer='Buildings - rotation series', extra=[PLAYER])
    # The tower has stairs on all four sides; retain its model orientation.
    for ox in (400, 800, 900):
        add_object(m, 'GBGHGenTowA', ox, 1050, layer='Towers - isolated and overlapping')
    add_object(m, 'RockGrey15', 1400, 1050, layer='Slope receiver')
    for template, ox, oy in [
        ('TreeEvergreen03c', 350, 1450), ('TreeDiospyros2', 600, 1450),
        ('TreeEvergreen03c', 900, 1440), ('TreeDiospyros2', 940, 1470),
        ('TreeDiospyros2', 1150, 1450), ('RockGrey15', 1450, 1450),
    ]:
        add_object(m, template, ox, oy, layer='Foliage and low silhouettes')
    for template, ox in [('GondorFighterHorde', 550), ('GondorArcherHorde', 900), ('GondorAragorn', 1200)]:
        add_object(m, template, ox, 330, layer='Animated units', extra=[PLAYER])

    writer = Writer(m)
    reveal = writer.operation('action', 'MAP_REVEAL_ALL_PERM', [arg(11, text='Player_1')])
    writer.install([writer.script('ShadowLab_Reveal',
                    [[writer.operation('condition', 'CONDITION_TRUE')]], [reveal])], side_index=2)
    add_sky(m, b.project.weather, SIZE * 10, SIZE * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    # Neutral studio lighting, shared by terrain and objects: a readable lit
    # ground and a fixed half-intensity shadow, with no weather animation.
    chunk = m.chunk('GlobalLighting')
    lighting = decode_lighting(chunk.data, chunk.version)
    for configuration in lighting['configurations']:
        for light in configuration:
            main = light['light_index'] == 0
            light['ambient'] = (0.4,) * 3 if main else (0.0,) * 3
            light['diffuse'] = (0.8,) * 3 if main else (0.03,) * 3
    lighting['shadow_color_raw'] = 0xFF808080
    chunk.data = encode_lighting(lighting, chunk.version)
    b.report['shadow_lab'] = dict(buildings=[450, 900, 1350], towers=[400, 800, 900],
                                 slope=[1400, 1050], ground=GROUND, maximum_height=float(z.max()))
    b.save(m, ini=ini_block(b.project.weather))
