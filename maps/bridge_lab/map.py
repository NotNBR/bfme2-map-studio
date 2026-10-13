"""Bridge Lab: do BFME2 bridges spanned between two endpoints still work?

The engine family draws a `Bridge` from roads.ini between two map objects
flagged 0x10 and 0x20 (W3DBridgeBuffer::loadBridges): a sectional model
(BRIDGE_LEFT / BRIDGE_SPAN / BRIDGE_RIGHT sub-objects) repeats its span and
is scaled along its axis to end exactly at the second point; a model without
sections is stretched in one piece. No retail BFME2 map uses one.

A river runs north to south through the middle; player 1 starts west of it,
player 2 east. Crossings, south to north (x 1300..1700 unless noted):

  y  600  TEST_EuropeanBridgeWide (roads.ini), 400 long
  y 1100  TEST_EuropeanBridgeWide, 700 long (x 1150..1850): more spans
  y 1600  TEST_NewBridgeWide (roads.ini), 400 long
  y 2100  LAB_ArcBridge, defined in this map's map.ini (the arc model at
          BridgeScale 1.0), 400 long: a map can define its own bridge type
  y 2600  GenericTreeBridge as an ordinary object, for comparison

Native results (bfme-workshop screenshots, 13 October 2026): 1, 2 and 4 span
bank to bank, 2 over its full 700. 3 is an arched stone bridge whose deck lies
about 40 below the walkable line, so it looks sunken in the river. A model
without BRIDGE_LEFT/SPAN/RIGHT sections (the tree bridge's NBTreeBrdge) crashes
the game while loading (access violation in W3DBridge::load), so only sectional
models can be endpoint bridges. Units cross them on the deck (bfme-workshop
navigation lab, endpoint-bridges-001; see mapkit.bridges).
"""
import numpy as np

from mapworkshop.mapkit.bridges import add_bridge, bridge_type
from mapworkshop.mapkit.blank import add_object, create, set_heights, set_materials, starts, terrain_cell_sizes, water_plane
from mapworkshop.mapkit.weather import add_sky, apply_weather, ini_block

SIZE, BORDER = 300, 30           # cells; the map is 3000 x 3000 units
GROUND, BED, WATER = 150.0, 122.0, 140.0
RIVER = (1350, 1650)             # banks, x
CROSSINGS = [('TEST_EuropeanBridgeWide', 1300, 1700, 600), ('TEST_EuropeanBridgeWide', 1150, 1850, 1100),
             ('TEST_NewBridgeWide', 1300, 1700, 1600), ('LAB_ArcBridge', 1300, 1700, 2100)]
PALETTE = ['GrassMediumType40', 'IthilienDirt07']

# A map-local bridge type. Its model must have BRIDGE_LEFT/SPAN/RIGHT sections:
# a one-piece model (e.g. NBTreeBrdge) crashes the game while loading.
MAP_INI = chr(10) + bridge_type('LAB_ArcBridge', 'CBWBrdgeArc', scale=1.0)


def build(b):
    m = create(SIZE, SIZE, BORDER, title=b.project.title, description=b.project.description,
               player_count=b.project.players)
    rows = cols = SIZE + 2 * BORDER
    y, x = (np.mgrid[0:rows, 0:cols] - BORDER) * 10.0
    # The river: a flat bed with banks sloping up over 60 units on each side.
    inside = np.clip(np.minimum(x - RIVER[0], RIVER[1] - x) / 60, 0, 1)
    z = GROUND - (GROUND - BED) * inside
    set_heights(m, z)
    labels = (inside > 0).astype('u2')
    set_materials(m, PALETTE, labels, blocked=z < WATER - 5, cell_sizes=terrain_cell_sizes(PALETTE), corner_blends=True)
    water_plane(m, 'Lab river', WATER)
    for i, (template, x0, x1, row) in enumerate(CROSSINGS, 1):
        add_bridge(m, template, (x0, row), (x1, row), name=f'Lab_Bridge_{i}', map_ini=MAP_INI)
    add_object(m, 'GenericTreeBridge', 1500, 2600, np.pi / 2, layer='Bridges',
               extra=[('objectName', 3, 'Lab_Bridge_5')])
    starts(m, [(500, 1500), (2500, 1500)])
    add_sky(m, b.project.weather, SIZE * 10, SIZE * 10, BORDER * 10)
    apply_weather(m, b.project.weather)
    b.save(m, ini=ini_block(b.project.weather) + MAP_INI)
