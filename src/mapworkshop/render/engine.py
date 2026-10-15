"""Offscreen renderer for BFME2 maps (moderngl, headless OpenGL 4.3)."""

import math
import re
import struct
from pathlib import Path
from collections import OrderedDict

import numpy as np
from PIL import Image

from mapworkshop.formats.lighting import decode
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.render import shaders
from mapworkshop.render.assets import GameAssets
from mapworkshop.render.camera import OrbitView, TopView, parse_view, _normalize
from mapworkshop.render.effects import QUAD_CORNERS, TRI_CORNERS, Effects
from mapworkshop.render.shadows import shadow_kind
from mapworkshop.render.terrain import TerrainData
from mapworkshop.render.w3d import ModelCache, chunks, fx_constants

ARRAY_SIZE = 512
# WaterShader.fx techniques with a GLSL port: the water shaders' `technique` uniform.
WATER_TECHNIQUES = {'BumpSpecular': 0, 'BumpSpecular_M': 1, 'PCA_L': 2}
SKIP_TEMPLATES = ('*waypoints', 'amb_', 'animalwanderpoint', 'waterripplespawn')


class TextureCache(OrderedDict):
    """Bound cached texture ownership; live batches retain their own references."""
    def __init__(self, budget=256*1024*1024):
        super().__init__()
        self.budget, self.bytes = budget, 0

    @staticmethod
    def cost(texture):
        return int(texture.width*texture.height*texture.components*4/3) if texture is not None else 0

    def __getitem__(self, key):
        texture = super().__getitem__(key)
        self.move_to_end(key)
        return texture

    def __setitem__(self, key, texture):
        if key in self:
            self.bytes -= self.cost(super().__getitem__(key))
        super().__setitem__(key, texture)
        self.move_to_end(key)
        self.bytes += self.cost(texture)
        while len(self) > 1 and (self.bytes > self.budget or len(self) > 1024):
            _, evicted = self.popitem(last=False)
            self.bytes -= self.cost(evicted)


def triangulate(points):
    """Ear clipping for simple polygons; returns triangle vertex lists."""
    pts = [tuple(p) for p in points]
    if len(pts) > 2 and pts[0] == pts[-1]:
        pts.pop()
    area = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(pts, pts[1:]+pts[:1]))
    if area < 0:
        pts.reverse()
    index = list(range(len(pts)))
    result = []
    def inside(p, a, b, c):
        d = lambda u, v, w: (u[0]-w[0])*(v[1]-w[1])-(v[0]-w[0])*(u[1]-w[1])
        s1, s2, s3 = d(p, a, b), d(p, b, c), d(p, c, a)
        return not ((s1 < 0 or s2 < 0 or s3 < 0) and (s1 > 0 or s2 > 0 or s3 > 0))
    guard = 0
    while len(index) > 3 and guard < 100000:
        guard += 1
        for i in range(len(index)):
            a, b, c = (pts[index[(i+j) % len(index)]] for j in (-1, 0, 1))
            if (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]) <= 0:
                continue
            if any(inside(pts[k], a, b, c) for k in index if pts[k] not in (a, b, c)):
                continue
            result.append((a, b, c))
            index.pop(i)
            break
        else:
            break
    if len(index) == 3:
        result.append(tuple(pts[k] for k in index))
    return result


def bleed_alpha(image):
    """Fill transparent texels with nearby opaque colour before mipmapping.

    Retail DDS files ship their own mip chains; regenerating mips from the top
    level would otherwise average hidden (often white) texels into foliage.
    """
    alpha = image[..., 3]
    if alpha.min() >= 250:
        return image
    rgb = image[..., :3].astype(np.float32)
    weight = (alpha > 127).astype(np.float32)
    if weight.sum() == 0:
        return image
    out = image.copy()
    filled = rgb*weight[..., None]
    total = weight.copy()
    for radius in (1, 2, 4, 8, 16, 32, 64):
        blur = lambda a: sum(np.roll(np.roll(a, dy, 0), dx, 1) for dy in (-radius, 0, radius) for dx in (-radius, 0, radius))
        filled, total = blur(filled), blur(total)
        missing = (weight == 0) & (total > 0)
        out[..., :3][missing] = (filled[missing]/total[missing, None]).astype(np.uint8)
        weight = np.maximum(weight, (total > 0).astype(np.float32))
        filled = out[..., :3].astype(np.float32)*weight[..., None]
        total = weight.copy()
        if weight.min() > 0:
            break
    return out


class MapRenderer:
    def __init__(self, source, assets=None, ctx=None, objects=True, normal_maps=None,
                 clouds=True, macro=True, samples=4, lod='medium', shadows=True, shared=None, weather=None,
                 progress=None, vegetation_limits=False, sun=None):
        """Synchronous entry point for CLI rendering; the viewer uses prepare/upload."""
        import moderngl
        self._prepare(source, assets, objects, normal_maps, clouds, macro, samples, lod,
                      shadows, shared, weather, progress, vegetation_limits, sun)
        for _ in self.upload(ctx or moderngl.create_standalone_context(require=430), shared):
            pass

    @classmethod
    def prepare(cls, source, **options):
        """CPU-only scene construction, safe to perform in a loader worker."""
        return cls.__new__(cls)._prepare(source, **options)

    def _prepare(self, source, assets=None, objects=True, normal_maps=None, clouds=True,
                 macro=True, samples=4, lod='medium', shadows=True, shared=None, weather=None,
                 progress=None, vegetation_limits=False, sun=None):
        report = progress or (lambda fraction, step: None)
        report(0.0, 'Indexing game assets' if assets is None else 'Reading map')
        base = assets or GameAssets()
        report(0.08, 'Reading map')
        self.source = None if isinstance(source, (bytes, bytearray)) else Path(source)
        data = self.source.read_bytes() if self.source else bytes(source)
        if data[:4] != b'CkMp':
            from mapworkshop.formats.map_archive import unpack
            data = unpack(data)
        self.map = Map(data)
        map_ini = self.source.parent/'map.ini' if self.source else None
        self.map_ini = map_ini.read_text(encoding='cp1252', errors='replace') if map_ini and map_ini.is_file() else ''
        self.assets = base.for_map(self.map_ini)
        self.pathing_assets = getattr(base, '_base', base)
        self.samples = samples
        lod = lod.lower()
        # GameLOD.ini: UseTerrainNormalMap only at High and above,
        # UseDistanceDependantTerrainTextures from Medium; Medium draws
        # stencil volume shadows, High and above use shadow mapping.
        high = lod in ('high', 'ultrahigh')
        self.distance_textures = lod in ('medium', 'high', 'ultrahigh')
        self.weather_preset = weather if weather not in (None, '', 'map') else None
        self.sun = sun if sun not in (None, '', 'own') else None
        self.options = dict(objects=objects, clouds=clouds, macro=macro, lod=lod, vegetation_limits=vegetation_limits,
                            normal_maps=high if normal_maps is None else normal_maps,
                            # GameLOD.ini UseShadowDecals: Low and Medium.
                            decals=lod in ('low', 'medium') and shadows,
                            shadows=(('map' if high else 'volume') if lod not in ('verylow', 'low') else 'none')
                                    if shadows else 'none')
        self.terrain = TerrainData(self.map, checkpoint=lambda: report(0.10, 'Preparing terrain'))
        shared = {} if shared is None else shared
        self.model_cache = shared.setdefault('model_cache', ModelCache(self.pathing_assets))
        self.shadow_settings = self._shadow_settings()
        # Runtime switches (used by the interactive viewer).
        self.visible = dict(terrain=True, objects=True, water=True, decals=True, shadows=True, weather=True,
                            walkable=False, effects=True, flow=False)
        self.report = dict(missing_textures=[], missing_models=[], objects_drawn=0, objects_skipped=0)
        self._progress = report
        self._effects = {}
        self._lighting()
        self._images = {}
        report(0.18, 'Preparing terrain textures')
        self._prepare_terrain()
        report(0.28, 'Preparing water')
        self._prepare_water()
        report(0.32, 'Preparing weather')
        self._prepare_weather()
        self.batches = []
        self.sky_horizon = None
        if objects:
            report(0.36, 'Preparing objects')
            self._prepared_objects = self._object_groups()
            self._prepare_models()
            report(0.65, 'Preparing shadows')
            self._prepare_volumes(self._prepared_objects[1])
            self._prepared_volume_triangles = self._volume_triangles()
        report(0.70, 'Ready to upload')
        return self

    def upload(self, ctx, shared=None):
        """Yield between GPU batches. Advance only on the context-owning thread."""
        import moderngl
        self.moderngl, self.ctx = moderngl, ctx
        self.textures = ({} if shared is None else shared).setdefault('textures', TextureCache())
        yield from self._terrain_steps()
        self._progress(0.78, 'Uploading water')
        yield from self._water_steps()
        self._rivers_gpu()
        self._weather_gpu()
        yield
        if self.options['objects']:
            yield from self._objects_steps()
        # Prepared pixel arrays are temporary. GameAssets owns the bounded
        # decoded-image cache; the live renderer needs only its GPU resources.
        self._images.clear()
        self.__dict__.pop('_terrain_pixels', None)
        self.__dict__.pop('_prepared_objects', None)
        self.__dict__.pop('_prepared_volume_triangles', None)
        self.__dict__.pop('_prepared_water', None)
        self._draw_batches = sorted(self.batches, key=lambda b: (not b['vegetation'], b['blend'] is not None and not b['depth_mask']))
        self._progress(1.0, 'Done')
        self._progress = lambda fraction, step: None

    def set_option(self, name, value):
        """Change a shader option at runtime: normal_maps, clouds or macro."""
        if name not in ('normal_maps', 'clouds', 'macro'):
            raise KeyError(name)
        self.options[name] = bool(value)
        if name == 'normal_maps':
            self._terrain_technique()
            return
        uniform = dict(clouds='use_cloud', macro='use_macro')[name]
        texture = dict(clouds=self.cloud_tex, macro=self.macro_tex)[name]
        self.terrain_program[uniform].value = int(bool(value) and texture is not None)

    def _terrain_technique(self):
        """terrain.fx technique (HeightMap 0x000E153A): Default with normal
        maps, else Default_M with distance-dependent textures, else Default_L.
        Without normal maps doTheLight keeps the sun in the vertex colour."""
        p = self.terrain_program
        normal = self.options['normal_maps']
        p['technique'].value = 2 if normal else (1 if self.distance_textures else 0)
        p['sun_in_vertex'].value = int(not normal)

    # Lighting ---------------------------------------------------------------
    def _lighting(self):
        chunk = self.map.chunk('GlobalLighting')
        value = decode(chunk.data, chunk.version)
        if self.weather_preset:
            from mapworkshop.mapkit.weather import apply_lighting
            apply_lighting(value, self.weather_preset)
        if self.sun:
            from mapworkshop.mapkit.weather import apply_sun
            apply_sun(value, self.sun)
        config = value['configurations'][max(0, min(3, value['time_of_day']-1))]
        lights = {(l['target'], l['light_index']): l for l in config}
        to_light = lambda l: tuple(-_normalize(l['direction']))
        self.terrain_ambient = lights[('terrain', 0)]['ambient']
        # As GlobalData holds them for drawRiverWater: directions as stored.
        self.terrain_lights = [(tuple(lights[('terrain', i)]['direction']), tuple(lights[('terrain', i)]['diffuse']))
                               for i in range(3)]
        self.time_of_day = value['time_of_day']
        self.sun_dir = to_light(lights[('terrain', 0)])
        self.sun_color = lights[('terrain', 0)]['diffuse']
        self.fills = [(to_light(lights[('terrain', i)]), lights[('terrain', i)]['diffuse']) for i in (1, 2)]
        # Terrain vertex lighting (getStaticDiffuse/doTheLight): rays are the
        # negated GlobalLighting directions as stored, not normalized, and the
        # diffuse colours are scaled by the v8 final values (GlobalData +0x944,
        # applied while the terrain rendering mode is 0).
        scale = value.get('final_values', (1.0, 1.0, 1.0))
        self.terrain_rays = [(tuple(-np.asarray(lights[('terrain', i)]['direction'], float)),
                              tuple(c*s for c, s in zip(lights[('terrain', i)]['diffuse'], scale))) for i in range(3)]
        self.object_ambient = lights[('objects', 0)]['ambient']
        self.object_lights = [(to_light(lights[('objects', i)]), lights[('objects', i)]['diffuse']) for i in range(3)]
        self.overbright = value['overbright_value'] > 1
        # ShaderLOD Low/Medium scale the object and vegetation light
        # environments by the chunk's last three values (1, 1, 1 by default).
        final = tuple(value.get('final_values') or (1.0, 1.0, 1.0))
        self.light_scale = final if self.options['lod'] in ('verylow', 'low', 'medium') else (1.0, 1.0, 1.0)
        raw = value.get('shadow_color_raw', 0xFFA0A0A0)
        self.shadow_color = tuple(((raw >> shift) & 255)/255 for shift in (16, 8, 0))
        try:
            self.environment = records(self.map, 'EnvironmentData')
        except ValueError:
            self.environment = {}

    # Terrain ----------------------------------------------------------------
    @staticmethod
    def _texture_pixels(images):
        layers = []
        for image in images:
            # Resize colour and alpha separately: Pillow premultiplies RGBA,
            # which would turn texels with zero alpha black.
            rgb = Image.fromarray(np.ascontiguousarray(image[..., :3])).resize((ARRAY_SIZE, ARRAY_SIZE), Image.Resampling.LANCZOS)
            alpha = Image.fromarray(np.ascontiguousarray(image[..., 3])).resize((ARRAY_SIZE, ARRAY_SIZE), Image.Resampling.LANCZOS)
            layers.append(np.dstack([np.asarray(rgb), np.asarray(alpha)]))
        return np.stack(layers).astype(np.uint8)

    def _texture_array(self, data):
        texture = self.ctx.texture_array((ARRAY_SIZE, ARRAY_SIZE, len(data)), 4, data.tobytes())
        texture.build_mipmaps()
        texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
        texture.repeat_x = texture.repeat_y = True
        texture.anisotropy = 16.0
        return texture

    def _prepare_terrain(self):
        t = self.terrain
        albedo, normals, has_normal, skipped = [], [], [], []
        for texture in t.textures:
            file = self.assets.terrain_textures.get(texture['name'].lower())
            image = self.assets.image(file) if file else None
            if image is None:
                self.report['missing_textures'].append(texture['name'])
                image = np.full((64, 64, 4), (255, 0, 255, 255), np.uint8)
            needed = texture['cell_size']*64
            if image.shape[0] < needed or image.shape[1] < needed:
                # WorldHeightMap::readTexClass (0x000AF917) skips a class whose
                # file has fewer 64-pixel tiles than declared; the game then
                # draws other texture data there. Drawn as declared, reported.
                self.report.setdefault('texture_size_errors', []).append(
                    dict(name=texture['name'], declared_cells=texture['cell_size'], pixels=list(image.shape[:2])))
                skipped.append(len(albedo))
            albedo.append(image)
            normal = self.assets.image(Path(file).stem+'_nrm') if file else None
            has_normal.append(int(normal is not None))
            # A flat normal without gloss (the High PS rebuilds z from RG and
            # reads B as gloss): in game, flat ground of a texture without a
            # _nrm map shows no sun glare where B = 255 would mirror the sun
            # (Specular Lab, High screenshots facing the sun, 15 October 2026).
            normals.append(normal if normal is not None else np.full((4, 4, 4), (128, 128, 0, 255), np.uint8))
        self._terrain_pixels = (self._texture_pixels(albedo), self._texture_pixels(normals))
        self.report['terrain_normal_maps'] = sum(has_normal)
        from mapworkshop.render.water import depth_tint
        try:
            areas = records(self.map, 'StandingWaterAreas')
        except ValueError:
            areas = []
        self._depth_tint = depth_tint(t.heights, t.border, areas, self.assets.read)
        for name in (self.environment.get('macro_texture', 'TSNoiseUrb.tga'),
                     self.environment.get('cloud_texture', 'TSCloudMed.tga')):
            self._prepare_image(name)

    def _terrain_steps(self):
        self._progress(0.72, 'Uploading terrain')
        t = self.terrain
        ctx = self.ctx
        self.heights = ctx.texture((t.width, t.height), 1, t.heights.astype('f4').tobytes(), dtype='f4')
        self.heights.filter = (self.moderngl.LINEAR, self.moderngl.LINEAR)
        self.heights.repeat_x = self.heights.repeat_y = False
        self.cells = ctx.texture((t.width, t.height), 4, t.cells.astype('u4').tobytes(), dtype='u4')
        self.cells.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        yield
        self.albedo = self._texture_array(self._terrain_pixels[0])
        yield
        self.normal_array = self._texture_array(self._terrain_pixels[1])
        yield
        self.terrain_program = ctx.program(vertex_shader=shaders.TERRAIN_VS, fragment_shader=shaders.TERRAIN_FS)
        p = self.terrain_program
        subtiles = [float(v) for v in t.subtiles] + [1.0]*(256-len(t.subtiles))
        p['subtiles'].value = subtiles
        p['array_size'].value = float(ARRAY_SIZE)
        p['grid'].value = (t.width, t.height)
        p['border'].value = t.border
        p['border_cells'].value = t.border
        self._terrain_lighting()
        self._terrain_technique()
        p['allow_2x'].value = int(self.distance_textures)
        self.tile_z = ctx.texture((t.tile_z.shape[1], t.tile_z.shape[0]), 2, t.tile_z.astype('f4').tobytes(), dtype='f4')
        self.tile_z.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        p['tile_z'].value = 9
        p['grid_lines'].value = 0
        tint = self._depth_tint
        self.depth_tint = ctx.texture((t.width, t.height), 3, tint.astype('f4').tobytes(), dtype='f4')
        self.depth_tint.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        self.report['depth_tinted_samples'] = int(np.count_nonzero((tint < .999).any(-1)))
        p['depth_tint'].value = 8
        for name, unit in [('heights', 0), ('cells', 1), ('albedo', 2), ('normals', 3), ('macro_tex', 4), ('cloud_tex', 5)]:
            p[name].value = unit
        # terrain.fx macro UV: stretched ((x + MapBorderWidth) / MapSize.x,
        # -(y + MapBorderWidth) / MapSize.y), MapSize = samples x 10
        # (callback 0x000E2EB7); else (x, -y) / (66 x MapCellSize).
        world_w, world_h = t.width*10, t.height*10
        border = t.border*10
        macro = self._plain_texture(self.environment.get('macro_texture', 'TSNoiseUrb.tga'))
        cloud = self._plain_texture(self.environment.get('cloud_texture', 'TSCloudMed.tga'))
        self.macro_tex, self.cloud_tex = macro, cloud
        if self.environment.get('macro_texture_stretched'):
            p['macro_xform'].value = (1/world_w, -1/world_h, border/world_w, -border/world_h)
        else:
            p['macro_xform'].value = (1/660, -1/660, 0, 0)
        # Cloud.ScaleUV_OffsetPerSecondUV (0x000E2BEE): 1 / weather.ini CloudTextureSize.
        from mapworkshop.render.terrain import cloud_texture_size
        size = cloud_texture_size(self.assets.ini_text('weather.ini'),
                                  self.map_ini)
        self.cloud_scale = (1/size[0], 1/size[1])
        p['cloud_xform'].value = (*self.cloud_scale, 0, 0)
        p['use_macro'].value = int(self.options['macro'] and macro is not None)
        p['use_cloud'].value = int(self.options['clouds'] and cloud is not None)
        self.terrain_vao = ctx.vertex_array(p, [])
        self.terrain_vertices = (t.width-1)*(t.height-1)*6

        yield

    def _prepare_image(self, name):
        if name and name.lower() not in self._images:
            image = self.assets.image(name)
            self._images[name.lower()] = bleed_alpha(image) if image is not None else None

    def _plain_texture(self, name, fallback=None, raw=False):
        """A mipmapped texture. `raw` keeps the colour under transparent
        texels (additive materials draw it), skipping bleed_alpha."""
        if raw:
            image = self.assets.image(name) if name else None
        else:
            self._prepare_image(name)
            image = self._images.get(name.lower()) if name else None
        if image is None:
            return fallback
        texture = self.ctx.texture((image.shape[1], image.shape[0]), 4, np.ascontiguousarray(image).tobytes())
        texture.build_mipmaps()
        texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
        texture.anisotropy = 8.0
        texture.repeat_x = texture.repeat_y = True
        return texture

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

    def _effect(self, name):
        """Compiled effect (Shaders/Compiled/<name>o) parsed by formats.fxo."""
        from mapworkshop.formats.fxo import Effect
        if not name:
            return None
        key = 'shaders/compiled/' + name.lower() + 'o'
        if key in self._effects:
            return self._effects[key]
        if not self.assets.exists(key):
            self._effects[key] = None
            return None
        try:
            effect = Effect(self.assets.read(key))
        except (ValueError, struct.error):
            effect = None
        self._effects[key] = effect
        return effect

    def _terrain_lighting(self):
        p = self.terrain_program
        p['ambient'].value = tuple(self.terrain_ambient)
        rays = self.terrain_rays
        p['fill_dir'].value = [r[0] for r in rays[1:]]
        p['fill_color'].value = [r[1] for r in rays[1:]]
        p['vs_sun_dir'].value = rays[0][0]
        p['vs_sun_color'].value = rays[0][1]
        # Default technique: Sas.DirectionalLight[0] of the terrain light
        # environment (0x000E3150): terrain diffuse 0 x final values, its
        # direction normalized by the VS preshader.
        p['sun_dir'].value = self.sun_dir
        p['sun_color'].value = rays[0][1]
        p['overbright'].value = int(self.overbright)

    def _object_lighting(self):
        """Light environment for objects and the vegetation buffers.

        The scene's fixed light environment (RTS3DScene, 0x0006E716) and the
        tree/shrub render step (0x00071A1F) build it from the three object
        lights and the object ambient, scaled at ShaderLOD Low/Medium by the
        GlobalLighting chunk's final three values (GlobalData +0x944). Sas
        colours double under overbright (`sas_scale`); the fixed-function
        path instead doubles texture x diffuse (MODULATE2X).
        """
        p = self.object_program
        self._bind_light_environment(p, scaled=True)
        p['sas_scale'].value = 2.0 if self.overbright else 1.0
        p['modulate2x'].value = int(self.overbright)

    def light_environment(self, scaled=True):
        """(ambient, [(direction, colour)] x 3) as LightEnvironmentClass holds
        them: Add_Light (0x00140770) drops lights whose diffuse is below 0.05
        in every channel and keeps the rest sorted by squared diffuse length;
        unused slots are black."""
        scale = np.asarray(self.light_scale if scaled else (1.0, 1.0, 1.0), np.float32)
        lights = [(tuple(d), np.asarray(c, np.float32)*scale) for d, c in self.object_lights]
        lights = [l for l in lights if not (l[1] < 0.05).all()]
        lights.sort(key=lambda l: -float(l[1] @ l[1]))
        lights += [((0.0, 0.0, 1.0), np.zeros(3, np.float32))]*(3-len(lights))
        ambient = tuple(float(v) for v in np.asarray(self.object_ambient)*scale)
        return ambient, [(d, tuple(float(v) for v in c)) for d, c in lights[:3]]

    def _bind_light_environment(self, p, scaled):
        ambient, lights = self.light_environment(scaled)
        p['ambient'].value = ambient
        p['light_dir'].value = [l[0] for l in lights]
        p['light_color'].value = [l[1] for l in lights]
        self._bound_scaled = scaled

    def set_weather(self, weather, sun=None):
        """Switch the weather preset (None or 'map' for the map's own) and the
        sun (None or 'own' for the weather's) in place: lighting uniforms, fog,
        particles and the sky dome's texture; nothing else reloads."""
        self.weather_preset = weather if weather not in (None, '', 'map') else None
        self.sun = sun if sun not in (None, '', 'own') else None
        self._apply_sky()
        self._lighting()
        self._terrain_lighting()
        if hasattr(self, 'object_program'):
            self._object_lighting()
        # The shadow light follows terrain light 0 (W3DShadowManager::setTimeOfDay).
        self._volume_extrusions()
        lights = self.object_lights
        for entry in self.water:
            u = entry['uniforms']
            u['light0_dir'] = tuple(lights[0][0])
            u['light0_color'] = tuple((2.0 if self.overbright else 1.0)*c for c in lights[0][1])
            if not entry.get('own_specular'):
                u['specular_dir'] = tuple(lights[1][0]) if len(lights) > 1 else (0.0, 0.0, 1.0)
        self._prepare_weather()
        self._weather_gpu()

    # Weather ----------------------------------------------------------------
    def _prepare_weather(self):
        """map.ini Weather over weather.ini: hardware fog and falling particles."""
        from mapworkshop.render.weather import parse, emitters
        map_ini = self.source.parent/'map.ini' if self.source else None
        if self.weather_preset:
            from mapworkshop.mapkit.weather import ini_block
            local = ini_block(self.weather_preset)
        else:
            local = self.map_ini
        sun = ''
        if self.sun:
            from mapworkshop.mapkit.weather import sun_ini
            sun = sun_ini(self.sun)
        self.weather = parse(self.assets.ini_text('weather.ini'), local, sun)
        w = self.weather
        self.report['weather'] = dict(fog=[*w['hardwarefogcolor'], w['hardwarefogstart'], w['hardwarefogend']]
                                      if w['hardwarefogenable'] else None,
                                      particles=w['snowtexture'] if w['issnowing'] and w['snowenabled'] else None)
        self.particles = None
        centers = emitters(w, *self.playable)
        self._weather_centers = centers
        if len(centers):
            self._prepare_image(w['snowtexture'])

    def _weather_gpu(self):
        w, centers = self.weather, self._weather_centers
        texture = self._plain_texture(w['snowtexture']) if len(centers) else None
        if texture is None:
            return
        program = self.ctx.program(vertex_shader=shaders.PARTICLE_VS, fragment_shader=shaders.PARTICLE_FS)
        corners = self.ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], 'f4').tobytes())
        instances = self.ctx.buffer(centers.tobytes())
        vao = self.ctx.vertex_array(program, [(corners, '2f', 'in_corner'), (instances, '3f/i', 'in_emitter')])
        self.particles = dict(program=program, vao=vao, texture=texture, count=len(centers))
        self.report['weather']['particle_count'] = len(centers)

    def _set_fog(self, program, eye):
        w = self.weather
        on = int(w['hardwarefogenable'] and self.visible['weather'])
        for key, value in [('fog_enabled', on), ('fog_color', tuple(w['hardwarefogcolor'])),
                           ('fog_range', (w['hardwarefogstart'], w['hardwarefogend'])), ('fog_eye', eye)]:
            if key in program:
                program[key].value = value

    def _draw_particles(self, vp, camera, eye, time=0.0):
        mgl, ctx = self.moderngl, self.ctx
        p = self.particles['program']
        forward = np.asarray(camera['target'], float) - np.asarray(camera['eye'], float)
        forward /= np.linalg.norm(forward) or 1.0
        right = np.cross(forward, (0.0, 0.0, 1.0))
        if np.linalg.norm(right) < 1e-6:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        p['view_projection'].write(vp)
        p['right'].value = tuple(right)
        w = self.weather
        box = float(max(int(w['snowboxheight']), 1))
        speed = float(w['snowspeed']) or 1.0
        p['size'].value = float(w['snowquadsize'])
        p['box'].value = box
        p['travelled'].value = float(time*w['snowspeed'])
        p['amplitude'].value = float(w['snowamplitude'])
        p['frequency'].value = (float(w['snowfrequencyscalex']), float(w['snowfrequencyscaley']))
        p['drift'].value = (float(time*w['snowxyspeed'][0]), float(time*w['snowxyspeed'][1]))
        p['drift_per_cycle'].value = (float(w['snowxyspeed'][0])*box/speed, float(w['snowxyspeed'][1])*box/speed)
        p['playable'].value = self.playable
        self.particles['texture'].use(0)
        p['tex'].value = 0
        ctx.enable(mgl.BLEND)
        ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
        ctx.fbo.depth_mask = False
        self.particles['vao'].render(mgl.TRIANGLES, instances=self.particles['count'])
        ctx.fbo.depth_mask = True
        ctx.disable(mgl.BLEND)

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

    def _prepare_rivers(self):
        """RiverAreas strips as meshes (render.rivers), with their textures;
        rivers whose minimum LOD is above the WaterLOD are left out, as in game."""
        from mapworkshop.render import rivers
        self.rivers, self._prepared_rivers = [], []
        try:
            areas = records(self.map, 'RiverAreas')
        except ValueError:
            areas = []
        for area in areas:
            mesh = rivers.mesh(area['cross_sections'], area['water_height'])
            if mesh is None or not rivers.drawn(area.get('min_lod'), self.water_level):
                continue
            self._prepared_rivers.append((area, mesh))
            for name in (area['texture'], area['noise'], area['alpha_edge'], area['sparkle']):
                self._prepare_image(name)
        if self._prepared_rivers:
            self.report['rivers'] = [dict(name=a['name'], sections=len(a['cross_sections']), additive=a['additive'])
                                     for a, _ in self._prepared_rivers]

    def _rivers_gpu(self):
        if not self._prepared_rivers:
            return
        self.river_program = program = self.ctx.program(vertex_shader=shaders.RIVER_VS,
                                                        fragment_shader=shaders.RIVER_FS)
        self.river_flow_program = self.ctx.program(vertex_shader=shaders.RIVER_VS,
                                                   fragment_shader=shaders.RIVER_FLOW_FS)
        white = self._plain_texture('', None)
        layout = '3f 2f 1f'
        for area, (vertices, triangles) in self._prepared_rivers:
            vbo = self.ctx.buffer(vertices.tobytes())
            ibo = self.ctx.buffer(triangles.tobytes())
            # RiverWater.fx's samplers s0-s3: river, sparkles, noise, opacity (the alpha edge).
            textures = [self._plain_texture(area[k]) or white for k in ('texture', 'sparkle', 'noise', 'alpha_edge')]
            self.rivers.append(dict(
                vao=self.ctx.vertex_array(program, [(vbo, layout, 'in_position', 'in_uv', 'in_v')],
                                          index_buffer=ibo, index_element_size=4),
                flow_vao=self.ctx.vertex_array(self.river_flow_program, [(vbo, layout, 'in_position', 'in_uv', 'in_v')],
                                               index_buffer=ibo, index_element_size=4),
                length=float(vertices[-1, 5]), textures=textures, color_bytes=tuple(area['color_bytes']),
                alpha=float(area['alpha']), uv_speed=float(area['uv_speed']), additive=int(area['additive'])))
        self._prepared_rivers = []

    def _draw_rivers(self, vp, eye, time, border):
        """The river strips over the standing water, and the flow overlay
        over them when it is on."""
        if self.visible['water']:
            self._draw_river_surfaces(vp, time, border)
        if self.visible['flow']:
            mgl, ctx, p = self.moderngl, self.ctx, self.river_flow_program
            p['view_projection'].write(vp)
            p['time'].value = float(time)
            p['playable'].value = self.playable
            p['show_border'].value = int(border)
            ctx.enable(mgl.BLEND)
            ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
            ctx.fbo.depth_mask = False
            for river in self.rivers:
                p['strip_length'].value = river['length']
                if 'uv_speed' in p:
                    p['uv_speed'].value = river['uv_speed']
                river['flow_vao'].render(mgl.TRIANGLES)
            ctx.fbo.depth_mask = True
            ctx.disable(mgl.BLEND)

    def _draw_river_surfaces(self, vp, time, border):
        """RiverWater.fx's pass: depth test without depth writes, no culling
        and no fog; SRCALPHA onto ONE (additive) or INVSRCALPHA."""
        from mapworkshop.render import rivers
        mgl, ctx, p = self.moderngl, self.ctx, self.river_program
        cache = self.__dict__.setdefault('_water_diffuse', {})
        if self.time_of_day not in cache:
            cache[self.time_of_day] = rivers.water_diffuse((self.assets.ini_text('water.ini'), self.map_ini),
                                                           self.time_of_day)
        water = cache[self.time_of_day]
        p['view_projection'].write(vp)
        p['time'].value = float(time)
        p['playable'].value = self.playable
        p['show_border'].value = int(border)
        for unit, name in enumerate(('river_tex', 'sparkle_tex', 'noise_tex', 'edge_tex'), start=1):
            p[name].value = unit
        ctx.enable(mgl.BLEND)
        ctx.fbo.depth_mask = False
        for river in self.rivers:
            for unit, texture in enumerate(river['textures'], start=1):
                if texture is not None:
                    texture.use(unit)
            p['diffuse'].value = rivers.vertex_colour(river['color_bytes'], self.terrain_ambient,
                                                      self.terrain_lights, water)
            p['opacity'].value = river['alpha']
            p['uv_speed'].value = river['uv_speed']
            ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE if river['additive'] else mgl.ONE_MINUS_SRC_ALPHA)
            river['vao'].render(mgl.TRIANGLES)
        ctx.fbo.depth_mask = True
        ctx.disable(mgl.BLEND)

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

    # Objects ----------------------------------------------------------------
    def _object_texture(self, name, raw=False):
        key = ('raw:' if raw else '') + name.lower()
        if key not in self.textures:
            texture = self._plain_texture(name, raw=raw)
            if texture is None and name:
                self.report['missing_textures'].append(name)
            self.textures[key] = texture
        return self.textures[key]

    def _show_props(self):
        """GameLOD.ini ShowProps of the imitated preset (GlobalData +0x1C):
        without it the shrub buffer and the prop buffer stay empty."""
        current, values = None, {}
        for line in self.assets.ini_text('gamelod.ini').splitlines():
            line = line.split(';')[0].strip()
            match = re.match(r'(?i)StaticGameLOD\s*=\s*(\w+)', line)
            if match:
                current = match.group(1).lower()
                continue
            match = re.match(r'(?i)ShowProps\s*=\s*(\w+)', line)
            if match and current:
                values.setdefault(current, match.group(1).lower() == 'yes')
        return values.get(self.options['lod'], self.options['lod'] not in ('verylow', 'low'))

    def _vertex_array(self, vertices, indices, inst, scales, sway):
        ctx = self.ctx
        vbo = ctx.buffer(np.ascontiguousarray(vertices, dtype='f4').tobytes())
        ibo = ctx.buffer(np.ascontiguousarray(indices, dtype='u4').tobytes())
        vao = ctx.vertex_array(self.object_program,
                               [(vbo, '3f 3f 2f 4f 3f 3f 2f', 'in_position', 'in_normal', 'in_uv', 'in_color',
                                 'in_tangent', 'in_binormal', 'in_uv2'),
                                (inst, '4f/i', 'in_place'), (scales, 'f/i', 'in_scale'), (sway, 'f/i', 'in_sway')],
                               index_buffer=ibo, index_element_size=4)
        self._object_resources += [vao, vbo, ibo]
        return vao

    def set_vegetation_limits(self, value):
        """Keep the game's tree and shrub buffer limits (True) or draw every
        tree and shrub (False). Rebuilds only the objects, their tree shadow
        decals and shadow volumes; terrain, water and weather stay."""
        value = bool(value)
        changed = value != self.options['vegetation_limits']
        self.options['vegetation_limits'] = value
        if not changed or not self.options['objects']:
            return
        for item in getattr(self, '_object_resources', []):
            item.release()
        for name in ('volume_vao', 'volume_buffer', 'volume_program', 'decal_tex', 'object_program'):
            item = getattr(self, name, None)
            if item is not None:
                item.release()
            if hasattr(self, name):
                delattr(self, name)
        self.report.update(missing_models=[], objects_drawn=0, objects_skipped=0)
        self.batches = []
        self._objects_gpu()

    def _object_groups(self):
        """Batches for map objects, as the game sorts them into draw paths.

        `KindOf TREE` and `KindOf SHRUB` templates with a W3DTreeDraw go to
        the tree and shrub buffers with the map angle and the template's
        Scale (a new game creates each one's drawable, whose W3DTreeDraw adds
        it; only a loaded savegame re-adds them with an identity matrix,
        GameLogic 0x00246422). addTree 0x000ECF79 keeps 1,200 trees, the shrub
        add 0x000E91CE 2,000 shrubs and only with ShowProps; they are drawn
        with vegetation.fx.
        Everything else is a W3D render object: fixed-function materials or
        FX materials (normalmapped.fx).
        """
        show_props = self._show_props()
        limits = self.options.get('vegetation_limits', False)
        self._effect_objects = []
        counts = dict(tree=0, shrub=0)
        dropped = dict(tree=0, shrub=0, prop=0)
        types = dict(tree=set(), shrub=set())
        groups = {}
        volumes = {}
        objects = self.map.objects()
        for o in objects:
            name = o['template']
            if o['flags'] & 0x30:
                continue                     # bridge endpoints: _bridges_gpu
            if name.lower().startswith(SKIP_TEMPLATES) or o['flags'] & 6:
                self.report['objects_skipped'] += 1
                continue
            resolved = self.assets.template_model(name)
            if resolved is None:
                self.report['missing_models'].append(name)
                continue
            kinds = resolved['kinds']
            buffer = None
            if resolved['tree']:
                buffer = 'tree' if 'TREE' in kinds else 'shrub' if 'SHRUB' in kinds else 'tree'
            if buffer == 'shrub' and not show_props:
                dropped['shrub'] += 1
                continue
            if buffer is None and resolved.get('prop') and not show_props:
                dropped['prop'] += 1
                continue
            z = float(self.terrain.height_at(o['x'], o['y'])) + o['z']
            from_map = buffer is not None and ('TREE' in kinds or 'SHRUB' in kinds)
            if buffer is not None:
                type_key = (resolved['model'], (resolved['texture'] or '').lower())
                if limits and (counts[buffer] >= (1200 if buffer == 'tree' else 2000)
                               or (type_key not in types[buffer] and len(types[buffer]) >= 64)):
                    dropped[buffer] += 1
                    continue
                counts[buffer] += 1
                types[buffer].add(type_key)
            if from_map:
                # A new game creates the tree's drawable at the map angle and
                # its W3DTreeDraw adds it to the buffer with that orientation
                # and the drawable's scale. The buffer rotates positions only
                # (0x000E7DF3 keeps model-space normals). Zero Hour and BFME1
                # zero the scale randomness there (InstanceScaleFuzziness is
                # applied by WorldBuilder); BFME2's W3DTreeDraw is unmatched.
                angle, scale = o['angle'], resolved['scale']
            else:
                # Deterministic per-object scale variation (InstanceScaleFuzziness).
                fuzz = resolved['fuzziness']
                jitter = ((o['index']*2654435761) % 1000)/999.0*2-1 if fuzz else 0.0
                angle, scale = o['angle'], resolved['scale']*(1+fuzz*jitter)
            # Object::updateObjValuesFromMapProperties: the map's
            # objectPrototypeScale multiplies the drawable's instance scale.
            scale *= self._prototype_scale(o)
            # addTree/addShrub: sway type GetGameClientRandomValue(1, 10), 0
            # for TaintedTree (stand-in: a hash of the object index).
            sway = 0.0 if (buffer is None or resolved['tainted']) else float(1 + (o['index']*2246822519 >> 7) % 10)
            shadow = resolved['shadow']
            kind = shadow_kind(shadow, self.options['shadows'] == 'volume')
            # Shadow maps (High): every object with a Shadow type casts.
            caster = self.options['shadows'] == 'map' and shadow not in ('SHADOW_NONE', 'NONE')
            # KindOf OPTIMIZED_PROP map objects go to the terrain's prop buffer
            # (W3DTerrainVisual::addProp 0x0009257A), which casts no shadow.
            if kind in ('classic', 'v2') and not resolved['tree'] and not self._template_has(name, 'KindOf', 'OPTIMIZED_PROP'):
                volumes.setdefault((resolved['model'], kind), []).append(
                    dict(x=o['x'], y=o['y'], z=z, angle=angle, scale=scale, ground=z-o['z'],
                         length_scale=self._template_float(name, 'ShadowSizeX')))
            # Optimized trees and shrubs (W3DTreeDraw) draw the template's
            # ShadowTexture when their Shadow is SHADOW_DECAL (addTreeType:
            # doShadow = shadowKind == 1). Without one they draw the default
            # decal, as native captures show: the shadow managers take
            # "shadow" for a name of one character or less (Zero Hour
            # createDecalShadow, BFME2 addShadow); the tree buffer's own
            # decal draw is unmatched.
            decal = None
            if resolved['tree'] and shadow == 'SHADOW_DECAL':
                decal = self._template_value(name, 'ShadowTexture') or 'shadow'
                if self.assets.texture_key(decal) is None:
                    decal = 'shadow'
            sky = 'SKYBOX' in kinds
            # The water reflection draws the tree buffer and KindOf
            # CAN_CAST_REFLECTIONS objects (sky domes have it), not the
            # shrub buffer, the terrain or other objects (Reflection Lab
            # game screenshots at High, 15 October 2026).
            reflects = buffer == 'tree' or 'CAN_CAST_REFLECTIONS' in kinds
            key = (resolved['model'], resolved['texture'], caster, decal, buffer, bool(resolved.get('prop')), sky, reflects)
            groups.setdefault(key, []).append((o['x'], o['y'], z, angle, scale, sway))
            if buffer is None and not resolved.get('prop'):
                # A drawable in the scene runs its emitters and particle
                # systems; the prop buffer (W3DPropDraw) never adds its
                # render objects to a scene, so their emitters stay idle.
                self._effect_objects.append((name, resolved['model'], o['x'], o['y'], z, angle, scale, o['index']))
        self.report['vegetation'] = dict(trees=counts['tree'], shrubs=counts['shrub'],
                                         trees_dropped=dropped['tree'], shrubs_dropped=dropped['shrub'],
                                         props_hidden=dropped['prop'], show_props=show_props, limits=limits,
                                         technique='Default' if self.options['lod'] in ('high', 'ultrahigh') else 'Default_L')
        return groups, volumes, objects

    def _objects_gpu(self):
        self._prepared_objects = self._object_groups()
        self._prepare_models()
        self._prepare_volumes(self._prepared_objects[1])
        self._prepared_volume_triangles = self._volume_triangles()
        for _ in self._objects_steps():
            pass
        self._draw_batches = sorted(self.batches, key=lambda b: (not b['vegetation'], b['blend'] is not None and not b['depth_mask']))

    def _prepare_models(self):
        """Decode models and their texture pixels before any GPU work begins."""
        groups, _, objects = self._prepared_objects
        names = set()

        def textures(model):
            for part in (model or {}).get('parts', []):
                names.update((part.get('texture'), part.get('detail_texture')))
                fx = part.get('fx') or {}
                names.update(value for key, value in fx.items()
                             if ('texture' in key.lower() or key == 'NormalMap') and isinstance(value, str))
                if fx.get('__shader__', '').lower() == 'normalmapped.fx':
                    self._effect('normalmapped.fx')

        for index, (model, override, caster, decal, buffer, prop, sky, _) in enumerate(groups):
            self._progress(0.38 + 0.25*index/max(len(groups), 1), f'Preparing models {index+1}/{len(groups)}: {model}')
            names.update((override, decal))
            if buffer is not None:
                tree = self.model_cache.load_tree(model)
                if tree:
                    names.add(tree.get('texture'))
            else:
                textures(self.model_cache.load(model))
        from mapworkshop.mapkit.bridges import bridge_types
        from mapworkshop.render.bridges import endpoint_pairs
        pairs = endpoint_pairs(objects)
        if pairs:
            types = {k.lower(): v for k, v in bridge_types(self.assets.ini_text('roads.ini')+'\n'+self.map_ini).items()}
            for a, _ in pairs:
                kind = types.get(a['template'].lower())
                if kind and kind['model']:
                    textures(self.model_cache.load(kind['model'].lower()))
                    names.add(kind['texture'])
        from mapworkshop.mapkit.weather import PRESETS, SUNS, sky_texture
        sky = (SUNS[self.sun].get('sky') if self.sun else None) or \
              (PRESETS[self.weather_preset].get('sky') if self.weather_preset else None)
        if sky:
            names.add(sky_texture(sky))
        for name in names:
            self._progress(0.64, 'Preparing object textures')
            self._prepare_image(name)
        self._prepare_effects()

    def _prepare_effects(self):
        """Emitters and particle systems of the placed objects (render.effects)."""
        effects = Effects(self.assets, self.options['lod'])
        for template, model, x, y, z, angle, scale, index in getattr(self, '_effect_objects', []):
            effects.add(template, self.model_cache.load(model), x, y, z, angle, scale, index)
        self.effects = effects.finish()
        # Additive particles draw the colour under zero alpha, so their
        # textures are kept as they are (no bleed_alpha).
        self._effect_images = {name: self.assets.image(name) for name in effects.textures()}
        self.report['effects'] = dict(emitters=effects.report['emitters'], systems=effects.report['systems'],
                                      skipped=dict(sorted(effects.report['skipped'].items())))

    def _objects_steps(self):
        ctx = self.ctx
        self._object_resources = []
        self.sky_horizon = None
        self.object_program = ctx.program(vertex_shader=shaders.OBJECT_VS, fragment_shader=shaders.OBJECT_FS)
        self._object_uniforms = frozenset(self.object_program)
        self.object_program['clip_z'].value = -1e30
        self._object_lighting()
        groups, volumes, objects = self._prepared_objects
        decals = {}
        fx_report = {}
        for index, ((model, texture_override, caster, decal, buffer, prop, sky, reflects), instances) in enumerate(groups.items()):
            self._progress(0.80+0.18*index/max(len(groups), 1), f'Uploading objects {index+1}/{len(groups)}: {model}')
            yield
            inst = ctx.buffer(np.array([i[:4] for i in instances], 'f4').tobytes())
            scales = ctx.buffer(np.array([i[4] for i in instances], 'f4').tobytes())
            sway = ctx.buffer(np.array([i[5] for i in instances], 'f4').tobytes())
            self._object_resources += [inst, scales, sway]
            if buffer is not None:
                tree = self.model_cache.load_tree(model)
                if tree is None:
                    self.report['missing_models'].append(model)
                    continue
                n = len(tree['positions'])
                zeros = np.zeros((n, 3), np.float32)
                vertices = np.hstack([tree['positions'], tree['normals'], tree['uv'], tree['colors'], zeros, zeros, tree['uv']])
                # TextureName (+ '.tga') replaces the model texture in the atlas.
                name_t = texture_override or tree['texture']
                self.batches.append(dict(
                    vao=self._vertex_array(vertices, tree['indices'], inst, scales, sway),
                    caster=caster, texture=self._object_texture(name_t), count=len(instances),
                    technique=2 if self.options['lod'] in ('high', 'ultrahigh') else 1,
                    vegetation=True, cull=True, depth_mask=True, alpha_ref=96/255,
                    # Vegetation.IsAlphaBlendEnabled: trees blend (slot 4 of the
                    # tree buffer returns false), shrubs do not.
                    blend=('src_alpha', 'one_minus_src_alpha') if buffer == 'tree' else None,
                    mode='alphatest', uniforms={}, scaled=True, reflects=reflects))
                self.report['objects_drawn'] += len(instances)
                if decal:
                    # W3DTreeBuffer: one size per tree type, the sum of the model's
                    # half extents; the decal is centred on the tree.
                    lo, hi = tree['bounds']
                    size = float((hi[0]-lo[0])/2+(hi[1]-lo[1])/2)
                    decals.setdefault(decal, []).extend((i[0], i[1], size) for i in instances)
                continue
            loaded = self.model_cache.load(model)
            if loaded is None:
                self.report['missing_models'].append(model)
                continue
            for part in loaded['parts']:
                yield
                n = len(part['positions'])
                tangents = part['tangents'] if part['tangents'] is not None else np.zeros((n, 3), np.float32)
                binormals = part['binormals'] if part['binormals'] is not None else np.zeros((n, 3), np.float32)
                vertices = np.hstack([part['positions'], part['normals'], part['uv'], part['colors'], tangents, binormals,
                                      part.get('uv2', part['uv'])])
                batch = self._material_batch(part, texture_override, fx_report)
                batch.update(vao=self._vertex_array(vertices, part['indices'], inst, scales, sway),
                             caster=caster, count=len(instances), vegetation=False, scaled=not prop, sky=sky,
                             reflects=reflects,
                             camera=part.get('camera', 0), pivot=tuple(float(v) for v in part.get('pivot', (0, 0, 0))),
                             grid=part['material'].get('grid'))
                self.batches.append(batch)
                if sky:
                    z = part['positions'][:, 2]
                    batch['sky_own'] = (batch['texture'], (part.get('fx') or {}).get('Texture_0') or part['texture'])
                    batch['sky_rim_uv'] = part['uv'][z <= z.min() + 1.0]
                    if self.sky_horizon is None:
                        self.sky_horizon = self._horizon_color(batch['sky_own'][1], batch['sky_rim_uv'])
                    z = part['positions'][:, 2]
                    lowest = min(i[2] + float(z.min())*i[4] for i in instances)
                    span = float(z.max() - z.min())*max(i[4] for i in instances)
                    batch['uniforms'].update(sky_horizon=self.sky_horizon or (0.0, 0.0, 0.0),
                                             sky_rim=(lowest, 0.18*span if self.sky_horizon else 0.0))
                elif batch['technique'] == 5:
                    batch['uniforms']['sky_rim'] = (0.0, 0.0)
            self.report['objects_drawn'] += len(instances)
        yield
        yield from self._bridges_steps(objects, fx_report)
        self.report['fx_materials'] = fx_report
        self.decal_count = sum(len(v) for v in decals.values())
        if decals and self.options['decals']:
            self._bake_decals(decals)
        yield
        self._upload_volumes(self._prepared_volume_triangles)
        self.report['missing_models'] = sorted(set(self.report['missing_models']))
        self._apply_sky()
        self._effects_gpu()

    def _effects_gpu(self):
        ctx = self.ctx
        self.effect_program = ctx.program(vertex_shader=shaders.EFFECT_VS, fragment_shader=shaders.EFFECT_FS)
        self.effect_corners = {}
        for shape, corners in (('quad', QUAD_CORNERS), ('tri', TRI_CORNERS)):
            self.effect_corners[shape] = ctx.buffer(corners.tobytes())
        self.effect_textures = {}
        for name, image in getattr(self, '_effect_images', {}).items():
            if image is None:
                self.report['missing_textures'].append(name)
                continue
            texture = ctx.texture((image.shape[1], image.shape[0]), 4, np.ascontiguousarray(image).tobytes())
            texture.build_mipmaps()
            texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
            texture.repeat_x = texture.repeat_y = False
            self.effect_textures[name.lower()] = texture
        self._object_resources += [self.effect_program, *self.effect_corners.values(), *self.effect_textures.values()]
        self.__dict__.pop('_effect_images', None)

    def _draw_effects(self, vp, camera, eye, time):
        """Particles of object effects at `time`: camera-facing quads or
        triangles (PointGroupClass), ground-aligned quads flat on the ground,
        drawn without depth writes; alpha-blended groups first, each sorted
        back to front, then additive ones. Fog fades additive particles to
        black and multiplicative ones to white."""
        groups = self.effects.particles(time)
        if not groups:
            return
        mgl, ctx = self.moderngl, self.ctx
        p = self.effect_program
        forward = np.asarray(camera['target'], float) - np.asarray(camera['eye'], float)
        forward /= np.linalg.norm(forward) or 1.0
        right = np.cross(forward, (0.0, 0.0, 1.0))
        right = right/np.linalg.norm(right) if np.linalg.norm(right) > 1e-6 else np.array([1.0, 0.0, 0.0])
        up = np.cross(right, forward)
        p['view_projection'].write(vp)
        self._set_fog(p, eye)
        p['tex'].value = 0
        ctx.enable(mgl.BLEND)
        ctx.fbo.depth_mask = False
        order = sorted(groups, key=lambda g: g[1] == ('one', 'one'))
        for texture_name, blend, alpha_ref, depth_test, shape, ground in order:
            texture = self.effect_textures.get(texture_name)
            if texture is None:
                continue
            rows = groups[(texture_name, blend, alpha_ref, depth_test, shape, ground)]
            if blend != ('one', 'one'):
                rows = rows[np.argsort(-np.linalg.norm(rows[:, :3] - np.asarray(eye, np.float32), axis=1))]
            p['right'].value = (1.0, 0.0, 0.0) if ground else tuple(right)
            p['up'].value = (0.0, 1.0, 0.0) if ground else tuple(up)
            p['alpha_ref'].value = -1.0 if alpha_ref is None else float(alpha_ref)
            p['fog_mode'].value = 1 if blend == ('one', 'one') else 2 if blend == ('zero', 'src_color') else 0
            ctx.blend_func = self._blend_func(blend)
            if depth_test:
                ctx.enable(mgl.DEPTH_TEST)
            else:
                ctx.disable(mgl.DEPTH_TEST)
            texture.use(0)
            instances = ctx.buffer(np.ascontiguousarray(rows, np.float32).tobytes())
            vao = ctx.vertex_array(p, [(self.effect_corners[shape], '4f', 'in_corner'),
                                       (instances, '3f f 4f f 3f/i', 'in_center', 'in_size', 'in_color', 'in_angle',
                                        'in_frame')])
            vao.render(mgl.TRIANGLES, vertices=6 if shape == 'quad' else 3, instances=len(rows))
            vao.release()
            instances.release()
        ctx.enable(mgl.DEPTH_TEST)
        ctx.fbo.depth_mask = True
        ctx.disable(mgl.BLEND)

    def walkable_overlay(self):
        """Local walkability as an overlay texture and its world extent.
        self.walkable holds the analysis: categories and cut-off areas."""
        if not hasattr(self, '_walk'):
            self.install_walkability(self.compute_walkability())
        return self._walk

    def compute_walkability(self):
        """CPU-only analysis; do not mutate the live renderer on a worker."""
        from mapworkshop.mapkit import pathing, walkable
        models = ModelCache(self.pathing_assets)
        models.cache = dict(self.model_cache.cache)
        grid = pathing.compute(self.map, assets=self.pathing_assets, map_ini=self.map_ini, models=models)
        result = walkable.analyse(grid, self.map)
        result['info'] = grid['info']
        return result, np.ascontiguousarray(walkable.overlay(result))

    def walkability_task(self):
        """Capture CPU data only; a worker must never own live GPU resources."""
        from functools import partial
        from types import SimpleNamespace
        data = SimpleNamespace(map=self.map, pathing_assets=self.pathing_assets,
                               map_ini=self.map_ini, model_cache=self.model_cache)
        return partial(MapRenderer.compute_walkability, data)

    def install_walkability(self, prepared):
        """Install a worker result on the context-owning thread."""
        from mapworkshop.mapkit import walkable
        self.walkable, rgba = prepared
        h, w = rgba.shape[:2]
        texture = self.ctx.texture((w, h), 4, rgba.tobytes())
        texture.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        texture.repeat_x = texture.repeat_y = False
        self._walk = (texture, (w*walkable.CELL, h*walkable.CELL))

    def _bridges_steps(self, objects, fx_report):
        """Bridges the game spans between two map objects flagged 0x10 and
        0x20 (render.bridges): their Bridge type (roads.ini or the map's
        map.ini) names the model, texture and BridgeScale. Drawn as lit
        objects; the game lights them like terrain (doTheLight), and their
        damaged states are not drawn."""
        from mapworkshop.mapkit.bridges import bridge_types
        from mapworkshop.render.bridges import FLOAT, endpoint_pairs, layout, pieces, place
        pairs = endpoint_pairs(objects)
        self.report['bridges'] = []
        if not pairs:
            return
        types = {k.lower(): v for k, v in bridge_types(self.assets.ini_text('roads.ini') + chr(10) + self.map_ini).items()}
        identity = self.ctx.buffer(np.zeros(4, 'f4').tobytes())
        one = self.ctx.buffer(np.ones(1, 'f4').tobytes())
        still = self.ctx.buffer(np.zeros(1, 'f4').tobytes())
        self._object_resources += [identity, one, still]
        for a, b in pairs:
            yield
            entry = dict(type=a['template'], start=[round(a['x']), round(a['y'])], end=[round(b['x']), round(b['y'])])
            self.report['bridges'].append(entry)
            kind = types.get(a['template'].lower())
            model = self.model_cache.load(kind['model'].lower()) if kind and kind['model'] else None
            plan = None
            if model is not None:
                ends = [(o['x'], o['y'], float(self.terrain.height_at(o['x'], o['y'])) + o['z'] + FLOAT) for o in (a, b)]
                found = pieces(model)
                plan = layout(found, ends[0], ends[1], kind['scale'])
            if plan is None:
                entry['drawn'] = False
                self.report['missing_models'].append(f"bridge {a['template']}")
                continue
            entry.update(drawn=True, model=kind['model'], spans=plan['spans'])
            texture = kind['texture']
            for piece, offset in plan['draw']:
                for part in found[piece]:
                    yield
                    positions, normals = place(part, offset, plan, ends[0])
                    n = len(positions)
                    zeros = np.zeros((n, 3), np.float32)
                    vertices = np.hstack([positions, normals, part['uv'], part['colors'], zeros, zeros, part['uv']])
                    batch = self._material_batch(dict(part, fx=None), texture, fx_report)
                    batch.update(vao=self._vertex_array(vertices, part['indices'], identity, one, still),
                                 caster=False, count=1, vegetation=False, scaled=True, sky=False, cull=False)
                    self.batches.append(batch)
            self.report['objects_drawn'] += 2

    def _material_batch(self, part, texture_override, fx_report):
        """Render states and uniforms of one W3D material."""
        fx = part['fx']
        state = part['state']
        lod = self.options['lod']
        if fx is not None and fx.get('__shader__', '').lower() == 'normalmapped.fx':
            from mapworkshop.render.water import technique as pick
            effect = self._effect('normalmapped.fx')
            names = [t['name'] for t in effect.techniques] if effect else []
            lod_index = dict(verylow=0, low=0, medium=1, high=2, ultrahigh=3).get(lod, 1)
            name = pick(names, fx.get('__technique__', 0), lod_index) if names else None
            one = lambda key, default: float((fx.get(key) or (default,))[0])
            vec = lambda key, default, n: tuple(float(v) for v in (tuple(fx.get(key) or ()) + default[len(fx.get(key) or ()):])[:n])
            entry = fx_report.setdefault('normalmapped.fx', dict(technique=name, meshes=0))
            entry['meshes'] += 1
            if name not in ('Default_M', 'Default_L'):
                entry['approximated'] = f'{name} drawn with the Default_M port'
            opacity = one('OpacityOverride', 1.0)
            normal = fx.get('NormalMap')
            return dict(texture=self._object_texture(fx.get('DiffuseTexture') or part['texture']),
                        normal=self._object_texture(normal) if isinstance(normal, str) else None,
                        technique=4 if name == 'Default_L' else 3, cull=True, depth_mask=True,
                        alpha_ref=96/255 if fx.get('AlphaTestEnable') else None,
                        blend=('src_alpha', 'one_minus_src_alpha') if opacity < 1 else None,
                        mode='alphatest' if fx.get('AlphaTestEnable') else 'opaque',
                        uniforms=dict(fx_ambient_color=vec('AmbientColor', (0.4, 0.4, 0.4), 3),
                                      fx_diffuse=vec('DiffuseColor', (1.0, 1.0, 1.0, 1.0), 4),
                                      fx_specular=vec('SpecularColor', (0.8, 0.8, 0.8), 3),
                                      fx_exponent=one('SpecularExponent', 50.0), fx_bump=one('BumpScale', 1.0),
                                      fx_opacity=opacity))
        if fx is not None and fx.get('__shader__', '').lower() == 'simple.fx':
            # simple.fx Default (sky domes): texture x ColorEmissive, unlit,
            # fogged only with FogEnable; UV = uv x TexCoordTransform_0.xy
            # (+ Time x zw, not animated here).
            fx_report.setdefault('simple.fx', dict(meshes=0))['meshes'] += 1
            emissive = tuple(float(v) for v in (tuple(fx.get('ColorEmissive') or ()) + (1.0, 1.0, 1.0))[:3])
            transform = tuple(fx.get('TexCoordTransform_0') or (1.0, 1.0, 0.0, 0.0))
            blend = fx.get('AlphaBlendingEnable')
            return dict(texture=self._object_texture(fx.get('Texture_0') or part['texture']), normal=None,
                        technique=5, cull=True, depth_mask=bool(fx.get('DepthWriteEnable', True)),
                        alpha_ref=None, blend=('src_alpha', 'one_minus_src_alpha') if blend else None,
                        mode='blend' if blend else 'opaque',
                        uniforms=dict(fx_emissive=emissive, fx_fog=int(bool(fx.get('FogEnable', True))),
                                      fx_uv_scale=(float(transform[0]), float(transform[1]))))
        if fx is not None:
            # Other effects are drawn as a lit, textured fixed-function material.
            name = fx.get('__shader__', '?').lower()
            fx_report.setdefault(name, dict(meshes=0, approximated='fixed-function stand-in'))['meshes'] += 1
        material, sources = part['material'], part['sources']
        texture = texture_override or part['texture']
        # Texture stage 1 (DetailColorFunc), drawn for the functions the
        # fragment shader knows; others leave stage 0 as it is.
        detail = state.get('detail', 0) if part.get('detail_texture') and state['texturing'] else 0
        # Without alpha blending or testing the texture's alpha is unused, and
        # additive glows keep their colour under zero alpha: draw it as stored.
        raw = state['blend'] is not None and state['blend'][0] != 'src_alpha' and state['alpha_ref'] is None
        return dict(texture=self._object_texture(texture, raw) if state['texturing'] and texture else None,
                    detail=self._object_texture(part['detail_texture'], raw) if detail else None,
                    normal=None, technique=0, cull=not part['two_sided'], depth_mask=state['depth_mask'],
                    alpha_ref=None if state['alpha_ref'] is None else state['alpha_ref']/255,
                    blend=state['blend'], mode=part['mode'],
                    uniforms=dict(mat_ambient=tuple(material['ambient']), mat_diffuse=tuple(material['diffuse']),
                                  mat_emissive=tuple(material['emissive']), mat_opacity=float(material['opacity']),
                                  ambient_from_vertex=int(sources['ambient']),
                                  diffuse_from_vertex=int(sources['diffuse']), lighting=int(sources['lighting']),
                                  gradient=state['gradient'] if state['gradient'] in (0, 1, 2) else 1,
                                  texturing=int(state['texturing']), detail_func=detail))
    @staticmethod
    def _prototype_scale(o):
        for name, _, value in o.get('properties') or ():
            if name == 'objectPrototypeScale':
                try:
                    return float(value) if float(value) > 0 else 1.0
                except (TypeError, ValueError):
                    return 1.0
        return 1.0

    def _template_value(self, template, key):
        """A template's INI value for `key`, inherited through ObjectReskin/ChildObject."""
        name, seen = template.lower(), set()
        while name and name not in seen:
            seen.add(name)
            entry = self.assets.templates.get(name)
            if entry is None:
                return None
            match = re.search(r'(?im)^\s*' + key + r'\s*=\s*([^\s;]+)', entry['body'])
            if match:
                return match.group(1)
            name = entry['parent']
        return None

    def _template_has(self, template, key, word):
        """Whether a template's (inherited) `key` line lists `word`."""
        name, seen = template.lower(), set()
        while name and name not in seen:
            seen.add(name)
            entry = self.assets.templates.get(name)
            if entry is None:
                return False
            match = re.search(r'(?im)^\s*' + key + r'\s*=([^;\r\n]*)', entry['body'])
            if match:
                return word.upper() in match.group(1).upper().split()
            name = entry['parent']
        return False

    def _template_float(self, template, key):
        try:
            return float(self._template_value(template, key) or 0.0)
        except ValueError:
            return 0.0

    # Shadow volumes ---------------------------------------------------------
    def _prepare_volumes(self, volumes):
        """Static GPU data for SHADOW_VOLUME / SHADOW_VOLUME_NEW casters."""
        from mapworkshop.render.shadows import shadow_geometry
        self.volumes = []
        self.volume_vao = None
        if not volumes:
            return
        counts = dict(classic=0, v2=0, without_geometry=0)
        for (model, kind), instances in volumes.items():
            loaded = self.model_cache.load(model)
            meshes = [m for m in (loaded or {}).get('shadow', [])
                      if not (kind == 'v2' and m['hidden'] and 'SHADOW' not in m['name'].upper())]
            if not meshes:
                # No CAST_SHADOW mesh: the game builds no shadow geometry.
                counts['without_geometry'] += len(instances)
                continue
            counts[kind] += len(instances)
            lo, hi = loaded['bounds']
            place = np.array([(i['x'], i['y'], i['z'], i['angle']) for i in instances])
            scale = np.array([i['scale'] for i in instances])
            for mesh in meshes:
                geometry = shadow_geometry(mesh['positions'], mesh['indices'])
                if not len(geometry['triangles']):
                    continue
                self.volumes.append(dict(model=model, kind=kind, geometry=geometry, instances=instances,
                                         place=place, scale=scale,
                                         mesh_top=float(mesh['positions'][:, 2].max()), bounds=(lo, hi)))
        self.report['shadow_volumes'] = counts

    def _volume_extrusions(self):
        self._upload_volumes(self._volume_triangles())

    def _volume_triangles(self):
        """Shadow volume triangles for the current light (see render.shadows)."""
        from mapworkshop.render.shadows import classic_extrusion, classic_floor, silhouette_quads, v2_offset, world_box
        direction = -np.asarray(self.sun_dir, float)
        direction /= np.linalg.norm(direction) or 1.0
        height_at = self.terrain.height_at
        min_height = float(self.terrain.heights.min())
        floors = {}
        parts = []
        for entry in getattr(self, 'volumes', []):
            vectors = []
            for i in entry['instances']:
                if entry['kind'] == 'v2':
                    vectors.append(v2_offset(i['z'], i['ground'], float(entry['bounds'][1][2])*i['scale'],
                                             direction, i['length_scale']))
                    continue
                key = id(i)
                if key not in floors:
                    box = world_box(entry['bounds'], i['x'], i['y'], i['z'], i['angle'], i['scale'])
                    floors[key] = classic_floor(box, i['z'], i['ground'], height_at, direction, min_height)
                vectors.append(classic_extrusion(i['z'] + entry['mesh_top']*i['scale'], floors[key], direction))
            entry['extrude'] = np.asarray(vectors, float).reshape(-1, 3)
            parts.append(silhouette_quads(entry['geometry'], entry['place'], entry['scale'], entry['extrude']))
        return np.concatenate(parts) if parts else np.zeros((0, 3, 3), np.float32)

    def _upload_volumes(self, triangles):
        if getattr(self, 'volume_vao', None) is not None:
            self.volume_vao.release()
            self.volume_buffer.release()
            self.volume_vao = None
        if not hasattr(self, 'volume_program'):
            self.volume_program = self.ctx.program(vertex_shader=shaders.VOLUME_VS, fragment_shader=shaders.VOLUME_FS)
        self.volume_vertices = len(triangles)*3
        if self.volume_vertices:
            self.volume_buffer = self.ctx.buffer(np.ascontiguousarray(triangles, 'f4').tobytes())
            self.volume_vao = self.ctx.vertex_array(self.volume_program,
                                                    [(self.volume_buffer, '3f', 'in_position')])

    def _volume_pass(self, camera, size):
        """Stencil count of the shadow volumes against the receivers' depth.

        Receivers are what is in the depth buffer when renderStencilShadows
        runs: terrain, opaque and alpha-tested objects, trees and water (its
        passes write depth, and native captures show volume shadows on the
        water surface); translucent meshes are flushed afterwards
        (RTS3DScene flush 0x000716E7..0x00071D2C). Returns the count texture
        or None."""
        ctx, mgl = self.ctx, self.moderngl
        if not self.volumes or not any(v['kind'] == 'classic' for v in self.volumes):
            # The full-screen shadow pass belongs to the classic manager and
            # runs only while it has shadows (renderShadows' m_shadowList).
            return None
        if getattr(self, 'volume_size', None) != size:
            for name in ('volume_fbo', 'volume_depth_fbo', 'volume_count', 'volume_depth'):
                if hasattr(self, name):
                    getattr(self, name).release()
            self.volume_size = size
            self.volume_depth = ctx.depth_texture(size)
            self.volume_count = ctx.texture(size, 1, dtype='f4')
            self.volume_count.filter = (mgl.NEAREST, mgl.NEAREST)
            self.volume_depth_fbo = ctx.framebuffer(depth_attachment=self.volume_depth)
            self.volume_fbo = ctx.framebuffer([self.volume_count], self.volume_depth)
        vp = np.ascontiguousarray(camera['view_projection'].T, dtype='f4').tobytes()
        # One clear for both: clearing the count framebuffer also clears depth.
        self.volume_fbo.use()
        ctx.viewport = (0, 0, *size)
        self.volume_fbo.clear(0.0, 0.0, 0.0, 0.0, depth=1.0)
        self.volume_depth_fbo.use()
        ctx.viewport = (0, 0, *size)
        ctx.enable(mgl.DEPTH_TEST)
        ctx.disable(mgl.CULL_FACE)
        p = self.terrain_program
        p['view_projection'].write(vp)
        p['use_shadows'].value = 0
        self.heights.use(0); self.cells.use(1); self.albedo.use(2); self.normal_array.use(3)
        self.terrain_vao.render(mgl.TRIANGLES, vertices=self.terrain_vertices)
        if self.visible['objects']:
            op = self.object_program
            op['view_projection'].write(vp)
            op['depth_only'].value = 1
            op['use_shadows'].value = 0
            for batch in self.batches:
                # Receivers' depth: everything that writes depth (the tree
                # buffer blends but still writes depth).
                if not batch['depth_mask']:
                    continue
                self._bind_batch(op, batch)
                batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
            op['depth_only'].value = 0
        if self.water and self.visible['water']:
            self.water_depth_program['view_projection'].write(vp)
            for entry in self.water:
                entry['depth_vao'].render(mgl.TRIANGLES)
        self.volume_fbo.use()
        # Depth writes are a framebuffer state in moderngl (glDepthMask); the
        # volume faces must not occlude each other.
        ctx.fbo.depth_mask = False
        ctx.depth_func = '<='
        ctx.enable(mgl.BLEND)
        ctx.blend_func = (mgl.ONE, mgl.ONE)
        if self.volume_vao is not None:
            self.volume_program['view_projection'].write(vp)
            self.volume_vao.render(mgl.TRIANGLES, vertices=self.volume_vertices)
        ctx.disable(mgl.BLEND)
        ctx.fbo.depth_mask = True
        ctx.depth_func = '<'
        return self.volume_count

    # Drawing ----------------------------------------------------------------
    # Shadow decals ----------------------------------------------------------
    def _bake_decals(self, decals, texel=2.0):
        """Multiply tree shadow decals into a world-space texture (top-down).

        `decals` maps a ShadowTexture name to (x, y, size) items. The tree and
        shrub buffers pack each type's ShadowTexture into a shadow atlas; the
        quads are drawn multiplicatively onto the terrain, straight down.
        """
        ctx, mgl = self.ctx, self.moderngl
        t = self.terrain
        b = t.border*10
        x0, y0 = -b, -b
        w, h = (t.width-1)*10, (t.height-1)*10
        size = (int(min(16384, w/texel)), int(min(16384, h/texel)))
        texture = ctx.texture(size, 4)
        texture.filter = (mgl.LINEAR, mgl.LINEAR)
        texture.repeat_x = texture.repeat_y = False
        fbo = ctx.framebuffer([texture])
        fbo.use(); ctx.viewport = (0, 0, *size)
        fbo.clear(1.0, 1.0, 1.0, 1.0)
        program = ctx.program(vertex_shader=shaders.DECAL_VS, fragment_shader=shaders.DECAL_FS)
        program['world_to_clip'].value = (2/w, 2/h, -1-2*x0/w, -1-2*y0/h)
        corners = ctx.buffer(np.array([-.5, -.5, .5, -.5, .5, .5, -.5, -.5, .5, .5, -.5, .5], 'f4').tobytes())
        ctx.disable(mgl.DEPTH_TEST)
        ctx.enable(mgl.BLEND)
        ctx.blend_func = (mgl.DST_COLOR, mgl.ZERO)
        drawn = 0
        for name, items in decals.items():
            shadow = self._plain_texture(name)
            if shadow is None:
                continue
            shadow.repeat_x = shadow.repeat_y = False
            shadow.use(0); program['tex'].value = 0
            instances = ctx.buffer(np.array(items, 'f4').tobytes())
            vao = ctx.vertex_array(program, [(corners, '2f', 'in_corner'), (instances, '3f/i', 'in_decal')])
            vao.render(mgl.TRIANGLES, instances=len(items))
            drawn += len(items)
            vao.release(); instances.release()
        ctx.disable(mgl.BLEND)
        for item in (corners, program, fbo):
            item.release()
        decals = [None]*drawn
        self.decal_tex = texture
        p = self.terrain_program
        p['decal_tex'].value = 7
        p['decal_xform'].value = (1/w, 1/h, -x0/w, -y0/h)
        self.report['shadow_decals'] = len(decals)

    # Shadows ----------------------------------------------------------------
    def _light_projection(self, camera, bounds=None, max_radius=12000.0):
        """Orthographic sun projection covering the camera's ground footprint.

        `bounds` (x0, y0, x1, y1) replaces the footprint for top views. When the
        footprint exceeds `max_radius`, the area around the camera target wins.
        """
        from mapworkshop.render.camera import look_at, orthographic
        if bounds is not None:
            x0, y0, x1, y1 = bounds
        else:
            inv = np.linalg.inv(camera['view_projection'])
            ground = float(camera['target'][2])
            xs, ys = [], []
            for sx in (-1, 0, 1):
                for sy in (-1, 0, 1):
                    near = inv @ np.array([sx, sy, -1, 1.0]); near = near[:3]/near[3]
                    far = inv @ np.array([sx, sy, 1, 1.0]); far = far[:3]/far[3]
                    d = far-near
                    t = (ground-near[2])/d[2] if abs(d[2]) > 1e-6 else 1.0
                    hit = near + d*min(max(t, 0.0), 1.0)
                    xs.append(hit[0]); ys.append(hit[1])
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        center = np.array([(x0+x1)/2, (y0+y1)/2, float(self.terrain.heights.mean())])
        radius = 0.5*math.hypot(x1-x0, y1-y0)+300
        if radius > max_radius:
            radius = max_radius
            if bounds is None:
                center[:2] = camera['target'][:2]
        top = float(self.terrain.heights.max())+radius+2000
        eye = center + np.array(self.sun_dir)*(top+radius)
        view_m = look_at(eye, center, up=(0, 1, 0) if abs(self.sun_dir[2]) < 0.99 else (1, 0, 0))
        depth = 2*(top+radius)
        proj = orthographic(-radius, radius, -radius, radius, 1.0, depth+radius)
        return proj @ view_m, radius, depth

    def _shadow_settings(self):
        """environment.ini ShadowMap block: MapSize texels over MaxViewDistance."""
        values = dict(mapsize=1024.0, maxviewdistance=1500.0)
        try:
            block = re.search(r'(?ims)^\s*ShadowMap\b(.*?)^\s*End\b', self.assets.ini_text('environment.ini'))
            for key, value in re.findall(r'(?im)^\s*(MapSize|MaxViewDistance)\s*=\s*([\d.]+)', block.group(1) if block else ''):
                values[key.lower()] = float(value)
        except (OSError, FileNotFoundError):
            pass
        # The map spans the shadowed range on both sides of the camera.
        values['texel'] = 2*values['maxviewdistance']/values['mapsize']
        return values

    def _shadow_pass(self, light_vp, radius, max_size=16384):
        ctx, mgl = self.ctx, self.moderngl
        # Shadow maps use the game's texel size so edges are equally soft;
        # stencil volumes are exact, approximated here by a fine map.
        texel = self.shadow_settings['texel'] if self.options['shadows'] == 'map' else 0.75
        size = int(min(max_size, max(256, round(2*radius/texel))))
        if getattr(self, 'shadow_size', None) != size:
            if hasattr(self, 'shadow_texture'):
                self.shadow_fbo.release(); self.shadow_texture.release()
            self.shadow_size = size
            self.shadow_texture = ctx.depth_texture((size, size))
            self.shadow_texture.compare_func = '<='
            # Retail shaders compare point samples (no hardware filtering).
            self.shadow_texture.filter = (mgl.NEAREST, mgl.NEAREST)
            self.shadow_texture.repeat_x = self.shadow_texture.repeat_y = False
            self.shadow_fbo = ctx.framebuffer(depth_attachment=self.shadow_texture)
        self.shadow_fbo.use()
        ctx.viewport = (0, 0, size, size)
        self.shadow_fbo.clear(depth=1.0)
        ctx.enable(mgl.DEPTH_TEST)
        op = self.object_program
        op['view_projection'].write(np.ascontiguousarray(light_vp.T, dtype='f4').tobytes())
        op['depth_only'].value = 1
        op['use_shadows'].value = 0
        for batch in self.batches:
            if not batch['caster'] or batch['mode'] in ('blend', 'additive'):
                continue
            self._bind_batch(op, batch)
            batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
        op['depth_only'].value = 0

    def _apply_sky(self):
        """Give the map's sky domes the sun's or the weather preset's sky
        texture (all WaterReflectionSkydome models share one dome), or their
        own without either."""
        from mapworkshop.mapkit.weather import PRESETS, SUNS, sky_texture
        sky = (SUNS[self.sun].get('sky') if self.sun else None) or \
              (PRESETS[self.weather_preset].get('sky') if self.weather_preset else None)
        for batch in getattr(self, 'batches', []):
            if 'sky_own' not in batch:
                continue
            texture, name = batch['sky_own']
            if sky:
                swapped = self._object_texture(sky_texture(sky))
                if swapped is not None:
                    texture, name = swapped, sky_texture(sky)
            batch['texture'] = texture
            self.sky_horizon = self._horizon_color(name, batch['sky_rim_uv']) or self.sky_horizon
            batch['uniforms']['sky_horizon'] = self.sky_horizon or (0.0, 0.0, 0.0)

    def _horizon_color(self, name, uv):
        """Mean colour of texture `name` along a sky dome's rim (`uv`): the
        background below the dome (seen past the map's edge) is cleared to it."""
        image = self.assets.image(name) if name else None
        if image is None:
            return None
        image = np.asarray(image)
        h, w = image.shape[:2]
        x = np.clip((uv[:, 0]*(w-1)).astype(int), 0, w-1)
        y = np.clip(((1.0-uv[:, 1])*(h-1)).astype(int), 0, h-1)
        return tuple(float(c)/255 for c in image[y, x, :3].mean(0))

    def _draw_sky(self, batches, vp, eye):
        """Sky domes (simple.fx, unlit), drawn before the terrain."""
        ctx, mgl = self.ctx, self.moderngl
        op = self.object_program
        op['view_projection'].write(vp)
        op['eye'].value = eye
        op['use_shadows'].value = 0
        ctx.enable(mgl.DEPTH_TEST)
        for batch in batches:
            if batch['cull']:
                ctx.enable(mgl.CULL_FACE)
            self._bind_batch(op, batch)
            if 'sky_horizon' in op:
                op['sky_horizon'].value = self._horizon()
            batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
            ctx.disable(mgl.CULL_FACE)

    def _horizon(self):
        """Colour the sky dome's rim and the background below it fade to:
        the fog colour while fog is on (the fogged land fades there too),
        else the dome's own rim colour."""
        w = self.weather
        if w['hardwarefogenable'] and self.visible['weather']:
            return tuple(float(c) for c in w['hardwarefogcolor'])
        return self.sky_horizon

    def _bind_batch(self, op, batch):
        """Per-material uniforms and textures of an object batch."""
        if batch['texture'] is not None:
            batch['texture'].use(0)
        op['tex'].value = 0
        op['has_texture'].value = int(batch['texture'] is not None)
        op['technique'].value = batch['technique']
        op['alpha_ref'].value = -1.0 if batch['alpha_ref'] is None else float(batch['alpha_ref'])
        op['texturing'].value = 1
        # Camera-facing meshes and Grid-mapped textures (render.w3d).
        op['camera_mode'].value = batch.get('camera', 0)
        op['pivot'].value = batch.get('pivot', (0.0, 0.0, 0.0))
        op['uv_grid'].value = tuple(float(v) for v in batch.get('grid') or (0, 0, 0))
        op['detail_func'].value = batch['uniforms'].get('detail_func', 0)
        if batch.get('detail') is not None:
            batch['detail'].use(3)
            op['detail_tex'].value = 3
        if batch.get('normal') is not None:
            batch['normal'].use(9)
            op['normal_tex'].value = 9
        for key, value in batch['uniforms'].items():
            if key in self._object_uniforms:
                op[key].value = value
        if batch.get('scaled', True) != getattr(self, '_bound_scaled', True):
            # W3DPropBuffer::drawProps builds its own light environment from
            # the object lights without the ShaderLOD scale.
            self._bind_light_environment(op, batch.get('scaled', True))

    def _blend_func(self, factors):
        mgl = self.moderngl
        table = dict(zero=mgl.ZERO, one=mgl.ONE, src_alpha=mgl.SRC_ALPHA, one_minus_src_alpha=mgl.ONE_MINUS_SRC_ALPHA,
                     src_color=mgl.SRC_COLOR, one_minus_src_color=mgl.ONE_MINUS_SRC_COLOR, dst_color=mgl.DST_COLOR)
        return table[factors[0]], table[factors[1]]

    def _sway_offsets(self, time):
        """Vegetation.SwayOffsets (0x000E68C5) for the default breeze
        (ScriptEngine::reset: direction PI/3, intensity 0.035 PI/4, lean
        0.02 PI/4, period 300 logic frames, randomness 0.2). The vegetation
        sway update (0x000E6406) tabulates 100 offsets of
        (dirX sin a, dirY sin a, cos a - 1) with a = lean + intensity
        cos(i x 0.0622) and advances ten sway types by 100 / period per
        frame, each step and amplitude scaled by a random factor in
        [0.9, 1.1] (fixed stand-ins here). Index 0 never sways."""
        direction, intensity, lean, period, randomness = math.pi/3, 0.035*math.pi/4, 0.02*math.pi/4, 300.0, 0.2
        dx, dy = math.sin(direction), math.cos(direction)
        table = []
        for i in range(100):
            a = lean + intensity*math.cos(i*0.06220976)
            table.append((dx*math.sin(a), dy*math.sin(a), math.cos(a)-1.0))
        offsets = [(0.0, 0.0, 0.0)]
        frames = time*30.0
        for k in range(10):
            step_factor = 1.0 + randomness*0.5*math.sin(12.9898*(k+1))
            amp_factor = 1.0 + randomness*0.5*math.sin(78.233*(k+1))
            position = (frames*100.0/period*step_factor) % 100.0
            lo = int(math.floor(position))
            hi = min(lo+1, 99)
            f = position - lo
            offsets.append(tuple(amp_factor*((1-f)*table[lo][j] + f*table[hi][j]) for j in range(3)))
        return offsets

    def _bind_shadow(self, program, light_vp, depth, volume_count=None):
        """Shadow uniforms: a shadow map (High) or the volume count (Medium)."""
        if 'shadow_color' in program:
            program['shadow_color'].value = self.shadow_color
        if volume_count is not None:
            program['use_shadows'].value = 2
            # Unit 10: 8 and 9 hold the depth tint and tile heights (terrain)
            # and the normal map (objects).
            volume_count.use(10)
            if 'volume_count' in program:
                program['volume_count'].value = 10
            return
        enabled = light_vp is not None and self.options['shadows'] == 'map'
        program['use_shadows'].value = 1 if enabled else 0
        if not enabled:
            return
        self.shadow_texture.use(6)
        program['shadow_map'].value = 6
        program['light_view_projection'].write(np.ascontiguousarray(light_vp.T, dtype='f4').tobytes())
        program['shadow_texel'].value = (1/self.shadow_size, 1/self.shadow_size)
        # A few world units of bias in normalized light depth.
        program['shadow_bias'].value = 3.0/depth

    def surface_at(self, x, y):
        """Visible surface height: terrain, raised to standing water levels."""
        from mapworkshop.render.water import inside
        x = np.asarray(x, float); y = np.asarray(y, float)
        z = np.asarray(self.terrain.height_at(x, y), float)
        for entry in self.water:
            level = float(entry['area']['water_height'])
            covered = inside(entry['area']['points'], np.atleast_1d(x), np.atleast_1d(y)).reshape(z.shape)
            z = np.where(covered & (z < level), level, z)
        return z

    @property
    def playable(self):
        t = self.terrain
        return ((t.width-1-2*t.border)*10.0, (t.height-1-2*t.border)*10.0)

    def render(self, view, size=(1600, 1200), grid=False, border=False, time=0.0, background=None):
        """Render an OrbitView, TopView or key=value spec string to an RGB array.

        The non-playable border fades out onto the sky (black in top views),
        unless `border`. `background` (r, g, b in 0..1) replaces the clear colour,
        e.g. for objects alone (visible['terrain'] False, render.items)."""
        if isinstance(view, str):
            view = parse_view(view.split())
        camera = view.resolve(self.terrain, size[0]/size[1])
        bounds = view.bounds(self.terrain) if isinstance(view, TopView) else None
        ctx = self.ctx
        width, height = size
        color = ctx.renderbuffer((width, height), 4, samples=self.samples)
        depth = ctx.depth_renderbuffer((width, height), samples=self.samples)
        fbo = ctx.framebuffer([color], depth)
        resolve = ctx.framebuffer([ctx.renderbuffer((width, height), 4)])
        extra = {} if background is None else dict(clear=tuple(background))
        self.draw(camera, size, fbo, grid=grid, border=border, bounds=bounds, time=time, **extra)
        ctx.copy_framebuffer(resolve, fbo)
        pixels = np.frombuffer(resolve.read(components=4), np.uint8).reshape(height, width, 4)
        for item in (fbo, resolve, color, depth):
            item.release()
        return np.flipud(pixels)[..., :3].copy()

    def draw(self, camera, size, framebuffer, grid=False, border=False, bounds=None,
             shadow_radius=12000.0, shadow_size=16384, clear=(0.08, 0.09, 0.10), time=0.0):
        """Draw the scene for a resolved camera into `framebuffer`.

        `camera` needs view_projection, eye and target (see render.camera).
        Interactive callers bound the shadow map with shadow_radius/size.
        """
        ctx, mgl = self.ctx, self.moderngl
        light_vp = volume_count = None
        if self.batches:
            self.object_program['sway'].value = self._sway_offsets(time)
        if self.batches and self.visible['shadows']:
            if self.options['shadows'] == 'map':
                light_vp, light_radius, light_depth = self._light_projection(camera, bounds, shadow_radius)
                self._shadow_pass(light_vp, light_radius, shadow_size)
            elif self.options['shadows'] == 'volume':
                volume_count = self._volume_pass(camera, size)
        reflection = self._reflection_pass(camera, size, time)
        width, height = size
        framebuffer.use()
        ctx.viewport = (0, 0, width, height)
        sky_visible = (getattr(self, 'sky_horizon', None) is not None and self.visible['objects']
                       and bounds is None and not border)
        horizon = self._horizon() if sky_visible else None
        # Below a sky dome (past the map's edge) the background is its horizon.
        framebuffer.clear(*(horizon or clear), 1.0)
        ctx.enable(mgl.DEPTH_TEST)
        ctx.disable(mgl.CULL_FACE)
        vp = np.ascontiguousarray(camera['view_projection'].T, dtype='f4').tobytes()
        eye = tuple(float(v) for v in camera['eye'])
        p = self.terrain_program
        p['view_projection'].write(vp)
        p['eye'].value = eye
        for program in (self.terrain_program, getattr(self, 'object_program', None), getattr(self, 'water_program', None)):
            if program is not None:
                self._set_fog(program, eye)
        if 'cloud_xform' in p:
            # weather.ini CloudOffsetPerSecond: texture units per second.
            k = self.cloud_scale
            ox, oy = self.weather['cloudoffsetpersecond']
            p['cloud_xform'].value = (k[0], k[1], (time*ox) % 1.0, (time*oy) % 1.0)
        # updateCenter: 2x tile textures within scale x (260 + 170) + 25 of the
        # camera, scale = display width / 1024 clamped to [0.5, 2.5].
        scale = min(max(width/1024, 0.5), 2.5)
        p['distance_2x'].value = scale*260 + scale*170 + 25
        p['grid_lines'].value = int(grid)
        walk = (getattr(self, '_walk', None) if getattr(self, 'defer_walkability', False)
                else self.walkable_overlay()) if self.visible['walkable'] else None
        if 'use_walk' in p:
            p['use_walk'].value = int(walk is not None)
            if walk is not None:
                walk[0].use(11)
                p['walk_tex'].value = 11
                p['walk_size'].value = walk[1]
        p['playable'].value = self.playable
        p['show_border'].value = int(border)
        # Perspective views fade the border out (top views keep it black).
        fading = bounds is None and not border
        p['border_fade'].value = float(self.terrain.border*10) if fading else 0.0
        sky = [b for b in self.batches if b.get('sky')] if self.visible['objects'] and fading else []
        if sky:
            # Sky domes first, so that the fading border blends onto them.
            self._draw_sky(sky, vp, eye)
            ctx.enable(mgl.DEPTH_TEST)
            ctx.disable(mgl.CULL_FACE)
        self._bind_shadow(p, light_vp, light_depth if light_vp is not None else 1.0, volume_count)
        p['use_decals'].value = int(hasattr(self, 'decal_tex') and self.visible['decals'] and self.visible['shadows'])
        if hasattr(self, 'decal_tex'):
            self.decal_tex.use(7)
        self.heights.use(0); self.cells.use(1); self.albedo.use(2); self.normal_array.use(3)
        self.depth_tint.use(8); self.tile_z.use(9)
        if self.macro_tex: self.macro_tex.use(4)
        if self.cloud_tex: self.cloud_tex.use(5)
        if fading:
            ctx.enable(mgl.BLEND)
            ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
        if self.visible['terrain']:
            self.terrain_vao.render(mgl.TRIANGLES, vertices=self.terrain_vertices)
        ctx.disable(mgl.BLEND)
        if self.batches and self.visible['objects']:
            op = self.object_program
            op['view_projection'].write(vp)
            op['eye'].value = eye
            back = np.asarray(camera['eye'], float) - np.asarray(camera['target'], float)
            op['camera_back'].value = tuple(back/(np.linalg.norm(back) or 1.0))
            op['time'].value = float(time)
            self._bind_shadow(op, light_vp, light_depth if light_vp is not None else 1.0, volume_count)
            op['use_cloud'].value = int(self.options['clouds'] and self.cloud_tex is not None)
            if 'cloud_xform' in p:
                op['cloud_xform'].value = p['cloud_xform'].value
            if self.cloud_tex:
                self.cloud_tex.use(5)
            op['cloud_tex'].value = 5
            # The tree and shrub buffers draw with the terrain; then opaque
            # objects, then translucent ones without depth writes.
            for batch in self._draw_batches:
                if batch.get('sky'):
                    # Drawn before the terrain; top views leave sky domes out.
                    continue
                if batch['blend'] is not None:
                    if volume_count is not None and not batch['vegetation']:
                        # Translucent meshes are flushed after the stencil shadows;
                        # the tree buffer draws with the terrain, before them.
                        op['use_shadows'].value = 0
                    ctx.enable(mgl.BLEND)
                    ctx.blend_func = self._blend_func(batch['blend'])
                ctx.fbo.depth_mask = batch['depth_mask']
                if batch['cull']:
                    # W3D culls clockwise (D3DCULL_CW); the effects set CULLMODE 2.
                    ctx.enable(mgl.CULL_FACE)
                self._bind_batch(op, batch)
                batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
                ctx.disable(mgl.BLEND)
                ctx.disable(mgl.CULL_FACE)
                ctx.fbo.depth_mask = True
        if self.water and self.visible['water']:
            wp = self.water_program
            wp['view_projection'].write(vp)
            wp['eye'].value = eye
            wp['time'].value = float(time)
            wp['playable'].value = self.playable
            self._bind_shadow(wp, light_vp, light_depth if light_vp is not None else 1.0, volume_count)
            wp['show_border'].value = int(border)
            wp['use_reflection'].value = int(reflection is not None)
            if reflection is not None:
                reflection.use(12)
                wp['reflection_tex'].value = 12
                wp['viewport_size'].value = (float(width), float(height))
            if 'use_walk' in wp:
                wp['use_walk'].value = int(walk is not None)
                if walk is not None:
                    wp['walk_tex'].value = 11
                    wp['walk_size'].value = walk[1]
            ctx.enable(mgl.BLEND)
            ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
            ctx.fbo.depth_mask = False
            for entry in self.water:
                for unit, name in [(1, 'bump'), (2, 'env'), (3, 'wave')]:
                    if entry[name] is not None:
                        entry[name].use(unit)
                wp['bump_tex'].value, wp['env_tex'].value, wp['wave_tex'].value = 1, 2, 3
                wp['has_wave'].value = int(entry['wave'] is not None)
                for key, value in entry['uniforms'].items():
                    if key in wp:
                        wp[key].value = value
                entry['vao'].render(mgl.TRIANGLES)
            ctx.fbo.depth_mask = True
            ctx.disable(mgl.BLEND)
        if getattr(self, 'rivers', None) and (self.visible['water'] or self.visible['flow']):
            self._draw_rivers(vp, eye, time, border)
        if getattr(self, 'effects', None) is not None and self.visible['objects'] and self.visible['effects'] \
                and hasattr(self, 'effect_program'):
            self._draw_effects(vp, camera, eye, time)
        if self.particles and self.visible['weather']:
            self._draw_particles(vp, camera, eye, time)

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

    def top_size(self, view, scale=2.0, border=False):
        """Pixel size for a TopView at `scale` pixels per terrain cell."""
        x0, y0, x1, y1 = view.bounds(self.terrain, border)
        return round((x1-x0)/10*scale), round((y1-y0)/10*scale)

    def save(self, image, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(image).save(path)
        return path
