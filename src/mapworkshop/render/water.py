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
Its WaterMixin is the standing-water part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""

import re

import numpy as np

from mapworkshop.mapkit.lines import inside
from mapworkshop.assets.models import chunks
from mapworkshop.assets.models import fx_constants
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.render import shaders
import math

# WaterShader.fx techniques with a GLSL port: the water shaders' `technique` uniform.
WATER_TECHNIQUES = {'BumpSpecular': 0, 'BumpSpecular_M': 1, 'PCA_L': 2}


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


class WaterMixin:
    """MapRenderer's standing water: its meshes and WaterShader materials, and the
    reflection pass that mirrors the scene about ReflectionPlaneZ."""

    # Water ------------------------------------------------------------------
    def _water_material(self, shader_name):
        """FX constants of the area's water model over the effect's defaults,
        plus the technique it runs at this detail level."""
        from mapworkshop.render.water import shader_model, technique
        model, lod_index = shader_model(shader_name or '', self.water_level,
                                        lambda name: self.assets.model_key(name) is not None)
        key = self.assets.model_key(model) if model else None
        if key is None:
            return {}
        values = {}
        for kind, payload in chunks(self.assets.read(key)):
            if kind == 0:
                for k, p in chunks(payload):
                    if k == 0x50:
                        values = fx_constants(p)
        effect = self._effect(values.get('__shader__'))
        if effect is None:
            return values
        defaults = {}
        for param in effect.parameters:
            v = param['value']
            if 'values' in v:
                defaults[param['name']] = tuple(v['values']) if param['type'] != 'bool' else bool(v['values'][0])
        values = {**defaults, **values}
        names = [t['name'] for t in effect.techniques]
        values['__technique_name__'] = technique(names, values.get('__technique__', 0), lod_index)
        return values

    def _prepare_water(self):
        from mapworkshop.render.water import build_mesh, reflection, transparency, water_level
        self.water = []
        self._prepared_water = []
        self.water_level = water_level(self.assets.ini_text('gamelod.ini'), self.options['lod'])
        # The reflection camera and texture exist only with WaterLOD High or
        # higher (GlobalData+0x5E) and WaterTransparency ReflectionOn
        # (callback 0x00080168, camera 0x0007FD89); otherwise the water reads
        # a black reflection texture.
        on, plane = reflection(self.assets.ini_text('water.ini'), self.map_ini)
        self.reflection_plane = plane if on and self.water_level >= 2 else None
        self._prepare_rivers()
        try:
            areas = records(self.map, 'StandingWaterAreas')
        except ValueError:
            areas = []
        if not areas:
            return
        map_ini = self.source.parent/'map.ini' if self.source else None
        depth, opacity = transparency(self.assets.ini_text('water.ini'),
                                      self.map_ini)
        self.report['water'] = dict(transparent_depth=depth, min_opacity=opacity, areas=[])
        for area in areas:
            mesh = build_mesh(area['points'], float(area['water_height']), self.terrain.height_at, self.water_level)
            if mesh is None:
                continue
            vertices, triangles, spacing = mesh
            fx = self._water_material(area.get('shader'))
            self._prepared_water.append((area, mesh, fx))
            for name in (fx.get('WaterBumpTexture') or area.get('bump_texture'),
                         fx.get('WaterEnvTexture') or area.get('sky_texture'), fx.get('WaveTexture')):
                self._prepare_image(name)

    def _water_steps(self):
        if not self._prepared_water:
            return
        program = self.ctx.program(vertex_shader=shaders.WATER_VS, fragment_shader=shaders.WATER_FS)
        self.water_program = program
        depth, opacity = self.report['water']['transparent_depth'], self.report['water']['min_opacity']
        for area, (vertices, triangles, spacing), fx in self._prepared_water:
            yield
            self.report['water']['areas'].append(dict(name=area['name'], grid_spacing=spacing,
                                                      vertices=len(vertices), triangles=len(triangles)))
            vbo = self.ctx.buffer(vertices.tobytes())
            ibo = self.ctx.buffer(triangles.tobytes())
            from mapworkshop.render.water import shader_model
            self.report['water']['areas'][-1]['model'] = shader_model(
                area.get('shader') or '', self.water_level, lambda n: self.assets.model_key(n) is not None)[0]
            self.report['water']['areas'][-1]['technique'] = fx.get('__technique_name__')
            name = fx.get('__technique_name__')
            technique = WATER_TECHNIQUES.get(name)
            if technique is None:
                technique = 0
                self.report['water']['areas'][-1]['approximated'] = 'drawn with the BumpSpecular port'
            vec = lambda name, default: tuple(fx.get(name, default))
            one = lambda name, default: float(fx.get(name, (default,))[0])
            diffuse = vec('MaterialColorDiffuse', (0.2, 0.35, 0.45, 1.0))
            dimming = one('DimmingFactor', 0.6)
            # Sas.DirectionalLight[i]: the light environment's directional
            # lights (towards the light), colours doubled under overbright.
            lights = self.object_lights
            if fx.get('UseMySpecularDirection'):
                # Preshader: degrees -> (cos x cos y, sin x cos y, -sin y).
                ax, ay = (math.radians(v) for v in vec('MySpecularDirection', (30.0, 60.0))[:2])
                specular_dir = (math.cos(ax)*math.cos(ay), math.sin(ax)*math.cos(ay), -math.sin(ay))
            else:
                specular_dir = tuple(lights[1][0]) if len(lights) > 1 else (0.0, 0.0, 1.0)
            if not hasattr(self, 'water_depth_program'):
                self.water_depth_program = self.ctx.program(vertex_shader=shaders.WATER_DEPTH_VS,
                                                             fragment_shader=shaders.DEPTH_FS)
            entry = dict(area=area, vao=self.ctx.vertex_array(program, [(vbo, '4f', 'in_vertex')],
                                                              index_buffer=ibo, index_element_size=4),
                         depth_vao=self.ctx.vertex_array(self.water_depth_program, [(vbo, '4f', 'in_vertex')],
                                                         index_buffer=ibo, index_element_size=4),
                         own_specular=bool(fx.get('UseMySpecularDirection')),
                         bump=self._plain_texture(fx.get('WaterBumpTexture') or area.get('bump_texture')),
                         env=self._plain_texture(fx.get('WaterEnvTexture') or area.get('sky_texture')),
                         wave=self._plain_texture(fx.get('WaveTexture')),
                         uniforms=dict(
                             bump_scale_uv=vec('BumpUVScale', (7.0, 7.0))[:2],
                             env_scale_uv=vec('EnvUVScale', (0.2, 0.2))[:2],
                             wave_scale_uv=vec('WaveUVScale', (7.0, 7.0))[:2],
                             wind_angle=one('WindAngle', 0.0),
                             scroll_speed=one('WindSpeed', 0.02)+one('WaveSpeed', 0.0),
                             bump_speed=one('WindSpeed', 0.02)+one('BumpSpeed', 0.0),
                             wave_angle=one('WaveAngle', 0.2),
                             bump_scale=one('BumpScale', 0.2),
                             technique=technique,
                             # PCA_L's preshader leaves out the factor 2.
                             diffuse=tuple((1 if technique == 2 else 2)*dimming*diffuse[i] for i in range(3)),
                             light0_dir=tuple(lights[0][0]),
                             light0_color=tuple((2.0 if self.overbright else 1.0)*c for c in lights[0][1]),
                             specular_dir=specular_dir,
                             specular_color=vec('SpecularColor', (0.8, 0.8, 0.8))[:3],
                             specular_exponent=one('SpecularExponent', 50.0),
                             reflection_strength=one('ReflectionStrength', 0.2),
                             reflection_perturbation=one('ReflectionPerturbation', 0.005),
                             shadow_lightness=one('ShadowLightness', 0.8),
                             transparent_depth=depth, min_opacity=opacity, material_alpha=diffuse[3],
                             terrain_alpha=int(fx.get('BlendUsingTerrainAlpha', True))))
            self.water.append(entry)

    def _reflection_pass(self, camera, size, time):
        """The water's reflection texture: the scene mirrored about
        ReflectionPlaneZ, as the main camera sees it. WaterShader's
        BumpSpecular reads it at the pixel's own screen position (vs 78:
        oT2 = ((clip.xy + clip.w) / 2, clip.w)), moved by
        ReflectionPerturbation x the bump normal. It holds the sky domes, the
        tree buffer and KindOf CAN_CAST_REFLECTIONS objects; the game clears
        it to black where nothing is drawn (assumed; skies cover it). Returns
        the texture, or None when the water reads black."""
        plane = getattr(self, 'reflection_plane', None)
        if (plane is None or not self.water or not self.visible['water'] or not self.batches
                or not any(e['uniforms']['technique'] == 0 for e in self.water)):
            return None
        ctx, mgl = self.ctx, self.moderngl
        if getattr(self, 'reflection_size', None) != size:
            for name in ('reflection_fbo', 'reflection_tex', 'reflection_depth'):
                if hasattr(self, name):
                    getattr(self, name).release()
            self.reflection_size = size
            self.reflection_tex = ctx.texture(size, 4)
            self.reflection_tex.repeat_x = self.reflection_tex.repeat_y = False
            self.reflection_depth = ctx.depth_renderbuffer(size)
            self.reflection_fbo = ctx.framebuffer([self.reflection_tex], self.reflection_depth)
        self.reflection_fbo.use()
        ctx.viewport = (0, 0, *size)
        self.reflection_fbo.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)
        if not self.visible['objects']:
            return self.reflection_tex
        mirror = np.diag([1.0, 1.0, -1.0, 1.0])
        mirror[2, 3] = 2.0*plane
        vp = np.ascontiguousarray((camera['view_projection'] @ mirror).T, dtype='f4').tobytes()
        eye = np.asarray(camera['eye'], float)*(1, 1, -1) + (0, 0, 2.0*plane)
        target = np.asarray(camera['target'], float)*(1, 1, -1) + (0, 0, 2.0*plane)
        eye_t = tuple(float(v) for v in eye)
        op = self.object_program
        self._set_fog(op, eye_t)
        # The mirror turns the winding round: culled faces flip.
        ctx.front_face = 'cw'
        sky = [b for b in self.batches if b.get('sky') and b.get('reflects')]
        if sky:
            self._draw_sky(sky, vp, eye_t)
        ctx.enable(mgl.DEPTH_TEST)
        op['view_projection'].write(vp)
        op['eye'].value = eye_t
        back = eye - target
        op['camera_back'].value = tuple(back/(np.linalg.norm(back) or 1.0))
        op['time'].value = float(time)
        op['use_shadows'].value = 0
        op['use_cloud'].value = int(self.options['clouds'] and self.cloud_tex is not None)
        if self.cloud_tex:
            self.cloud_tex.use(5)
        op['cloud_tex'].value = 5
        op['clip_z'].value = plane
        self._begin_batches()
        for batch in self._draw_batches:
            if batch.get('sky') or not batch.get('reflects'):
                continue
            if batch['blend'] is not None:
                ctx.enable(mgl.BLEND)
                ctx.blend_func = self._blend_func(batch['blend'])
            ctx.fbo.depth_mask = batch['depth_mask']
            if batch['cull']:
                ctx.enable(mgl.CULL_FACE)
            self._bind_batch(op, batch)
            batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
            ctx.disable(mgl.BLEND)
            ctx.disable(mgl.CULL_FACE)
            ctx.fbo.depth_mask = True
        op['clip_z'].value = -1e30
        ctx.front_face = 'ccw'
        return self.reflection_tex
