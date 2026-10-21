"""Showcase: one new map, Brightwater Fold, from `mw new` to its last details.

It draws the Python viewer's toolbar and marks, which phase 4 of the Godot viewer
removed: run it at commit 7b5ab1a (`git worktree add ../showcase 7b5ab1a`).

    python -m misc.studio_showcase.showcase [--stills 12,20,36] [--out DIR]

Everything shown happened. Brightwater Fold was made for this video in
seven steps, each kept as a snapshot in local/videos/studio-showcase/steps/
(the project's map.py and map.toml, its build, the marks drawn on it and the
command output at the time); facts.py collects the map changes between the
steps and the lines of map.py each one added. The images the agent looked at
while making it (item collages, texture sheets, its own check renders) are
in looks/.

Every frame is drawn by the workshop's renderer (render.engine) from those
step builds, at 1920x1080, with the viewer's own toolbar (viewer.toolbar)
and mark overlay (viewer.overlay). On top: the cursor, captions and a
simplified Claude Code session replaying the step's prompt, tool calls,
output and the images it looked at. The tricks between steps are the
renderer's own data changed in place: terrain heights rising from the flat
field, the river filling, textures spreading from the water, every object
growing at its own place, a before/after wipe, a sweep of new light and a
rewind through all of it. The original score is in score.py.
"""
import argparse
import json
import math
import subprocess
import time as clock
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from mapworkshop.config import ROOT, VIDEOS
from mapworkshop.render.camera import parse_view
from mapworkshop.render.engine import MapRenderer
from mapworkshop.render.water import build_mesh
from mapworkshop.video.encoding import encode, export_profile, validate
from mapworkshop.viewer.overlay import MarkOverlay
from mapworkshop.viewer.toolbar import Toolbar

from .score import score

W, H, FPS = 1920, 1080, 30
DURATION = 120.0
HOME = VIDEOS/'studio-showcase'
STEPS = HOME/'steps'
LOOKS = HOME/'looks'
MAP_NAME = 'map mp brightwater fold.map'
PROFILES = ROOT/'src/mapworkshop/video/profiles.toml'
FONTS = Path('C:/Windows/Fonts')
UI = 1.3                                   # toolbar scale at 1080p
GOLD = (232, 196, 120)
CLAUDE = (217, 119, 87)                    # Claude Code's accent orange
C = 2395.0                                 # the map's centre (map units)
FLAT = 150.0                               # the new map's ground height (the template's)

# Section starts. The map changes on screen at `reload_*`.
TIMELINE = dict(open=0.0, rewind=6.2, new=9.0, shape=16.5, reload_shape=26.0, paint=30.5, reload_paint=37.0,
                populate=41.5, reload_populate=49.8, creek=60.0, reload_creek=72.0, paddock=76.0,
                reload_paddock=86.0, polish=90.0, reload_polish=100.4, walls=103.0, reload_walls=109.6, finale=111.8,
                end=115.8)
T = TIMELINE
CHAPTERS = [('NEW', T['new']), ('SHAPE', T['shape']), ('PAINT', T['paint']), ('POPULATE', T['populate']),
            ('CREEK', T['creek']), ('PADDOCK', T['paddock']), ('POLISH', T['polish'])]


def font(name, size):
    return ImageFont.truetype(str(FONTS/name), size)


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u*u*(3-2*u)


def lerp(a, b, u):
    return a+(b-a)*u


def span(t, t0, t1):
    return ease((t-t0)/(t1-t0)) if t1 > t0 else float(t >= t1)


def fade(t, t0, t1, inn=0.4, out=0.4):
    """0..1 visibility of something shown from t0 to t1."""
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t-t0)/inn if inn else 1.0, (t1-t)/out if out else 1.0)


def back(u, s=1.6):
    """Ease out with a little overshoot, for things that pop into place."""
    u = np.clip(u, 0, 1)-1
    return 1+u*u*((s+1)*u+s)


# --- the camera ------------------------------------------------------------------------------
def cam(x, y, d, e, h):
    return dict(x=float(x), y=float(y), distance=float(d), elevation=float(e), heading=float(h))


def aside(c, k):
    """The camera moved k map units to its right: the map slides left of a side panel."""
    h = math.radians(c['heading'])
    return dict(c, x=c['x']+math.cos(h)*k, y=c['y']-math.sin(h)*k)


DRAW_CREEK = cam(870, 3270, 2600, 60, 10)
DRAW_PADDOCK = cam(2060, 1240, 1650, 60, 15)
DRAW_PINS = cam(C, C, 1350, 60, 45)
HOLD = cam(C, C, 1400, 36, 45)
GATE = cam(2262, 2254, 430, 22, 45)
WALLS = cam(2700, 2100, 640, 35, 300)
WALLS_WIDE = cam(2640, 2150, 1000, 30, 300)
# (time, camera, stop): the camera eases to a halt at a stop and flows
# through the other keys.
KEYS = [
    (0.0, cam(2000, 1850, 4700, 30, 36), True), (6.2, cam(C, C, 2500, 33, 62), True),
    (9.0, cam(C, C, 6200, 52, 20), True), (16.5, cam(C, C, 5700, 48, 26), True),
    (17.3, aside(cam(C, C, 5900, 48, 26), 1300), True), (25.9, aside(cam(C, C, 5900, 48, 26), 1300), True),
    (26.6, cam(C, C, 4800, 38, 30), False), (29.4, cam(C, C, 3500, 31, 55), False), (30.5, cam(C, C, 3400, 31, 60), True),
    (31.2, aside(cam(C, C, 4400, 42, 40), 1100), True), (36.6, aside(cam(C, C, 4400, 42, 40), 1100), True),
    (37.3, cam(C, C, 4500, 38, 30), False), (41.5, cam(C, C, 3500, 33, 58), True),
    (42.2, aside(cam(C, C, 3300, 40, 45), 850), True), (49.4, aside(cam(C, C, 3300, 40, 45), 850), True),
    (50.2, cam(C, C, 1500, 34, 45), False), (52.8, cam(C, C, 1250, 31, 62), False),
    (56.2, cam(C, C, 4400, 36, 72), False), (57.4, cam(C, C, 5300, 58, 45), True), (59.8, cam(C, C, 5200, 58, 50), True),
    (61.0, DRAW_CREEK, True), (65.1, DRAW_CREEK, True), (65.8, aside(DRAW_CREEK, 700), True),
    (71.6, aside(DRAW_CREEK, 700), True), (72.0, DRAW_CREEK, True), (74.4, DRAW_CREEK, True),
    (76.0, cam(1350, 3330, 1150, 30, -30), True), (76.8, DRAW_PADDOCK, True), (78.3, DRAW_PADDOCK, True),
    (78.9, aside(DRAW_PADDOCK, 520), True), (85.6, aside(DRAW_PADDOCK, 520), True), (86.0, DRAW_PADDOCK, True),
    (88.2, DRAW_PADDOCK, True), (90.0, cam(1990, 1250, 700, 30, 60), True), (90.6, DRAW_PINS, True),
    (91.9, DRAW_PINS, True), (92.5, aside(DRAW_PINS, 460), True), (100.0, aside(DRAW_PINS, 460), True),
    (100.5, HOLD, True), (102.9, cam(C, C, 1300, 34, 52), True), (103.8, aside(WALLS_WIDE, 420), True),
    (109.3, aside(WALLS_WIDE, 420), True), (109.6, WALLS, True), (111.8, WALLS, True),
    (113.8, cam(C, C, 2000, 28, 62), False), (115.8, cam(C, C, 4800, 34, 95), False),
    (DURATION, cam(C, C, 5200, 36, 108), True)]


def camera_at(t):
    keys = KEYS
    if t <= keys[0][0]:
        return keys[0][1]
    for i in range(len(keys)-1):
        (t0, a, stop_a), (t1, b, stop_b) = keys[i], keys[i+1]
        if t0 <= t <= t1:
            u = (t-t0)/(t1-t0)

            def tangent(j, stop):
                if stop or j == 0 or j == len(keys)-1:
                    return {k: 0.0 for k in a}
                (tp, p, _), (tn, n, _) = keys[j-1], keys[j+1]
                return {k: (n[k]-p[k])/(tn-tp)*(t1-t0) for k in a}
            ma, mb = tangent(i, stop_a), tangent(i+1, stop_b)
            h00, h10, h01, h11 = 2*u**3-3*u**2+1, u**3-2*u**2+u, -2*u**3+3*u**2, u**3-u**2
            return {k: h00*a[k]+h10*ma[k]+h01*b[k]+h11*mb[k] for k in a}
    return keys[-1][1]


def spec(c):
    return (f"target={c['x']:.2f},{c['y']:.2f} distance={c['distance']:.2f} "
            f"elevation={c['elevation']:.3f} heading={c['heading']:.3f}")


# --- the renderers -----------------------------------------------------------------------
class Morph(MapRenderer):
    """The shaped dale, whose heights can be eased in from the flat field and
    whose river can be filled from its bed."""

    def setup(self):
        t = self.terrain
        self.final = t.heights.astype('f4').copy()
        rows, cols = self.final.shape
        y, x = (np.mgrid[0:rows, 0:cols]-t.border)*10.0
        # Outer ground rises a little after the middle.
        self.delay = np.clip(np.hypot(x-C, y-C)/3400, 0, 1).astype('f4')
        self.tint = np.asarray(self._depth_tint, 'f4')
        entry = self.water[0]
        area = entry['area']
        vertices, triangles, _ = build_mesh(area['points'], float(area['water_height']), t.height_at, self.water_level)
        self.water_vertices = vertices.copy()
        self.water_vbo = self.ctx.buffer(vertices.tobytes())
        ibo = self.ctx.buffer(triangles.tobytes())
        entry['vao'] = self.ctx.vertex_array(self.water_program, [(self.water_vbo, '4f', 'in_vertex')],
                                             index_buffer=ibo, index_element_size=4)
        self.level = float(area['water_height'])
        self.rise(1.0)

    def rise(self, u):
        """u 0: the flat field, 1: the dale; the river is dry until it is filled."""
        k = np.clip((u*1.35-.35*self.delay), 0, 1)
        k = k*k*(3-2*k)
        self.heights.write((FLAT+(self.final-FLAT)*k).astype('f4').tobytes())
        self.depth_tint.write((self.tint if u >= 1 else np.ones_like(self.tint)).tobytes())
        if u < 1:
            self.visible['water'] = False

    def fill(self, u):
        """The river's water from 18 below its level (u 0) to its level (u 1)."""
        v = self.water_vertices.copy()
        v[:, 2] = self.level-18*(1-ease(u))
        self.water_vbo.write(v.tobytes())
        self.visible['water'] = u > 0


class Grow(MapRenderer):
    """A build whose objects can grow in at their own places: every instance's
    scale is rewritten each frame from its own start time."""

    def _vertex_array(self, vertices, indices, inst, scales, sway):
        vao = super()._vertex_array(vertices, indices, inst, scales, sway)
        self.__dict__.setdefault('_buffers', {})[id(scales)] = (inst, scales)
        self.__dict__.setdefault('_vao_scales', {})[id(vao)] = id(scales)
        return vao

    def setup(self, hold_radius=470):
        sky = {self._vao_scales[id(b['vao'])] for b in self.batches if b.get('sky') and id(b['vao']) in self._vao_scales}
        self.groups = []
        rng = np.random.default_rng(5)
        for key, (inst, scales) in self._buffers.items():
            if key in sky:
                continue
            place = np.frombuffer(inst.read(), 'f4').reshape(-1, 4)
            base = np.frombuffer(scales.read(), 'f4').copy()
            d = np.hypot(place[:, 0]-C, place[:, 1]-C)
            hold = d < hold_radius
            # The hold first, from its middle out; then the land from the river out.
            start = np.where(hold, d/hold_radius*.9, 1.1+np.clip(d/3300, 0, 1)*2.6)+rng.uniform(0, .25, len(d))
            length = np.where(hold, .7, .5)
            self.groups.append((scales, base, start.astype('f4'), length.astype('f4')))
        self.grow(10.0)

    def grow(self, s):
        """Objects s seconds after the growth began."""
        for scales, base, start, length in self.groups:
            scales.write((base*back((s-start)/length)).astype('f4').tobytes())


class Stage:
    """Every step's renderer, a shared framebuffer and the mark overlay."""

    def __init__(self):
        shared = {}
        path = lambda step: STEPS/step/MAP_NAME
        self.new = MapRenderer(path('00-new'), shared=shared)
        self.ctx = ctx = self.new.ctx
        base = self.new.pathing_assets
        self.shape = Morph(path('01-shape'), assets=base, ctx=ctx, shared=shared)
        self.paint = MapRenderer(path('02-paint'), assets=base, ctx=ctx, shared=shared)
        self.populate = Grow(path('03-populate'), assets=base, ctx=ctx, shared=shared)
        self.creek = MapRenderer(path('04-creek'), assets=base, ctx=ctx, shared=shared)
        self.paddock = MapRenderer(path('05-paddock'), assets=base, ctx=ctx, shared=shared)
        self.final = MapRenderer(path('06-polish'), assets=base, ctx=ctx, shared=shared)
        self.walls = MapRenderer(path('07-walls'), assets=base, ctx=ctx, shared=shared)
        self.shape.setup()
        self.populate.setup()
        self.terrain = self.final.terrain
        color = ctx.renderbuffer((W, H), 4, samples=4)
        depth = ctx.depth_renderbuffer((W, H), samples=4)
        self.fbo = ctx.framebuffer([color], depth)
        self.resolve = ctx.framebuffer([ctx.renderbuffer((W, H), 4)])
        self.overlay = MarkOverlay(ctx)

    GRADES = {}

    @classmethod
    def grade(cls, img, lift):
        """A tone curve: gamma below 1 and a little gain, through a lookup table."""
        if lift not in cls.GRADES:
            v = np.arange(256)/255
            gamma, gain = {'early': (.78, 1.12), 'final': (.92, 1.04)}[lift]
            curve = np.clip(v**gamma*gain, 0, 1)
            curve = curve*.94+.06*(curve*curve*(3-2*curve))          # a touch of contrast
            cls.GRADES[lift] = (curve*255).astype(np.uint8)
        return cls.GRADES[lift][img]

    def cam(self, c):
        return parse_view(spec(c).split()).resolve(self.terrain, W/H)

    def _read(self):
        self.ctx.copy_framebuffer(self.resolve, self.fbo)
        return np.flipud(np.frombuffer(self.resolve.read(components=3), np.uint8).reshape(H, W, 3)).copy()

    def shot(self, renderer, c, t, marks=None):
        """(scene, scene with marks) for camera parameters c at time t."""
        camera = self.cam(c)
        renderer.draw(camera, (W, H), self.fbo, time=t)
        lift = 'final' if renderer in (self.final, self.walls) else 'early'
        scene = self.grade(self._read(), lift)
        if not marks or not (marks[0] or marks[1]):
            return scene, scene
        self.fbo.use()
        self.overlay.draw(marks[0], marks[1], None, camera, renderer.surface_at, (W, H), UI)
        return scene, self.grade(self._read(), lift)

    def screen(self, c, x, y, renderer=None):
        world = MarkOverlay.drape([[x, y]], (renderer or self.final).surface_at)
        px, _ = MarkOverlay.project(world, self.cam(c)['view_projection'], (W, H))
        return tuple(px[0])

    def ground(self, c, renderer, step=4):
        """Map x, y of the ground under every step-th pixel (a few fixed-point
        steps from the valley floor to the terrain)."""
        camera = self.cam(c)
        inv = np.linalg.inv(camera['view_projection'])
        w, h = W//step, H//step
        nx, ny = np.meshgrid((np.arange(w)+.5)/w*2-1, 1-(np.arange(h)+.5)/h*2)
        ones = np.ones_like(nx)

        def unproject(z):
            p = np.einsum('ij,jhw->ihw', inv, np.stack([nx, ny, z*ones, ones]))
            return p[:3]/p[3]
        near, far = unproject(-1), unproject(1)
        d = far-near
        z = np.full(nx.shape, 175.0)
        for _ in range(5):
            s = (z-near[2])/np.where(np.abs(d[2]) < 1e-9, -1e-9, d[2])
            x, y = near[0]+s*d[0], near[1]+s*d[1]
            z = renderer.terrain.height_at(x, y)
        return x, y


def water_distance(step):
    """The signed distance from the water (map units, negative in it) of a
    step's own map.py, with the border it is sampled on."""
    import importlib.util
    spec_ = importlib.util.spec_from_file_location(f'step_{step.replace("-", "_")}', STEPS/step/'map.py')
    module = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(module)
    return module.terrain()['sd'].astype(np.float32), module.BORDER


def upsample(a):
    """A low-resolution 0..1 mask to the frame's size."""
    img = Image.fromarray((np.clip(a, 0, 1)*255).astype(np.uint8))
    return np.asarray(img.resize((W, H), Image.Resampling.BILINEAR), np.float32)/255


# --- the record --------------------------------------------------------------------------
def code_lines(step, needles, width=70):
    """(line number, text) of the first line of map.py at a step containing each needle."""
    lines = (STEPS/step/'map.py').read_text(encoding='utf-8').splitlines()
    out = []
    for needle in needles:
        for i, line in enumerate(lines):
            if needle in line:
                out.append((i+1, line if len(line) <= width else line[:width-1]+'…'))
                break
    return out


def creek_points():
    marks = json.loads((STEPS/'04-creek'/'marks.json').read_text(encoding='utf-8'))
    return [tuple(p) for p in marks['marks'][0]['points']]


def paddock_mark():
    marks = json.loads((STEPS/'05-paddock'/'marks.json').read_text(encoding='utf-8'))
    m = marks['marks'][0]
    return tuple(m['points'][0]), m['radius']


def pin_points():
    marks = json.loads((STEPS/'06-polish'/'marks.json').read_text(encoding='utf-8'))
    return [tuple(m['points'][0]) for m in marks['marks']]


def recorded(step, name):
    p = STEPS/step/name
    return p.read_text(encoding='utf-8').splitlines() if p.exists() else []


# --- the Claude Code session ---------------------------------------------------------------
PROMPTS = dict(
    shape='Make it a Rohan dale: a river through the middle that parts round an island knoll, rolling downs, '
          'and chalk escarpments where the river enters and leaves.',
    paint='Paint it like Rohan: golden grass, greener by the river, rock on the scarps, mud at the banks. '
          'Roads from each base: one over the river, one to the island.',
    populate='Build a walled hold on the island with golden halls and longhouses. Fords and bridges for the '
             'roads, pine copses on the hills, rocks and reeds.',
    creek='Run a creek along mark 1 into the river, with a footbridge where the north road crosses it. '
          'Same on the other side.',
    paddock='Put a horse paddock in mark 1: a rail fence, a stable at its gate, horses grazing.',
    circular='also; its too perfectly circular',
    polish="Last details: torches at the gateways (pins 1 and 2), wear the hold's ground, and give it warm "
           'late-afternoon light.',
    torches='try to look at the torches again',
    walls='look at a render of the fortification, the walls in particular, and fix them')
FILE = 'maps/brightwater_fold/map.py'


def session(facts):
    """The Claude Code panel's script: (time, kind, payload) entries, spinner
    spans, typed prompts (start, stop, sent, text), panel spans and pops
    (start, end, image, label) of the images Claude looked at."""
    e, spin, typing, pops = [], [], [], []

    def prompt(at, text, length):
        typing.append((at, at+length, at+length+.2, text))
        e.append((at+length+.2, 'user', text))
        e.append((at+length+.2, 'blank', ''))
        return at+length+.2

    def update(at, step, needles, count=None):
        e.append((at, 'tool', ('Update', FILE)))
        e.append((at+.15, 'out', f'Updated {FILE} with {count} additions' if count else f'Updated {FILE}'))
        for k, (n, line) in enumerate(code_lines(step, needles)):
            e.append((at+.25+.08*k, 'diff', (n, line)))
        e.append((at+.6, 'blank', ''))

    def tool(at, name, arg, lines=(), dt=.12):
        e.append((at, 'tool', (name, arg)))
        for k, line in enumerate(lines):
            e.append((at+.3+dt*k, 'out', line))
        e.append((at+.3+dt*len(lines), 'blank', ''))

    def say(at, text):
        e.append((at, 'say', text))
        e.append((at, 'blank', ''))

    def look(at, image, label, pop=1.5):
        e.append((at, 'image', image))
        pops.append((at+.15, at+.15+pop, image, label))

    def changes(step, k, first=None):
        lines = [line.strip() for line in facts[step].get('changes', [])]
        if first:
            lines = [line for line in lines if line.startswith(first)]+[line for line in lines if not line.startswith(first)]
        return lines[:k]

    # 02 Shape.
    s = prompt(T['shape']+.5, PROMPTS['shape'], 2.4)
    spin.append((s+.1, s+.9, 'Shaping the dale'))
    update(s+.9, '01-shape', ['UPSTREAM = [', 'ISLAND = dict(', 'sd = np.maximum(smooth_min(', 'swell = 44*fbm('],
           facts['01-shape']['added_count'])
    tool(s+1.9, 'Bash', 'mw build brightwater-fold', ['Built Brightwater Fold in 5 s', 'heights 128..603'])
    tool(s+2.6, 'Bash', 'python look.py check.jpg')
    look(s+2.8, LOOKS/'01-shape-second.jpg', 'Claude renders its build and looks at it')
    say(s+4.4, 'The river runs in a walled trench. The downs should fall in a long slope to the water.')
    update(s+5.0, '01-shape', ['floor = WATER+5', 'reach = 520+180', 'land = floor+(land-floor)'])
    tool(s+5.7, 'Bash', 'mw build brightwater-fold', ['Built Brightwater Fold in 5 s'])
    spans = [(T['shape'], T['reload_shape']-.1)]

    # 03 Paint.
    s = prompt(T['paint']+.5, PROMPTS['paint'], 2.2)
    tool(s+.2, 'Bash', 'python swatches.py textures.png GrassRohan01 … CliffRohan05')
    look(s+.45, LOOKS/'02-textures-rohan.png', "Claude compares the game's Rohan textures")
    say(s+1.9, 'GrassRohan04 and 01 for the downs, 03 and 12 by the water, RockRohan and CliffRohan on the steep '
               'ground.')
    update(s+2.5, '02-paint', ['PALETTE = [', 'labels[(sd < 320+140*mid)', 'labels[slope > 1.15]', 'NORTH_ROAD = ['],
           facts['02-paint']['added_count'])
    tool(s+3.2, 'Bash', 'mw build brightwater-fold', changes('02-paint', 1, 'Textures'))
    spans.append((T['paint'], T['reload_paint']-.2))

    # 04 Populate.
    s = prompt(T['populate']+.5, PROMPTS['populate'], 2.2)
    tool(s+.2, 'Bash', 'mw items RohanGoldenHall RohanHouse01 … --views 0/40,90/40,180/40,270/40')
    look(s+.45, LOOKS/'03-fronts.png', 'Before turning a building, it finds the front by looking', 1.7)
    say(s+2.1, "The hall's stairs are on its local -y side, the longhouse porches on -x: into DOOR_SIDES.")
    update(s+2.8, '03-populate', ["HALL = ('RohanGoldenHall'", 'DOOR_SIDES = {', 'def hold(s, t):', 'def fairness('],
           facts['03-populate']['added_count'])
    built = [line.strip() for line in recorded('03-populate', 'build.txt') if 'objects,' in line or 'island' in line]
    tool(s+3.6, 'Bash', 'mw build brightwater-fold', built[:3])
    spans.append((T['populate'], T['reload_populate']-.2))

    # 05 Creek: the mark is drawn in the viewer first.
    s = prompt(T['creek']+5.6, PROMPTS['creek'], 2.0)
    marks = [line.strip() for line in recorded('04-creek', 'marks.txt') if line.strip().startswith(('#', 'objects', 'layers'))]
    tool(s+.2, 'Bash', 'mw marks', [line if len(line) < 74 else line[:73]+'…' for line in marks[:3]])
    say(s+1.2, 'Mark 1 runs 48 points from (85, 3403) east to (1591, 3246). I carry it on into the river and '
               "turn a copy onto player 2's side.")
    update(s+2.2, '04-creek', ['CREEK = [(85, 3403)', 'sd = smooth_min(sd, creek_sd', 'CREEK_BRIDGE_SCALE ='],
           facts['04-creek']['added_count'])
    tool(s+3.0, 'Bash', 'mw build brightwater-fold', changes('04-creek', 3))
    spans.append((T['creek']+5.2, T['reload_creek']-.2))

    # 06 Paddock, and a follow-up.
    s = prompt(T['paddock']+2.8, PROMPTS['paddock'], 1.6)
    update(s+.3, '05-paddock', ['PADDOCK = (2060, 1240, 300)', "DOOR_SIDES['RohanStable']", 'HORSES = ['])
    tool(s+1.0, 'Bash', 'mw build brightwater-fold', ['Built Brightwater Fold in 12 s'])
    tool(s+1.5, 'Bash', 'python look.py paddock.jpg')
    look(s+1.7, LOOKS/'05-paddock-second.jpg', 'Claude checks its own render', 1.3)
    s2 = prompt(s+3.1, PROMPTS['circular'], .8)
    say(s2+.2, 'Straight fence runs between eleven uneven corner posts, round a lopsided oval inside the mark.')
    update(s2+.8, '05-paddock', ['def paddock_outline():', 'reach = r*(.84+.1*math.cos'], facts['05-paddock']['added_count'])
    tool(s2+1.4, 'Bash', 'mw build brightwater-fold', changes('05-paddock', 1, 'Objects'))
    spans.append((T['paddock']+2.4, T['reload_paddock']-.2))

    # 07 Polish: pins, and looking twice for a torch.
    s = prompt(T['polish']+2.4, PROMPTS['polish'], 2.0)
    tool(s+.2, 'Bash', 'mw items "*torch*" "*brazier*"')
    look(s+.4, LOOKS/'06-torches.png', 'Claude looks for a torch', 1.0)
    say(s+1.3, 'GenericTorch2 renders as a bare pole; the others are units carrying torches.')
    s2 = prompt(s+1.8, PROMPTS['torches'], .7)
    tool(s2+.2, 'Bash', 'mw items TownLamp1 … TownLamp5 FirePit FireBonfire … --columns 5')
    look(s2+.4, LOOKS/'06-lamps-fires-wide.png', '…and again, wider: lamps and fires', 1.2)
    say(s2+1.4, 'TownLamp4 is an iron stand with a burning torch, 57 high: right for a gateway.')
    update(s2+2.0, '06-polish', ["GATE_TORCH, LANTERN = 'TownLamp4'", 'SUN = dict(', 's.pair(GATE_TORCH'],
           facts['06-polish']['added_count'])
    lighting = next((line.strip() for line in facts['06-polish']['changes'] if line.strip().startswith('Objects')), '')
    tool(s2+2.7, 'Bash', 'mw build brightwater-fold', [lighting, 'GlobalLighting: diffuse (0.7, 0.65, 0.56) -> (1, 0.86, 0.62)'])
    spans.append((T['polish']+2.0, T['reload_polish']-.1))

    # A follow-up on the hold's walls.
    s = prompt(T['walls']+.6, PROMPTS['walls'], 1.4)
    tool(s+.2, 'Bash', 'python look.py walls.jpg')
    look(s+.4, LOOKS/'07-walls-before.jpg', 'Claude renders the walls and looks', 1.4)
    say(s+1.9, "The sections hang off the knoll's edge, gaps open at every bend, and the longhouses run into the wall.")
    update(s+2.6, '07-walls', ['WALL_LINE = 88', 'def wall_corners():', 'ends.append(WALL_DEPTH/2*math.tan(turn/2))'],
           facts['07-walls']['added_count'])
    tool(s+3.3, 'Bash', 'mw build brightwater-fold', changes('07-walls', 1, 'Heights'))
    spans.append((T['walls']+.2, T['reload_walls']-.2))
    spinners = spin+[(a-.9, a-.05, 'Building') for a, kind, payload in e if kind == 'tool' and payload[0] == 'Bash'
                      and 'build' in payload[1]]
    return dict(entries=e, spinners=spinners, typing=typing, spans=spans, pops=pops)


def mascot(d, x, y, cell):
    """Claude Code's pixel mascot, simplified."""
    rows = ['...XXXXXX...', '...X.XX.X...', '.XXXXXXXXXX.', '...XXXXXX...', '...X.XX.X...']
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == 'X':
                d.rectangle([x+i*cell, y+j*cell, x+(i+1)*cell-1, y+(j+1)*cell-1], fill=CLAUDE)


def wrap(text, width):
    rows, row = [], ''
    for word in text.split(' '):
        if row and len(row)+1+len(word) > width:
            rows.append(row)
            row = word
        else:
            row = f'{row} {word}' if row else word
    return rows+[row]


class Panel:
    """A simplified Claude Code session sliding in from the right."""
    PW, PH, TOP = 900, 870, 118

    def __init__(self, script):
        self.s = script
        self.mono = font('consola.ttf', 20)
        self.bold = font('consolab.ttf', 20)
        self.small = font('consola.ttf', 17)
        self.title = font('seguisb.ttf', 19)
        self.cw = self.mono.getlength('M')
        self.lh = 26
        self.thumbs = {}

    def thumb(self, path, height=210):
        key = (str(path), height)
        if key not in self.thumbs:
            img = Image.open(path).convert('RGB')
            w = round(img.width*height/img.height)
            if w > self.PW-120:
                w = self.PW-120
                height = round(img.height*w/img.width)
            self.thumbs[key] = img.resize((w, height), Image.Resampling.LANCZOS)
        return self.thumbs[key]

    def slide(self, t):
        return max((span(t, a, a+.55)-span(t, b-.1, b+.45) for a, b in self.s['spans']), default=0.0)

    def draw(self, img, t):
        slide = self.slide(t)
        if slide <= 0:
            return img
        pw, ph = self.PW, self.PH
        x0, y0 = lerp(W+10, W-48-pw, slide), self.TOP
        mono, bold, cw, lh = self.mono, self.bold, self.cw, self.lh
        bg = (12, 12, 12, 246)
        white, grey, dim = (236, 236, 236), (150, 150, 150), (110, 110, 110)
        panel = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
        d = ImageDraw.Draw(panel)
        d.rounded_rectangle([0, 0, pw-1, ph-1], radius=14, fill=bg, outline=(64, 64, 64, 255))
        pad = 26
        width = int((pw-2*pad-2*cw)/cw)
        typed = ''
        for start, stop, sent, text in self.s['typing']:
            if start-.6 <= t < sent:
                typed = text[:int(len(text)*span(t, start, stop))]
        box_rows = wrap(typed, width) if typed else ['']
        footer_y = ph-36
        box_bottom = footer_y-12
        box_top = box_bottom-14-lh*len(box_rows)
        # The conversation: rows of (kind, payload, height).
        rows = [('head', '', lh), ('head+', '', lh), ('head+', '', lh), ('blank', '', lh)]
        for start, kind, payload in self.s['entries']:
            if t < start:
                continue
            if kind == 'user':
                rows += [('user', ('> ' if i == 0 else '  ')+r, lh) for i, r in enumerate(wrap(payload, width))]
            elif kind == 'say':
                rows += [('say' if i == 0 else 'say+', r, lh) for i, r in enumerate(wrap(payload, width))]
            elif kind == 'out':
                first = rows[-1][0] not in ('out', 'out+', 'diff')
                text = payload if len(payload) <= width-4 else payload[:width-5]+'…'
                rows.append(('out' if first else 'out+', text, lh))
            elif kind == 'diff':
                rows.append(('diff', payload, lh))
            elif kind == 'image':
                rows.append(('image', payload, self.thumb(payload).height+14))
            else:
                rows.append((kind, payload, lh))
        spin = next((s for s in self.s['spinners'] if s[0] <= t < s[1]), None)
        top = 60
        bottom = box_top-10-(lh+6 if spin else 0)
        total = sum(r[2] for r in rows)
        y = top-max(0, total-(bottom-top))
        for kind, payload, height in rows:
            if y < top-height+1 or y >= bottom:
                y += height
                continue
            if kind == 'head':
                mascot(d, pad, y+10, 8)
                d.text((pad+118, y+2), 'Claude Code', font=bold, fill=white)
                d.text((pad+118, y+lh+2), 'Opus 5.5', font=mono, fill=grey)
                d.text((pad+118, y+2*lh+2), '~\\bfme2-map-studio', font=mono, fill=grey)
            elif kind == 'user':
                d.rectangle([pad-10, y-1, pw-pad+10, y+lh-1], fill=(44, 44, 44))
                d.text((pad, y), payload, font=mono, fill=white)
            elif kind == 'tool':
                name, arg = payload
                d.ellipse([pad+2, y+8, pad+12, y+18], fill=(98, 200, 110))
                d.text((pad+2*cw, y), name, font=bold, fill=white)
                text = f'({arg})'
                room = width-len(name)-2
                d.text((pad+2*cw+bold.getlength(name), y), text if len(text) <= room else text[:room-2]+'…)',
                       font=mono, fill=white)
            elif kind in ('out', 'out+'):
                if kind == 'out':
                    d.line([pad+2*cw+4, y+2, pad+2*cw+4, y+13], fill=grey, width=2)
                    d.line([pad+2*cw+4, y+13, pad+2*cw+19, y+13], fill=grey, width=2)
                d.text((pad+5*cw, y), payload, font=mono, fill=grey)
            elif kind == 'diff':
                n, line = payload
                d.rectangle([pad+5*cw-6, y, pw-pad, y+lh-2], fill=(22, 58, 30))
                d.text((pad+5*cw, y), f'{n:>4} +', font=mono, fill=(120, 190, 130))
                room = width-12
                d.text((pad+12*cw, y), line if len(line) <= room else line[:room-1]+'…', font=mono, fill=(214, 240, 214))
            elif kind == 'image':
                thumb = self.thumb(payload)
                d.line([pad+2*cw+4, y+2, pad+2*cw+4, y+13], fill=grey, width=2)
                d.line([pad+2*cw+4, y+13, pad+2*cw+19, y+13], fill=grey, width=2)
                panel.paste(thumb, (int(pad+5*cw), int(y+4)))
                d.rectangle([pad+5*cw-1, y+3, pad+5*cw+thumb.width, y+4+thumb.height], outline=(80, 80, 80))
            elif kind in ('say', 'say+'):
                if kind == 'say':
                    d.ellipse([pad+2, y+8, pad+12, y+18], fill=white)
                d.text((pad+2*cw, y), payload, font=mono, fill=white)
            y += height
        if spin:
            sy = box_top-10-lh
            k = t*6
            cx, cy, r = pad+7, sy+13, 8
            for a in range(3):
                ang = math.pi*a/3+k
                d.line([cx-r*math.cos(ang), cy-r*math.sin(ang), cx+r*math.cos(ang), cy+r*math.sin(ang)],
                       fill=CLAUDE, width=3)
            label = spin[2]+'.'*(1+int(t*3) % 3)
            d.text((pad+2*cw, sy), label, font=mono, fill=CLAUDE)
            d.text((pad+2*cw+mono.getlength(spin[2]+'...')+cw, sy), '(esc to interrupt)', font=mono, fill=dim)
        # Title bar with a single tab.
        d.rounded_rectangle([0, 0, pw-1, 44], radius=14, fill=(32, 32, 32, 255))
        d.rectangle([0, 30, pw-1, 44], fill=(32, 32, 32, 255))
        d.rounded_rectangle([12, 8, 236, 44], radius=8, fill=bg[:3])
        d.rectangle([12, 30, 236, 44], fill=bg[:3])
        d.rounded_rectangle([26, 19, 39, 32], radius=3, fill=CLAUDE)
        d.text((50, 26), 'Claude Code', font=self.title, fill=white, anchor='lm')
        # The prompt box and its footer.
        d.rectangle([1, box_top-6, pw-2, ph-2], fill=bg)
        d.line([pad-10, box_top, pw-pad+10, box_top], fill=(96, 96, 96), width=2)
        d.line([pad-10, box_bottom, pw-pad+10, box_bottom], fill=(96, 96, 96), width=2)
        for i, row in enumerate(box_rows):
            ry = box_top+7+i*lh
            if i == 0:
                d.text((pad, ry), '>', font=bold, fill=white)
            d.text((pad+2*cw, ry), row, font=mono, fill=white)
        if not typed:
            d.text((pad+2*cw, box_top+7), 'Try "a forest in mark 2"', font=mono, fill=dim)
        if int(t*2.5) % 2 == 0 and not spin:
            cx = pad+2*cw+(mono.getlength(box_rows[-1]) if typed else 0)
            d.rectangle([cx, box_top+10, cx+cw-2, box_top+3+lh], fill=(220, 220, 220))
        d.text((pad, footer_y), '? for shortcuts', font=self.small, fill=dim)
        d.text((pw-pad, footer_y), 'auto mode on', font=self.small, fill=CLAUDE, anchor='ra')
        base = img.convert('RGBA')
        shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([x0+10, y0+16, x0+pw+10, y0+ph+16], radius=18, fill=(0, 0, 0, 120))
        base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(14)))
        base.alpha_composite(panel, (int(x0), y0))
        return base.convert('RGB')

    def pop(self, img, t, layers):
        """An image Claude looked at, shown large over the map for a moment."""
        for start, end, path, label in self.s['pops']:
            a = fade(t, start, end, .3, .3)
            if a <= 0:
                continue
            grow = .86+.14*ease((t-start)/.3)
            maxw, maxh = 860*grow, 740*grow
            src = Image.open(path).convert('RGB')
            k = min(maxw/src.width, maxh/src.height)
            big = src.resize((max(1, round(src.width*k)), max(1, round(src.height*k))), Image.Resampling.LANCZOS)
            cx, cy = 490, 120+430
            x, y = int(cx-big.width/2), int(cy-big.height/2)
            base = img.convert('RGBA')
            dim = Image.new('RGBA', base.size, (8, 9, 12, int(110*a)))
            base = Image.alpha_composite(base, dim)
            shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
            ImageDraw.Draw(shadow).rectangle([x+8, y+14, x+big.width+8, y+big.height+14], fill=(0, 0, 0, int(140*a)))
            base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(12)))
            card = Image.new('RGBA', (big.width+8, big.height+8), (250, 250, 250, 255))
            card.paste(big, (4, 4))
            card.putalpha(int(255*a))
            base.alpha_composite(card, (x-4, y-4))
            d = ImageDraw.Draw(base)
            d.rounded_rectangle([x-4, y-48, x-4+layers.kicker.getlength(label)+48, y-12], radius=8,
                                fill=(12, 12, 12, int(230*a)))
            d.rounded_rectangle([x+8, y-36, x+20, y-24], radius=3, fill=CLAUDE+(int(255*a),))
            d.text((x+30, y-30), label, font=layers.kicker, fill=(240, 240, 240, int(255*a)), anchor='lm')
            img = base.convert('RGB')
        return img


# --- 2D layers -----------------------------------------------------------------------------
class Layers:
    def __init__(self):
        self.title = font('georgiab.ttf', 100)
        self.title_small = font('georgiab.ttf', 60)
        self.sub = font('segoeuisl.ttf', 34)
        self.kicker = font('seguisb.ttf', 22)
        self.caption = font('segoeui.ttf', 38)
        self.mono = font('consola.ttf', 26)
        self.mono_small = font('consola.ttf', 20)
        self.chapter = font('seguisb.ttf', 16)
        y = np.arange(H, dtype=np.float32)
        self.bottom_shade = (np.clip((y-(H-330))/330, 0, 1)[:, None]**1.6*0.72)*np.ones((1, W), np.float32)
        vx = (np.arange(W)-W/2)/(W/2); vy = (y-H/2)/(H/2)
        self.vignette = np.clip(np.hypot(vx[None, :], vy[:, None])-0.55, 0, 1)**1.5*0.55

    @staticmethod
    def darken(img, mask, k=1.0):
        a = np.asarray(img, np.float32)
        a *= (1-mask*k)[..., None]
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def text_center(self, draw, y, text, fnt, alpha, fill=(244, 238, 222), spacing=0):
        width = (sum(draw.textlength(ch, font=fnt) for ch in text)+spacing*(len(text)-1)) if spacing else draw.textlength(text, font=fnt)
        x = (W-width)/2
        if spacing:
            for ch in text:
                draw.text((x+2, y+3), ch, font=fnt, fill=(0, 0, 0, int(140*alpha)))
                draw.text((x, y), ch, font=fnt, fill=fill+(int(255*alpha),))
                x += draw.textlength(ch, font=fnt)+spacing
        else:
            draw.text((x+2, y+3), text, font=fnt, fill=(0, 0, 0, int(140*alpha)))
            draw.text((x, y), text, font=fnt, fill=fill+(int(255*alpha),))

    def caption_block(self, draw, kicker, text, alpha):
        if alpha <= 0:
            return
        x, y = 92, H-176
        draw.rectangle([x, y+4, x+46, y+7], fill=GOLD+(int(255*alpha),))
        draw.text((x+60, y-9), kicker, font=self.kicker, fill=GOLD+(int(255*alpha),))
        draw.text((x+2, y+34), text, font=self.caption, fill=(0, 0, 0, int(150*alpha)))
        draw.text((x, y+32), text, font=self.caption, fill=(246, 242, 232, int(255*alpha)))

    def chapters(self, draw, t, alpha):
        """The seven steps along the bottom right, the current one lit."""
        if alpha <= 0:
            return
        current = max((i for i, (_, at) in enumerate(CHAPTERS) if t >= at), default=-1)
        labels = [f'{i+1} {name}' for i, (name, _) in enumerate(CHAPTERS)]
        widths = [draw.textlength(s, font=self.chapter) for s in labels]
        gap = 22
        x = W-64-sum(widths)-gap*(len(labels)-1)
        y = H-58
        for i, (label, w) in enumerate(zip(labels, widths)):
            if i == current:
                fill = GOLD
            elif i < current:
                fill = (232, 228, 218)
            else:
                fill = (150, 150, 150)
            a = int(255*alpha*(1 if i <= current else .7))
            draw.text((x+1, y+2), label, font=self.chapter, fill=(0, 0, 0, int(a*.6)))
            draw.text((x, y), label, font=self.chapter, fill=fill+(a,))
            if i == current:
                draw.rectangle([x, y+24, x+w, y+26], fill=GOLD+(a,))
            x += w+gap

    def cursor(self, draw, pos, alpha, pressed=False):
        if alpha <= 0 or pos is None:
            return
        x, y = pos
        k = 1.25
        arrow = [(0, 0), (0, 25), (6.5, 19), (11, 29), (15, 27.5), (10.5, 17.8), (19, 17.8)]
        pts = [(x+px*k, y+py*k) for px, py in arrow]
        draw.polygon([(px+2, py+3) for px, py in pts], fill=(0, 0, 0, int(90*alpha)))
        draw.polygon(pts, fill=(255, 255, 255, int(255*alpha)), outline=(10, 10, 10, int(255*alpha)))
        if pressed:
            draw.ellipse([x-5, y-5, x+5, y+5], outline=(255, 255, 255, int(200*alpha)), width=2)

    @staticmethod
    def ripple(draw, pos, age):
        if 0 <= age < 0.5:
            r = 8+age*70
            a = int(220*(1-age/0.5))
            x, y = pos
            draw.ellipse([x-r, y-r, x+r, y+r], outline=(255, 255, 255, a), width=3)


class Console:
    """A terminal window: typed commands and their output over time."""

    def __init__(self, lines, rect, title='PowerShell', size=24):
        self.lines, self.rect, self.title = lines, rect, title
        self.mono = font('consola.ttf', size)
        self.bold = font('consolab.ttf', size)
        self.head = font('segoeui.ttf', 17)
        self.lh = int(size*1.4)

    def draw(self, img, t, alpha):
        if alpha <= 0:
            return img
        x0, y0, w, h = self.rect
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w-1, h-1], radius=12, fill=(14, 16, 22, 248), outline=(70, 74, 84, 255))
        d.rounded_rectangle([0, 0, w-1, 40], radius=12, fill=(36, 38, 46, 255))
        d.rectangle([0, 28, w-1, 40], fill=(36, 38, 46, 255))
        d.text((20, 20), self.title, font=self.head, fill=(220, 220, 225), anchor='lm')
        y = 60
        for start, stop, kind, text in self.lines:
            if t < start:
                continue
            if kind == 'cmd':
                shown = text[:int(len(text)*span(t, start, stop))] if t < stop else text
                d.text((24, y), 'PS ~\\bfme2-map-studio>', font=self.mono, fill=(110, 200, 130))
                px = 24+self.mono.getlength('PS ~\\bfme2-map-studio> ')
                d.text((px, y), shown, font=self.bold, fill=(240, 240, 240))
                if t < stop+.6 and int(t*2.5) % 2 == 0:
                    cx = px+self.bold.getlength(shown)
                    d.rectangle([cx+2, y+3, cx+self.mono.getlength('M'), y+self.lh-6], fill=(220, 220, 220))
            else:
                d.text((24, y), text, font=self.mono, fill=(170, 176, 186))
            y += self.lh
        card.putalpha(card.getchannel('A').point(lambda v: int(v*alpha)))
        base = img.convert('RGBA')
        shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle([x0+10, y0+16, x0+w+10, y0+h+16], radius=16, fill=(0, 0, 0, int(130*alpha)))
        base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(14)))
        base.alpha_composite(card, (int(x0), int(y0)))
        return base.convert('RGB')


# --- the marking performance -------------------------------------------------------------
class Marking:
    """Cursor path, clicks, tools and marks, in screen space of the drawing cameras."""

    def __init__(self, stage, main_bar, mark_bar):
        self.stage = stage
        center = lambda boxes, target, top: next(((x0+x1)/2, top+(y0+y1)/2) for x0, y0, x1, y1, tg in boxes if tg == target)
        mark_btn = center(main_bar.boxes, ('toggle', 'marking'), 0)
        row = main_bar.height
        tool = lambda k: center(mark_bar.boxes, ('toggle', 'tool_'+k), row)
        copy = center(mark_bar.boxes, ('button', 'copy'), row)
        self.copy_btn = copy
        # The creek: the real 48-point freehand path, drawn by hand.
        self.creek = creek_points()
        s = T['creek']
        creek_px = [stage.screen(DRAW_CREEK, x, y, stage.populate) for x, y in self.creek]
        self.creek_span = (s+2.4, s+4.6)
        draw_t = np.linspace(*self.creek_span, len(creek_px))
        keys = [(s+1.0, (1250, 640)), (s+1.5, mark_btn), (s+1.75, mark_btn), (s+2.0, tool('freehand')),
                (s+2.15, tool('freehand')), (s+2.35, creek_px[0])]
        keys += [(float(tt), q) for tt, q in zip(draw_t, creek_px)]
        keys += [(s+4.8, creek_px[-1]), (s+5.0, copy), (s+5.25, copy), (s+5.6, (copy[0]+40, copy[1]+160))]
        clicks = [s+1.65, s+2.1, self.creek_span[0], s+5.15]
        # The paddock: a circle dragged out from its centre.
        p = T['paddock']
        (cx, cy), self.radius = paddock_mark()
        self.circle_c = (cx, cy)
        c_px = stage.screen(DRAW_PADDOCK, cx, cy, stage.creek)
        edge_px = stage.screen(DRAW_PADDOCK, cx+self.radius, cy, stage.creek)
        self.circle_span = (p+1.4, p+2.3)
        keys += [(p+.8, (1150, 560)), (p+1.0, tool('circle')), (p+1.15, tool('circle')), (p+1.35, c_px),
                 (p+1.4, c_px), (p+2.3, edge_px), (p+2.4, edge_px), (p+2.6, (edge_px[0]+60, edge_px[1]+120))]
        clicks += [p+1.1, p+1.4]
        # The pins on the hold's gateways.
        q = T['polish']
        self.pins = pin_points()
        pin_px = [stage.screen(DRAW_PINS, x, y, stage.paddock) for x, y in self.pins]
        self.pin_times = [q+1.0, q+1.65]
        keys += [(q+.5, (1300, 560)), (q+.65, tool('pin')), (q+.75, tool('pin')), (q+.95, pin_px[0]), (q+1.0, pin_px[0]),
                 (q+1.55, pin_px[1]), (q+1.65, pin_px[1]), (q+1.9, (pin_px[1][0]+80, pin_px[1][1]+90))]
        clicks += [q+.7]+self.pin_times
        self.keys, self.clicks = keys, clicks
        self.tools = [(s+2.1, 'freehand'), (s+4.8, None), (p+1.1, 'circle'), (p+2.5, None), (q+.7, 'pin'),
                      (q+1.9, None)]
        self.pressed = [(self.creek_span[0], self.creek_span[1]), self.circle_span]
        self.windows = [(s+1.0, s+5.6), (p+.8, p+2.6), (q+.5, q+1.9)]

    def cursor(self, t):
        if not any(a <= t <= b for a, b in self.windows):
            return None
        keys = self.keys
        for (t0, a), (t1, b) in zip(keys[:-1], keys[1:]):
            if t0 <= t <= t1:
                u = (t-t0)/(t1-t0) if t1 > t0 else 1.0
                if t1-t0 > 0.2:
                    u = ease(u)
                return (lerp(a[0], b[0], u), lerp(a[1], b[1], u))
        return None

    def tool(self, t):
        current = None
        for at, name in self.tools:
            if t >= at:
                current = name
        return current

    def marking(self, t):
        """Whether the viewer's Mark row is open."""
        return (T['creek']+1.65 <= t < T['reload_creek']+2.4 or T['paddock'] <= t < T['reload_paddock']+2.2
                or T['polish'] <= t < T['reload_polish']+1.0)

    def marks(self, t):
        """(marks, preview) at time t."""
        s, p, q = T['creek'], T['paddock'], T['polish']
        items, preview = [], None
        a, b = self.creek_span
        if a <= t < b:
            n = max(2, int(len(self.creek)*(t-a)/(b-a))+1)
            preview = dict(kind='freehand', points=[list(pt) for pt in self.creek[:n]])
        elif b <= t < T['reload_creek']+2.4:
            items.append(dict(id=1, kind='freehand', points=[list(pt) for pt in self.creek]))
        a, b = self.circle_span
        if a <= t < b:
            cur = self.cursor(t)
            edge = self.stage.ground(DRAW_PADDOCK, self.stage.creek, 1) if False else None
            r = self.radius*ease((t-a)/(b-a))
            preview = dict(kind='circle', points=[list(self.circle_c)], radius=max(r, 5.0))
        elif b <= t < T['reload_paddock']+2.2:
            items.append(dict(id=1, kind='circle', points=[list(self.circle_c)], radius=self.radius))
        for k, (at, pin) in enumerate(zip(self.pin_times, self.pins)):
            if at <= t < T['reload_polish']+1.0:
                items.append(dict(id=k+1, kind='pin', points=[list(pin)]))
        return items, preview

    def hint(self, t):
        tool = self.tool(t)
        return {None: 'pick a tool to draw; click a mark to select it',
                'pin': 'click the terrain to drop pins - Esc when done',
                'circle': 'drag from the centre outwards - Esc when done',
                'freehand': 'hold the left button and draw - Esc when done'}[tool]


# --- effects -------------------------------------------------------------------------------
def rewind_fx(img, k, t):
    """Tape-rewind look: shifted bands, split colour, scanlines, a little grain."""
    a = img.astype(np.float32)
    rng = np.random.default_rng(int(t*1000))
    for _ in range(int(3+5*k)):
        y0 = rng.integers(0, H-60); hgt = rng.integers(8, 60)
        a[y0:y0+hgt] = np.roll(a[y0:y0+hgt], int(rng.integers(-40, 40)*k), axis=1)
    shift = int(8*k)
    if shift:
        a[..., 0] = np.roll(a[..., 0], shift, axis=1)
        a[..., 2] = np.roll(a[..., 2], -shift, axis=1)
    grey = a.mean(axis=2, keepdims=True)
    a = a*(1-.35*k)+grey*.35*k
    a[::3] *= 1-.18*k
    a += rng.normal(0, 9*k, a.shape[:2])[..., None]
    return np.clip(a, 0, 255).astype(np.uint8)


def wipe(new, old, u):
    """New on the left of a moving edge, old on the right, with a bright line."""
    edge = int(u*W)
    out = old.copy()
    out[:, :edge] = new[:, :edge]
    return out, edge


def sweep(new, old, u, glow=(255, 196, 120)):
    """New light sweeping diagonally across old, its front glowing warm."""
    yy, xx = np.mgrid[0:H, 0:W]
    front = (xx+.45*yy)/(W+.45*H)
    pos = lerp(-.15, 1.15, u)
    mix = np.clip((pos-front)/.12, 0, 1)[..., None]
    rim = np.exp(-((front-pos)/.05)**2)[..., None]
    out = old.astype(np.float32)*(1-mix)+new.astype(np.float32)*mix
    out += np.array(glow, np.float32)*rim*.35
    return np.clip(out, 0, 255).astype(np.uint8)


# --- frames --------------------------------------------------------------------------------
class Show:
    def __init__(self, stage, layers, panel, bars, marking, facts):
        self.stage, self.layers, self.panel = stage, layers, panel
        self.main_bar, self.mark_bar = bars
        self.marking = marking
        self.facts = facts
        self.walk_ready = False
        new_lines = [line for line in facts['00-new'].get('output', [])]
        nc = T['new']
        self.console = Console([
            (nc+.8, nc+2.2, 'cmd', 'mw new "Brightwater Fold" --size 480x480'),
            (nc+2.4, 0, 'out', new_lines[0].replace('D:\\LAN\\bfme2-map-studio\\', '') if new_lines else ''),
            (nc+2.5, 0, 'out', 'Next: `mw dev brightwater-fold` builds it and opens the viewer.'),
            (nc+2.6, 0, 'out', ''),
            (nc+3.0, nc+3.9, 'cmd', 'mw dev brightwater-fold'),
            (nc+4.1, 0, 'out', 'Building Brightwater Fold...'),
            (nc+4.4, 0, 'out', 'Built Brightwater Fold in 2 s: local\\build\\brightwater-fold'),
            (nc+4.6, 0, 'out', 'Opening the viewer; watching maps\\brightwater_fold for changes.')],
            (W/2-560, 300, 1120, 420))
        walk = recorded('03-populate', 'walkable.txt')
        self.walk_console = Console([(56.9, 57.6, 'cmd', 'mw walkable brightwater-fold')]
                                    + [(57.8+.15*k, 0, 'out', line) for k, line in enumerate(walk[1:4])],
                                    (W-48-900, 118, 900, 230), size=19)
        f = T['finale']
        self.play_console = Console([(f+.6, f+1.5, 'cmd', 'mw play brightwater-fold'),
                                     (f+1.8, 0, 'out', 'Installed Brightwater Fold into the BFME2 maps folder.'),
                                     (f+2.1, 0, 'out', 'Starting The Battle for Middle-earth II...')],
                                    (W-48-820, 118, 820, 200), size=19)

    # The scene, with whatever trick is running at time t.
    def scene(self, t, c, marks):
        st = self.stage
        shot = lambda r: st.shot(r, c, t, marks)
        if t < T['rewind']:
            return shot(st.walls)[1]
        if t < T['new']:
            return self.rewind(t, c)
        if t < T['reload_shape']:
            return shot(st.new)[1]
        if t < T['reload_shape']+4.4:
            u = (t-T['reload_shape'])/2.8
            st.shape.rise(min(u, 1.0))
            st.shape.fill(span(t, T['reload_shape']+2.6, T['reload_shape']+4.2) if u >= 1 else 0.0)
            img = shot(st.shape)[1]
            st.shape.rise(1.0); st.shape.fill(1.0)
            return img
        if t < T['reload_paint']:
            return shot(st.shape)[1]
        if t < T['reload_paint']+3.4:
            return self.paint_spread(t, c, (t-T['reload_paint'])/3.2)
        if t < T['reload_populate']:
            return shot(st.paint)[1]
        if t < T['reload_populate']+6.6:
            return self.growth(t, c, t-T['reload_populate'])
        if t < T['reload_creek']:
            img = shot(st.populate)[1]
            a = fade(t, 57.0, 60.0, .5, .6)
            if a > 0:
                img = self.walkable(t, c, img, a)
            return img
        if t < T['reload_creek']+2.4:
            return self.wipe(t, c, st.creek, st.populate, marks, (t-T['reload_creek'])/2.4)
        if t < T['reload_paddock']:
            return shot(st.creek)[1]
        if t < T['reload_paddock']+2.2:
            return self.wipe(t, c, st.paddock, st.creek, marks, (t-T['reload_paddock'])/2.2)
        if t < T['reload_polish']:
            return shot(st.paddock)[1]
        if t < T['reload_polish']+2.6:
            new = shot(st.final)[1]
            old = shot(st.paddock)[1]
            return sweep(new, old, ease((t-T['reload_polish'])/2.6))
        if t < T['reload_walls']:
            return shot(st.final)[1]
        if t < T['reload_walls']+2.0:
            return self.wipe(t, c, st.walls, st.final, None, (t-T['reload_walls'])/2.0)
        return shot(st.walls)[1]

    def wipe(self, t, c, new_r, old_r, marks, u):
        new, _ = self.stage.shot(new_r, c, t)
        _, old = self.stage.shot(old_r, c, t, marks)
        img, edge = wipe(new, old, ease(u))
        img[:, max(0, edge-2):edge+2] = 255
        return img

    def paint_spread(self, t, c, u):
        """The textures spreading from the river outwards, a warm line at their front."""
        st = self.stage
        new, _ = st.shot(st.paint, c, t)
        old, _ = st.shot(st.shape, c, t)
        x, y = st.ground(c, st.paint)
        if not hasattr(self, '_paint_sd'):
            self._paint_sd = water_distance('02-paint')
            rng = np.random.default_rng(3)
            n = rng.normal(0, 1, self._paint_sd[0].shape).astype(np.float32)
            for _ in range(3):                    # a cheap blur: soft blotches about 100 units across
                n = (n+np.roll(n, 3, 0)+np.roll(n, -3, 0)+np.roll(n, 3, 1)+np.roll(n, -3, 1))/5
            self._paint_noise = n/n.std()
        sd, border = self._paint_sd
        iy = np.clip((y/10+border).astype(int), 0, sd.shape[0]-1)
        ix = np.clip((x/10+border).astype(int), 0, sd.shape[1]-1)
        front = np.maximum(sd[iy, ix], 0)+self._paint_noise[iy, ix]*90
        reach = lerp(-150, 2600, ease(u)**.8)
        mask = upsample(np.clip((reach-front)/110, 0, 1))[..., None]
        rim = upsample(np.exp(-((front-reach)/45)**2))[..., None]
        out = old.astype(np.float32)*(1-mask)+new.astype(np.float32)*mask+np.array(GOLD, np.float32)*rim*.16
        return np.clip(out, 0, 255).astype(np.uint8)

    def growth(self, t, c, s):
        """Objects growing at their own places, shadows fading in when done."""
        st = self.stage
        r = st.populate
        r.grow(s)
        r.visible['shadows'] = r.visible['decals'] = False
        img, _ = st.shot(r, c, t)
        r.visible['shadows'] = r.visible['decals'] = True
        r.grow(10.0)
        k = span(s, 5.6, 6.5)
        if k > 0:
            lit, _ = st.shot(r, c, t)
            img = (img.astype(np.float32)*(1-k)+lit.astype(np.float32)*k).astype(np.uint8)
        return img

    def walkable(self, t, c, img, a):
        r = self.stage.populate
        if not self.walk_ready:
            r.walkable_overlay()
            self.walk_ready = True
        r.visible['walkable'] = True
        over, _ = self.stage.shot(r, c, t)
        r.visible['walkable'] = False
        return (img.astype(np.float32)*(1-a)+over.astype(np.float32)*a).astype(np.uint8)

    def rewind(self, t, c):
        """Back through every step to the empty field, fast."""
        st = self.stage
        u = (t-T['rewind'])/(T['new']-T['rewind'])
        k = min(1.0, u*4, (1-u)*5+.2)
        if u < .12:
            img, _ = st.shot(st.walls, c, t)
        elif u < .24:
            img, _ = st.shot(st.paddock, c, t)
        elif u < .34:
            img, _ = st.shot(st.creek, c, t)
        elif u < .55:
            r = st.populate
            r.grow(lerp(4.0, 0.0, (u-.34)/.21))
            r.visible['shadows'] = r.visible['decals'] = False
            img, _ = st.shot(r, c, t)
            r.visible['shadows'] = r.visible['decals'] = True
            r.grow(10.0)
        elif u < .7:
            img = self.paint_spread(t, c, 1-(u-.55)/.15)
        else:
            v = 1-(u-.7)/.3
            st.shape.fill(max(0.0, v*3-2))
            st.shape.rise(min(1.0, v*1.4) if v < 1/1.4 or v*3-2 <= 0 else 1.0)
            img, _ = st.shot(st.shape, c, t)
            st.shape.rise(1.0); st.shape.fill(1.0)
        return rewind_fx(img, k, t)

    def frame(self, t):
        L, st = self.layers, self.stage
        c = camera_at(t)
        mk = self.marking
        marks = mk.marks(t)
        img = self.scene(t, c, marks)
        pic = Image.fromarray(img)
        # The title and end card sit over a darkened picture; so does the console.
        if t < T['new']+5.0:
            k = fade(t, -1, T['rewind']-.2, .01, .8) if t < T['rewind'] else fade(t, T['new']+.4, T['new']+5.4, .5, .8)*.9
            if k > 0:
                pic = Layers.darken(pic, L.vignette+.3, k)
        if t >= T['end']:
            pic = Layers.darken(pic, L.vignette+.3, fade(t, T['end'], DURATION+1, 1.0, .01))
        # The viewer's toolbar and mark row.
        ui = fade(t, T['new']+4.8, T['end']-.4, .6, .6)
        over = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        cur = mk.cursor(t)
        if ui > 0:
            status = f'focus {c["x"]:.0f}, {c["y"]:.0f}   distance {c["distance"]:.0f}'
            for name, stamp in (('reload_shape', '02:38:05'), ('reload_paint', '02:40:44'), ('reload_populate', '02:45:48'),
                                ('reload_creek', '02:47:31'), ('reload_paddock', '02:50:25'), ('reload_polish', '03:18:37'),
                                ('reload_walls', '08:44:31')):
                at = T[name]
                if at-1.4 <= t < at-.05:
                    status = 'map changed - reloading...'
                elif at-.05 <= t < at+3.0:
                    status = f'reloaded {stamp} (0.9 s)'
            if T['creek']+5.15 <= t < T['creek']+7.2:
                status = 'copied 1 mark for the agent'
            self.main_bar.hover = None
            self.mark_bar.hover = None
            if cur:
                for x0, y0, x1, y1, target in self.main_bar.boxes:
                    if x0 <= cur[0] < x1 and y0 <= cur[1] < y1:
                        self.main_bar.hover = target
            marking = mk.marking(t)
            top = self.main_bar._render(W, UI, dict(map='Brightwater Fold', lod='Medium', weather="Map's own",
                                                     sun="Weather's own", marking=marking, status=status, fps='60 fps'))
            if marking:
                if cur:
                    for x0, y0, x1, y1, target in self.mark_bar.boxes:
                        if x0 <= cur[0] < x1 and y0+self.main_bar.height <= cur[1] < y1+self.main_bar.height:
                            self.mark_bar.hover = target
                tool = mk.tool(t)
                count = len(marks[0])
                row = self.mark_bar._render(W, UI, dict({f'tool_{k}': tool == k for k in ('pin', 'circle', 'rect', 'freehand')},
                                                        hint=f'{mk.hint(t)}   |   {count} mark{"s" if count != 1 else ""}'))
                row.putalpha(row.getchannel('A').point(lambda v: int(v*ui)))
                over.alpha_composite(row, (0, self.main_bar.height))
            top.putalpha(top.getchannel('A').point(lambda v: int(v*ui)))
            over.alpha_composite(top, (0, 0))
        pic = Image.alpha_composite(pic.convert('RGBA'), over).convert('RGB')
        pic = self.console.draw(pic, t, fade(t, T['new']+.4, T['new']+5.4, .4, .5))
        pic = self.walk_console.draw(pic, t, fade(t, 56.7, 60.0, .35, .4))
        pic = self.play_console.draw(pic, t, fade(t, T['finale']+.4, T['end']-.3, .35, .5))
        pic = self.panel.draw(pic, t)
        pic = self.panel.pop(pic, t, L)
        # Captions over a soft bottom shade.
        captions = [(T['new']+5.4, T['shape']-.1, '01  NEW', 'mw new: a folder with map.py, a flat field and two starts'),
                    (T['reload_shape']+.3, T['paint']-.2, '02  SHAPE', 'Heights from code: downs, a river and an island knoll'),
                    (T['reload_paint']+.2, T['populate']-.2, '03  PAINT', "Seventeen of the game's own textures, blended as the game does"),
                    (T['reload_populate']+.3, 56.6, '04  POPULATE', '1,190 objects placed by code, each build checked for fairness'),
                    (57.2, 59.8, 'CHECK', 'mw walkable: every area reachable from both starts'),
                    (T['creek']+.6, T['creek']+5.0, '05  MARK', 'Draw on the map where you mean'),
                    (T['reload_creek']+.2, T['paddock']-.2, '05  CREEK', 'The agent reads the marks and writes them into the code'),
                    (T['paddock']+.6, T['paddock']+2.3, '06  MARK', 'Circle a place'),
                    (T['reload_paddock']+.2, T['polish']-.2, '06  PADDOCK', 'Not quite right? Say so, and it looks again'),
                    (T['polish']+.6, T['polish']+1.9, '07  MARK', 'Pin the last details'),
                    (T['reload_polish']+.3, T['walls']-.1, '07  POLISH', 'Torches at the gates, a trodden plaza, late-afternoon light'),
                    (T['reload_walls']+.2, T['finale']-.2, '07  POLISH', 'The walls on the level top, every joint closed'),
                    (T['finale']+.4, T['end']-.4, 'PLAY', 'mw play: straight into the game')]
        alpha = max((fade(t, a, b) for a, b, _, _ in captions), default=0)
        if alpha > 0:
            pic = Layers.darken(pic, L.bottom_shade, alpha)
        over = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        for a, b, kick, text in captions:
            L.caption_block(d, kick, text, fade(t, a, b))
        L.chapters(d, t, fade(t, T['new']+5.0, T['end']-.4, .6, .6))
        # Cursor and click ripples.
        for click in mk.clicks:
            pos = mk.cursor(click)
            if pos:
                Layers.ripple(d, pos, t-click)
        pressed = any(a <= t <= b for a, b in mk.pressed)
        L.cursor(d, cur, 1.0, pressed)
        # Title and end card.
        ta = fade(t, .8, T['rewind']-.3, .9, .6)
        if ta > 0:
            L.text_center(d, 390, 'BFME2 MAP STUDIO', L.title, ta, spacing=8)
            d.rectangle([W/2-60, 530, W/2+60, 533], fill=GOLD+(int(255*ta),))
            L.text_center(d, 558, 'One new map, from an empty field to the last detail', L.sub, ta)
        if T['rewind']+.2 <= t < T['new']:
            ra = fade(t, T['rewind']+.2, T['new']-.1, .2, .3)
            d.polygon([(122, 92), (92, 112), (122, 132)], fill=(255, 255, 255, int(235*ra)))
            d.polygon([(154, 92), (124, 112), (154, 132)], fill=(255, 255, 255, int(235*ra)))
            d.text((176, 112), 'Back to the beginning', font=L.kicker, fill=(255, 255, 255, int(235*ra)), anchor='lm')
        ea = fade(t, T['end']+.6, DURATION+1, .9, .01)
        if ea > 0:
            L.text_center(d, 300, 'Brightwater Fold', L.title_small, ea)
            L.text_center(d, 384, f'7 steps   ·   3 follow-ups   ·   {self.facts["07-walls"]["lines"]} lines of Python',
                          L.sub, ea, fill=(226, 220, 204))
            d.rectangle([W/2-60, 462, W/2+60, 465], fill=GOLD+(int(255*ea),))
            L.text_center(d, 498, 'BFME2 MAP STUDIO', L.title, ea, spacing=8)
            L.text_center(d, 640, 'Maps as code   ·   A live viewer   ·   Marks for agents', L.sub, ea, fill=(226, 220, 204))
        pic = Image.alpha_composite(pic.convert('RGBA'), over).convert('RGB')
        # Fade from and to black.
        k = min(1.0, t/1.0, (DURATION-t)/1.2)
        if k < 1:
            pic = Image.fromarray((np.asarray(pic, np.float32)*max(k, 0)).astype(np.uint8))
        return pic


def build_show():
    facts = json.loads((HOME/'facts.json').read_text(encoding='utf-8'))
    stage = Stage()
    main_bar = Toolbar(stage.ctx, [
        dict(kind='dropdown', id='map', label='Map'),
        dict(kind='button', id='build', label='Build'), dict(kind='button', id='play', label='Play'),
        dict(kind='gap'),
        dict(kind='dropdown', id='lod', label='Detail'),
        dict(kind='dropdown', id='weather', label='Weather'),
        dict(kind='dropdown', id='sun', label='Sun'), dict(kind='gap'),
        dict(kind='dropdown', id='view', title='View'), dict(kind='toggle', id='marking', label='Mark'),
        dict(kind='gap'),
        dict(kind='button', id='top', label='Top view'), dict(kind='button', id='reset', label='Reset view'),
        dict(kind='button', id='shot', label='Screenshot'),
        dict(kind='status', id='status'), dict(kind='dropdown', id='fps', align='right')])
    tools = [('pin', 'Pin'), ('circle', 'Circle'), ('rect', 'Rectangle'), ('freehand', 'Freehand')]
    mark_bar = Toolbar(stage.ctx, [dict(kind='toggle', id='tool_'+k, label=l) for k, l in tools] +
                       [dict(kind='gap'), dict(kind='button', id='delete', label='Delete'),
                        dict(kind='button', id='clear', label='Clear all'), dict(kind='gap'),
                        dict(kind='button', id='copy', label='Copy for agent'), dict(kind='status', id='hint')])
    main_bar._render(W, UI, dict(map='Brightwater Fold', lod='Medium', weather="Map's own", sun="Weather's own",
                                 marking=True, status='', fps='60 fps'))
    mark_bar._render(W, UI, dict(hint=''))
    marking = Marking(stage, main_bar, mark_bar)
    script = session(facts)
    return Show(stage, Layers(), Panel(script), (main_bar, mark_bar), marking, facts), script


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=HOME/'video')
    parser.add_argument('--stills', help='Comma-separated times: render these frames as PNGs only')
    args = parser.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    started = clock.time()
    show, script = build_show()
    print(f'set up in {clock.time()-started:.1f} s', flush=True)
    if args.stills:
        for s in args.stills.split(','):
            t = float(s)
            show.frame(t).save(out/f'still-{t:05.1f}.png')
            print('still', t, flush=True)
        return 0
    video = out/'showcase-video.mp4'
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
                             '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                             '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', str(video)],
                            stdin=subprocess.PIPE)
    count = int(DURATION*FPS)
    for i in range(count):
        proc.stdin.write(show.frame(i/FPS).tobytes())
        if i % 150 == 0:
            print(f'frame {i}/{count}  {clock.time()-started:.0f} s', flush=True)
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError('ffmpeg failed')
    typing = [(start, stop) for start, stop, _, _ in script['typing']]
    typing += [(a, b) for a, b, kind, _ in show.console.lines + show.walk_console.lines + show.play_console.lines
               if kind == 'cmd']
    reveals = [T[k] for k in ('reload_shape', 'reload_paint', 'reload_populate', 'reload_creek', 'reload_paddock',
                              'reload_polish', 'reload_walls')]
    wav = score(DURATION, out, clicks=show.marking.clicks, typing=typing, cuts=TIMELINE, reveals=reveals,
                rewind=(T['rewind'], T['new']))
    master = out/'Map-Studio-Showcase.mp4'
    encode(['-i', video, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
            '-shortest', master], out/'mux.log')
    report = dict(master=validate(master, expected_duration=DURATION, expected_frames=count))
    for name in ('mobile', 'under20mb'):
        target = out/f'Map-Studio-Showcase-{name}.mp4'
        if target.exists():
            target.unlink()
        export_profile(master, target, PROFILES, name)
        report[name] = validate(target, expected_duration=DURATION)
    for second in (3, 12, 20, 28, 38, 46, 52, 58, 63, 70, 73, 82, 88, 95, 102, 106, 110, 114, 118):
        encode(['-ss', str(second), '-i', master, '-frames:v', '1', out/f'frame-{second:03}.jpg'], out/'frames.log')
    report['seconds'] = round(clock.time()-started)
    (out/'showcase.json').write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
