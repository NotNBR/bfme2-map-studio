"""Terrain sections: HeightMapData v5 and BlendTileData v8..18, read and written
by one codec each, plus a read-only inspection of the texture records.

Retain raw values alongside source-based names; legacy semantics may differ.
See docs/game/terrain-textures.md for provenance
and docs/format/terrain.md for the layout.
"""

import math
import struct

import numpy as np

from mapworkshop.formats.map import Reader, string


DIRECTIONS = ('horizontal', 'vertical', 'right_diagonal', 'left_diagonal')
# Bit planes after the index arrays, and the BlendTileData version that adds each.
PLANES = (('impassable', 8), ('impassable_players', 10), ('passage_widths', 11), ('taintable', 14),
          ('extra_passable', 15), ('flammability', 16), ('visible', 17))
BLEND_RECORD, CLIFF_RECORD = 'I4sBBiI', 'I8fBB'


# HeightMapData v5 ---------------------------------------------------------
def decode_heights(data):
    """width, height, border, borders (the playable (w, h) per border record),
    elevations (height x width u16, 0.0390625 units each) and the byte offset
    of the elevations in the payload."""
    r = Reader(data)
    w, h, border, count = r.get('4I')
    if not 1 <= w <= 4096 or not 1 <= h <= 4096 or count > 1000:
        raise ValueError('Invalid dimensions/borders')
    borders = [r.get('2I') for _ in range(count)]
    area, = r.get('I')
    if area != w * h or w <= 2 * border or h <= 2 * border:
        raise ValueError('Invalid terrain area')
    offset = r.pos
    elevations = np.frombuffer(r.take(w * h * 2), dtype='<u2').reshape(h, w)
    r.finish()
    return dict(width=w, height=h, border=border, borders=borders, offset=offset, elevations=elevations)


def playable_extent(heights):
    """The playable area's (x, y) size in world units for decode_heights'
    values, as the game takes it: W3DTerrainLogic::getExtent (ROTWK game.dat
    RW 0x46273E, 0x4626A3, as reconstructed in OpenBFME's TerrainLogic) runs
    from (0, 0) to the largest border record on each axis times 10. A map
    without border records has (W - 2B, H - 2B) samples, which is what nearly
    every stock map and every map the toolkit writes stores."""
    borders = heights.get('borders') or [(heights['width'] - 2*heights['border'],
                                          heights['height'] - 2*heights['border'])]
    return max(b[0] for b in borders)*10.0, max(b[1] for b in borders)*10.0


def encode_heights(value):
    """The payload for decode_heights' values; the size comes from the elevations."""
    elevations = np.asarray(value['elevations'])
    h, w = elevations.shape
    out = bytearray(struct.pack('<4I', w, h, value['border'], len(value['borders'])))
    for b in value['borders']:
        out += struct.pack('<2I', *b)
    out += struct.pack('<I', w * h)
    return bytes(out) + elevations.astype('<u2').tobytes()


# BlendTileData v8..18 -------------------------------------------------------
def plane_names(version):
    return [name for name, minimum in PLANES if version >= minimum]


def _index_type(version):
    return '<u4' if version >= 14 else '<u2'


def decode_blend(data, version, m):
    """The texture layer of terrain `m` (its HeightMapData gives the grid size):
    arrays (tiles, blend/three-way/cliff indices and the per-cell planes, each
    height x width), the texture and edge-texture tables, the blend and cliff
    records, and their declared counts. Also the byte offsets of the arrays and
    of the tables (`offsets`, `tail_offset`), for inspection."""
    terrain = decode_heights(m.chunk('HeightMapData').data)
    w, h = terrain['width'], terrain['height']
    area = w * h
    r = Reader(data)
    if r.get('I')[0] != area:
        raise ValueError('Blend/height dimensions disagree')
    arrays, offsets, packed = {}, {}, {}
    index_type = _index_type(version)
    for name, dtype in [('tiles', '<u2'), ('blends', index_type), ('three_way', index_type), ('cliffs', index_type)]:
        offsets[name] = r.pos
        arrays[name] = np.frombuffer(r.take(area * np.dtype(dtype).itemsize), dtype=dtype).reshape(h, w)
    for name in plane_names(version):
        offsets[name] = r.pos
        if name == 'flammability':
            arrays[name] = np.frombuffer(r.take(area), dtype='u1').reshape(h, w)
        else:
            raw = r.take(((w + 7) // 8) * h)
            arrays[name] = np.unpackbits(np.frombuffer(raw, dtype='u1').reshape(h, -1), axis=1, bitorder='little')[:, :w]
            if np.packbits(arrays[name], axis=1, bitorder='little').tobytes() != raw:
                packed[name] = raw   # padding bits past the last column are set: keep them
    tail_offset = r.pos
    cells, blend_count, cliff_count, texture_count = r.get('4I')
    if texture_count > 4096:
        raise ValueError('Invalid texture table')
    textures = []
    for _ in range(texture_count):
        start, count, size, magic = r.get('4I')
        textures.append(dict(cell_start=start, cell_count=count, cell_size=size, magic=magic, name=r.string()))
    edge_cells, edge_count = r.get('2I')
    if edge_count > 4096:
        raise ValueError('Invalid edge texture table')
    edges = []
    for _ in range(edge_count):
        start, count, size = r.get('3I')
        edges.append(dict(cell_start=start, cell_count=count, cell_size=size, name=r.string()))
    offsets['blend_records'] = r.pos
    blends = []
    for _ in range(max(blend_count - 1, 0)):
        tile, direction, flags, long_diagonal, edge, marker = r.get(BLEND_RECORD)
        blends.append(dict(tile=tile, direction=direction, flags=flags, long_diagonal=long_diagonal,
                           custom_edge_class=edge, marker=marker))
    offsets['cliff_records'] = r.pos
    cliffs = []
    for _ in range(max(cliff_count - 1, 0)):
        tile, *values = r.get(CLIFF_RECORD)
        cliffs.append(dict(tile=tile, uv=tuple(values[:8]), flip=values[8], mutant=values[9]))
    r.finish()
    return dict(arrays=arrays, texture_cells=cells, textures=textures, edge_texture_cells=edge_cells,
                edge_textures=edges, blend_records=blends, cliff_records=cliffs,
                blend_count=blend_count, cliff_count=cliff_count, packed_planes=packed,
                offsets=offsets, tail_offset=tail_offset, version=version)


def _declared(count, records):
    """A table's stored count is its records plus one; with no records the
    file may store 0 or 1, so a given count is kept when it agrees."""
    return count if count is not None and max(count - 1, 0) == len(records) else len(records) + 1


def encode_blend(value, version, m=None):
    """The payload for decode_blend's values; the grid size comes from the arrays.
    Planes this version does not store are ignored; counts follow the tables."""
    arrays = value['arrays']
    h, w = np.shape(arrays['tiles'])
    out = bytearray(struct.pack('<I', w * h))
    index_type = _index_type(version)
    for name, dtype in [('tiles', '<u2'), ('blends', index_type), ('three_way', index_type), ('cliffs', index_type)]:
        out += np.asarray(arrays[name]).astype(dtype).tobytes()
    packed = value.get('packed_planes', {})
    for name in plane_names(version):
        plane = np.asarray(arrays[name]).astype('u1')
        if name == 'flammability':
            out += plane.tobytes()
            continue
        raw = np.packbits(plane, axis=1, bitorder='little').tobytes()
        kept = packed.get(name)
        if kept is not None and len(kept) == len(raw) and np.array_equal(
                np.unpackbits(np.frombuffer(kept, 'u1').reshape(h, -1), axis=1, bitorder='little')[:, :w], plane):
            raw = kept
        out += raw
    blends, cliffs = value['blend_records'], value['cliff_records']
    out += struct.pack('<4I', value['texture_cells'], _declared(value.get('blend_count'), blends),
                       _declared(value.get('cliff_count'), cliffs), len(value['textures']))
    for t in value['textures']:
        out += struct.pack('<4I', t['cell_start'], t['cell_count'], t['cell_size'], t.get('magic', 0)) + string(t['name'])
    out += struct.pack('<2I', value['edge_texture_cells'], len(value['edge_textures']))
    for e in value['edge_textures']:
        out += struct.pack('<3I', e['cell_start'], e['cell_count'], e['cell_size']) + string(e['name'])
    for b in blends:
        out += struct.pack('<' + BLEND_RECORD, b['tile'], b['direction'], b['flags'], b['long_diagonal'],
                           b['custom_edge_class'], b['marker'])
    for c in cliffs:
        out += struct.pack('<' + CLIFF_RECORD, c['tile'], *c['uv'], c['flip'], c['mutant'])
    return bytes(out)


# Inspection -------------------------------------------------------------------
def terrain_records(m, blend=None):
    """The texture tables and blend/cliff records with source-based names,
    keeping raw values; does not change the map."""
    c = m.chunk('BlendTileData')
    value = decode_blend(c.data, c.version, m)
    blends = []
    for index, b in enumerate(value['blend_records'], 1):
        direction = b['direction']
        # Do not coerce unusual direction bytes into booleans or discard flag bits.
        known_direction = all(v in (0, 1) for v in direction) and sum(direction) == 1
        flags = b['flags']
        blends.append(dict(index=index, tile=b['tile'], direction_hex=direction.hex(),
                           direction=DIRECTIONS[direction.index(1)] if known_direction else None,
                           flags=flags, inverted=bool(flags & 1), force_flip=bool(flags & 2),
                           unknown_flag_bits=flags & ~3, long_diagonal=b['long_diagonal'],
                           custom_edge_class=b['custom_edge_class'], marker=b['marker']))
    cliffs = []
    for index, record in enumerate(value['cliff_records'], 1):
        uv = record['uv']
        if not all(math.isfinite(v) for v in uv):
            raise ValueError(f'Non-finite cliff UV in record {index}')
        cliffs.append(dict(index=index, tile=record['tile'], uv=[list(uv[i:i + 2]) for i in range(0, 8, 2)],
                           flip=record['flip'], mutant=record['mutant']))
    return dict(texture_cells=value['texture_cells'], textures=len(value['textures']),
                declared_blend_count=value['blend_count'], declared_cliff_count=value['cliff_count'],
                edge_texture_cells=value['edge_texture_cells'], edge_textures=value['edge_textures'],
                blends=blends, cliffs=cliffs, cliff_mapping_offset=value['offsets']['cliff_records'])
