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
"""

import re

import numpy as np

from mapworkshop.formats.terrain import terrain_records

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
        self.heights = hm['elevations'].astype(np.float32) * 0.0390625
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
