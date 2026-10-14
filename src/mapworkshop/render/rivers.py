"""River strips (RiverAreas) as the game draws them.

Port of WaterRenderObjClass::drawRiverWater (game.dat 1.06 RVA 0x00100A0B,
reconstructed in Open-BFME-2's W3DWaterDrawRiverWater.cpp) and of the
RiverWater.fx effect it draws with (shaders.RIVER_VS/RIVER_FS):

- The river's points run round its outline: the first cross-section's two
  ends, then along one bank to the last cross-section and back along the
  other. Each cross-section becomes a vertex pair at the river's water height.
  Which stored end of a cross-section starts the outline is not known (its
  builder, 0x00082D6A, is not reconstructed); the first end is taken here.
- UVs: u1 (river and sparkle textures) runs 0 to 0.5 across, u2 (alpha
  edge) 0 to 1. v advances `v_scale` per cross-section, however far apart
  they are: the outline's length less its closing edge, halved, less the
  first cross-section's width, in first-section widths, shared out over the
  quads. So one repeat is about as long as the first cross-section is wide.
- The texture scrolls by VOrigin, which grows by the river's UV speed every
  second, so it moves from the first cross-section towards the last; v also
  wobbles by sin(2 pi v - 3 VOrigin) / 22 (in the vertex shader here).
- Vertex colour: a white river (every stock one) takes the terrain's ambient
  plus each terrain light's diffuse times its downward component, times the
  time of day's WaterSet DiffuseColor (water.ini), whose alpha is the vertex
  alpha. Any other colour is used as it is, black as white.
- A river is skipped when its minimum LOD is above the game's WaterLOD.
"""
import math

import numpy as np

from mapworkshop.render.water import WATER_LODS

TIMES_OF_DAY = ('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT')    # GlobalLighting time_of_day 1-4


def mesh(cross_sections, water_height):
    """(vertices[n, 6] = x, y, z, u1, u2, v; triangle indices[m, 3]) for a
    river, or None when it has fewer than two cross-sections. v is before the
    scroll and wobble, which depend on time."""
    cs = np.asarray(cross_sections, float).reshape(-1, 4)
    if len(cs) < 2:
        return None
    first, second = cs[:, :2], cs[:, 2:]
    outline = np.concatenate([first[:1], second, first[:0:-1]])
    end = float(np.hypot(*(outline[1]-outline[0])))
    total = float(np.hypot(*np.diff(outline, axis=0).T).sum())    # without the closing edge
    quads = len(cs)-1
    v_scale = ((total/2-end)/end)/quads if end > 0 else 0.0
    vertices = np.zeros((2*len(cs), 6), np.float32)
    vertices[0::2, :2], vertices[1::2, :2] = second, first
    vertices[:, 2] = float(water_height)
    vertices[0::2, 3], vertices[0::2, 4] = 0.5, 1.0                # the second bank: u1 0.5, u2 1
    vertices[0::2, 5] = vertices[1::2, 5] = v_scale*np.arange(len(cs))
    i = np.arange(quads)*2
    triangles = np.concatenate([np.column_stack([i, i+1, i+3]), np.column_stack([i, i+3, i+2])]).astype(np.uint32)
    return vertices, triangles


def drawn(min_lod, water_level):
    """Whether the game draws a river with this minimum LOD name at a WaterLOD
    (0-3); an empty or unknown name counts as Low."""
    name = (min_lod or '').strip().lower()
    return (WATER_LODS.index(name) if name in WATER_LODS else 0) <= water_level


def water_diffuse(ini_texts, time_of_day):
    """The WaterSet DiffuseColor for a time of day (1-4) as RGBA 0-1, the last
    of the given INI texts that sets it winning; mid grey if none does."""
    import re
    name = TIMES_OF_DAY[max(0, min(3, time_of_day-1))]
    colour = (175, 175, 175, 255)
    for text in ini_texts:
        block = re.search(rf'(?ims)^\s*WaterSet\s+{name}\b(.*?)^\s*End\b', text or '')
        found = block and re.search(r'(?im)^\s*DiffuseColor\s*=\s*(.*)$', block.group(1))
        if found:
            parts = dict(re.findall(r'([RGBA])\s*:\s*(\d+)', found.group(1).upper()))
            colour = tuple(int(parts.get(k, 255 if k == 'A' else 0)) for k in 'RGBA')
    return tuple(c/255 for c in colour)


def vertex_colour(color_bytes, terrain_ambient, terrain_lights, water):
    """The colour every vertex of a river gets (RGBA 0-1). `terrain_lights`
    are (direction as stored, diffuse) of the terrain's global lights, `water`
    the WaterSet diffuse. Stock WaterSets are grey, so their channel order
    (the game reads the low byte as red) does not matter."""
    rgb = [c/255 for c in color_bytes[:3]]
    if rgb == [1.0, 1.0, 1.0]:
        rgb = list(terrain_ambient)
        for direction, diffuse in terrain_lights:
            down = -float(direction[2])
            if down > 0:
                rgb = [c+down*d for c, d in zip(rgb, diffuse)]
        rgb = [c*w for c, w in zip(rgb, water[:3])]
    elif rgb == [0.0, 0.0, 0.0]:
        rgb = [1.0, 1.0, 1.0]
    # The game packs these into colour bytes without clamping; past 255 a
    # channel would spill into the next, which the stock lighting never reaches.
    return tuple(min(max(c, 0.0), 1.0) for c in rgb) + (float(water[3]),)


def wobble(v, origin):
    """v after the scroll and wobble at a VOrigin (what RIVER_VS computes)."""
    return v+math.sin(2*math.pi*v-3*origin)/22-origin
