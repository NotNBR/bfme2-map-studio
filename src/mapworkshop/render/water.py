"""Standing-water meshes as the game builds them.

Port of RenderableStandingWaterArea::AllocateAndFillBuffers (game.dat 1.06
RVA 0x0008304A) and its CachedVertexAdder (0x00082E33):

- A regular grid over the polygon's bounds. Spacing starts at 20 units (40
  while WaterLOD <= 2, i.e. every preset but UltraHigh) and doubles until the
  cell count fits 60000 (30000 at those levels). Bounds snap outwards to the
  spacing.
- A cell is kept when its centre lies inside the polygon; it becomes two
  triangles (i,j)(i+1,j+1)(i,j+1) and (i,j)(i+1,j)(i+1,j+1).
- Each vertex stores the terrain height below it (StandingWaveQuery 0x0008026B);
  WaterShader.fx turns that into a per-vertex alpha, so shorelines fade over
  one grid cell.

Water transparency comes from the WaterTransparency INI block (data/ini/
water.ini, overridden by the map's map.ini), copied into the terrain render
object by its constructor (0x0006C9CF): TransparentWaterDepth and
TransparentWaterMinOpacity.
"""

import re

import numpy as np

from mapworkshop.mapkit.lines import inside


def grid_spacing(bounds, level=3):
    # Coarse while TheGameLODManager's WaterLOD (+0x1784) is High or lower.
    low = level <= 2
    spacing, limit = (40.0, 30000) if low else (20.0, 60000)
    x0, y0, x1, y1 = bounds
    while True:
        nx = int(x1/spacing) - int(x0/spacing) + 1
        ny = int(y1/spacing) - int(y0/spacing) + 1
        if nx*ny <= limit:
            return spacing, nx, ny
        spacing *= 2.0


def build_mesh(points, water_z, height_at, level=3):
    """(vertices[n, 4] = x, y, z, ground height; triangle indices[m, 3]; spacing)."""
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    bounds = (min(xs), min(ys), max(xs), max(ys))
    spacing, nx, ny = grid_spacing(bounds, level)
    ox = int(bounds[0]/spacing)*spacing
    oy = int(bounds[1]/spacing)*spacing
    cj, ci = np.mgrid[0:ny, 0:nx]
    keep = inside(points, ox+(ci+0.5)*spacing, oy+(cj+0.5)*spacing)
    if not keep.any():
        return None
    used = np.zeros((ny+1, nx+1), bool)
    for dj, di in ((0, 0), (0, 1), (1, 0), (1, 1)):
        used[dj:dj+ny, di:di+nx] |= keep
    index = -np.ones((ny+1, nx+1), np.int64)
    index[used] = np.arange(int(used.sum()))
    vj, vi = np.nonzero(used)
    vx = ox + vi*spacing; vy = oy + vj*spacing
    ground = np.asarray(height_at(vx, vy), float)
    vertices = np.column_stack([vx, vy, np.full(len(vx), water_z), ground]).astype('f4')
    j, i = np.nonzero(keep)
    a, b, c, d = index[j, i], index[j, i+1], index[j+1, i], index[j+1, i+1]
    triangles = np.concatenate([np.column_stack([a, d, c]), np.column_stack([a, b, d])]).astype('u4')
    return vertices, triangles, spacing


def transparency(ini_text, map_ini_text=''):
    """(TransparentWaterDepth, TransparentWaterMinOpacity), map.ini first."""
    values = {'transparentwaterdepth': 3.0, 'transparentwaterminopacity': 1.0}
    for text in (ini_text, map_ini_text):
        block = re.search(r'(?ims)^\s*WaterTransparency\b(.*?)^\s*End\b', text or '')
        if not block:
            continue
        for key, value in re.findall(r'(?im)^\s*(TransparentWaterDepth|TransparentWaterMinOpacity)\s*=\s*([-\d.]+)', block.group(1)):
            values[key.lower()] = float(value)
    return values['transparentwaterdepth'], values['transparentwaterminopacity']


def reflection(ini_text, map_ini_text=''):
    """(ReflectionOn, ReflectionPlaneZ) of the WaterTransparency block, map.ini
    over water.ini; retail water.ini sets No and 59."""
    on, plane = False, 59.0
    for text in (ini_text, map_ini_text):
        block = re.search(r'(?ims)^\s*WaterTransparency\b(.*?)^\s*End\b', text or '')
        if not block:
            continue
        for key, value in re.findall(r'(?im)^\s*(ReflectionOn|ReflectionPlaneZ)\s*=\s*([-\w.]+)', block.group(1)):
            if key.lower() == 'reflectionon':
                on = value.lower() in ('yes', 'true', '1')
            else:
                plane = float(value)
    return on, plane


WATER_LODS = ('low', 'medium', 'high', 'ultrahigh')    # GameLOD WaterLOD values 0-3
LOD_SUFFIXES = ('L', 'M', '', '')                       # 0x00C07F00
SHADER_LODS = (0, 1, 2, 3)                              # 0x00DBD774


def water_level(gamelod_ini, lod):
    """WaterLOD (0-3) of a StaticGameLOD preset in GameLOD.ini; Medium gives
    WaterLOD = Medium (1) in the retail file."""
    presets = {}
    current = None
    for line in (gamelod_ini or '').splitlines():
        line = line.split(';')[0].strip()
        m = re.match(r'(?i)StaticGameLOD\s*=\s*(\w+)', line)
        if m:
            current = m.group(1).lower()
            continue
        m = re.match(r'(?i)WaterLOD\s*=\s*(\w+)', line)
        if m and current and m.group(1).lower() in WATER_LODS:
            presets.setdefault(current, WATER_LODS.index(m.group(1).lower()))
    default = dict(verylow=0, low=0, medium=1, high=2, ultrahigh=3)
    return presets.get(lod, default.get(lod, 1))


def shader_model(shader_name, level, exists):
    """Water model and shader LOD as StandingWaterArea::loadFXShaderSetup
    (0x00308C31) picks them from TheGameLODManager's WaterLOD (+0x1784):
    strip '.W3D', try the level's suffix (Low 'L', Medium 'M', High and
    UltraHigh none) and upwards, else the bare name; the shader LOD is
    SHADER_LODS[WaterLOD]. Returns (model name, shader LOD index)."""
    base = shader_name[:-4] if shader_name and len(shader_name) > 4 else ''
    if not base:
        return None, 0
    suffix = ''
    for index in range(level, 4):
        if exists(base + LOD_SUFFIXES[index]):
            suffix = LOD_SUFFIXES[index]
            break
    return base + suffix, SHADER_LODS[min(max(level, 0), 3)]


TECHNIQUE_SUFFIXES = ('_L', '_M', '', '_U')


def technique(names, index, lod_index):
    """Technique an FX material runs at a shader LOD, as FXShaderSetup does.

    Load_W3D (0x00152E4D) takes the stored technique index's name;
    InitializeShader (0x0015288F) strips an _L/_M/_U suffix, then tries the
    base name with the suffix of each level from min(name level, LOD)
    downwards, then upwards, keeping the first technique the effect has.
    """
    if not 0 <= index < len(names):
        return None
    name = names[index]
    base, level = name, 3
    for i, suffix in enumerate(TECHNIQUE_SUFFIXES):
        if suffix and name.endswith(suffix):
            base, level = name[:-len(suffix)], i
    start = min(level, lod_index)
    for i in list(range(start, -1, -1)) + list(range(start+1, 4)):
        if base + TECHNIQUE_SUFFIXES[i] in names:
            return base + TECHNIQUE_SUFFIXES[i]
    return name


def depth_lut(data):
    """BGR pixels of a 24-bit uncompressed TGA depth LUT, as
    StandingWaterArea::getDepthColoringTexturePixels reads it (raw rows after
    the header; any other format gives no tint)."""
    if len(data) < 18:
        return None
    id_length, colormap, image_type = data[0], data[1], data[2]
    width = data[12] | data[13] << 8
    height = data[14] | data[15] << 8
    bits = data[16]
    if id_length or colormap or image_type != 2 or bits != 24 or width < 2 or height < 1:
        return None
    pixels = np.frombuffer(data[18:18+width*height*3], np.uint8)
    if len(pixels) < width*3:
        return None
    return pixels[:width*3].reshape(width, 3)


def depth_tint(heights, border, areas, read):
    """Per-sample RGB factor for terrain under standing water.

    BaseHeightMapRenderObjClass::getStaticDiffuse (0x0006B4CC) multiplies the
    vertex diffuse by the area's depth LUT at (waterZ - groundZ) / max(waterZ, 1)
    (StandingWaterArea 0x00308A12: index = int(width * position), clamped).
    """
    h, w = heights.shape
    tint = np.ones((h, w, 3), np.float32)
    yy, xx = np.indices((h, w))
    px = (xx - border) * 10.0
    py = (yy - border) * 10.0
    done = np.zeros((h, w), bool)
    for area in areas:
        name = area.get('depth_colors')
        if not name:
            continue
        data = None
        for key in ('art/terrain/' + name, name):
            try:
                data = read(key)
                break
            except FileNotFoundError:
                continue
        lut = depth_lut(data) if data else None
        if lut is None:
            continue
        water = float(area['water_height'])
        covered = inside(area['points'], px, py) & ~done
        under = covered & (water > heights)
        position = np.clip((water - heights) / max(water, 1.0), 0, 1)
        index = np.minimum((lut.shape[0] * position).astype(int), lut.shape[0] - 1)
        rgb = lut[index][..., ::-1].astype(np.float32) / 256.0
        tint[under] = rgb[under]
        done |= covered
    return tint
