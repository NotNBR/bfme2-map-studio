"""TerrainData(m): a map's terrain heights, formats.terrain.Heights.of(m).

What is left of the studio renderer's terrain: maps/helms_deep_battle/map.py
imports it. New code uses formats.terrain.Heights.
"""

from mapworkshop.formats.terrain import Heights


def TerrainData(m):
    return Heights.of(m)
