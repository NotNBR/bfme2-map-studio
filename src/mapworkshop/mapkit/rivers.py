"""Flowing rivers and shore waves: the RiverAreas and StandingWaveAreas sections.

Stock evidence (local/game/maps, measured):

- A river is a strip of cross-sections (two bank points each, every 50 to 180
  along it, the strip 100 to 350 wide) at one water height. In the stock
  maps it lies 1 above a standing water area that covers it (Argonath 90 over
  89, the Fords of Isen 295 over 294, Weathertop 96 over 95): the standing
  water is the water units wade and sink in, the river the flowing surface
  over it. The usual look is additive TWWaterEmpty with Noise0000,
  TWAlphaEdge and WaterSurfaceBubbles: black itself, so what shows is moving
  bubbles and noise, faded out at both banks. The strip flows from its first
  cross-section to its last; which bank a section names first varies (1,277
  to 910), so it is not the flow.
- A shore wave is a line of two points about 400 long (144 of 255 records)
  with nine parameters: final width, final height, initial width and height
  (percent), initial velocity, time to fade, time to compress, second wave
  offset (milliseconds) and distance from shore. 209 of 226 records with
  points use (28, 18, 50, 100, 5, 2000, 1000, 3000, 40) and wave256.tga. The
  land lies to the left of the line from its first point to its second (114
  of 144).

    from mapworkshop.mapkit.rivers import add_river, add_shore_waves
    water_plane(m, 'Lake', 150)
    add_river(m, 'Brook', line, width=140, height=151)
    add_shore_waves(m, 'Beach', shoreline)          # land to the left of the line
"""
import math

from mapworkshop.formats import sections

# Look: texture, noise, alpha edge, sparkle, additive.
LOOKS = {
    'flow': ('TWWaterEmpty.tga', 'Noise0000.tga', 'TWAlphaEdge.tga', 'WaterSurfaceBubbles.tga', 1),
    'water': ('TWWater01.tga', 'Noise0000.tga', 'TWAlphaEdge.tga', 'WaterSurfaceBubbles.tga', 0),
    'lava': ('TLava_Mor01.tga', 'Noise0000.tga', 'TLava_Mor02.tga', 'WaterSurfaceBubbles.tga', 0),
}
WAVE = (28, 18, 50, 100, 5, 2000, 1000, 3000, 40)
WAVE_TEXTURE = 'wave256.tga'
WAVE_LENGTH = 400


def _ids(m):
    found = []
    for name in ('StandingWaterAreas', 'RiverAreas', 'StandingWaveAreas'):
        try:
            found += [a['id'] for a in sections.read(m, name)]
        except ValueError:
            pass
    return found


def _resample(line, step):
    """Points every `step` along a polyline (its ends included), with the
    direction there."""
    lengths = [math.dist(a, b) for a, b in zip(line, line[1:])]
    total = sum(lengths)
    if total <= 0:
        raise ValueError('A river line needs length')
    n = max(1, round(total/step))
    out = []
    for k in range(n+1):
        s = total*k/n
        for (a, b), length in zip(zip(line, line[1:]), lengths):
            if s <= length or (a, b) == (line[-2], line[-1]):
                f = min(1.0, s/length) if length else 0.0
                p = (a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f)
                out.append((p, math.atan2(b[1]-a[1], b[0]-a[0])))
                break
            s -= length
    return out


def cross_sections(line, width, step=120):
    """The strip's cross-sections along `line` (x, y points, in flow order):
    (left x, left y, right x, right y) every about `step`, `width` across
    (a number, or a function of the distance along the line). At each point the
    strip runs across the mean direction of the line on either side."""
    points = _resample([tuple(map(float, p)) for p in line], step)
    out, along = [], 0.0
    for i, (p, heading) in enumerate(points):
        before = points[max(0, i-1)][0]
        after = points[min(len(points)-1, i+1)][0]
        heading = math.atan2(after[1]-before[1], after[0]-before[0]) if before != after else heading
        if i:
            along += math.dist(points[i-1][0], p)
        w = width(along) if callable(width) else width
        nx, ny = -math.sin(heading), math.cos(heading)
        out.append((p[0]+nx*w/2, p[1]+ny*w/2, p[0]-nx*w/2, p[1]-ny*w/2))
    return out


def add_river(m, name, line, width, height, look='flow', step=120, alpha=1.0, uv_speed=0.06, min_lod='Medium',
              layer=''):
    """Append a river strip flowing along `line`. `height` is its water height
    (a whole number; over standing water, 1 above it as in the stock maps)."""
    texture, noise, alpha_edge, sparkle, additive = LOOKS[look]
    sections_ = cross_sections(line, width, step)
    if len(sections_) < 2:
        raise ValueError('A river needs at least two cross-sections')
    rivers = sections.read(m, 'RiverAreas')
    rivers.append(dict(id=max(_ids(m), default=0)+1, name=name, layer=layer, uv_speed=float(uv_speed),
                       additive=additive, texture=texture, noise=noise, alpha_edge=alpha_edge, sparkle=sparkle,
                       color_bytes=(255, 255, 255, 0), alpha=float(alpha), water_height=int(round(height)),
                       min_lod=min_lod, cross_sections=[tuple(map(float, c)) for c in sections_]))
    sections.write(m, 'RiverAreas', rivers)
    return rivers[-1]


def add_shore_wave(m, name, start, end, parameters=WAVE, texture=WAVE_TEXTURE, layer=''):
    """Append one shore wave along the line from `start` to `end`, with the land
    to its left."""
    if len(parameters) != 9 or any(int(p) != p or p < 0 for p in parameters):
        raise ValueError('A wave takes nine whole numbers (see WAVE)')
    if math.dist(start, end) < 1:
        raise ValueError('A wave line needs length')
    waves = sections.read(m, 'StandingWaveAreas')
    waves.append(dict(id=max(_ids(m), default=0)+1, name=name, layer=layer, uv_speed=0.06, additive=0,
                      points=[tuple(map(float, start)), tuple(map(float, end))], unknown_u32=0,
                      wave_parameters_raw=tuple(int(p) for p in parameters), texture=texture, enable_pca=1))
    sections.write(m, 'StandingWaveAreas', waves)
    return waves[-1]


def point_along(line, s):
    """The point `s` along a polyline (clamped to its ends)."""
    for a, b in zip(line, line[1:]):
        length = math.dist(a, b)
        if s <= length:
            f = s/length if length else 0.0
            return a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f
        s -= length
    return tuple(line[-1])


def add_shore_waves(m, name, shoreline, length=WAVE_LENGTH, gap=0.0, **kw):
    """Waves along a shoreline (x, y points with the land to their left): a
    line `length` long, then `gap`, and so on to its end. Returns how many."""
    line = [tuple(map(float, p)) for p in shoreline]
    total = sum(math.dist(a, b) for a, b in zip(line, line[1:]))
    s, count = 0.0, 0
    while s+length <= total+1e-6:
        add_shore_wave(m, f'{name} {count+1}', point_along(line, s), point_along(line, s+length), **kw)
        s += length+gap
        count += 1
    return count
