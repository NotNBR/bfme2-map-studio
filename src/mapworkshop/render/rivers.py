"""River strips (RiverAreas) as meshes: one quad strip per river at its water height.

Each cross-section gives the strip's two bank points; u runs across the strip
(0 at the first point, 1 at the second), v along it in strip widths from the
first cross-section, so the textures stay square and scroll downstream. The
game's own river shader is not matched yet: the renderer draws the texture
scrolled at the river's UV speed, the sparkle texture modulated by the noise
texture over it, faded across by the alpha-edge texture, additively when the
river is additive (shaders.RIVER_FS).
"""
import numpy as np


def mesh(cross_sections, water_height):
    """(vertices[n, 5] = x, y, z, u, v; triangle indices[m, 3]) for a river, or
    None when it has fewer than two cross-sections."""
    cs = np.asarray(cross_sections, float).reshape(-1, 4)
    if len(cs) < 2:
        return None
    left, right = cs[:, :2], cs[:, 2:]
    widths = np.hypot(*(right-left).T)
    width = max(float(widths.mean()), 1.0)
    middle = (left+right)/2
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(middle, axis=0).T))])/width
    n = len(cs)
    vertices = np.zeros((2*n, 5), np.float32)
    vertices[0::2, :2], vertices[1::2, :2] = left, right
    vertices[:, 2] = float(water_height)
    vertices[0::2, 3], vertices[1::2, 3] = 0.0, 1.0
    vertices[0::2, 4] = vertices[1::2, 4] = along
    i = np.arange(n-1)*2
    triangles = np.concatenate([np.column_stack([i, i+1, i+2]), np.column_stack([i+1, i+3, i+2])]).astype(np.uint32)
    return vertices, triangles


def colour(color_bytes):
    """The river's tint from its four colour bytes (the first three; the
    fourth is 0 in every stock river)."""
    return tuple(c/255 for c in color_bytes[:3])
