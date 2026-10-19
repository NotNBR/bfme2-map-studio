"""Terrain cell data for the GPU, following WorldHeightMap's tile rules.

Each height-map cell is drawn as two triangles. The base tile and up to two
blend tiles (primary and three-way) are packed per cell. BFME2 composites
these on the CPU into one texture per 16x16-cell tile
(getPointerToTileData 0x000AED2E: rawTile, then blendTile 0x000ADDCE for the
blend and, with GameData Use3WayTerrainBlends, the three-way blend), mixing
texels by the 64x64 alpha tiles of setupAlphaTiles 0x000AC6F9 only; the
tile's own alpha is not used. Those alpha tiles are linear ramps across one
cell, which the per-corner 0/1 values of getAlphaUVData reproduce when
interpolated over the cell's triangles (diagonal blends rotate the split).
Cliff cells take no primary blend (0x000ABD19 in 0x000AED2E). A cliff
record (mapkit.cliffs) applies when its tile's texture is the cell's
(getUVForTileIndex / 0x000AE490): the cell then takes the record's corner
UVs in that texture, wrapping, and its triangle flip.
Its TerrainMixin is the terrain part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""

import re

import numpy as np

from mapworkshop.formats.terrain import playable_extent, terrain_records
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.render import shaders
from mapworkshop.render.materials import ARRAY_SIZE
from pathlib import Path

INVERTED, FLIPPED = 1, 2
# Corner order: 0 (x,y), 1 (x+1,y), 2 (x+1,y+1), 3 (x,y+1).
TILE_CELLS = 16   # W3DTerrainBackground tile size (HeightMap initHeightData 0x000E1A39)


def cloud_texture_size(*texts):
    """weather.ini CloudTextureSize (world units per cloud repeat); later texts win.
    The terrain FX gets 1 / size as Cloud.ScaleUV (callback 0x000E2BEE)."""
    size = (660.0, 660.0)
    for text in texts:
        for block in re.findall(r'(?ims)^\s*Weather\s*$(.*?)^\s*End\b', text or ''):
            m = re.search(r'(?im)^\s*CloudTextureSize\s*=\s*([^\r\n;]*)', block)
            if m:
                found = dict((k.upper(), float(v)) for k, v in re.findall(r'([XY])\s*:\s*(-?[\d.]+)', m.group(1), re.I))
                size = (found.get('X', size[0]) or size[0], found.get('Y', size[1]) or size[1])
    return size


def blend_corners(record):
    """(corner bit mask, needs flip) for one blend record (EA getAlphaUVData)."""
    if record is None:
        return 0, False
    direction = bytes.fromhex(record['direction_hex'])
    horiz, vert, right, left = (bool(v) for v in direction[:4])
    inverted = record['flags'] & INVERTED
    long_diagonal = bool(record['long_diagonal'])
    alpha = [0, 0, 0, 0]
    flip = False
    if horiz:
        flip = bool(record['flags'] & FLIPPED)
        if inverted: alpha[0] = alpha[3] = 1
        else: alpha[1] = alpha[2] = 1
    if vert:
        flip = bool(record['flags'] & FLIPPED)
        if inverted: alpha[0] = alpha[1] = 1
        else: alpha[2] = alpha[3] = 1
    if right:
        if inverted:
            alpha[1] = 1
            if long_diagonal: alpha[0] = alpha[2] = 1
        else:
            flip = True
            alpha[2] = 1
            if long_diagonal: alpha[1] = alpha[3] = 1
    if left:
        if inverted:
            flip = True
            alpha[0] = 1
            if long_diagonal: alpha[1] = alpha[3] = 1
        else:
            alpha[3] = 1
            if long_diagonal: alpha[0] = alpha[2] = 1
    if record['custom_edge_class'] >= 0:
        return 0, False
    return sum(bit << i for i, bit in enumerate(alpha)), flip


class TerrainData:
    def __init__(self, m, checkpoint=lambda: None):
        hm = m.heightmap()
        self.width, self.height, self.border = hm['width'], hm['height'], hm['border']
        self.playable = playable_extent(hm)
        self.heights = hm['elevations'].astype(np.float32) * 0.0390625
        # Read every frame (the shadow light's window); the heights never change.
        self.mean_height, self.max_height = float(self.heights.mean()), float(self.heights.max())
        blend = m.blend(inspection=True)
        self.textures = blend['textures']
        arrays = blend['arrays']
        tiles = arrays['tiles'].astype(np.int64)
        self.impassable = arrays.get('impassable')
        starts = np.array([t['tile_start'] for t in self.textures])
        counts = np.array([t['tile_count'] for t in self.textures])
        sizes = np.array([t['cell_size'] for t in self.textures])
        total = int((starts+counts).max()) if len(starts) else 1
        # Tile index -> (texture, subtile x, subtile y), subtiles counted from
        # the image's bottom-left as the engine reads TGA rows.
        lut = np.zeros((total+1, 3), np.int64)
        for i, t in enumerate(self.textures):
            local = np.arange(t['tile_count'])
            c, q = local >> 2, local & 3
            size = t['cell_size']
            lut[t['tile_start']+local, 0] = i
            lut[t['tile_start']+local, 1] = (c % size)*2 + (q & 1)
            lut[t['tile_start']+local, 2] = (c // size)*2 + ((q >> 1) & 1)
        self.subtiles = 2*sizes  # subtiles across each texture
        tables = terrain_records(m, blend)
        records = {r['index']: r for r in tables['blends']}
        self.blend_count = len(records)

        def pack(tile_array):
            t = np.clip(tile_array, 0, total)
            return lut[t, 0] | (lut[t, 1] << 10) | (lut[t, 2] << 15)

        base = pack(tiles)
        def layer(indices):
            # Pack each blend once, then gather by ID. A full-map mask for
            # each record made stock maps with many blends take minutes.
            count = max(records, default=0) + 1
            words = np.zeros(count, np.int64)
            flips = np.zeros(count, bool)
            for number, index in enumerate(np.unique(indices)):
                if number % 128 == 0:
                    checkpoint()
                if index == 0 or int(index) not in records:
                    continue
                record = records[int(index)]
                mask, flip = blend_corners(record)
                if not mask:
                    continue
                packed = pack(np.full(1, record['tile']))[0]
                words[index] = packed | (mask << 20) | (1 << 24)
                flips[index] = flip
            safe = np.where((indices >= 0) & (indices < count), indices, 0)
            return words[safe], flips[safe]
        primary, flip = layer(arrays['blends'].astype(np.int64))
        extra, _ = layer(arrays['three_way'].astype(np.int64))
        cliff = arrays['cliffs'] != 0
        primary[cliff] = 0
        # Cliff UVs, per cell: u0..u3 and v0..v3, and whether the cell uses them.
        self.cliff_u = np.zeros((self.height, self.width, 4), np.float32)
        self.cliff_v = np.zeros((self.height, self.width, 4), np.float32)
        cliff_records = tables.get('cliffs', [])
        mapped = np.zeros(cliff.shape, bool)
        if cliff_records:
            table = np.zeros((len(cliff_records)+1, 8), np.float32)
            tile_texture = np.zeros(len(cliff_records)+1, np.int64)-1
            record_flip = np.zeros(len(cliff_records)+1, bool)
            for r in cliff_records:
                table[r['index']] = np.ravel(r['uv'])
                tile_texture[r['index']] = lut[min(max(r['tile'], 0), total), 0]
                record_flip[r['index']] = bool(r['flip'])
            index = np.where(arrays['cliffs'].astype(np.int64) <= len(cliff_records), arrays['cliffs'].astype(np.int64), 0)
            mapped = (index > 0) & (tile_texture[index] == (base & 1023))
            self.cliff_u[mapped] = table[index[mapped]][:, 0::2]
            self.cliff_v[mapped] = table[index[mapped]][:, 1::2]
            flip = np.where(mapped, record_flip[index], flip)
        self.cells = np.stack([base | (mapped.astype(np.int64) << 25), primary, extra, flip.astype(np.int64)], -1).astype(np.uint32)
        self.cliff_cells = int(np.count_nonzero(cliff))
        self.cliff_mapped = int(np.count_nonzero(mapped))
        # Height range of each 16x16-cell tile (samples origin..origin+16),
        # for W3DTerrainBackground::updateCenter's camera distance.
        nx, ny = (self.width + TILE_CELLS - 2)//TILE_CELLS, (self.height + TILE_CELLS - 2)//TILE_CELLS
        self.tile_z = np.zeros((ny, nx, 2), np.float32)
        for j in range(ny):
            for i in range(nx):
                block = self.heights[j*TILE_CELLS:(j+1)*TILE_CELLS+1, i*TILE_CELLS:(i+1)*TILE_CELLS+1]
                self.tile_z[j, i] = block.min(), block.max()

    def height_at(self, x, y):
        """Bilinear terrain height at world coordinates (playable origin)."""
        gx = np.clip(np.asarray(x, float)/10 + self.border, 0, self.width-1.001)
        gy = np.clip(np.asarray(y, float)/10 + self.border, 0, self.height-1.001)
        ix, iy = gx.astype(int), gy.astype(int)
        fx, fy = gx-ix, gy-iy
        h = self.heights
        return ((1-fy)*((1-fx)*h[iy, ix] + fx*h[iy, ix+1]) + fy*((1-fx)*h[iy+1, ix] + fx*h[iy+1, ix+1]))


class TerrainMixin:
    """MapRenderer's terrain: its cell data on the GPU, the shading technique of the
    detail level, and its lighting uniforms."""

    def _terrain_technique(self):
        """terrain.fx technique (HeightMap 0x000E153A): Default with normal
        maps, else Default_M with distance-dependent textures, else Default_L.
        Without normal maps doTheLight keeps the sun in the vertex colour."""
        p = self.terrain_program
        normal = self.options['normal_maps']
        p['technique'].value = 2 if normal else (1 if self.distance_textures else 0)
        p['sun_in_vertex'].value = int(not normal)

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
        self.cliff_u = ctx.texture((t.width, t.height), 4, t.cliff_u.tobytes(), dtype='f4')
        self.cliff_v = ctx.texture((t.width, t.height), 4, t.cliff_v.tobytes(), dtype='f4')
        for texture in (self.cliff_u, self.cliff_v):
            texture.filter = (self.moderngl.NEAREST, self.moderngl.NEAREST)
        self.report['cliff_mapped_cells'] = t.cliff_mapped
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
        for name, unit in [('heights', 0), ('cells', 1), ('albedo', 2), ('normals', 3), ('macro_tex', 4), ('cloud_tex', 5),
                           ('cliff_u', 13), ('cliff_v', 14)]:
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
