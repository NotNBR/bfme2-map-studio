"""Cliff texture mapping: per-cell UVs that stop steep terrain stretching its texture.

Terrain is textured straight down, so a cell whose corners differ by more
than a few units of height stretches its texture into streaks. BFME2 reads a
cliff record for such cells instead (BlendTileData's cliff plane and table;
formats.terrain): the UV of each corner in its own texture, a triangle flip
and an editor flag. WorldBuilder writes them with its cliff tool
(WHeightMapEdit::doCliffAdjustment).

What the game does with them (Open-BFME-2, WorldHeightMap::getUVForTileIndex
and 0x000AE490): a record applies to a cell only when the record's tile
belongs to the same texture as the cell's own tile; the cell then takes the
record's corner UVs and its triangle flip, and keeps no primary or three-way
blend (0x000ABD19 in getPointerToTileData). 0x000AEAA6 builds the texture
those UVs sample from the texture of the first cliff record alone, so this
module maps one texture per map.

The UVs follow the stock maps (measured over the 8 maps with cliff records,
mapping 5,700 cells): along any cell edge the UV distance is 0.155 per cell
of true surface length, flat or steep, for textures 4 tiles wide; steep edges
run along V, height going up as V goes down; UVs wrap far outside 0..1. Here
each steep cell is projected onto the vertical plane along its wall: U runs
along the wall, V up it. The wall's direction is smoothed over neighbouring
cells and taken in 45-degree steps, so long stretches of wall share one
projection and only its bends make a seam; U is at most 8 % short on a wall
between two steps, V on a slope of 1.5 about 17 %, against 180 % stretch
straight down.
"""
import math

import numpy as np

UV_PER_CELL = 0.15625           # stock UV distance per cell of surface, 4-tile textures
STEEP = 1.0                     # slope (rise over run) from which a cell is mapped by default


def steep_cells(heights, slope=STEEP):
    """Cells (height-map shape; cell (y, x) spans samples y..y+1, x..x+1) whose
    steepest edge rises more than `slope` per unit run. The last row and
    column, which have no cell, are False."""
    z = np.asarray(heights, float)
    edges = [np.abs(z[:-1, 1:]-z[:-1, :-1]), np.abs(z[1:, 1:]-z[1:, :-1]),
             np.abs(z[1:, :-1]-z[:-1, :-1]), np.abs(z[1:, 1:]-z[:-1, 1:])]
    out = np.zeros(z.shape, bool)
    out[:-1, :-1] = np.max(edges, axis=0) > slope*10
    return out


def _box(a, r):
    c = np.cumsum(np.cumsum(np.pad(a, r+1, mode='edge'), 0), 1)
    n = 2*r+1
    return (c[n:, n:]-c[:-n, n:]-c[n:, :-n]+c[:-n, :-n])[:a.shape[0], :a.shape[1]]/(n*n)


def cliff_uvs(heights, mask, cell_size=4, scale=1.0, smoothing=4, steps=4):
    """The cliff record UVs of the masked cells.

    `heights` are the height-map samples in world units (10 per cell
    across), `cell_size` the mapped texture's width in 64-pixel tiles,
    `scale` how much larger than in the stock maps the texture lies on the
    face (2: each repeat covers twice the width and height).
    Returns uv, an array (h, w, 8) of (u0, v0, u1, v1, u2, v2, u3, v3) in the
    corner order 0 (x, y), 1 (x+1, y), 2 (x+1, y+1), 3 (x, y+1), and flip
    (h, w), the triangle flip WorldBuilder gives a cliff cell: the diagonal
    through corners 1 and 3 when corners 0 and 2 differ more in height.
    Unmasked cells are zero."""
    z = np.asarray(heights, float)
    mask = np.asarray(mask, bool).copy()
    mask[-1, :] = mask[:, -1] = False
    density = UV_PER_CELL*4/cell_size/scale
    h00, h10, h11, h01 = z[:-1, :-1], z[:-1, 1:], z[1:, 1:], z[1:, :-1]
    gx = np.zeros(z.shape); gy = np.zeros(z.shape)
    gx[:-1, :-1] = (h10-h00+h11-h01)/20
    gy[:-1, :-1] = (h01-h00+h11-h10)/20
    # The wall's facing, smoothed over its neighbours so that one stretch
    # of wall keeps one projection; weighted by steepness, so the flat ground
    # beside a wall does not turn it.
    weight = np.hypot(gx, gy)
    sx, sy = _box(gx*weight, smoothing), _box(gy*weight, smoothing)
    step = math.pi/steps
    along = np.round((np.arctan2(sy, sx)+math.pi/2)/step)*step       # the wall's direction, in steps
    ca, sa = np.cos(along), np.sin(along)
    ys, xs = np.nonzero(mask)
    corners = [(0, 0), (1, 0), (1, 1), (0, 1)]                     # (dx, dy) per corner
    u = np.stack([(xs+dx)*ca[ys, xs]+(ys+dy)*sa[ys, xs] for dx, dy in corners], -1)*density
    v = np.stack([-z[ys+dy, xs+dx]/10 for dx, dy in corners], -1)*density
    # Neighbouring cells share their corners' UVs exactly, as WorldBuilder's
    # do: shifting a cell by whole repeats shows as a seam in the game.
    # Only the whole map is moved, to keep the values near zero.
    if len(ys):
        u -= np.floor(u.min()); v -= np.floor(v.min())
    uv = np.zeros(z.shape+(8,), np.float32)
    uv[ys, xs, 0::2] = u; uv[ys, xs, 1::2] = v
    flip = np.zeros(z.shape, bool)
    flip[:-1, :-1] = np.abs(h11-h00) >= np.abs(h01-h10)
    return uv, flip & mask
