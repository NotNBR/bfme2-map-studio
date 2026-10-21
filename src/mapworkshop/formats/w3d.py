"""BFME W3D animation files: skeletons, their channels (adaptive-delta and
time-coded) and a model's still pose at an animation's first frame (pose).

GPL-3.0-only. Adaptive delta decoding follows OpenSAGE's
W3dAdaptiveDeltaCodec / W3dAdaptiveDeltaBlock (see THIRD_PARTY.md).
Format cross-checked against openbfme2's recovered W3D definitions.
"""
import math
import struct
import numpy as np


def chunks(data):
    pos = 0
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError('Truncated W3D chunk header')
        kind, size = struct.unpack_from('<II', data, pos)
        end = pos + 8 + (size & 0x7fffffff)
        if end > len(data):
            raise ValueError('W3D chunk exceeds its parent')
        yield kind, data[pos + 8:end]
        pos = end


def cstr(data):
    return data.split(b'\0', 1)[0].decode('ascii').lower()


def matrix(t, q):
    q = np.asarray(q, dtype=float)
    q /= max(np.linalg.norm(q), 1e-10)
    x, y, z, w = q
    m = np.eye(4)
    m[:3, :3] = [
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ]
    m[:3, 3] = t
    return m


def skeleton(data):
    hierarchy = dict(chunks(data))[0x100]
    items = dict(chunks(hierarchy))
    count = struct.unpack_from('<I', items[0x101], 20)[0]
    pivots = items[0x102]
    if len(pivots) != count * 60:
        raise ValueError('Unexpected W3D pivot layout')
    bones = []
    for i in range(count):
        p = pivots[i*60:(i+1)*60]
        parent = struct.unpack_from('<i', p, 16)[0]
        if parent >= i:
            raise ValueError('Skeleton is not parent ordered')
        local = matrix(struct.unpack_from('<3f', p, 20), struct.unpack_from('<4f', p, 44))
        world = bones[parent]['bind'] @ local if parent >= 0 else local
        bones.append(dict(name=cstr(p[:16]), parent=parent, local=local, bind=world))
    return bones


def decode_delta(data, count, components, bits):
    scale = struct.unpack_from('<f', data)[0]
    result = np.zeros((count, components))
    result[0] = struct.unpack_from('<'+'f'*components, data, 4)
    pos = 4 + components*4
    for block in range((count + 15)//16):
        for component in range(components):
            index = data[pos]
            pos += 1
            factor = 10.0**(index-8) if index < 16 else 1-math.sin(math.pi/2*(index-16)/240)
            factor *= scale * (1 if bits == 4 else 1/16)
            raw = data[pos:pos+bits*2]
            if len(raw) != bits*2:
                raise ValueError('Truncated adaptive delta block')
            pos += bits*2
            deltas = []
            for byte in raw:
                if bits == 4:
                    for n in (byte & 15, byte >> 4):
                        deltas.append(n-16 if n >= 8 else n)
                else:
                    deltas.append(byte-128)
            for j, delta in enumerate(deltas):
                frame = block*16+j+1
                if frame >= count:
                    break
                result[frame, component] = result[frame-1, component] + factor*delta
    return result


def interpolate(times, values, frames, quaternion=False, start=0):
    """Values at frames start .. start+frames-1 from keys at `times`."""
    result = np.empty((frames, values.shape[1]))
    right = 0
    for index, frame in enumerate(range(start, start+frames)):
        while right < len(times)-1 and times[right] < frame:
            right += 1
        left = max(0, right-1)
        a, b = values[left], values[right].copy()
        t = float(np.clip((frame-times[left])/max(1, int(times[right])-int(times[left])), 0, 1))
        if quaternion:
            a = a/max(np.linalg.norm(a), 1e-10)
            b /= max(np.linalg.norm(b), 1e-10)
            dot = np.dot(a, b)
            if dot < 0:
                b, dot = -b, -dot
            if dot < .9995:
                angle = math.acos(np.clip(dot, -1, 1))
                result[index] = (a*math.sin((1-t)*angle)+b*math.sin(t*angle))/math.sin(angle)
                continue
        result[index] = a*(1-t)+b*t
    return result


def channels(data):
    """An animation file's motion: (dict(name, hierarchy, frames, fps),
    [(pivot, channel, times, values)]). Channel 0-2 is a translation along
    X, Y or Z, 6 a quaternion (x, y, z, w); visibility channels are left out.
    Reads uncompressed animations (0x200), compressed ones with timecoded
    channels (0x282) and BFME's motion channels (0x284, timecoded or
    adaptive delta)."""
    top = dict(chunks(data))
    kind = 0x280 if 0x280 in top else 0x200 if 0x200 in top else None
    if kind is None:
        raise ValueError('No W3D animation')
    items = list(chunks(top[kind]))
    header = dict(items)[kind+1]
    frames, fps = struct.unpack_from('<IH' if kind == 0x280 else '<II', header, 36)
    info = dict(name=cstr(header[4:20]), hierarchy=cstr(header[20:36]), frames=frames, fps=int(fps))
    motion = []
    for kind, payload in items:
        if kind == 0x202:
            # W3dAnimChannelStruct: first and last frame, vector length,
            # type, pivot, padding; then a value for every frame between.
            first, last, components, channel, pivot = struct.unpack_from('<5H', payload)
            count = last-first+1
            times = np.arange(first, last+1)
            values = np.frombuffer(payload, '<f4', count*components, 12).reshape(count, components)
        elif kind == 0x282:
            # W3dTimeCodedAnimationChannel: count, pivot, vector length, type,
            # then each time code (top bit: no interpolation) and its value.
            count, pivot, components, channel = struct.unpack_from('<IHBB', payload)
            rows = np.frombuffer(payload, [('time', '<u4'), ('value', '<f4', (components,))], count, 8)
            times = (rows['time'] & 0x7fffffff).astype(int)
            values = rows['value'].reshape(count, components)
        elif kind == 0x284:
            zero, delta, components, channel, count, pivot = struct.unpack_from('<4B2H', payload)
            if delta == 0:
                times = np.frombuffer(payload, '<u2', count, 8).astype(int) & 0x7fff
                start = 8 + ((count+1)//2)*4
                values = np.frombuffer(payload, '<f4', count*components, start).reshape(count, components)
            elif delta in (1, 2):
                times = np.arange(count)
                values = decode_delta(payload[8:], count, components, 4 if delta == 1 else 8)
            else:
                raise ValueError(f'Unsupported W3D delta type {delta}')
        elif kind in (0x201, 0x203, 0x281, 0x283):
            continue                     # headers and visibility channels
        else:
            raise ValueError(f'Unsupported animation chunk {kind:#x}')
        if channel not in (0, 1, 2, 6):
            continue
        if not count:
            raise ValueError('Invalid animation channel')
        motion.append((pivot, channel, times, np.asarray(values, float)))
    return info, motion


def sample(times, values, frame, quaternion=False):
    """One channel's value at `frame`, as interpolate gives it."""
    right = min(int(np.searchsorted(times, frame)), len(times)-1)
    return interpolate(times[max(0, right-1):right+1], values[max(0, right-1):right+1], 1, quaternion,
                       start=frame)[0]


def local_poses(bones, motion, frames):
    """Each frame's (translation, rotation) offsets of every bone."""
    translation = np.zeros((len(frames), len(bones), 3))
    rotation = np.zeros((len(frames), len(bones), 4)); rotation[:, :, 3] = 1
    for pivot, channel, times, values in motion:
        if pivot >= len(bones):
            raise ValueError('Invalid animation channel')
        if len(frames) == 1:
            values = sample(times, values, frames[0], channel == 6)[None]
        else:
            values = interpolate(times, values, len(frames), channel == 6)
        if channel == 6:
            rotation[:, pivot] = values
        else:
            translation[:, pivot, channel] = values[:, 0]
    return translation, rotation


def posed(bones, translation, rotation):
    """Model-space matrices of the bones under one frame's offsets."""
    world = []
    for i, bone in enumerate(bones):
        # OpenSAGE uses row vectors: AnimatedOffset * BindLocal.
        # Our column-vector equivalent is BindLocal * AnimatedOffset.
        local = bone['local'] @ matrix(translation[i], rotation[i])
        world.append(world[bone['parent']] @ local if bone['parent'] >= 0 else local)
    return world


def pose(data, skeleton_of, frame=0):
    """One frame of an animation file: the bones of its hierarchy and their
    model-space matrices (W3D coordinates). `skeleton_of(name)` gives a
    hierarchy's bones as skeleton() reads them."""
    info, motion = channels(data)
    bones = skeleton_of(info['hierarchy'])
    translation, rotation = local_poses(bones, motion, [min(frame, max(info['frames']-1, 0))])
    return bones, posed(bones, translation[0], rotation[0])
