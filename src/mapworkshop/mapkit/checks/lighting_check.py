"""Read-only BFME2 1.06 lighting observation; requires the host's image hash gate."""

import math
import struct

from mapworkshop.formats.lighting import slots


def snapshot(game):
    data = game.u32(game.base + 0x9FE758)
    if not data:
        raise ValueError('Missing native GlobalData')
    def floats(address, n):
        return struct.unpack('<' + 'f' * n, game.read(address, 4*n))
    configurations = []
    for time in range(1, 5):
        lights = []
        for target, index in slots(8):
            offset = {'terrain':0x140, 'objects':0x3C8, 'third':0x650}[target]
            v = floats(data + offset + (time*3+index)*36, 9)
            lights.append(dict(target=target, light_index=index, ambient=v[:3], diffuse=v[3:6], direction=v[6:]))
        configurations.append(lights)
    shadow = game.u32(game.base + 0x9E5DFC)
    return dict(time_of_day=game.u32(data+0x134), configurations=configurations,
                overbright_enabled=bool(game.read(game.base+0x9B5F84,1)[0]),
                chunk_flag_raw=game.read(data+0xD34,1)[0],
                vector_triplets=[floats(game.base+0x9BD788+i*16,3) for i in range(3)],
                shadow_color_raw=game.u32(shadow+4) if shadow else None,
                final_values=floats(data+0x944,3))


def differences(expected, observed):
    expected = dict(expected)
    expected['overbright_enabled'] = expected.pop('overbright_value') > 1
    expected['chunk_flag_raw'] = int(expected['chunk_flag_raw'] != 0)
    errors = []
    def check(a,b,path):
        if isinstance(a, dict):
            if not isinstance(b, dict): errors.append(path); return
            for key, value in a.items(): check(value,b.get(key),path+'.'+key)
        elif isinstance(a,(list,tuple)):
            if not isinstance(b,(list,tuple)) or len(a)!=len(b): errors.append(path); return
            for i,(x,y) in enumerate(zip(a,b)): check(x,y,f'{path}[{i}]')
        elif isinstance(a,float):
            if not isinstance(b,(float,int)) or not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6): errors.append(path)
        elif a != b: errors.append(path)
    check(expected,observed,'lighting')
    return errors
