"""Distance from every terrain sample to authored lines: roads, lanes, rivers, ridges.

    from mapworkshop.mapkit.lines import polyline_distance, nearest
    d, along = polyline_distance(river, x, y)            # exact everywhere
    lanes = nearest(lane_lines, x, y, reach=500)        # exact within 500, inf beyond

Each segment is measured against every sample, so a long smoothed line over a
large map is slow: Hollin Dales' 1,346 lane segments took 45 s. With `reach`,
each segment is measured only against the samples within `reach` of it,
which gives exactly the same values there (0.2 s for the same lanes); use it
for fields that are only compared against distances below `reach`.
"""
import math

import numpy as np


def _grid(x, y):
    """(x0, y0, step) when x and y are a regular 2-D grid, x along the rows; else None."""
    if np.ndim(x) != 2 or np.shape(x) != np.shape(y) or min(np.shape(x)) < 2:
        return None
    step = float(x[0, 1]-x[0, 0])
    if step <= 0 or float(y[1, 0]-y[0, 0]) != step or float(x[1, 0]) != float(x[0, 0]) or float(y[0, 1]) != float(y[0, 0]):
        return None
    h, w = x.shape
    if float(x[-1, -1]) != float(x[0, 0])+(w-1)*step or float(y[-1, -1]) != float(y[0, 0])+(h-1)*step:
        return None
    return float(x[0, 0]), float(y[0, 0]), step


def polyline_distance(points, x, y, reach=None):
    """Distance from every sample (x, y) to the polyline, and the arc length
    along it of its nearest point. Zero-length segments are skipped.

    With `reach` (x and y a regular grid, as terrain samples are), samples
    farther than `reach` from the line get distance inf and arc length 0;
    the others get exactly the values they would without it."""
    best = np.full(np.shape(x), np.inf); along = np.zeros(np.shape(x)); s = 0.
    grid = _grid(x, y) if reach is not None else None
    if reach is not None and grid is None:
        raise ValueError('polyline_distance with reach needs x and y on a regular grid')
    for (ax, ay), (bx, by) in zip(points, points[1:]):
        dx, dy = bx-ax, by-ay; length2 = dx*dx+dy*dy
        if length2 == 0:
            continue
        if grid is None:
            xs, ys, b, a = x, y, best, along
        else:
            x0, y0, step = grid
            c0 = max(math.floor((min(ax, bx)-reach-x0)/step), 0)
            c1 = min(math.ceil((max(ax, bx)+reach-x0)/step)+1, best.shape[1])
            r0 = max(math.floor((min(ay, by)-reach-y0)/step), 0)
            r1 = min(math.ceil((max(ay, by)+reach-y0)/step)+1, best.shape[0])
            if c0 >= c1 or r0 >= r1:
                s += math.sqrt(length2)
                continue
            xs, ys = x[r0:r1, c0:c1], y[r0:r1, c0:c1]
            b, a = best[r0:r1, c0:c1], along[r0:r1, c0:c1]
        t = np.clip(((xs-ax)*dx+(ys-ay)*dy)/length2, 0, 1)
        d = np.hypot(xs-ax-t*dx, ys-ay-t*dy)
        closer = d < b
        if grid is None:
            best = np.where(closer, d, best); along = np.where(closer, s+t*math.sqrt(length2), along)
        else:
            b[closer] = d[closer]; a[closer] = (s+t*math.sqrt(length2))[closer]
        s += math.sqrt(length2)
    if grid is not None:
        far = best > reach
        best[far] = np.inf; along[far] = 0
    return best, along


def nearest(lines, x, y, reach=None):
    """Distance from every sample to the nearest of several polylines
    (polyline_distance, with the same `reach`)."""
    d = np.full(np.shape(x), np.inf)
    for line in lines:
        d = np.minimum(d, polyline_distance(line, x, y, reach)[0])
    return d
