"""Shadow volumes as BFME2 (game.dat 1.06) builds them at Medium detail.

Which objects cast what: W3DShadowManager::addShadow (0x0009A8D3). INI
Shadow names are bits in this order: SHADOW_DECAL 1, SHADOW_VOLUME 2,
SHADOW_VOLUME_NEW 4, SHADOW_DYNAMIC_PROJECTION 8, SHADOW_DIRECTIONAL_PROJECTION
0x10, SHADOW_ALPHA_DECAL 0x20, SHADOW_ADDITIVE_DECAL 0x40,
SHADOW_VOLUME_NON_SELF_1..3 0x80..0x200, SHADOW_ALPHA_DECAL_DYNAMIC 0x400,
SHADOW_ADDITIVE_DECAL_DYNAMIC 0x800, SHADOW_MERGE_DECAL 0x1000,
SHADOW_DECAL_TERRAIN_CLAIM 0x2000, SHADOW_VOLUME_OR_DECAL 0x4000,
SHADOW_VOLUME_NEW_OR_DECAL 0x8000. The *_OR_DECAL types become volumes when
GameLOD UseShadowVolumes is on, else decals. SHADOW_VOLUME and NON_SELF go to
W3DVolumetricShadowManager ('classic'), SHADOW_VOLUME_NEW to the V2 manager
('v2'), decal types to the projected-shadow manager.

Geometry: the top LOD's meshes with CAST_SHADOW (assets.models 'shadow'). V2
skips a hidden mesh unless its name contains SHADOW (0x00107E76).

Extrusion (the light is TheW3DShadowManager light 0: the time of day's
terrain light 0 direction, reversed and placed 10,000,000 units away, so
effectively directional):

- classic: W3DVolumetricShadow::Update (0x000F4017) and
  updateOptimalExtrusionPadding (0x000F1212): from the four top corners of
  the object's world box, march along the light ray in 20-unit steps up to
  5120, keeping the lowest terrain sampled (stopping a corner where the ray
  dips under the terrain but is above it again 200 units further); the floor
  is that height - 0.1 (objects 2 or more units above ground use the
  terrain's minimum height instead). updateMeshVolume extrudes every
  silhouette vertex of a mesh by the distance from the mesh box top to that
  floor along the light ray.
- v2: W3DVolumetricShadowV2 update (0x001074D5): offset = normalized
  (position - light) scaled so that its z is -(height above ground +
  object box top + 20 + 0.1); every silhouette vertex moves by it.
Its ShadowsMixin is the shadow part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""

import math

import numpy as np
from mapworkshop.render import shaders
import re

SHADOW_BITS = ('SHADOW_DECAL', 'SHADOW_VOLUME', 'SHADOW_VOLUME_NEW', 'SHADOW_DYNAMIC_PROJECTION',
               'SHADOW_DIRECTIONAL_PROJECTION', 'SHADOW_ALPHA_DECAL', 'SHADOW_ADDITIVE_DECAL',
               'SHADOW_VOLUME_NON_SELF_1', 'SHADOW_VOLUME_NON_SELF_2', 'SHADOW_VOLUME_NON_SELF_3',
               'SHADOW_ALPHA_DECAL_DYNAMIC', 'SHADOW_ADDITIVE_DECAL_DYNAMIC', 'SHADOW_MERGE_DECAL',
               'SHADOW_DECAL_TERRAIN_CLAIM', 'SHADOW_VOLUME_OR_DECAL', 'SHADOW_VOLUME_NEW_OR_DECAL')
SHADOW_EXTRUSION_BUFFER = 0.1
AIRBORNE_UNIT_GROUND_DELTA = 2.0
SAMPLING_INTERVAL, SAMPLING_LOOKAHEAD, SAMPLING_LENGTH = 20.0, 200.0, 5120.0


def shadow_kind(name, volumes):
    """'classic', 'v2', 'decal' or None for an INI Shadow value, as
    W3DShadowManager::addShadow routes it (volumes = UseShadowVolumes)."""
    name = (name or '').upper()
    if name == 'SHADOW_VOLUME_OR_DECAL':
        name = 'SHADOW_VOLUME' if volumes else 'SHADOW_DECAL'
    elif name == 'SHADOW_VOLUME_NEW_OR_DECAL':
        name = 'SHADOW_VOLUME_NEW' if volumes else 'SHADOW_DECAL'
    if name in ('SHADOW_VOLUME', 'SHADOW_VOLUME_NON_SELF_1', 'SHADOW_VOLUME_NON_SELF_2', 'SHADOW_VOLUME_NON_SELF_3'):
        return 'classic' if volumes else None
    if name == 'SHADOW_VOLUME_NEW':
        return 'v2' if volumes else None
    if name in ('SHADOW_DECAL', 'SHADOW_ALPHA_DECAL', 'SHADOW_ADDITIVE_DECAL', 'SHADOW_ALPHA_DECAL_DYNAMIC',
                'SHADOW_ADDITIVE_DECAL_DYNAMIC', 'SHADOW_MERGE_DECAL'):
        return 'decal'
    return None


def shadow_geometry(positions, triangles):
    """Welded shadow mesh with polygon neighbours, as W3DShadowGeometry builds it.

    Vertices at identical positions are merged (initFromMesh folds
    duplicates). buildPolygonNeighbors: the neighbour across edge k of a
    triangle (tri[k] -> tri[k+1]) is the first triangle that runs that edge
    the other way, unless its normal is exactly opposite (a back-to-back
    face); -1 when there is none. Returns dict(vertices [n, 3],
    triangles [m, 3], neighbours [m, 3], normals [m, 3])."""
    unique, inverse = np.unique(np.asarray(positions, np.float32), axis=0, return_inverse=True)
    vertices = unique.astype(np.float64)
    tris = inverse.reshape(-1)[np.asarray(triangles, np.int64)]
    tris = tris[(tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 2] != tris[:, 0])]
    p = vertices[tris]
    normals = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    unit = normals/np.where(length > 0, length, 1)
    runs = {}
    for t, (a, b, c) in enumerate(tris):
        for edge in ((a, b), (b, c), (c, a)):
            runs.setdefault(edge, []).append(t)
    neighbours = np.full((len(tris), 3), -1, np.int64)
    for t, tri in enumerate(tris):
        for k in range(3):
            a, b = tri[k], tri[(k+1) % 3]
            for other in runs.get((b, a), ()):
                if abs(float(unit[other] @ unit[t]) + 1.0) > 0.01:
                    neighbours[t, k] = other
                    break
    return dict(vertices=vertices, triangles=tris, neighbours=neighbours, normals=normals)


def silhouette_quads(geometry, place, scale, extrude):
    """World-space shadow volume triangles [k, 3, 3] of a shadow mesh's instances.

    W3DVolumetricShadow::buildSilhouette marks each polygon lit once
    (dot(light->vertex, normal) < 0; the light is effectively directional,
    so the light vector is the instance's extrusion direction). A silhouette
    edge is an edge of a lit polygon whose neighbour is unlit, or that has
    no neighbour (addNeighborlessEdges). constructVolume extrudes it into a
    quad from the edge to the edge moved by the extrusion vector, wound
    outwards so that its front face adds to the stencil count.

    place: [i, 4] x, y, z, angle; scale: [i]; extrude: [i, 3]."""
    place = np.asarray(place, np.float64).reshape(-1, 4)
    scale = np.asarray(scale, np.float64).reshape(-1)
    extrude = np.asarray(extrude, np.float64).reshape(-1, 3)
    if not len(place) or not len(geometry['triangles']):
        return np.zeros((0, 3, 3), np.float32)
    c, s = np.cos(place[:, 3]), np.sin(place[:, 3])
    rot = np.zeros((len(place), 3, 3))
    rot[:, 0, 0], rot[:, 0, 1], rot[:, 1, 0], rot[:, 1, 1], rot[:, 2, 2] = c, -s, s, c, 1.0
    world = np.einsum('iab,vb->iva', rot, geometry['vertices'])*scale[:, None, None] + place[:, None, :3]
    lit = np.einsum('iab,mb,ia->im', rot, geometry['normals'], extrude) < 0
    tris, neighbours = geometry['triangles'], geometry['neighbours']
    owner = np.repeat(np.arange(len(tris)), 3)
    start = tris.reshape(-1)
    end = tris[:, [1, 2, 0]].reshape(-1)
    across = neighbours.reshape(-1)
    other_lit = np.where(across >= 0, lit[:, np.maximum(across, 0)], False)
    instance, edge = np.nonzero(lit[:, owner] & ~other_lit)
    a = world[instance, start[edge]]
    b = world[instance, end[edge]]
    e = extrude[instance]
    quads = np.stack([np.stack([a, a + e, b], 1), np.stack([b, a + e, b + e], 1)], 1)
    return quads.reshape(-1, 3, 3).astype(np.float32)


def world_box(bounds, x, y, z, angle, scale):
    """World AABB (lo, hi) of a model box rotated about Z, scaled and placed."""
    lo, hi = (np.asarray(b, float)*scale for b in bounds)
    corners = np.array([[px, py, pz] for px in (lo[0], hi[0]) for py in (lo[1], hi[1]) for pz in (lo[2], hi[2])])
    c, s = math.cos(angle), math.sin(angle)
    rotated = np.column_stack([c*corners[:, 0] - s*corners[:, 1], s*corners[:, 0] + c*corners[:, 1], corners[:, 2]])
    rotated += (x, y, z)
    return rotated.min(0), rotated.max(0)


def classic_floor(box, z, ground, height_at, direction, min_height):
    """Floor z of a classic volume (updateOptimalExtrusionPadding + updateVolumes).
    `direction` is the unit vector from the light towards the scene."""
    if abs(z - ground) >= AIRBORNE_UNIT_GROUND_DELTA:
        return z - (abs(z - min_height) + SHADOW_EXTRUSION_BUFFER)
    lo, hi = box
    base = z
    d = np.asarray(direction, float)
    for cx, cy in ((hi[0], hi[1]), (lo[0], hi[1]), (lo[0], lo[1]), (hi[0], lo[1])):
        corner = np.array([cx, cy, hi[2]])
        steps = np.arange(1, int(math.ceil(SAMPLING_LENGTH/SAMPLING_INTERVAL)))
        points = corner + np.outer(steps*SAMPLING_INTERVAL, d)
        terrain = np.asarray(height_at(points[:, 0], points[:, 1]), float)
        ahead = points + d*SAMPLING_LOOKAHEAD
        above_again = ahead[:, 2] > np.asarray(height_at(ahead[:, 0], ahead[:, 1]), float)
        stop = np.nonzero((terrain > points[:, 2]) & above_again)[0]
        end = stop[0] if len(stop) else len(points)
        if end:
            base = min(base, float(terrain[:end].min()))
    return base - SHADOW_EXTRUSION_BUFFER


def classic_extrusion(mesh_top, floor, direction):
    """Extrusion vector of one mesh: the top of its box to the floor along the ray."""
    d = np.asarray(direction, float)
    return d*abs((mesh_top - floor)/d[2]) if abs(d[2]) > 1e-6 else d*SAMPLING_LENGTH


def v2_offset(z, ground, box_top, direction, length_scale=0.0, padding=0.1):
    """W3DVolumetricShadowV2's light offset (0x001074D5); box_top is the
    object-space box top (the constructor adds 20 units)."""
    d = np.asarray(direction, float).copy()
    if length_scale > 0.0:
        horizontal = (d[0]*d[0] + d[1]*d[1])*length_scale*length_scale
        if horizontal > d[2]:
            d[2] = math.sqrt(horizontal)
    if not d[2] > -0.01:
        height = box_top + 20.0
        d *= (z + height - ground + padding)*(-1.0/d[2])
    return d


class ShadowsMixin:
    """MapRenderer's shadows: stencil volumes (Medium), the shadow map (High) and the
    trees' baked shadow decals, with the sun's projection over the camera's footprint."""

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
        self.cliff_u.use(13); self.cliff_v.use(14)
        self.terrain_vao.render(mgl.TRIANGLES, vertices=self.terrain_vertices)
        if self.visible['objects']:
            op = self.object_program
            op['view_projection'].write(vp)
            op['depth_only'].value = 1
            op['use_shadows'].value = 0
            self._begin_batches()
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
    def _light_projection(self, camera, bounds=None, max_radius=12000.0, max_size=16384):
        """Orthographic sun projection covering the camera's ground footprint,
        with the shadow map's size in texels and its depth range.

        `bounds` (x0, y0, x1, y1) replaces the footprint for top views. The
        footprint lies at the height of the camera's `ground` point (its target
        when it has none); when it exceeds `max_radius`, the area around that
        point wins. The window is on whole texels of a grid fixed by the sun, so
        a camera that moves shifts the map by whole texels and the
        point-sampled shadow edges do not jump or crawl.
        """
        from mapworkshop.render.camera import look_at, orthographic
        anchor = np.asarray(camera.get('ground', camera['target']), float)
        if bounds is not None:
            x0, y0, x1, y1 = bounds
        else:
            inv = np.linalg.inv(camera['view_projection'])
            ground = float(anchor[2])
            xs, ys = [], []
            for sx in (-1, 0, 1):
                for sy in (-1, 0, 1):
                    near = inv @ np.array([sx, sy, -1, 1.0]); near = near[:3]/near[3]
                    far = inv @ np.array([sx, sy, 1, 1.0]); far = far[:3]/far[3]
                    d = far-near
                    t = (ground-near[2])/d[2] if abs(d[2]) > 1e-6 else 1.0
                    # A ray that never comes down to the ground sees as far as the far plane.
                    hit = near + d*(t if 0.0 <= t <= 1.0 else 1.0)
                    xs.append(hit[0]); ys.append(hit[1])
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        center = np.array([(x0+x1)/2, (y0+y1)/2, self.terrain.mean_height])
        radius = 0.5*math.hypot(x1-x0, y1-y0)+300
        if radius > max_radius:
            radius = max_radius
            if bounds is None:
                center[:2] = anchor[:2]
        # Shadow maps use the game's texel size so edges are equally soft;
        # stencil volumes are exact, approximated here by a fine map.
        texel = self.shadow_settings['texel'] if self.options['shadows'] == 'map' else 0.75
        size = int(min(max_size, max(256, math.ceil(2*radius/texel)+1)))
        texel = max(texel, 2*radius/(size-1))
        top = self.terrain.max_height+radius+2000
        # The light looks at a fixed point, so its axes depend on the sun alone;
        # the window then sits around `center`, its corner on the texel grid.
        origin = np.array([0.0, 0.0, center[2]])
        view_m = look_at(origin + np.array(self.sun_dir)*(top+radius), origin,
                         up=(0, 1, 0) if abs(self.sun_dir[2]) < 0.99 else (1, 0, 0))
        cx, cy, cz = (view_m @ np.append(center, 1.0))[:3]
        left, bottom = (math.floor((c-radius)/texel)*texel for c in (cx, cy))
        # The depth range as seen from `top+radius` above the centre along the sun.
        near = -cz-(top+radius)
        depth = 2*(top+radius)
        proj = orthographic(left, left+size*texel, bottom, bottom+size*texel, near+1.0, near+depth+radius)
        return proj @ view_m, size, depth

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

    def _shadow_pass(self, light_vp, size):
        ctx, mgl = self.ctx, self.moderngl
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
        self._begin_batches()
        for batch in self.batches:
            if not batch['caster'] or batch['mode'] in ('blend', 'additive'):
                continue
            self._bind_batch(op, batch)
            batch['vao'].render(mgl.TRIANGLES, instances=batch['count'])
        op['depth_only'].value = 0

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
