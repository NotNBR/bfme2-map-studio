"""BFME2 GlobalLighting v1..8 layout from the matched retail reader/writer.

Names for the third light array, chunk flag, vector triplets and final values
remain neutral: their serialization is proven, their visual purpose is not.
"""

import math
import struct

from mapworkshop.formats.map import Reader


def slots(version):
    if version not in range(1, 9):
        raise ValueError(f'Unsupported GlobalLighting version {version}')
    result = [('terrain', 0), ('objects', 0)]
    if version >= 2:
        result += [('objects', 1), ('objects', 2)]
    if version >= 3:
        result += [('terrain', 1), ('terrain', 2)]
    if version >= 4:
        result += [('third', i) for i in range(3)]
    return result


def decode(data, version):
    order = slots(version)
    r = Reader(data)
    result = dict(time_of_day=r.get('I')[0], configurations=[])
    for _ in range(4):
        result['configurations'].append([
            dict(target=target, light_index=index, ambient=r.get('3f'),
                 diffuse=r.get('3f'), direction=r.get('3f')) for target, index in order])
    if version >= 5:
        result['overbright_value'] = r.get('f')[0]
    if version >= 6:
        result['chunk_flag_raw'] = r.get('I')[0]
        result['vector_triplets'] = [r.get('3f')]
    if version >= 7:
        result['vector_triplets'] += [r.get('3f'), r.get('3f')]
    # The native reader accepts an omitted shadow in earlier versions. In v8
    # the following 12 bytes are mandatory, so an absent shadow is ambiguous
    # and rejected here instead of consuming its first final value as a color.
    if r.pos < len(data):
        result['shadow_color_raw'] = r.get('I')[0]
    if version >= 8:
        result['final_values'] = r.get('3f')
    r.finish()
    return result


def encode(value, version=8):
    """Write explicit fields; reject unsupported versions/order/nonfinite floats."""
    order = slots(version)
    out = bytearray(struct.pack('<I', value['time_of_day']))

    def floats(values, size):
        if len(values) != size or not all(math.isfinite(v) for v in values):
            raise ValueError(f'Expected {size} finite lighting values')
        out.extend(struct.pack('<' + 'f' * size, *values))

    configs = value['configurations']
    if len(configs) != 4:
        raise ValueError('Expected four time-of-day configurations')
    for lights in configs:
        if [(v['target'], v['light_index']) for v in lights] != order:
            raise ValueError('Lighting slots do not match the native serialization order')
        for light in lights:
            for name in ('ambient', 'diffuse', 'direction'):
                floats(light[name], 3)
    if version >= 5:
        floats([value['overbright_value']], 1)
    if version >= 6:
        out.extend(struct.pack('<I', value['chunk_flag_raw']))
        vectors = value['vector_triplets']
        if len(vectors) != (3 if version >= 7 else 1):
            raise ValueError('Incorrect lighting vector count')
        for vector in vectors:
            floats(vector, 3)
    if 'shadow_color_raw' in value:
        out.extend(struct.pack('<I', value['shadow_color_raw']))
    elif version >= 8:
        raise ValueError('GlobalLighting v8 requires the shadow color before final values')
    if version >= 8:
        floats(value['final_values'], 3)
    return bytes(out)
