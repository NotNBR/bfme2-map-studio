"""River strips (RiverAreas) as the game draws them.

Port of WaterRenderObjClass::drawRiverWater (game.dat 1.06 RVA 0x00100A0B,
reconstructed in Open-BFME-2's W3DWaterDrawRiverWater.cpp) and of the
RiverWater.fx effect it draws with (shaders.RIVER_VS/RIVER_FS):

- The river's points run round its outline: the first cross-section's two
  ends, then along one bank to the last cross-section and back along the
  other. Each cross-section becomes a vertex pair at the river's water height.
  Which stored end of a cross-section starts the outline is not known (its
  builder, 0x00082D6A, is not reconstructed); the first end is taken here.
- UVs: u1 (river and sparkle textures) runs 0 to 0.5 across, u2 (alpha
  edge) 0 to 1. v advances `v_scale` per cross-section, however far apart
  they are: the outline's length less its closing edge, halved, less the
  first cross-section's width, in first-section widths, shared out over the
  quads. So one repeat is about as long as the first cross-section is wide.
- The texture scrolls by VOrigin, which grows by the river's UV speed every
  second, so it moves from the first cross-section towards the last; v also
  wobbles by sin(2 pi v - 3 VOrigin) / 22 (in the vertex shader here).
- Vertex colour: a white river (every stock one) takes the terrain's ambient
  plus each terrain light's diffuse times its downward component, times the
  time of day's WaterSet DiffuseColor (water.ini), whose alpha is the vertex
  alpha. Any other colour is used as it is, black as white.
- A river is skipped when its minimum LOD is above the game's WaterLOD.
Its RiversMixin is the river part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""
import math

import numpy as np

from mapworkshop.render.water import WATER_LODS
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.render import shaders

TIMES_OF_DAY = ('MORNING', 'AFTERNOON', 'EVENING', 'NIGHT')    # GlobalLighting time_of_day 1-4


def mesh(cross_sections, water_height):
    """(vertices[n, 6] = x, y, z, u1, u2, v; triangle indices[m, 3]) for a
    river, or None when it has fewer than two cross-sections. v is before the
    scroll and wobble, which depend on time."""
    cs = np.asarray(cross_sections, float).reshape(-1, 4)
    if len(cs) < 2:
        return None
    first, second = cs[:, :2], cs[:, 2:]
    outline = np.concatenate([first[:1], second, first[:0:-1]])
    end = float(np.hypot(*(outline[1]-outline[0])))
    total = float(np.hypot(*np.diff(outline, axis=0).T).sum())    # without the closing edge
    quads = len(cs)-1
    v_scale = ((total/2-end)/end)/quads if end > 0 else 0.0
    vertices = np.zeros((2*len(cs), 6), np.float32)
    vertices[0::2, :2], vertices[1::2, :2] = second, first
    vertices[:, 2] = float(water_height)
    vertices[0::2, 3], vertices[0::2, 4] = 0.5, 1.0                # the second bank: u1 0.5, u2 1
    vertices[0::2, 5] = vertices[1::2, 5] = v_scale*np.arange(len(cs))
    i = np.arange(quads)*2
    triangles = np.concatenate([np.column_stack([i, i+1, i+3]), np.column_stack([i, i+3, i+2])]).astype(np.uint32)
    return vertices, triangles


def drawn(min_lod, water_level):
    """Whether the game draws a river with this minimum LOD name at a WaterLOD
    (0-3); an empty or unknown name counts as Low."""
    name = (min_lod or '').strip().lower()
    return (WATER_LODS.index(name) if name in WATER_LODS else 0) <= water_level


def water_diffuse(ini_texts, time_of_day):
    """The WaterSet DiffuseColor for a time of day (1-4) as RGBA 0-1, the last
    of the given INI texts that sets it winning; mid grey if none does."""
    import re
    name = TIMES_OF_DAY[max(0, min(3, time_of_day-1))]
    colour = (175, 175, 175, 255)
    for text in ini_texts:
        block = re.search(rf'(?ims)^\s*WaterSet\s+{name}\b(.*?)^\s*End\b', text or '')
        found = block and re.search(r'(?im)^\s*DiffuseColor\s*=\s*(.*)$', block.group(1))
        if found:
            parts = dict(re.findall(r'([RGBA])\s*:\s*(\d+)', found.group(1).upper()))
            colour = tuple(int(parts.get(k, 255 if k == 'A' else 0)) for k in 'RGBA')
    return tuple(c/255 for c in colour)


def vertex_colour(color_bytes, terrain_ambient, terrain_lights, water):
    """The colour every vertex of a river gets (RGBA 0-1). `terrain_lights`
    are (direction as stored, diffuse) of the terrain's global lights, `water`
    the WaterSet diffuse. Stock WaterSets are grey, so their channel order
    (the game reads the low byte as red) does not matter."""
    rgb = [c/255 for c in color_bytes[:3]]
    if rgb == [1.0, 1.0, 1.0]:
        rgb = list(terrain_ambient)
        for direction, diffuse in terrain_lights:
            down = -float(direction[2])
            if down > 0:
                rgb = [c+down*d for c, d in zip(rgb, diffuse)]
        rgb = [c*w for c, w in zip(rgb, water[:3])]
    elif rgb == [0.0, 0.0, 0.0]:
        rgb = [1.0, 1.0, 1.0]
    # The game packs these into colour bytes without clamping; past 255 a
    # channel would spill into the next, which the stock lighting never reaches.
    return tuple(min(max(c, 0.0), 1.0) for c in rgb) + (float(water[3]),)


def wobble(v, origin):
    """v after the scroll and wobble at a VOrigin (what RIVER_VS computes)."""
    return v+math.sin(2*math.pi*v-3*origin)/22-origin


class RiversMixin:
    """MapRenderer's rivers: the RiverAreas strips on the GPU and drawn over the water,
    with the flow arrows of the walkable/flow views."""

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
