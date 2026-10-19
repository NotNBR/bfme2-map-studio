"""Lossless CkMp container with narrowly scoped BFME2 authoring operations.

GPL-3.0-only. Layouts cross-checked with OpenSAGE Data/Map (see THIRD_PARTY).
Unknown chunks stay byte-identical. This is not a replacement game renderer.
"""

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import struct

import numpy as np

from mapworkshop.formats.map_archive import unpack


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tile_offset(x, y, cell_size):
    """Native texture cells contain four 2x2 subtiles, not row-major subtile IDs."""
    return 4 * (((y // 2) % cell_size) * cell_size + (x // 2) % cell_size) + (y % 2) * 2 + x % 2


class Reader:
    def __init__(self, data):
        # A growing ObjectsList is a bytearray (Map.add_object); what is read
        # from it is bytes, as from every other chunk.
        self.data, self.pos = bytes(data) if isinstance(data, bytearray) else data, 0

    def take(self, n):
        if n < 0 or self.pos + n > len(self.data):
            raise ValueError('Truncated map data')
        value = self.data[self.pos:self.pos + n]
        self.pos += n
        return value

    def get(self, fmt):
        return struct.unpack('<' + fmt, self.take(struct.calcsize('<' + fmt)))

    def string(self, wide=False):
        length, = self.get('H')
        return self.take(length * (2 if wide else 1)).decode('utf-16-le' if wide else 'cp1252')

    def finish(self):
        if self.pos != len(self.data):
            raise ValueError('Unexpected trailing data')


def string(value, wide=False):
    data = value.encode('utf-16-le' if wide else 'cp1252')
    return struct.pack('<H', len(data) // (2 if wide else 1)) + data


@dataclass
class Chunk:
    name_id: int
    version: int
    data: bytes

    def encode(self):
        return struct.pack('<IHI', self.name_id, self.version, len(self.data)) + self.data


def chunks(data, names):
    result, r = [], Reader(data)
    while r.pos < len(data):
        idx, version, size = r.get('IHI')
        if idx not in names:
            raise ValueError('Unknown chunk name index')
        result.append(Chunk(idx, version, r.take(size)))
    return result


class Map:
    def __init__(self, data):
        self.original = unpack(data)
        r = Reader(self.original)
        if r.take(4) != b'CkMp':
            raise ValueError('Expected CkMp')
        count, = r.get('I')
        if count > 100000:
            raise ValueError('Too many strings')
        self.names = {}
        for expected in range(count, 0, -1):
            length = shift = 0
            while True:
                b, = r.get('B')
                length |= (b & 127) << shift
                shift += 7
                if shift > 35:
                    raise ValueError('Invalid name length')
                if b < 128:
                    break
            name = r.take(length).decode('utf-8')
            idx, = r.get('I')
            if idx != expected:
                raise ValueError('Unexpected name index')
            self.names[idx] = name
        self.chunks = chunks(r.take(len(r.data) - r.pos), self.names)

    def encode(self):
        out = bytearray(b'CkMp' + struct.pack('<I', len(self.names)))
        for idx in range(len(self.names), 0, -1):
            name = self.names[idx].encode('utf-8')
            size = len(name)
            while size >= 128:
                out.append((size & 127) | 128)
                size >>= 7
            out.append(size)
            out.extend(name + struct.pack('<I', idx))
        return bytes(out) + b''.join(c.encode() for c in self.chunks)

    def intern(self, name):
        for idx, text in self.names.items():
            if name == text:
                return idx
        idx = len(self.names) + 1
        self.names[idx] = name
        return idx

    def chunk(self, name):
        found = [c for c in self.chunks if self.names[c.name_id] == name]
        if len(found) != 1:
            raise ValueError(f'Expected exactly one {name} chunk')
        return found[0]

    def properties(self, r):
        count, = r.get('H')
        result = []
        for _ in range(count):
            kind, = r.get('B')
            name = self.names[int.from_bytes(r.take(3), 'little')]
            if kind in (0, 1, 2):
                value, = r.get({0: 'B', 1: 'i', 2: 'f'}[kind])
            elif kind in (3, 4, 5):
                value = r.string(kind == 4)
            else:
                raise ValueError(f'Unknown property kind {kind}')
            result.append((name, kind, value))
        return result

    def encode_properties(self, properties):
        out = bytearray(struct.pack('<H', len(properties)))
        for name, kind, value in properties:
            out.append(kind)
            out.extend(self.intern(name).to_bytes(3, 'little'))
            if kind in (0, 1, 2):
                out.extend(struct.pack('<' + {0: 'B', 1: 'i', 2: 'f'}[kind], value))
            else:
                out.extend(string(value, kind == 4))
        return bytes(out)

    def objects(self):
        """The placed objects in file order: index, template, x, y, z (above the
        ground), angle, flags and properties (formats.sections OBJECT)."""
        from mapworkshop.formats import sections
        return [dict(index=i, **o) for i, o in enumerate(sections.read(self, 'ObjectsList'))]

    def encode_object(self, o):
        """An Object v3 chunk from a dict as objects() returns it."""
        from mapworkshop.formats import sections
        payload = sections.object_payload(o, self)
        return Chunk(self.intern('Object'), 3, payload)

    def set_objects(self, objects):
        """Replace the ObjectsList with these objects, in this order."""
        from mapworkshop.formats import sections
        sections.write(self, 'ObjectsList', objects)

    def add_object(self, o):
        """Append one object (a dict as objects() returns it) to the
        ObjectsList. The list's data grows in place as a bytearray, so adding
        n objects costs O(n), not a copy of the whole list per object."""
        chunk = self.chunk('ObjectsList')
        if not isinstance(chunk.data, bytearray):
            chunk.data = bytearray(chunk.data)
        chunk.data += self.encode_object(o).encode()

    def append_object(self, prototype, x, y, angle, name):
        # Map object Z is a terrain-relative offset. Preserve the donor's offset.
        props = [(k, t, v) for k, t, v in prototype['properties'] if k not in ('objectName', 'uniqueID')]
        props.append(('uniqueID', 3, name))
        self.add_object(dict(prototype, x=x, y=y, angle=angle, properties=props))

    def heightmap(self):
        """HeightMapData v5 (formats.terrain.decode_heights)."""
        from mapworkshop.formats.terrain import decode_heights
        c = self.chunk('HeightMapData')
        if c.version != 5:
            raise ValueError('Only BFME2 HeightMapData v5 is editable')
        return decode_heights(c.data)

    def blend(self, *, inspection=False):
        """The terrain's texture arrays and texture table, checked: v18 only and
        every index inside its table, unless `inspection` (v8..17, and indices
        outside the tables reported in inspection_issues)."""
        from mapworkshop.formats.terrain import decode_blend
        c = self.chunk('BlendTileData')
        self.heightmap()
        if c.version != 18 and not (inspection and 8 <= c.version <= 17):
            raise ValueError('Only BFME2 BlendTileData v18 is editable')
        value = decode_blend(c.data, c.version, self)
        arrays = value['arrays']
        textures, tile_start = [], 0
        for t in value['textures']:
            size, count = t['cell_size'], t['cell_count']
            if size * size != count or t['magic'] != 0 or size == 0:
                raise ValueError('Invalid texture descriptor')
            textures.append(dict(name=t['name'], cell_start=t['cell_start'], cell_size=size,
                                 tile_start=tile_start, tile_count=4 * count))
            tile_start += 4 * count
        blends, cliffs = value['blend_count'], value['cliff_count']
        issues = {}
        for field, limit, message in [('tiles', tile_start, 'Tile index outside texture palette'),
                ('blends', max(blends, 1), 'Blend index outside palette'),
                ('three_way', max(blends, 1), 'Blend index outside palette'),
                ('cliffs', max(cliffs, 1), 'Cliff index outside palette')]:
            invalid = int(np.count_nonzero(arrays[field] >= limit))
            if invalid:
                if not inspection:
                    raise ValueError(message)
                issues[field + '_outside_palette'] = invalid
        offsets = {k: v for k, v in value['offsets'].items() if k in arrays}
        return dict(arrays=arrays, offsets=offsets, textures=textures, tail_offset=value['tail_offset'],
                    inspection_issues=issues, version=c.version)

    def report(self, *, inspection=False):
        t, b, objects = self.heightmap(), self.blend(inspection=inspection), self.objects()
        heights = t['elevations'] * 0.0390625
        from mapworkshop.formats.terrain import playable_extent
        extent = playable_extent(t)
        pw, ph = round(extent[0] / 10), round(extent[1] / 10)
        r = Reader(self.chunk('WorldInfo').data)
        world = {k: v for k, _, v in self.properties(r)}
        r.finish()
        warnings = []
        if max(pw, ph) > 600:
            warnings.append('Over 600 tiles: editor/engine size support must be tested; not certified by this tool.')
        if any(not all(math.isfinite(o[k]) for k in ('x', 'y', 'z', 'angle')) for o in objects):
            raise ValueError('Non-finite object coordinate')
        names = [v for o in objects for k, _, v in o['properties'] if k == 'uniqueID' and v]
        duplicates = [k for k, v in Counter(names).items() if v > 1]
        if duplicates:
            warnings.append(f'Duplicate object names: {duplicates[:10]}')
        return dict(sha256=sha(self.encode()), raw_roundtrip_exact=self.encode() == self.original,
                    dimensions=dict(samples=[t['width'], t['height']], border=t['border'],
                                    playable_tiles=[pw, ph], playable_area_tiles=pw * ph,
                                    world_extent=[pw * 10, ph * 10], borders=t['borders']),
                    height_range=[float(heights.min()), float(heights.max())],
                    objects=len(objects), templates=dict(Counter(o['template'] for o in objects).most_common()),
                    textures=b['textures'], world=world, warnings=warnings, terrain_issues=b['inspection_issues'],
                    chunks=[dict(name=self.names[c.name_id], version=c.version, size=len(c.data), sha256=sha(c.data)) for c in self.chunks])


def differences(before, after):
    a, b = before.report(), after.report()
    changed = []
    for i in range(max(len(a['chunks']), len(b['chunks']))):
        left = a['chunks'][i] if i < len(a['chunks']) else None
        right = b['chunks'][i] if i < len(b['chunks']) else None
        if left != right:
            changed.append((right or left)['name'])
    return dict(before_sha256=a['sha256'], after_sha256=b['sha256'],
                objects_added=b['objects'] - a['objects'],
                dimensions_before=a['dimensions'], dimensions_after=b['dimensions'],
                changed_chunks=changed,
                name_table_changed=before.names != after.names,
                warnings=b['warnings'])
