"""Map weather for previews: hardware fog and falling snow or rain.

Settings come from weather.ini's Weather block, overridden field by field by
the map's map.ini Weather block (as the game's overridable WeatherSetting).

Fog: HardwareFogEnable/Color/Start/End, applied by the effects by distance
from the camera (see shaders.apply_fog).

Particles: W3DSnowManager (W3DSnowManagerRender.cpp, Snow.cpp
updateIniSettings, update 0x000949D9) and renderAsQuads (0x00093CC3, read
from game.dat; SnowPointSprites = no is the retail setting). When IsSnowing
is set, emitters sit on a lattice every SnowSpacing world units, but only
over the first of NumberTiles x NumberTiles sub-boxes of the playable map
(extent // NumberTiles); that set is drawn once per tile with the world
matrix moved by the sub-box size, so the pattern repeats. Each falls from
the ceiling SnowBoxHeight (absolute world height) by
h = box - fmod(start[noise] + travelled, box), start being a 64x64 table of
rand() % box indexed by the emitter's lattice position, wobbles sideways by
SnowAmplitude * sin(h * SnowFrequencyScale + x), and drifts by
time * SnowXYSpeed - floor((start + travelled) / box) * SnowXYSpeed * box /
SnowSpeed. Each particle is a quad spanned by the camera's right vector and
the world Z axis, 0.707 * SnowQuadSize either side of the centre, V = 0 at
the top, vertex colour white (grey only under the brightness gate), drawn
with shader bits 0x198B3: depth test without depth writes, alpha blending
and no fog. Nothing is culled by distance; the near clip plane (10) is the
only limit.
Its WeatherMixin is the weather part of render.engine.MapRenderer: the methods
that put it on the GPU and draw it, sharing the renderer's state.
"""

import re

import numpy as np
from mapworkshop.mapkit.weather import WEATHER_BLOCK
from mapworkshop.render import shaders

DEFAULTS = dict(hardwarefogenable=False, hardwarefogcolor=(0, 0, 0), hardwarefogstart=0.0, hardwarefogend=1.0,
                snowenabled=True, issnowing=False, snowtexture='EXRainDrop.tga', snowboxheight=300.0,
                snowspacing=30.0, snowamplitude=0.0, snowfrequencyscalex=0.0, snowfrequencyscaley=0.0,
                snowquadsize=10.0, snowspeed=50.0, snowminpointsize=40.0, snowmaxpointsize=80.0,
                snowxyspeed=(0.0, 0.0), numbertiles=1.0, cloudoffsetpersecond=(-0.012, -0.018))
_PAIRS = ('snowxyspeed', 'cloudoffsetpersecond')


def _value(key, text):
    text = text.split(';')[0].strip()
    default = DEFAULTS.get(key)
    if isinstance(default, bool):
        return text.lower() in ('yes', 'true', '1')
    if key in _PAIRS:
        found = dict((k.upper(), float(v)) for k, v in re.findall(r'([XY])\s*:\s*(-?[\d.]+)', text, re.I))
        return (found.get('X', 0.0), found.get('Y', 0.0))
    if isinstance(default, tuple):
        found = dict(re.findall(r'([RGB])\s*:\s*(\d+)', text, re.I))
        return tuple(int(found.get(c, found.get(c.lower(), 0))) / 255 for c in 'RGB')
    if isinstance(default, float):
        match = re.search(r'-?[\d.]+', text)
        return float(match.group(0)) if match else default
    return text


def parse(*texts):
    """Weather settings from INI texts, later ones overriding earlier ones."""
    settings = dict(DEFAULTS)
    for text in texts:
        if not text:
            continue
        for block in re.findall(WEATHER_BLOCK, text):
            for key, value in re.findall(r'(?im)^\s*(\w+)\s*=\s*([^\r\n]*)', block):
                key = key.lower()
                if key in DEFAULTS:
                    settings[key] = _value(key, value)
    return settings


def msvc_rand(seed=1):
    """MSVC rand(): the table the game fills at start-up, with the CRT's seed."""
    state = seed
    while True:
        state = (state * 214013 + 2531011) & 0xFFFFFFFF
        yield (state >> 16) & 0x7FFF


def emitters(settings, width, height):
    """Emitters (N, 3) as (x, y, starting height) for the GPU, which falls
    them by `travelled` = time x SnowSpeed (W3DSnowManager::update adds
    elapsed seconds x velocity each frame) and wraps them in the box.
    Emitters of the first sub-box are repeated over NumberTiles^2 tiles."""
    if not (settings['snowenabled'] and settings['issnowing']):
        return np.zeros((0, 3), np.float32)
    box = max(int(settings['snowboxheight']), 1)
    rand = msvc_rand()
    start = np.array([next(rand) % box for _ in range(64*64)], np.float32).reshape(64, 64)
    spacing = max(int(settings['snowspacing']), 1)
    tiles = max(int(settings.get('numbertiles', 1)), 1)
    sub_x, sub_y = int(width) // tiles, int(height) // tiles
    x, y = np.meshgrid(np.arange(0, sub_x, spacing), np.arange(0, sub_y, spacing))
    s = start[(y + 100000) % 64, (x + 100000) % 64]
    base = np.stack([x, y, s], -1).reshape(-1, 3).astype(np.float32)
    out = [base + np.array([i*sub_x, j*sub_y, 0], np.float32) for j in range(tiles) for i in range(tiles)]
    return np.concatenate(out)


def particles(settings, width, height, travelled=0.0):
    """World positions (N, 3) of the falling particles over a width x height map."""
    if not (settings['snowenabled'] and settings['issnowing']):
        return np.zeros((0, 3), np.float32)
    box = max(int(settings['snowboxheight']), 1)
    rand = msvc_rand()
    start = np.array([next(rand) % box for _ in range(64*64)], np.float32).reshape(64, 64)
    spacing = max(int(settings['snowspacing']), 1)
    xs = np.arange(0, int(width), spacing)
    ys = np.arange(0, int(height), spacing)
    x, y = np.meshgrid(xs, ys)
    # MODPOW2(x + 100000, 64) + MODPOW2(y + 100000, 64) * 64
    h0 = box - np.fmod(start[(y + 100000) % 64, (x + 100000) % 64] + travelled, box)
    amplitude = settings['snowamplitude']
    px = x + amplitude*np.sin(h0*settings['snowfrequencyscalex'] + x)
    py = y + amplitude*np.sin(h0*settings['snowfrequencyscaley'] + y)
    return np.stack([px, py, h0], -1).reshape(-1, 3).astype(np.float32)


class WeatherMixin:
    """MapRenderer's weather: fog uniforms and the falling rain or snow particles."""

    # Weather ----------------------------------------------------------------
    def _prepare_weather(self):
        """map.ini Weather over weather.ini: hardware fog and falling particles."""
        from mapworkshop.render.weather import parse, emitters
        map_ini = self.source.parent/'map.ini' if self.source else None
        if self.weather_preset:
            from mapworkshop.mapkit.weather import ini_block
            local = ini_block(self.weather_preset)
        else:
            local = self.map_ini
        sun = ''
        if self.sun:
            from mapworkshop.mapkit.weather import sun_ini
            sun = sun_ini(self.sun)
        self.weather = parse(self.assets.ini_text('weather.ini'), local, sun)
        w = self.weather
        self.report['weather'] = dict(fog=[*w['hardwarefogcolor'], w['hardwarefogstart'], w['hardwarefogend']]
                                      if w['hardwarefogenable'] else None,
                                      particles=w['snowtexture'] if w['issnowing'] and w['snowenabled'] else None)
        self.particles = None
        centers = emitters(w, *self.playable)
        self._weather_centers = centers
        if len(centers):
            self._prepare_image(w['snowtexture'])

    def _weather_gpu(self):
        w, centers = self.weather, self._weather_centers
        texture = self._plain_texture(w['snowtexture']) if len(centers) else None
        if texture is None:
            return
        program = self.ctx.program(vertex_shader=shaders.PARTICLE_VS, fragment_shader=shaders.PARTICLE_FS)
        corners = self.ctx.buffer(np.array([-1, -1, 1, -1, 1, 1, -1, -1, 1, 1, -1, 1], 'f4').tobytes())
        instances = self.ctx.buffer(centers.tobytes())
        vao = self.ctx.vertex_array(program, [(corners, '2f', 'in_corner'), (instances, '3f/i', 'in_emitter')])
        self.particles = dict(program=program, vao=vao, texture=texture, count=len(centers))
        self.report['weather']['particle_count'] = len(centers)

    def _set_fog(self, program, eye):
        w = self.weather
        on = int(w['hardwarefogenable'] and self.visible['weather'])
        for key, value in [('fog_enabled', on), ('fog_color', tuple(w['hardwarefogcolor'])),
                           ('fog_range', (w['hardwarefogstart'], w['hardwarefogend'])), ('fog_eye', eye)]:
            if key in program:
                program[key].value = value

    def _draw_particles(self, vp, camera, eye, time=0.0):
        mgl, ctx = self.moderngl, self.ctx
        p = self.particles['program']
        forward = np.asarray(camera['target'], float) - np.asarray(camera['eye'], float)
        forward /= np.linalg.norm(forward) or 1.0
        right = np.cross(forward, (0.0, 0.0, 1.0))
        if np.linalg.norm(right) < 1e-6:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        p['view_projection'].write(vp)
        p['right'].value = tuple(right)
        w = self.weather
        box = float(max(int(w['snowboxheight']), 1))
        speed = float(w['snowspeed']) or 1.0
        p['size'].value = float(w['snowquadsize'])
        p['box'].value = box
        p['travelled'].value = float(time*w['snowspeed'])
        p['amplitude'].value = float(w['snowamplitude'])
        p['frequency'].value = (float(w['snowfrequencyscalex']), float(w['snowfrequencyscaley']))
        p['drift'].value = (float(time*w['snowxyspeed'][0]), float(time*w['snowxyspeed'][1]))
        p['drift_per_cycle'].value = (float(w['snowxyspeed'][0])*box/speed, float(w['snowxyspeed'][1])*box/speed)
        p['playable'].value = self.playable
        self.particles['texture'].use(0)
        p['tex'].value = 0
        ctx.enable(mgl.BLEND)
        ctx.blend_func = (mgl.SRC_ALPHA, mgl.ONE_MINUS_SRC_ALPHA)
        ctx.fbo.depth_mask = False
        self.particles['vao'].render(mgl.TRIANGLES, instances=self.particles['count'])
        ctx.fbo.depth_mask = True
        ctx.disable(mgl.BLEND)
