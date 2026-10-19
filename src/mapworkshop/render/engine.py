"""Offscreen renderer for BFME2 maps (moderngl, headless OpenGL 4.3).

MapRenderer reads a map (prepare, on any thread), puts it on the GPU (upload,
on the thread that owns the context) and draws it (draw, render). Each subject
it draws is a part of its own, a mixin in that subject's module, all sharing
the renderer's state:

    materials  textures, the terrain's texture array, compiled effects
    lighting   the map's lights, the object light environment, set_weather
    terrain    the terrain on the GPU and its technique
    water      standing water and the reflection pass
    rivers     river strips
    weather    fog and falling rain or snow
    objects    placed objects, units and bridges as batches; binding them
    effects    particle effects on objects
    shadows    volumes, the shadow map, tree shadow decals
    sky        sky domes and the horizon
    overlays   the walkability overlay

This module holds the renderer's life and the frame (draw): which passes run,
in what order, into which framebuffers.
"""

from pathlib import Path

import numpy as np
from PIL import Image

from mapworkshop.assets.library import GameAssets
from mapworkshop.assets.models import ModelCache
from mapworkshop.formats.map import Map
from mapworkshop.render.camera import TopView, parse_view
from mapworkshop.render.effects import EffectsMixin
from mapworkshop.render.lighting import LightingMixin
from mapworkshop.render.materials import MaterialsMixin, TextureCache
from mapworkshop.render.objects import ObjectsMixin
from mapworkshop.render.overlays import OverlaysMixin
from mapworkshop.render.photo import Post, active
from mapworkshop.render.rivers import RiversMixin
from mapworkshop.render.shadows import ShadowsMixin
from mapworkshop.render.sky import SkyMixin
from mapworkshop.render.terrain import TerrainData, TerrainMixin
from mapworkshop.render.water import WaterMixin
from mapworkshop.render.weather import WeatherMixin


class MapRenderer(MaterialsMixin, LightingMixin, TerrainMixin, WaterMixin, RiversMixin, WeatherMixin, ObjectsMixin,
                  EffectsMixin, ShadowsMixin, SkyMixin, OverlaysMixin):
    """A map, ready to draw: see the module docstring for its parts."""

    def __init__(self, source, assets=None, ctx=None, objects=True, normal_maps=None,
                 clouds=True, macro=True, samples=4, lod='medium', shadows=True, shared=None, weather=None,
                 progress=None, vegetation_limits=False, sun=None, editor_markers=False, units=True):
        """Synchronous entry point for CLI rendering; the viewer uses prepare/upload."""
        import moderngl
        self._prepare(source, assets, objects, normal_maps, clouds, macro, samples, lod,
                      shadows, shared, weather, progress, vegetation_limits, sun, editor_markers, units)
        for _ in self.upload(ctx or moderngl.create_standalone_context(require=430), shared):
            pass

    @classmethod
    def prepare(cls, source, **options):
        """CPU-only scene construction, safe to perform in a loader worker."""
        return cls.__new__(cls)._prepare(source, **options)

    def _prepare(self, source, assets=None, objects=True, normal_maps=None, clouds=True,
                 macro=True, samples=4, lod='medium', shadows=True, shared=None, weather=None,
                 progress=None, vegetation_limits=False, sun=None, editor_markers=False, units=True):
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
                            editor_markers=editor_markers, units=units,
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
        self.report = dict(missing_textures=[], missing_models=[], unreadable_models={}, objects_drawn=0,
                           objects_skipped=0, editor_markers=0, units=dict(hidden=0, hordes=0, members=0, crew=0, posed=0))
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


    def surface_at(self, x, y):
        """Visible surface height: terrain, raised to standing water levels."""
        from mapworkshop.mapkit.lines import inside
        x = np.asarray(x, float); y = np.asarray(y, float)
        z = np.asarray(self.terrain.height_at(x, y), float)
        for entry in self.water:
            level = float(entry['area']['water_height'])
            covered = inside(entry['area']['points'], np.atleast_1d(x), np.atleast_1d(y)).reshape(z.shape)
            z = np.where(covered & (z < level), level, z)
        return z

    @property
    def playable(self):
        """The playable area's (x, y) size in world units (formats.terrain.playable_extent)."""
        return self.terrain.playable

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
        extra = {} if background is None else dict(clear=tuple(background))
        photo = camera.get('photo') or {}
        pixels_rb = ctx.renderbuffer((width, height), 4)
        resolve = ctx.framebuffer([pixels_rb])
        if active(photo):
            # Exposure and depth of field (render.photo) over the scene.
            post = Post(ctx, self.samples)
            self.draw(camera, size, post.target(size), grid=grid, border=border, bounds=bounds, time=time, **extra)
            post.finish(camera, photo, resolve, taps=256)
            post.release()
            items = (resolve, pixels_rb)
        else:
            color = ctx.renderbuffer((width, height), 4, samples=self.samples)
            depth = ctx.depth_renderbuffer((width, height), samples=self.samples)
            fbo = ctx.framebuffer([color], depth)
            self.draw(camera, size, fbo, grid=grid, border=border, bounds=bounds, time=time, **extra)
            ctx.copy_framebuffer(resolve, fbo)
            items = (fbo, resolve, color, depth, pixels_rb)
        pixels = np.frombuffer(resolve.read(components=4), np.uint8).reshape(height, width, 4)
        for item in items:
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
                light_vp, light_size, light_depth = self._light_projection(camera, bounds, shadow_radius, shadow_size)
                self._shadow_pass(light_vp, light_size)
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
        self.cliff_u.use(13); self.cliff_v.use(14)
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
            self._begin_batches()
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


    def top_size(self, view, scale=2.0, border=False):
        """Pixel size for a TopView at `scale` pixels per terrain cell."""
        x0, y0, x1, y1 = view.bounds(self.terrain, border)
        return round((x1-x0)/10*scale), round((y1-y0)/10*scale)

    def save(self, image, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(image).save(path)
        return path
