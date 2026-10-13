"""CastleTemplates v1..5 serialization, from BFME2's matched native routines.

Coordinates are relative to the castle center. Priority/phase and path names
are stored by the v5 writer but ignored by the matched retail chunk reader.
No claim that writing this section alone makes a usable base template.
"""

import math
import struct

from mapworkshop.formats.map import Reader, string


def checked_version(version):
    if version not in range(1, 6):
        raise ValueError(f'Unsupported CastleTemplates version {version}')


def decode(data, names, version):
    checked_version(version)
    r = Reader(data)
    def count():
        value = r.get('I')[0]
        if value > 100000: raise ValueError('Unreasonable castle record count')
        return value
    kind = r.get('B')[0]
    idx = int.from_bytes(r.take(3), 'little')
    result = dict(faction=names[idx], property_kind=kind, buildings=[], paths=[])
    for _ in range(count()):
        item = dict(building_name=r.string(), template=r.string(), position=r.get('3f'), angle=r.get('f')[0])
        if version >= 4: item.update(priority=r.get('i')[0], phase=r.get('i')[0])
        result['buildings'].append(item)
    if version >= 2:
        for _ in range(count()):
            item = {}
            if version >= 5: item['name'] = r.string()
            item['points'] = [r.get('2f' if version >= 3 else '3i') for _ in range(count())]
            result['paths'].append(item)
    r.finish()
    return result


def encode(value, intern, version=5):
    checked_version(version)
    out = bytearray(struct.pack('<B', value.get('property_kind',3)))
    out.extend(intern(value['faction']).to_bytes(3,'little'))
    buildings, paths = value['buildings'], value['paths']
    if len(buildings)>100000 or len(paths)>100000: raise ValueError('Unreasonable castle count')
    out.extend(struct.pack('<I',len(buildings)))
    def floats(values, size):
        if len(values)!=size or not all(math.isfinite(v) for v in values):
            raise ValueError('Invalid castle coordinates')
        out.extend(struct.pack('<'+'f'*size,*values))
    for building in buildings:
        out.extend(string(building['building_name'])+string(building['template']))
        floats(building['position'],3)
        floats([building['angle']],1)
        if version>=4: out.extend(struct.pack('<2i',building['priority'],building['phase']))
    if version>=2:
        out.extend(struct.pack('<I',len(paths)))
        for path in paths:
            if version>=5: out.extend(string(path['name']))
            if len(path['points'])>100000: raise ValueError('Unreasonable castle point count')
            out.extend(struct.pack('<I',len(path['points'])))
            for point in path['points']:
                if version>=3: floats(point,2)
                else: out.extend(struct.pack('<3i',*point))
    elif paths:
        raise ValueError('CastleTemplates v1 cannot store paths')
    return bytes(out)
