"""Particle effects on map objects: W3D emitters and FXParticleSystems.

Objects get effects two ways (docs/game/renderer/effects.md):

- W3D emitters: the model's HLOD aggregate array names emitter files
  (GBTORCH's E_Fire_SM, E_Smoke_SM, E_FireSparks_SM), each on a bone.
  ParticleEmitterClass (WW3D2 part_emt.cpp, part_buf.cpp, pointgr.cpp).
- FXParticleSystems: `ParticleSysBone = <bone> <system>` in the template's
  default model-condition state, the system from fxparticlesystem.ini. The
  game evaluates them as Generals' ParticleSystem (ParticleSys.cpp) with
  BFME2's colour-scale change (the colour module constructor, 0x0055BCF1).

Both are evaluated statelessly: each particle's state is a closed-form
function of its age, so any instant can be drawn without simulating up to
it. Effects are shown as on a map that has run for a while: systems with a
SystemLifetime (or MaxEmissions) have stopped, the rest emit forever.
Randomness comes from a hash of the object, the emission and the particle,
so a render is reproducible.
Its EffectsMixin is the effects part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""

import math
import re
import struct
import zlib

import numpy as np

from mapworkshop.assets import ini
from mapworkshop.assets.models import chunks
from mapworkshop.render import shaders

FRAMES_PER_SECOND = 30.0
WARM_UP = 3600.0            # seconds of emission before time 0

# ParticleSystemTemplate.cpp: ParticlePriorityNames and ParticleShaderTypeNames.
PRIORITIES = ('NONE', 'ULTRA_HIGH_ONLY', 'HIGH_OR_ABOVE', 'MEDIUM_OR_ABOVE', 'LOW_OR_ABOVE',
              'VERY_LOW_OR_ABOVE', 'ALWAYS_RENDER')
# DefaultModule<6>::doParticles picks the sprite shader preset by the index:
# blend factors, alpha test reference (0..1) and depth test.
SPRITE_SHADERS = {
    'ADDITIVE': (('one', 'one'), None, True),
    'ADDITIVE_ALPHA_TEST': (('one', 'one'), 0x60/255, True),
    'ALPHA': (('src_alpha', 'one_minus_src_alpha'), None, True),
    'ALPHA_TEST': (('src_alpha', 'one_minus_src_alpha'), 0x60/255, True),
    'MULTIPLY': (('zero', 'src_color'), None, True),
    'ADDITIVE_NO_DEPTH_TEST': (('one', 'one'), None, False),
    'ALPHA_NO_DEPTH_TEST': (('src_alpha', 'one_minus_src_alpha'), None, False),
}

# W3dShaderStruct blend enums (w3d_file.h W3DSHADER_SRCBLENDFUNC_*/DESTBLENDFUNC_*).
SRC_BLEND = ('zero', 'one', 'src_alpha', 'one_minus_src_alpha')
DST_BLEND = ('zero', 'one', 'src_color', 'one_minus_src_color', 'src_alpha', 'one_minus_src_alpha', 'src_color')

# PointGroupClass::_Init: unrotated corners (camera-space x right, y up, in
# units of the point size) with the texture coordinates inside one frame.
QUAD_CORNERS = np.array([(-.5, .5, 0, 0), (-.5, -.5, 0, 1), (.5, -.5, 1, 1),
                         (.5, -.5, 1, 1), (.5, .5, 1, 0), (-.5, .5, 0, 0)], np.float32)
TRI_CORNERS = np.array([(0, -2, .5, 0), (-1.732, 1, 0, .866), (1.732, 1, 1, .866)], np.float32)


# Random numbers ---------------------------------------------------------------
_M32 = np.uint64(0xffffffff)


def _mix(x):
    """lowbias32 integer hash on uint64 arrays holding 32-bit values."""
    x = np.asarray(x, np.uint64) & _M32
    x ^= x >> np.uint64(16)
    x = (x*np.uint64(0x7feb352d)) & _M32
    x ^= x >> np.uint64(15)
    x = (x*np.uint64(0x846ca68b)) & _M32
    x ^= x >> np.uint64(16)
    return x


class _Random:
    """Uniform values for an array of particle seeds, one stream per use."""
    def __init__(self, seeds):
        self.seeds = _mix(seeds)
        self.stream = 0

    def __call__(self, lo=0.0, hi=1.0):
        self.stream += 1
        u = _mix(self.seeds ^ _mix(np.uint64(self.stream*0x9e3779b9 & 0xffffffff))).astype(np.float64)/2.0**32
        return lo + (hi - lo)*u

    def signed(self, scale=1.0):
        return self(-1.0, 1.0)*scale

    def unit_sphere(self):
        """computePointOnUnitSphere: a uniform direction."""
        z = self(-1.0, 1.0)
        a = self(0.0, 2*math.pi)
        r = np.sqrt(np.maximum(1 - z*z, 0))
        return np.stack([r*np.cos(a), r*np.sin(a), z], -1)


def _seed(*parts):
    """Combine integer arrays (broadcast) into one 32-bit seed array."""
    seed = np.uint64(0x2545f491)
    for p in parts:
        seed = _mix(seed ^ (np.asarray(p).astype(np.int64).astype(np.uint64) & _M32))
    return seed


# Keyframes --------------------------------------------------------------------
def _interp(x, times, values):
    """Piecewise linear in x through (times, values), constant outside.
    values: (k, c) shared or (n, k, c) per particle; returns (n, c)."""
    times = np.maximum.accumulate(np.asarray(times, np.float64))
    values = np.asarray(values, np.float64)
    if len(times) == 1:
        return np.broadcast_to(values[..., 0, :], (len(x), values.shape[-1])).copy()
    i = np.clip(np.searchsorted(times, x, 'right') - 1, 0, len(times) - 2)
    span = np.maximum(times[i+1] - times[i], 1e-9)
    f = np.clip((x - times[i])/span, 0.0, 1.0)[:, None]
    if values.ndim == 2:
        a, b = values[i], values[i+1]
    else:
        rows = np.arange(len(x))
        a, b = values[rows, i], values[rows, i+1]
    return a + (b - a)*f


def _integrate(x, times, rates):
    """Integral from 0 to x of the piecewise-linear rate through (times,
    rates), constant after the last key."""
    times = np.asarray(times, np.float64)
    rates = np.asarray(rates, np.float64)
    seg = np.diff(times)
    cumulative = np.concatenate([[0.0], np.cumsum(seg*(rates[:-1] + rates[1:])/2)])
    i = np.clip(np.searchsorted(times, x, 'right') - 1, 0, len(times) - 1)
    dt = x - times[i]
    slope = np.where(i < len(times) - 1, np.diff(rates, append=rates[-1])[i]/np.maximum(
        np.diff(times, append=times[-1] + 1)[i], 1e-9), 0.0)
    return cumulative[i] + rates[i]*dt + 0.5*slope*dt*dt


# W3D emitters -----------------------------------------------------------------
def _cstr(data):
    return data.split(b'\0', 1)[0].decode('latin-1')


def _keys(data, pos, count, width):
    """`count` (time, value...) records of `width` floats or one RGBA."""
    out = []
    for _ in range(count):
        if width == 'rgba':
            t = struct.unpack_from('<f', data, pos)[0]
            out.append((t, tuple(c/255 for c in data[pos+4:pos+7])))
            pos += 8
        else:
            t, v = struct.unpack_from('<2f', data, pos)
            out.append((t, (v,)))
            pos += 8
    return out, pos


def _keyed(keys, random):
    times = [0.0] + [t for t, _ in keys[1:]]
    return dict(times=np.array(times), values=np.array([v for _, v in keys], np.float64),
                random=np.atleast_1d(np.asarray(random, np.float64)))


def parse_emitter(data):
    """A W3D_CHUNK_EMITTER (0x500) as ParticleEmitterDefClass::Load_W3D reads
    it, or None. Times in seconds, colours and opacities 0..1."""
    for kind, payload in chunks(data):
        if kind == 0x500:
            return _emitter(payload)
    return None


def _emitter(payload):
    parts = {}
    for kind, chunk in chunks(payload):
        parts.setdefault(kind, chunk)
    if 0x503 not in parts or 0x504 not in parts or 0x505 not in parts:
        return None                                  # version 1 emitters are not used
    info, v2, props = parts[0x503], parts[0x504], parts[0x505]
    lifetime, rate, max_emissions = struct.unpack_from('<3f', info, 268)
    velocity = struct.unpack_from('<3f', info, 300)
    acceleration = struct.unpack_from('<3f', info, 312)
    burst = struct.unpack_from('<I', v2)[0]
    volume = struct.unpack_from('<I3f', v2, 4)
    vel_random = struct.unpack_from('<I3f', v2, 36)
    outward, inherit = struct.unpack_from('<2f', v2, 68)
    shader = v2[76:92]
    render_mode, frame_mode = struct.unpack_from('<2I', v2, 92)
    # W3D_CHUNK_EMITTER_PROPS: counts include the starting value.
    counts = struct.unpack_from('<3I', props)
    color_random = tuple(c/255 for c in props[12:15])
    opacity_random, size_random = struct.unpack_from('<2f', props, 16)
    pos = 40
    colors, pos = _keys(props, pos, counts[0], 'rgba')
    opacities, pos = _keys(props, pos, counts[1], 1)
    sizes, pos = _keys(props, pos, counts[2], 1)
    if len(colors) > 2 and not any(colors[-1][1]) and any(color_random):
        # Read_Props: a black last key with a colour random becomes -random.
        colors[-1] = (colors[-1][0], tuple(-c for c in color_random))
    rotation = dict(times=np.zeros(1), values=np.zeros((1, 1)), random=np.zeros(1))
    orientation_random = 0.0
    if 0x50a in parts:
        count, rand, orientation_random = struct.unpack_from('<I2f', parts[0x50a])
        keys, _ = _keys(parts[0x50a], 16, count + 1, 1)
        rotation = _keyed(keys, rand)
    frame = dict(times=np.zeros(1), values=np.zeros((1, 1)), random=np.zeros(1))
    if 0x50b in parts:
        count, rand = struct.unpack_from('<If', parts[0x50b])
        keys, _ = _keys(parts[0x50b], 16, count + 1, 1)
        frame = _keyed(keys, rand)
    src, dst = shader[7], shader[3]
    blend = (SRC_BLEND[src] if src < len(SRC_BLEND) else 'one', DST_BLEND[dst] if dst < len(DST_BLEND) else 'zero')
    return dict(kind='emitter', name=_cstr(parts.get(0x501, b'\0\0\0\0')[4:20]), texture=_cstr(info[:260]),
                lifetime=lifetime, rate=rate, max_emissions=max_emissions, burst=max(burst, 1),
                velocity=np.array(velocity), acceleration=np.array(acceleration),
                volume=volume, vel_random=vel_random, outward=outward,
                blend=blend, depth_test=shader[0] != 7, alpha_ref=0x60/255 if shader[12] else None,
                render_mode=render_mode, frame_mode=frame_mode,
                color=_keyed(colors, color_random), opacity=_keyed(opacities, opacity_random),
                size=_keyed(sizes, size_random), rotation=rotation, orientation_random=orientation_random,
                frame=frame)


def _randomizer(spec, rnd, n):
    """Vector3Randomizer (v3_rnd.cpp) from a W3dVolumeRandomizerStruct:
    solid box (extents), solid sphere, hollow sphere (radius), solid
    cylinder (extent along x, radius)."""
    kind, a, b, c = spec
    if kind == 0:
        return np.stack([rnd.signed(a), rnd.signed(b), rnd.signed(c)], -1)
    if kind in (1, 2):
        d = rnd.unit_sphere()
        r = a if kind == 2 else a*np.cbrt(rnd())
        return d*np.atleast_1d(r)[..., None]
    if kind == 3:
        ang, r = rnd(0, 2*math.pi), b*np.sqrt(rnd())
        return np.stack([rnd.signed(a), r*np.cos(ang), r*np.sin(ang)], -1)
    return np.zeros((n, 3))


def emitter_particles(e, origins, rotations, scales, seeds, time):
    """Live particles of emitter `e` on N instances at `time` seconds.

    Emissions every int(1000 / rate) ms of `burst` particles; a particle's
    position is the emitter-space random position rotated by the emitter's
    transform, moving at its rotated velocity under the world acceleration.
    Visual properties follow the keyframes by age (part_buf.cpp
    Update_Visual_Particle_State) plus per-particle randoms."""
    if e['lifetime'] <= 0 or e['max_emissions'] > 0 or e['render_mode'] > 1:
        return None
    interval = (int(1000.0/e['rate']) if e['rate'] > 0 else 1000)/1000.0
    life = e['lifetime']
    slots = int(math.ceil(life/interval)) + 1
    n = len(origins)
    phase = _Random(_seed(seeds, 7))()*interval
    now = time + WARM_UP + phase                                             # (n,)
    last = np.floor(now/interval)
    k = last[:, None] - np.arange(slots)[None, :]                           # (n, slots)
    ages = now[:, None] - k*interval
    inst = np.broadcast_to(np.arange(n)[:, None, None], (n, slots, e['burst']))
    j = np.broadcast_to(np.arange(e['burst'])[None, None, :], (n, slots, e['burst']))
    k = np.broadcast_to(k[:, :, None], (n, slots, e['burst']))
    ages = np.broadcast_to(ages[:, :, None], (n, slots, e['burst']))
    alive = (ages < life) & (ages >= 0)
    inst, j, k, age = inst[alive], j[alive], k[alive], ages[alive]
    m = len(age)
    if m == 0:
        return None
    rnd = _Random(_seed(seeds[inst], k, j))
    s = scales[inst][:, None]
    pos = _randomizer(e['volume'], rnd, m)
    vel = _randomizer(e['vel_random'], rnd, m)
    if e['outward']:
        length = np.linalg.norm(pos, axis=1, keepdims=True)
        out = np.where(length > 0, pos/np.maximum(length, 1e-9), np.array([1.0, 0.0, 0.0]))
        vel = vel + out*e['outward']
    vel = vel + e['velocity']
    R = rotations[inst]
    world_pos = origins[inst] + np.einsum('nij,nj->ni', R, pos*s)
    world_vel = np.einsum('nij,nj->ni', R, vel*s)
    a = age[:, None]
    center = world_pos + world_vel*a + 0.5*e['acceleration']*s*a*a
    # One random offset per particle and channel (the random tables of
    # ParticleBufferClass::Reset_Colors and friends).
    key = lambda prop, c: (_interp(age, prop['times'], prop['values'])
                           + np.stack([rnd.signed(r) for r in prop['random'][:c]], -1))
    color = np.clip(key(e['color'], 3), 0, 1)
    alpha = np.clip(key(e['opacity'], 1), 0, 1)[:, 0]
    size = np.maximum(key(e['size'], 1)[:, 0], 0)*scales[inst]
    rot = e['rotation']
    orientation = (_integrate(age, rot['times'], rot['values'][:, 0]) + rnd.signed(rot['random'][0])*age
                   + rnd.signed(e['orientation_random']))
    angle = (np.floor(orientation*256).astype(np.int64) & 255)*(2*math.pi/256)
    rows = 1 << min(e['frame_mode'], 4)
    frame = (_interp(age, e['frame']['times'], e['frame']['values'])[:, 0]
             + rnd.signed(e['frame']['random'][0])).astype(np.int64) & 255
    frame %= rows*rows
    return _pack(center, size, color, alpha, angle, frame, rows)


def _pack(center, size, color, alpha, angle, frame, rows):
    """Instance rows: centre (3), size, RGBA, angle, frame origin u, v and size."""
    du = 1.0/rows
    return np.column_stack([center, size, color, alpha, angle, (frame % rows)*du, (frame//rows)*du,
                            np.full(len(size), du)]).astype(np.float32)


# FXParticleSystems ------------------------------------------------------------
def _numbers(text):
    return [float(v) for v in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', text)]


def _range(text):
    v = _numbers(text)
    return (v[0], v[1] if len(v) > 1 else v[0]) if v else (0.0, 0.0)


def _coord(text):
    found = dict(re.findall(r'([XYZ])\s*:\s*([-+\d.eE]+)', text, re.I))
    return np.array([float(found.get(a, found.get(a.lower(), 0))) for a in 'XYZ'])


def parse_systems(text):
    """FXParticleSystem blocks: {lower name: system}. Each system holds its
    System fields and its modules as {slot: (kind, {field: value})}."""
    systems = {}
    current = module = None
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].split('//', 1)[0].strip()
        if not line:
            continue
        if current is None:
            head = re.match(r'(?i)FXParticleSystem\s+(\S+)', line)
            if head:
                current = dict(name=head.group(1), system={}, modules={})
            continue
        if line.lower() == 'end':
            if module is None:
                systems[current['name'].lower()] = current
                current = None
            module = None
            continue
        if module is None:
            match = re.match(r'(\w+)\s*(?:=\s*(\w+))?$', line)
            if match and match.group(1).lower() in MODULE_SLOTS:
                slot = match.group(1).lower()
                module = {}
                current['modules'][slot] = (match.group(2) or slot, module)
                if slot == 'system':
                    current['system'] = module
            continue
        key, _, value = line.partition('=')
        module[key.strip().lower()] = value.strip()
    return systems


MODULE_SLOTS = ('system', 'color', 'alpha', 'update', 'physics', 'emissionvelocity', 'emissionvolume',
                'draw', 'wind', 'event')


def prepare_system(s):
    """The fields render.effects evaluates, or (None, reason)."""
    sys = s['system']
    mods = s['modules']
    get = lambda slot: mods.get(slot, (None, {}))
    if sys.get('type', 'PARTICLE').upper() not in ('PARTICLE', 'NONE'):
        return None, f"type {sys.get('type')}"
    draw = get('draw')[0]
    if draw not in (None, 'DefaultDraw'):
        return None, f'draw {draw}'
    volume_kind, volume = get('emissionvolume')
    if volume_kind not in (None, 'PointEmissionVolume', 'LineEmissionVolume', 'SphereEmissionVolume',
                           'BoxEmissionVolume', 'CylinderEmissionVolume'):
        return None, f'volume {volume_kind}'
    velocity_kind, velocity = get('emissionvelocity')
    yes = lambda d, k: d.get(k, 'No').strip().lower() in ('yes', 'true', '1')
    rng = lambda d, k, default=(0.0, 0.0): _range(d[k]) if k in d else default
    shader = sys.get('shader', 'ADDITIVE').upper()
    blend, alpha_ref, depth_test = SPRITE_SHADERS.get(shader, SPRITE_SHADERS['ADDITIVE'])
    colors = []
    color_kind, color = get('color')
    for i in range(1, 9):
        v = color.get(f'color{i}')
        if v is None:
            continue
        rgb = [float(c)/255 for c in re.findall(r'[RGB]\s*:\s*([-\d.]+)', v, re.I)][:3]
        frame = re.sub(r'[RGB]\s*:\s*[-\d.]+', '', v, flags=re.I)
        frame = _numbers(frame)
        if len(rgb) == 3:
            colors.append((frame[0] if frame else 0.0, rgb))
    # Keys after the first stop at the first one with frame 0.
    kept = colors[:1]
    for f, c in colors[1:]:
        if f <= 0:
            break
        kept.append((f, c))
    alphas = None
    alpha_kind, alpha = get('alpha')
    if alpha_kind:
        alphas = []
        for i in range(1, 9):
            v = _numbers(alpha.get(f'alpha{i}', ''))
            if len(v) >= 3 and (i == 1 or v[2] > 0):
                alphas.append((v[2], v[0], v[1]))
            elif i > 1:
                break
        alphas = alphas or None
    update, physics = get('update')[1], get('physics')[1]
    return dict(
        kind='system', name=s['name'], texture=sys.get('particlename', ''),
        priority=PRIORITIES.index(sys.get('priority', 'ALWAYS_RENDER').upper())
        if sys.get('priority', 'ALWAYS_RENDER').upper() in PRIORITIES else 6,
        lifetime=rng(sys, 'lifetime', (30.0, 30.0)), system_lifetime=_range(sys.get('systemlifetime', '0'))[0],
        one_shot=yes(sys, 'isoneshot'), size=rng(sys, 'size', (1.0, 1.0)),
        burst_delay=rng(sys, 'burstdelay'), burst_count=rng(sys, 'burstcount', (1.0, 1.0)),
        ground_aligned=yes(sys, 'isgroundaligned'), shader=shader, additive=blend == ('one', 'one'),
        blend=blend, alpha_ref=alpha_ref, depth_test=depth_test,
        colors=kept or [(0.0, [1.0, 1.0, 1.0])], color_scale=tuple(v/255 for v in rng(color, 'colorscale')),
        alphas=alphas,
        size_rate=rng(update, 'sizerate'), size_damping=rng(update, 'sizeratedamping', (1.0, 1.0)),
        angle=rng(update, 'anglez'), angular_rate=rng(update, 'angularratez'),
        angular_damping=rng(update, 'angulardamping', (1.0, 1.0)),
        gravity=_range(physics.get('gravity', '0'))[0], damping=rng(physics, 'velocitydamping', (1.0, 1.0)),
        drift=_coord(physics.get('driftvelocity', '')),
        volume_kind=volume_kind or 'PointEmissionVolume', hollow=yes(volume, 'ishollow'),
        start=_coord(volume.get('startpoint', '')), end=_coord(volume.get('endpoint', volume.get('startpoint', ''))),
        radius=_range(volume.get('radius', '0'))[0], length=_range(volume.get('length', '0'))[0],
        offset=_coord(volume.get('offset', '')), half_size=_coord(volume.get('halfsize', '')),
        velocity_kind=velocity_kind, ortho=[rng(velocity, a) for a in 'xyz'],
        speed=rng(velocity, 'speed'), other_speed=rng(velocity, 'otherspeed'),
        radial=rng(velocity, 'radial'), normal=rng(velocity, 'normal')), None


def _whole_frames(d, n):
    """n, or the last whole frame where the damping d is negative: such a
    damping flips the sign every frame, so d^n is only real at whole frames
    (some systems have VelocityDamping = -0.1 0.5)."""
    return np.where(d < 0, np.floor(n), n)


def _geometric(d, n):
    """sum_{k=0}^{n-1} d^k for damping d and (fractional) frame count n."""
    d = np.asarray(d, np.float64)
    n = _whole_frames(d, n)
    near = np.abs(1 - d) < 1e-6
    return np.where(near, n, (1 - np.power(d, n))/np.where(near, 1.0, 1 - d))


def motion(p0, v0, damping, gravity, drift, n):
    """Position after n frames of Particle::update: each frame the velocity
    gains (0, 0, gravity) and is multiplied by the damping, then the position
    moves by the velocity plus the drift. Closed form, so n may be fractional."""
    d = np.asarray(damping, np.float64)[:, None]
    g = np.array([0.0, 0.0, gravity])
    n = _whole_frames(d, np.asarray(n, np.float64)[:, None])
    dn = np.power(d, n)
    near = np.abs(1 - d) < 1e-6
    safe = np.where(near, 1.0, 1 - d)
    moved = np.where(near, v0*n + g*n*(n + 1)/2, v0*d*(1 - dn)/safe + g*d/safe*(n - d*(1 - dn)/safe))
    return p0 + moved + n*np.asarray(drift, np.float64)


def _volume_point(s, rnd, m):
    """ParticleSystem::computeParticlePosition."""
    kind = s['volume_kind']
    if kind == 'LineEmissionVolume':
        return s['start'] + rnd()[:, None]*(s['end'] - s['start'])
    if kind == 'SphereEmissionVolume':
        r = s['radius'] if s['hollow'] else rnd(0, s['radius'])
        return rnd.unit_sphere()*np.broadcast_to(r, (m,))[:, None]
    if kind == 'BoxEmissionVolume':
        h = s['half_size']
        p = np.stack([rnd.signed(h[0]), rnd.signed(h[1]), rnd.signed(h[2])], -1)
        if s['hollow']:
            side = np.floor(rnd(0, 6)).astype(int)
            axis = np.array([2, 0, 1])[side % 3]
            sign = np.where(side < 3, -1.0, 1.0)
            p[np.arange(m), axis] = sign*h[axis]
        return p
    if kind == 'CylinderEmissionVolume':
        a = rnd(0, 2*math.pi)
        r = s['radius'] if s['hollow'] else rnd(0, s['radius'])
        z = rnd(-s['length']/2, s['length']/2)
        return np.stack([r*np.cos(a), r*np.sin(a), z], -1) + s['offset']
    return np.zeros((m, 3))


def _volume_velocity(s, pos, rnd, m):
    """ParticleSystem::computeParticleVelocity."""
    kind = s['velocity_kind']
    if kind == 'OrthoEmissionVelocity':
        return np.stack([rnd(*s['ortho'][0]), rnd(*s['ortho'][1]), rnd(*s['ortho'][2])], -1)
    if kind == 'OutwardEmissionVelocity':
        speed, other = rnd(*s['speed']), rnd(*s['other_speed'])
        volume = s['volume_kind']
        if volume == 'CylinderEmissionVolume':
            disk = (pos - s['offset'])[:, :2]
            disk = disk/np.maximum(np.linalg.norm(disk, axis=1, keepdims=True), 1e-9)
            return np.column_stack([disk*speed[:, None], other])
        if volume == 'LineEmissionVolume':
            along = s['end'] - s['start']
            along = along/max(np.linalg.norm(along), 1e-9)
            perp = np.cross((0.0, 0.0, 1.0), along)
            up = np.cross(along, perp)
            return speed[:, None]*perp + other[:, None]*up
        if volume == 'PointEmissionVolume':
            return rnd.unit_sphere()*speed[:, None]
        direction = pos/np.maximum(np.linalg.norm(pos, axis=1, keepdims=True), 1e-9)
        return direction*speed[:, None]
    if kind == 'SphericalEmissionVelocity':
        return rnd.unit_sphere()*rnd(*s['speed'])[:, None]
    if kind == 'HemisphericalEmissionVelocity':
        d = np.stack([rnd(-1, 1), rnd(-1, 1), rnd(0, 1)], -1)
        d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
        return d*rnd(*s['speed'])[:, None]
    if kind == 'CylindricalEmissionVelocity':
        radial, a = rnd(*s['radial']), rnd(0, 2*math.pi)
        return np.stack([radial*np.cos(a), radial*np.sin(a), rnd(*s['normal'])], -1)
    return np.zeros((m, 3))


def system_particles(s, origins, angles, seeds, time):
    """Live particles of FXParticleSystem `s` on N instances at `time`.

    A burst of BurstCount particles every BurstDelay + 1 frames (the mean
    delay); each particle then moves per frame as Particle::update does
    (velocity += gravity, *= damping; position += velocity + drift; size
    and angle rates damped), evaluated here in closed form at a fractional
    frame age."""
    if s['system_lifetime'] > 0 or s['one_shot']:
        return None
    period = (s['burst_delay'][0] + s['burst_delay'][1])/2 + 1
    lmax = max(s['lifetime'])
    slots = int(math.ceil(lmax/period)) + 1
    burst = max(int(math.ceil(s['burst_count'][1])), 1)
    n = len(origins)
    now = (time + WARM_UP)*FRAMES_PER_SECOND + _Random(_seed(seeds, 11))()*period
    k = np.floor(now/period)[:, None] - np.arange(slots)[None, :]
    ages = now[:, None] - k*period
    shape = (n, slots, burst)
    inst = np.broadcast_to(np.arange(n)[:, None, None], shape)
    j = np.broadcast_to(np.arange(burst)[None, None, :], shape)
    k = np.broadcast_to(k[:, :, None], shape)
    ages = np.broadcast_to(ages[:, :, None], shape)
    count = np.floor(_Random(_seed(seeds[inst], k, 5))(*s['burst_count']))
    lifetime = _Random(_seed(seeds[inst], k, j, 3))(*s['lifetime'])
    alive = (j < count) & (ages < lifetime) & (ages >= 0)
    inst, j, k, n_age = inst[alive], j[alive], k[alive], ages[alive]
    m = len(n_age)
    if m == 0:
        return None
    rnd = _Random(_seed(seeds[inst], k, j))
    pos = _volume_point(s, rnd, m)
    vel = _volume_velocity(s, pos, rnd, m)
    c, si = np.cos(angles[inst]), np.sin(angles[inst])
    turn = lambda v: np.column_stack([c*v[:, 0] - si*v[:, 1], si*v[:, 0] + c*v[:, 1], v[:, 2]])
    center = motion(origins[inst] + turn(pos), turn(vel), rnd(*s['damping']), s['gravity'], s['drift'], n_age)
    size = np.maximum(rnd(*s['size']) + rnd(*s['size_rate'])*_geometric(rnd(*s['size_damping']), n_age), 0)
    angle = rnd(*s['angle']) + rnd(*s['angular_rate'])*_geometric(rnd(*s['angular_damping']), n_age)
    frames = [f for f, _ in s['colors']]
    keys = np.array([c for _, c in s['colors']], np.float64)
    keys = np.broadcast_to(keys, (m,) + keys.shape).copy()
    lo, hi = s['color_scale']
    if lo or hi:
        # BFME2: every non-zero channel of keys 1..6 gets its own draw of
        # the colour scale, clamped.
        for i in range(1, min(len(frames), 7)):
            for ch in range(3):
                nonzero = keys[:, i, ch] != 0
                keys[:, i, ch] = np.where(nonzero, np.clip(keys[:, i, ch] + rnd(lo, hi), 0, 1), 0)
    color = np.clip(_interp(n_age, frames, keys), 0, 1)
    if s['alphas'] and not s['additive']:
        a_frames = [f for f, _, _ in s['alphas']]
        a_keys = np.stack([rnd(a, b) for _, a, b in s['alphas']], -1)[:, :, None]
        alpha = np.clip(_interp(n_age, a_frames, a_keys)[:, 0], 0, 1)
    else:
        alpha = np.ones(m)
    return _pack(center, size, color, alpha, angle, np.zeros(m, np.int64), 1)


# Attaching effects to objects -------------------------------------------------
def particle_bones(assets, template):
    """(bone, system) pairs of `ParticleSysBone` in the states an idle object
    shows: the draw module's DefaultModelConditionState and BFME2's
    IdleAnimationState (FireBonfire keeps its systems there), however deep
    in them. Follows ObjectReskin/ChildObject parents (assets.ini)."""
    states = ('defaultmodelconditionstate', 'idleanimationstate')
    for body in ini.bodies(assets, template):
        by_state = {}
        for s in ini.statements(body):
            words = ini.words(s.value)
            state = next((p for p in s.path if p in states), None)
            if s.key == 'particlesysbone' and state and len(words) > 1:
                by_state.setdefault(state, []).append((words[0].lower(), words[1]))
        # A state may repeat a system (CineFireRing, twelve times, for a denser
        # fire); a pair the default state has already given (the Ents name
        # TreeBeardIdleLeaves in both) is not added again.
        found = []
        for pairs in by_state.values():
            earlier = set(found)
            found += [p for p in pairs if p not in earlier]
        if found:
            return found
    return []


def min_priority(gamelod_text, lod):
    """GameLOD.ini MinParticlePriority of the imitated level, as an index."""
    current, values = None, {}
    for line in gamelod_text.splitlines():
        line = line.split(';')[0].strip()
        match = re.match(r'(?i)StaticGameLOD\s*=\s*(\w+)', line)
        if match:
            current = match.group(1).lower()
            continue
        match = re.match(r'(?i)MinParticlePriority\s*=\s*(\w+)', line)
        if match and current and match.group(1).upper() in PRIORITIES:
            values.setdefault(current, PRIORITIES.index(match.group(1).upper()))
    return values.get(lod.lower(), PRIORITIES.index('MEDIUM_OR_ABOVE'))


class Effects:
    """The particle sources of a map's objects, evaluated at any time.

    `add(template, model, x, y, z, angle, scale, seed)` attaches a placed
    object's emitters and systems; `particles(time)` returns draw groups."""

    def __init__(self, assets, lod='medium'):
        self.assets = assets
        self.lod_priority = min_priority(assets.ini_text('gamelod.ini'), lod)
        self.sources = {}                       # key -> dict(definition, instances)
        self.report = dict(emitters=0, systems=0, skipped={})
        self._emitters = {}

    @property
    def _systems(self):
        if not hasattr(self, '_system_defs'):
            text = '\n'.join(self.assets.ini_text(f) for f in ('fxparticlesystem.ini', 'fxparticlesystemcustom.ini')
                             if self._has_ini(f))
            # The map's own map.ini last: its systems are new or replace the game's.
            self._system_defs = parse_systems(text + '\n' + getattr(self.assets, 'map_ini', ''))
        return self._system_defs

    def _has_ini(self, name):
        try:
            self.assets.ini_text(name)
            return True
        except (FileNotFoundError, OSError):
            return False

    def _emitter(self, name):
        if name not in self._emitters:
            key = self.assets.model_key(name)
            self._emitters[name] = parse_emitter(self.assets.read(key)) if key else None
        return self._emitters[name]

    def _skip(self, name, reason):
        self.report['skipped'][name] = reason

    def add(self, template, model, x, y, z, angle, scale, seed):
        """Attach the effects of one placed object. `model` is ModelCache.load's
        result for its model (or None)."""
        c, s = math.cos(angle), math.sin(angle)
        turn = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        place = np.array([x, y, z])
        for name, bone in (model or {}).get('aggregates', []):
            e = self._emitter(name)
            if e is None:
                continue
            if e['lifetime'] <= 0 or e['max_emissions'] > 0 or e['render_mode'] > 1:
                self._skip(name, 'one-shot or line emitter')
                continue
            rotation = turn @ bone[:3, :3]
            rotation /= np.cbrt(max(abs(np.linalg.det(rotation)), 1e-9))
            origin = place + turn @ (bone[:3, 3]*scale)
            self._instance(('emitter', name), e, origin, rotation, 0.0, scale, seed)
            self.report['emitters'] += 1
        for bone_name, system_name in particle_bones(self.assets, template):
            raw = self._systems.get(system_name.lower())
            if raw is None:
                self._skip(system_name, 'not found')
                continue
            key = ('system', system_name.lower())
            if key not in self.sources:
                s, reason = prepare_system(raw)
                if s is None:
                    self._skip(system_name, reason)
                    continue
                if s['system_lifetime'] > 0 or s['one_shot']:
                    self._skip(system_name, 'stops after its SystemLifetime')
                    continue
                if s['priority'] < self.lod_priority:
                    self._skip(system_name, f"priority {PRIORITIES[s['priority']]} below this detail level")
                    continue
            else:
                s = self.sources[key]['definition']
            # W3DModelDraw: the bone's model-space translation times the
            # drawable's scale and only its Z rotation; origin without the bone.
            matrix = (model or {}).get('bones', {}).get(bone_name)
            offset, bone_angle = np.zeros(3), 0.0
            if matrix is not None and bone_name != 'none':
                offset = matrix[:3, 3]*scale
                bone_angle = math.atan2(matrix[1, 0], matrix[0, 0])
            self._instance(key, s, place + turn @ offset, None, angle + bone_angle, scale, seed)
            self.report['systems'] += 1

    def _instance(self, key, definition, origin, rotation, angle, scale, seed):
        source = self.sources.setdefault(key, dict(definition=definition, origins=[], rotations=[], angles=[],
                                                   scales=[], seeds=[]))
        source['origins'].append(origin)
        source['rotations'].append(np.eye(3) if rotation is None else rotation)
        source['angles'].append(angle)
        source['scales'].append(scale)
        source['seeds'].append((seed*1000003 + len(source['seeds'])*7919 + zlib.crc32(key[1].encode())) & 0xffffffff)

    def finish(self):
        for source in self.sources.values():
            for name in ('origins', 'rotations', 'angles', 'scales', 'seeds'):
                source[name] = np.asarray(source[name], np.float64 if name != 'seeds' else np.int64)
        return self

    def textures(self):
        return {s['definition']['texture'] for s in self.sources.values() if s['definition']['texture']}

    def particles(self, time):
        """Draw groups at `time` seconds: {(texture, blend, alpha_ref,
        depth_test, shape, ground): rows} with rows as `_pack` lays them out
        and shape 'tri' or 'quad'."""
        groups = {}
        for key, source in self.sources.items():
            d = source['definition']
            if d['kind'] == 'emitter':
                rows = emitter_particles(d, source['origins'], source['rotations'], source['scales'],
                                         source['seeds'], time)
                shape = 'tri' if d['render_mode'] == 0 else 'quad'
                ground = False
            else:
                rows = system_particles(d, source['origins'], source['angles'], source['seeds'], time)
                shape, ground = 'quad', d['ground_aligned']
            if rows is None or not len(rows):
                continue
            group = (d['texture'].lower(), d['blend'], d['alpha_ref'], d['depth_test'], shape, ground)
            groups.setdefault(group, []).append(rows)
        return {k: np.concatenate(v) for k, v in groups.items()}


class EffectsMixin:
    """MapRenderer's particle effects on objects: their systems prepared and drawn."""

    def _prepare_effects(self):
        """Emitters and particle systems of the placed objects (render.effects)."""
        effects = Effects(self.assets, self.options['lod'])
        for template, model, x, y, z, angle, scale, index in getattr(self, '_effect_objects', []):
            effects.add(template, self.model_cache.load(model), x, y, z, angle, scale, index)
        self.effects = effects.finish()
        # Additive particles draw the colour under zero alpha, so their
        # textures are kept as they are (no bleed_alpha).
        self._effect_images = {name: self.assets.image(name) for name in effects.textures()}
        self.report['effects'] = dict(emitters=effects.report['emitters'], systems=effects.report['systems'],
                                      skipped=dict(sorted(effects.report['skipped'].items())))

    def _effects_gpu(self):
        ctx = self.ctx
        self.effect_program = ctx.program(vertex_shader=shaders.EFFECT_VS, fragment_shader=shaders.EFFECT_FS)
        self.effect_corners = {}
        for shape, corners in (('quad', QUAD_CORNERS), ('tri', TRI_CORNERS)):
            self.effect_corners[shape] = ctx.buffer(corners.tobytes())
        self.effect_textures = {}
        for name, image in getattr(self, '_effect_images', {}).items():
            if image is None:
                self.report['missing_textures'].append(name)
                continue
            texture = ctx.texture((image.shape[1], image.shape[0]), 4, np.ascontiguousarray(image).tobytes())
            texture.build_mipmaps()
            texture.filter = (self.moderngl.LINEAR_MIPMAP_LINEAR, self.moderngl.LINEAR)
            texture.repeat_x = texture.repeat_y = False
            self.effect_textures[name.lower()] = texture
        self._object_resources += [self.effect_program, *self.effect_corners.values(), *self.effect_textures.values()]
        self.__dict__.pop('_effect_images', None)

    def _draw_effects(self, vp, camera, eye, time):
        """Particles of object effects at `time`: camera-facing quads or
        triangles (PointGroupClass), ground-aligned quads flat on the ground,
        drawn without depth writes; alpha-blended groups first, each sorted
        back to front, then additive ones. Fog fades additive particles to
        black and multiplicative ones to white."""
        groups = self.effects.particles(time)
        if not groups:
            return
        mgl, ctx = self.moderngl, self.ctx
        p = self.effect_program
        forward = np.asarray(camera['target'], float) - np.asarray(camera['eye'], float)
        forward /= np.linalg.norm(forward) or 1.0
        right = np.cross(forward, (0.0, 0.0, 1.0))
        right = right/np.linalg.norm(right) if np.linalg.norm(right) > 1e-6 else np.array([1.0, 0.0, 0.0])
        up = np.cross(right, forward)
        p['view_projection'].write(vp)
        self._set_fog(p, eye)
        p['tex'].value = 0
        ctx.enable(mgl.BLEND)
        ctx.fbo.depth_mask = False
        order = sorted(groups, key=lambda g: g[1] == ('one', 'one'))
        for texture_name, blend, alpha_ref, depth_test, shape, ground in order:
            texture = self.effect_textures.get(texture_name)
            if texture is None:
                continue
            rows = groups[(texture_name, blend, alpha_ref, depth_test, shape, ground)]
            if blend != ('one', 'one'):
                rows = rows[np.argsort(-np.linalg.norm(rows[:, :3] - np.asarray(eye, np.float32), axis=1))]
            p['right'].value = (1.0, 0.0, 0.0) if ground else tuple(right)
            p['up'].value = (0.0, 1.0, 0.0) if ground else tuple(up)
            p['alpha_ref'].value = -1.0 if alpha_ref is None else float(alpha_ref)
            p['fog_mode'].value = 1 if blend == ('one', 'one') else 2 if blend == ('zero', 'src_color') else 0
            ctx.blend_func = self._blend_func(blend)
            if depth_test:
                ctx.enable(mgl.DEPTH_TEST)
            else:
                ctx.disable(mgl.DEPTH_TEST)
            texture.use(0)
            instances = ctx.buffer(np.ascontiguousarray(rows, np.float32).tobytes())
            vao = ctx.vertex_array(p, [(self.effect_corners[shape], '4f', 'in_corner'),
                                       (instances, '3f f 4f f 3f/i', 'in_center', 'in_size', 'in_color', 'in_angle',
                                        'in_frame')])
            vao.render(mgl.TRIANGLES, vertices=6 if shape == 'quad' else 3, instances=len(rows))
            vao.release()
            instances.release()
        ctx.enable(mgl.DEPTH_TEST)
        ctx.fbo.depth_mask = True
        ctx.disable(mgl.BLEND)
