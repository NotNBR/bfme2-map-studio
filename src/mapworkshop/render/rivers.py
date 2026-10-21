"""River strips (RiverAreas) as the game builds them.

Port of the strip WaterRenderObjClass::drawRiverWater draws (game.dat 1.06 RVA
0x00100A0B, reconstructed in Open-BFME-2's W3DWaterDrawRiverWater.cpp), as
OpenBFME builds it too (WaterGeometry::buildRiverStrip, Open-BFME/openbfme-godot#79);
the viewer's flow arrows lie on it (render.godot.flow_strips).

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
"""
import numpy as np

from mapworkshop.mapkit.checks.analyze import records


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


def strips(m):
    """The map's RiverAreas records with their meshes, [(area, mesh)], every one
    as OpenBFME draws them."""
    try:
        areas = records(m, 'RiverAreas')
    except ValueError:
        return []
    out = []
    for area in areas:
        strip = mesh(area['cross_sections'], area['water_height'])
        if strip is not None:
            out.append((area, strip))
    return out
