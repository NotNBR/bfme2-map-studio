"""BFME W3D -> Recoil piece geometry and sampled animation.

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


def interpolate(times, values, frames, quaternion=False):
    result = np.empty((frames, values.shape[1]))
    right = 0
    for frame in range(frames):
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
                result[frame] = (a*math.sin((1-t)*angle)+b*math.sin(t*angle))/math.sin(angle)
                continue
        result[frame] = a*(1-t)+b*t
    return result


# W3D: Z up, X forward. Recoil: Y up, Z forward. Positive determinant.
BASIS = np.array([[0, 1, 0, 0], [0, 0, 1, 0], [1, 0, 0, 0], [0, 0, 0, 1]], dtype=float)


def recoil_pose(m):
    """Translation + native Y-X-Z Euler angles (script X,Y,Z components)."""
    pitch = math.asin(float(np.clip(-m[1, 2], -1, 1)))
    if abs(math.cos(pitch)) > 1e-6:
        yaw = math.atan2(m[0, 2], m[2, 2])
        roll = math.atan2(m[1, 0], m[1, 1])
    else:
        yaw = math.atan2(-m[2, 0], m[0, 0]); roll = 0
    return [*m[:3, 3], pitch, yaw, roll]


def animation(data, bones, scale=1):
    items = list(chunks(dict(chunks(data))[0x280]))
    header = dict(items)[0x281]
    frames, fps = struct.unpack_from('<IH', header, 36)
    translation = np.zeros((frames, len(bones), 3))
    rotation = np.zeros((frames, len(bones), 4)); rotation[:, :, 3] = 1
    for kind, payload in items:
        if kind != 0x284:
            if kind not in (0x281, 0x283):
                raise ValueError(f'Unsupported animation chunk {kind:#x}')
            continue
        zero, delta, components, channel, count, pivot = struct.unpack_from('<4B2H', payload)
        if channel not in (0, 1, 2, 6):
            continue
        if not count or pivot >= len(bones):
            raise ValueError('Invalid animation channel')
        if delta == 0:
            times = np.frombuffer(payload, '<u2', count, 8).astype(int) & 0x7fff
            start = 8 + ((count+1)//2)*4
            values = np.frombuffer(payload, '<f4', count*components, start).reshape(count, components)
        elif delta in (1, 2):
            times = np.arange(count)
            values = decode_delta(payload[8:], count, components, 4 if delta == 1 else 8)
        else:
            raise ValueError(f'Unsupported W3D delta type {delta}')
        values = interpolate(times, values, frames, channel == 6)
        if channel == 6:
            rotation[:, pivot] = values
        else:
            translation[:, pivot, channel] = values[:, 0]
    transforms = []
    for frame in range(frames):
        world = []
        for i, bone in enumerate(bones):
            # OpenSAGE uses row vectors: AnimatedOffset * BindLocal.
            # Our column-vector equivalent is BindLocal * AnimatedOffset.
            local = bone['local'] @ matrix(translation[frame, i], rotation[frame, i])
            world.append(world[bone['parent']] @ local if bone['parent'] >= 0 else local)
        converted = []
        for m in world:
            m = BASIS @ m @ BASIS.T
            m[:3, 3] *= scale
            converted.append(recoil_pose(m))
        transforms.append(converted)
    return dict(fps=int(fps), frames=transforms)


def meshes(data, bones, scale=1):
    top = list(chunks(data))
    attachment = {}
    for kind, payload in top:
        if kind == 0x700:
            for t, p in chunks(payload):
                if t == 0x702:
                    for k, v in chunks(p):
                        if k == 0x704:
                            attachment[cstr(v[4:]).split('.')[-1]] = struct.unpack_from('<I', v)[0]
    result = []
    for kind, payload in top:
        if kind != 0:
            continue
        parts = dict(chunks(payload))
        header = parts[0x1f]
        name = cstr(header[8:24])
        if any(x in name for x in ('forged', 'glow', 'fire')):
            continue  # upgrade effect meshes, not the base unit
        verts = np.frombuffer(parts[2], '<f4').reshape(-1, 3).copy()
        normals = np.frombuffer(parts[3], '<f4').reshape(-1, 3).copy()
        triangles = np.frombuffer(parts[0x20], '<u4').reshape(-1, 8)[:, :3]
        textures = []
        for k, tex in chunks(parts.get(0x30, b'')):
            if k == 0x31:
                textures.append(cstr(dict(chunks(tex))[0x32]))
        stages = [v for k, v in chunks(parts[0x38]) if k == 0x48]
        stage = dict(chunks(stages[0]))
        uv = np.frombuffer(stage[0x4a], '<f4').reshape(-1, 2)
        texids = np.frombuffer(stage[0x49], '<u4')
        if 0xe in parts:
            influences = np.frombuffer(parts[0xe], '<u2').reshape(-1, 4)
            bone_ids = np.where(influences[:, 3] > influences[:, 2], influences[:, 1], influences[:, 0])
            skinned = True
        else:
            bone_ids = np.full(len(verts), attachment.get(name, 0))
            skinned = False
        groups = {}
        for j, tri in enumerate(triangles):
            # Recoil's standard S3O renderer is rigid-piece based. One dominant
            # bone per triangle avoids detached individual triangle vertices.
            ids, counts = np.unique(bone_ids[tri], return_counts=True)
            bone = int(ids[np.argmax(counts)])
            texture = textures[int(texids[0 if len(texids) == 1 else j])]
            key = bone, texture
            out = groups.setdefault(key, [])
            inverse = np.linalg.inv(bones[bone]['bind']) if skinned else np.eye(4)
            for idx in tri:
                # BFME stores each skinned vertex in its own bone's space.
                # Rebase it to the triangle's selected rigid bone.
                rebase = inverse @ bones[int(bone_ids[idx])]['bind'] if skinned else np.eye(4)
                position = rebase @ np.r_[verts[idx], 1]
                normal = rebase[:3, :3] @ normals[idx]
                position = BASIS @ position
                normal = BASIS[:3, :3] @ normal
                out.append([*(position[:3]*scale), *normal, *uv[idx]])
        for (bone, texture), vertices in groups.items():
            result.append(dict(bone=bone, texture=texture, vertices=vertices, source=name))
    return result
