"""Synthetic native documents; no proprietary assets required."""
import struct
import numpy as np
from mapworkshop.formats.map import Map, Chunk, string


def fixture():
    names = ['HeightMapData', 'BlendTileData', 'WorldInfo', 'ObjectsList', 'Object', 'uniqueID', 'MysteryChunk']
    m = object.__new__(Map)
    m.names = dict(enumerate(names, 1))
    width, height, border = 30, 34, 2  # Not divisible by 8: exercise per-row bit padding.
    area = width * height
    terrain = struct.pack('<7I', width, height, border, 1, width - 2 * border, height - 2 * border, area)
    terrain += np.full((height, width), 2560, dtype='<u2').tobytes()
    blend = struct.pack('<I', area) + bytes(area * 14)
    bits = bytes(((width + 7) // 8) * height)
    blend += bits * 5 + bytes(area) + bits
    blend += struct.pack('<4I', 16, 1, 1, 1)
    blend += struct.pack('<4I', 0, 16, 4, 0) + string('GrassTest') + bytes(8)
    obj = struct.pack('<4fI', 25, 25, 0, 0, 0) + string('TreeEvergreen03')
    obj += m.encode_properties([('uniqueID', 3, 'TreeEvergreen03 0')])
    m.chunks = [Chunk(1, 5, terrain), Chunk(2, 18, blend), Chunk(3, 1, bytes(2)),
                Chunk(4, 3, Chunk(5, 3, obj).encode()), Chunk(7, 19, b'unknown data must survive\x00\xff')]
    return m.encode()
