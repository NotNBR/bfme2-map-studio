"""Shared placement rules for Glacial Crossroads' scenery.

Every footprint keeps at least 70 units clear of the protected ground
(construction pads, route cores, the ice field, capture shelves and the
fighting hollows), sits wholly on one side of the terrain's movement edge and
keeps its distance from earlier objects. Each object takes stable random
numbers from its own position, so editing one cluster leaves the rest alone.
"""
from collections import Counter, defaultdict
import math
import numpy as np

from mapworkshop.mapkit.blank import add_object
from mapworkshop.mapkit.relief import distance_to
from mapworkshop.mapkit.variety import spot_random
from .design import BORDER, EXTENT

MARGIN = 70.  # Clearance beyond every protected footprint.


class Placer:
    """Placement checks and counts shared by the scenery modules."""

    def __init__(self, m, t):
        self.m, self.t = m, t
        self.protected = (t['pads'] | t['route_core'] | t['ice'] | t['checkpoints']
                          | t['tower_hollows'])
        self.clearance = distance_to(self.protected)*10
        self.open_clearance = distance_to(t['blocked'])*10
        self.closed_clearance = distance_to(~t['blocked'])*10
        self.counts, self.layers = Counter(), Counter()
        self.occupied = defaultdict(list)
        self.trees = self.shrubs = 0
        self.minimum_margin = math.inf

    @staticmethod
    def at(x, y):
        return round(y/10)+BORDER, round(x/10)+BORDER

    def free(self, x, y, radius, max_slope=.25, max_rise=None, spacing=None, margin=MARGIN):
        if not (300 < x < EXTENT-300 and 300 < y < EXTENT-300):
            return False
        r, c = self.at(x, y)
        if self.clearance[r, c] < radius+margin or self.t['slope'][r, c] > max_slope:
            return False
        # A footprint must sit entirely on one side of the terrain's
        # movement edge, avoiding tiny enclosed pockets behind a rock.
        if max(self.open_clearance[r, c]-30, self.closed_clearance[r, c]) < radius+20:
            return False
        if max_rise is not None:
            n = math.ceil(radius/10)
            if np.ptp(self.t['z'][r-n:r+n+1, c-n:c+n+1]) > max_rise:
                return False
        key = (int(x//250), int(y//250))
        separation = radius if spacing is None else spacing
        for ky in range(key[1]-1, key[1]+2):
            for kx in range(key[0]-1, key[0]+2):
                if any((x-a)**2+(y-b)**2 < (separation+size+5)**2
                       for a, b, size in self.occupied[kx, ky]):
                    return False
        return True

    def paint(self, x, y, radius, material, stretch=1., angle=0.):
        """An irregular patch of `material`, never on protected ground."""
        r, c = self.at(x, y)
        n = math.ceil(radius*max(1, stretch)/10)+2
        sy, sx = slice(r-n, r+n+1), slice(c-n, c+n+1)
        yy, xx = np.mgrid[-n:n+1, -n:n+1]*10.
        along = xx*math.cos(angle)+yy*math.sin(angle)
        across = -xx*math.sin(angle)+yy*math.cos(angle)
        contour = radius*(1+.22*np.sin((xx+x)/65+(yy+y)/110)+.13*np.cos((yy+y)/43))
        mask = (np.hypot(along/stretch, across) < contour) & ~self.protected[sy, sx]
        self.t['materials'][sy, sx][mask] = material

    def place(self, template, x, y, layer, radius, angle=None, max_slope=.25,
              max_rise=None, sink=0., spacing=None, scale=1., kind=None,
              margin=MARGIN, extra=()):
        """Place one object if its footprint is free; `kind` counts trees/shrubs."""
        if not self.free(x, y, radius, max_slope, max_rise, spacing, margin):
            return False
        rng = spot_random(8612, template, x, y)
        properties = list(extra)
        if abs(scale-1) > 1e-6:
            properties.append(('objectPrototypeScale', 2, round(scale, 3)))
        add_object(self.m, template, x, y, z=-sink,
                   angle=rng.random()*math.tau if angle is None else angle,
                   layer=layer, extra=properties)
        self.occupied[int(x//250), int(y//250)].append(
            (x, y, radius if spacing is None else spacing))
        self.counts[template] += 1
        self.layers[layer] += 1
        if kind == 'tree':
            self.trees += 1
        elif kind == 'shrub':
            self.shrubs += 1
        if margin >= MARGIN:
            # Flat props allowed onto protected ground do not count here.
            r, c = self.at(x, y)
            self.minimum_margin = min(self.minimum_margin, self.clearance[r, c]-radius)
        return True

    def reserve(self, x, y, radius):
        """Keep later objects off a painted feature, such as a frozen tarn."""
        self.occupied[int(x//250), int(y//250)].append((x, y, radius))

    def find_site(self, px, py, radius, reach=650, max_height=2100, max_slope=.12, max_rise=9):
        """The nearest free, level spot within `reach` of (px, py)."""
        candidates = []
        offsets = sorted(set(range(-reach, reach+1, 40)) | {0})
        for dy in offsets:
            for dx in offsets:
                if dx*dx+dy*dy > reach*reach:
                    continue
                x, y = px+dx, py+dy
                r, c = self.at(x, y)
                if (300 < x < EXTENT-300 and 300 < y < EXTENT-300
                        and self.t['z'][r, c] < max_height
                        and self.free(x, y, radius, max_slope, max_rise)):
                    candidates.append((dx*dx+dy*dy, x, y))
        return min(candidates)[1:] if candidates else None
