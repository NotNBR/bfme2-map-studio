"""Nanduhirion v1's soft changes of texture: in-between textures for every
pair of ground textures that meet.

The game blends a change of texture inside one cell, which looks hard on
patches three times the original's size. The Blend Lab
(maps/blend_lab/map.py) found that the change turns soft through bands of
in-between tone, about 40 units each, two or three for a strong contrast,
and that an in-between texture has to match the pair in pattern as well as
in colour. This module finds them for v1, from the game's own textures:

- Pairs: every two ground textures (terrain.ini Type Grass or Dirt) that
  share at least MIN_EDGE cells of edge in v1's painting and differ by GATE
  or more in colour (CIE Lab, of the texture file's mean colour).
- Steps: one band per STEP of colour difference, at most MAX_BANDS, at even
  steps from the darker texture to the brighter.
- Candidates: the grass and dirt textures of the families v1 already uses
  (a family is a name without its number: GrassErebor, DirtRhun, ...) and
  the Amon Hen grasses the Blend Lab's ladder used (EXTRA_FAMILIES). Other
  families bring patterns of their own: flowers, ploughed stripes, broad
  blotches (seen in a first try with every texture of the game). A few of
  the families' own read as spots or blotches too (EXCLUDED).
- Choice: the candidate nearest the step's colour and the pair's pattern
  there (the spread of the texture's lightness and of its fine detail, in
  units of their spread over the candidates, PATTERN_WEIGHT colour units
  each), a texture of the pair's own families counting FAMILY_BONUS nearer.
  It may be no blotchier, more speckled with colour or more striped than the
  pair is at that step, between the two (SLACK): so no flowers where the
  darker side has none. A step nothing comes within MAX_MISS of colour and
  MAX_PATTERN of pattern goes without.

soften() then turns the darker side of each such edge into the pair's
bands, BAND cells each, nearest the brighter texture first; the brighter
side, often a narrow path, stays whole. Their edges wander by about 15
units.
"""
import re
from functools import lru_cache

import numpy as np

from mapworkshop.config import GAME_DATA
from mapworkshop.mapkit.earth import fbm

MIN_EDGE = 100                  # cells of shared edge (1,000 units) before a pair gets bands
GATE = 10.0                     # colour difference (Lab) below which a change stays as it is
STEP = 10.0                     # colour difference per band
MAX_BANDS = 3
BAND = 4                        # cells: 40 units a band
MAX_MISS = 7.0                  # colour difference an in-between texture may miss its step by
MAX_PATTERN = 1.2               # pattern difference it may miss by
PATTERN_WEIGHT = 4.0            # colour units per unit of pattern difference
FAMILY_BONUS = 2.0              # colour units a texture of the pair's own families counts nearer
EXTRA_FAMILIES = ('grassamon_hen',)
# Candidates that read as spots or blotches in a band, picked out by eye from
# a sheet of the chosen textures (measures of speck and spot did not tell
# them from v1's own speckled grasses): flowers (Harlindon04, Rohan06),
# large spiky plants (Rohan02), broad grey blotches (Mordor05).
EXCLUDED = ('grassharlindon04', 'grassrohan06', 'grassrohan02', 'dirtmordor05')
# How much blotchier (coarse lightness spread), more speckled (spread of
# colourfulness) and more striped (coherence of its gradients) than the pair
# at its step an in-between texture may be.
SLACK = dict(blotch=.8, speck=1.0, streak=.08)


def lab(rgb):
    """sRGB (0-255) to CIE Lab (D65)."""
    c = np.asarray(rgb, float)/255
    linear = np.where(c <= .04045, c/12.92, ((c + .055)/1.055)**2.4)
    xyz = linear @ np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]]).T
    xyz = xyz/(.95047, 1., 1.08883)
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787*xyz + 16/116)
    return np.stack([116*f[..., 1] - 16, 500*(f[..., 0] - f[..., 1]), 200*(f[..., 1] - f[..., 2])], -1)


def family(name):
    """The texture's family: its name without the trailing number."""
    return re.sub(r'\d+\w?$', '', name).lower()


@lru_cache(maxsize=1)
def types():
    """terrain.ini's terrain textures by lower-case name: (name, Type)."""
    text = (GAME_DATA/'data/ini/terrain.ini').read_text(encoding='cp1252', errors='replace')
    return {name.lower(): (name, (re.search(r'(?i)\bType\s+(\w+)', body) or [None, ''])[1].lower())
            for name, body in re.findall(r'(?ms)^Terrain\s+(\S+)\s*\n(.*?)^End', text)}


def box(a, r):
    """`a` averaged over the (2r+1) x (2r+1) pixels around each, wrapping
    round as the texture tiles."""
    n = 2*r + 1
    c = np.pad(np.cumsum(np.cumsum(np.pad(a, r, mode='wrap'), 0), 1), ((1, 0), (1, 0)))
    return (c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n])/(n*n)


def measure(name, assets):
    """The texture's mean colour (Lab), its pattern (the spread of its
    lightness, and of its fine detail: lightness against its 5-pixel mean)
    and its marks: blotch (the spread of its lightness over 25 pixels),
    speck (the spread of its colourfulness) and streak (how much its
    gradients share one direction)."""
    rgb = np.asarray(assets.image(assets.terrain_textures[name.lower()]))[..., :3].astype(float)
    rgb = rgb[::max(1, rgb.shape[0]//256), ::max(1, rgb.shape[1]//256)]
    colour = lab(rgb)
    lightness = colour[..., 0]
    gy, gx = np.gradient(box(lightness, 1))
    xx, yy, xy = (gx*gx).mean(), (gy*gy).mean(), (gx*gy).mean()
    marks = dict(blotch=box(lightness, 12).std(), speck=np.hypot(colour[..., 1], colour[..., 2]).std(),
                 streak=np.sqrt((xx - yy)**2 + 4*xy*xy)/(xx + yy))
    return (lab(rgb.reshape(-1, 3).mean(0)),
            np.array([lightness.std(), np.abs(lightness - box(lightness, 2)).mean()]), marks)


def edges(labels, ground):
    """Cells of shared edge per pair of different ground textures (a < b)."""
    out = {}
    for a, b in ((labels[:, :-1], labels[:, 1:]), (labels[:-1], labels[1:])):
        keep = (a != b) & ground[a] & ground[b]
        lo, hi = np.minimum(a[keep], b[keep]), np.maximum(a[keep], b[keep])
        keys, counts = np.unique(lo.astype(np.int64)*4096 + hi, return_counts=True)
        for key, count in zip(keys, counts):
            out[divmod(int(key), 4096)] = out.get(divmod(int(key), 4096), 0) + int(count)
    return out


def ladders(labels, names):
    """The in-between textures for the pairs in `labels` (indices into
    `names`): (names, with the chosen textures added, and {(darker, brighter):
    [in-between indices, darker side first]})."""
    from mapworkshop.assets.library import GameAssets
    assets = GameAssets.shared()
    kinds = {n: t for n, (_, t) in types().items()}
    spelled = {n: name for n, (name, _) in types().items()}
    ground = np.array([kinds.get(n.lower()) in ('grass', 'dirt') for n in names])
    families = {family(n) for n, g in zip(names, ground) if g} | set(EXTRA_FAMILIES)
    # The grass and dirt textures of those families whose file the game has.
    pool = sorted(n for n, t in kinds.items() if t in ('grass', 'dirt') and family(n) in families
                  and n not in EXCLUDED and n in assets.terrain_textures
                  and assets.image(assets.terrain_textures[n]) is not None)
    measured = {n: measure(n, assets) for n in pool + [n.lower() for n in names if n.lower() not in pool]}
    colour = np.array([measured[n][0] for n in pool])
    pattern = np.array([measured[n][1] for n in pool])
    spread = pattern.std(0)
    marks = {key: np.array([measured[n][2][key] for n in pool]) for key in SLACK}
    names, chosen = list(names), {}
    for (a, b), length in sorted(edges(labels, ground).items()):
        if length < MIN_EDGE:
            continue
        (ca, pa, ma), (cb, pb, mb) = measured[names[a].lower()], measured[names[b].lower()]
        gap = float(np.linalg.norm(ca - cb))
        if gap < GATE:
            continue
        if ca[0] > cb[0]:                                # darker first
            a, b, ca, cb, pa, pb, ma, mb = b, a, cb, ca, pb, pa, mb, ma
        bonus = np.array([family(n) in (family(names[a]), family(names[b])) for n in pool])*FAMILY_BONUS
        count = min(MAX_BANDS, max(1, round(gap/STEP)))
        steps = []
        for k in range(1, count + 1):
            t = k/(count + 1)
            miss = np.linalg.norm(colour - (ca + t*(cb - ca)), axis=1)
            off = np.linalg.norm((pattern - (pa + t*(pb - pa)))/spread, axis=1)
            marked = np.zeros(len(pool), bool)
            for key, slack in SLACK.items():
                marked |= marks[key] > ma[key] + t*(mb[key] - ma[key]) + slack
            cost = miss + PATTERN_WEIGHT*off - bonus
            cost[(miss > MAX_MISS) | (off > MAX_PATTERN) | marked] = np.inf
            for n in (names[a].lower(), names[b].lower()):
                if n in pool:
                    cost[pool.index(n)] = np.inf
            if np.isfinite(cost.min()):
                best = spelled[pool[int(np.argmin(cost))]]
                if best not in names:
                    names.append(best)
                if not steps or steps[-1] != names.index(best):
                    steps.append(names.index(best))
        if steps:
            chosen[a, b] = steps
    return names, chosen


def soften(labels, chosen):
    """The labels with each chosen pair's darker side turned into its bands
    near the edge (see the module docstring)."""
    count = max(labels.max(), max(max(k) for k in chosen) if chosen else 0) + 1
    ladder = np.full((count, count), -1)
    for i, (pair, steps) in enumerate(chosen.items()):
        ladder[pair] = i
    steps = list(chosen.values())
    reached = np.zeros(labels.shape, int)
    source = np.full(labels.shape, -1)
    front = labels.copy()                                 # every cell starts a wave with its own texture
    span = BAND*MAX_BANDS
    for step in range(1, span + 1):
        best = np.full(labels.shape, -1)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    p = np.pad(front, 1, constant_values=-1)
                    near = p[1 + dy:1 + dy + labels.shape[0], 1 + dx:1 + dx + labels.shape[1]]
                    fits = (near >= 0) & (best < 0) & (ladder[labels, np.maximum(near, 0)] >= 0)
                    best = np.where(fits, near, best)
        new = (reached == 0) & (best >= 0)
        reached[new], source[new] = step, best[new]
        front = np.where(new, best, -1)
    y, x = np.mgrid[0:labels.shape[0], 0:labels.shape[1]]*10.0
    wander = fbm(x, y, scale=60, seed=420, octaves=2)
    band = np.maximum(np.floor((reached - 1 + 1.5*wander/wander.std())/BAND).astype(int), 0)
    out = labels.copy()
    for i, pair_steps in enumerate(steps):
        here = (reached > 0) & (ladder[labels, np.maximum(source, 0)] == i)
        for k, texture in enumerate(pair_steps[::-1]):     # nearest the brighter side first
            out[here & (band == k)] = texture
    return out
