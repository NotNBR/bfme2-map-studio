"""Trailer for the map viewer: mark the map, hand it to Claude Code, see the edit.

    python -m misc.map_viewer_trailer.trailer [--stills 12,20,36] [--out DIR]

Every frame is drawn by the workshop's renderer (render.engine) at 1920x1080
with the viewer's own toolbar (render.toolbar) and mark overlay
(render.overlay); captions, the cursor and a simplified Claude Code session
are composited on top and the frames are piped to ffmpeg with the original
score (score.py). The marks are written to the output folder, never to the
user's own marks, and the "after" state is the map's objects edited in
memory: the marked bridge removed, a forest planted in the marked circle and
Osgiliath ruins raised in the freehand area on the central meadow. The map
file is untouched.
"""
import argparse
import json
import math
import random
import subprocess
import time as clock
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from mapworkshop.config import VIDEOS
from mapworkshop import project
import mapworkshop.viewer.marks as marklib
from mapworkshop.render.camera import parse_view
from mapworkshop.render.engine import MapRenderer
from mapworkshop.viewer.overlay import MarkOverlay
from mapworkshop.render.terrain import TerrainData
from mapworkshop.viewer.toolbar import Toolbar
from mapworkshop.video.encoding import encode, export_profile, validate

from .score import score

W, H, FPS = 1920, 1080, 30
DURATION = 82.0
MAP = project.find('greywater-marches').map_file
OUT = VIDEOS/'map-viewer-trailer'
PROFILES = Path(__file__).resolve().parents[2]/'src/mapworkshop/video/profiles.toml'
FONTS = Path('C:/Windows/Fonts')
UI = 1.3                                   # toolbar scale at 1080p
GOLD = (232, 196, 120)
CLAUDE = (217, 119, 87)                    # Claude Code's accent orange
# `terminal`: the Claude Code panel slides in; `edit`: the map reloads;
# `ruins`: the before/after wipe on the meadow; `follow`: the panel returns
# for a follow-up request; `ground`: the reload with rubble and worn ground.
TIMELINE = dict(title=0.0, viewer=6.0, mark=11.0, pan=28.4, terminal=34.6, edit=47.0, ruins=58.2, follow=62.0,
                ground=70.4, close=76.0)

HERO = dict(x=7100, y=5900, distance=2600, elevation=48, heading=0)
OPEN_A = dict(x=6750, y=4400, distance=9200, elevation=29, heading=18)
OPEN_B = dict(x=6800, y=4700, distance=7600, elevation=34, heading=34)
APPROACH = dict(x=6850, y=5400, distance=5400, elevation=40, heading=-14)
PUSH = dict(x=7110, y=5720, distance=2150, elevation=52, heading=6)
# The open meadow in the middle of the central half-island, framed left of
# the Claude Code panel.
MEADOW_AREA = (5250.0, 5080.0)
MEADOW = dict(x=5850, y=5140, distance=2600, elevation=48, heading=0)
MEADOW_AFTER = dict(x=5330, y=4960, distance=1750, elevation=40, heading=-10)
MEADOW_SIDE = dict(x=5730, y=4930, distance=1750, elevation=40, heading=-10)
MEADOW_CLOSE = dict(x=5290, y=5010, distance=1250, elevation=36, heading=-24)
MEADOW_CLOSE_B = dict(x=5290, y=5010, distance=1180, elevation=37, heading=-32)
CLOSE_A = dict(x=6750, y=4600, distance=8400, elevation=30, heading=52)
CLOSE_B = dict(x=6750, y=4600, distance=8000, elevation=32, heading=62)
RUINS = ['OsgiliathRuin01', 'OsgiliathRuin09', 'OsgiliathRuin13', 'OsgiliathRuin15', 'OsgiliathRuin11',
         'OsgiliathRuin10', 'OsgiliathRuin03', 'OsgiliathRuin04', 'OsgiliathRuin07', 'OsgiliathRuin16',
         'OsgiliathRuin17', 'OsgiliathRuin19', 'OsgiliathRuin20', 'OsgiliathRuin24', 'OsgiliathRuin02',
         'OsgiliathRuin05']
RUBBLE = ['OsgiliathRubble01', 'OsgiliathRubble02', 'OsgiliathRubble03', 'OsgiliathRubble04', 'OsgiliathPillar01',
          'OsgiliathPillar02', 'PileDebris01', 'PileDebris02', 'PileDebris03', 'OsgiliathRuin06', 'OsgiliathRuin12']
GROUND = ['OsgiliathDirt01', 'ConcOsgiliath02']    # trodden earth, broken paving


def font(name, size):
    return ImageFont.truetype(str(FONTS/name), size)


def ease(u):
    u = min(max(u, 0.0), 1.0)
    return u*u*(3 - 2*u)


def lerp(a, b, u):
    return a + (b - a)*u


def blend(a, b, u):
    return {k: lerp(a[k], b[k], u) for k in a}


def span(t, t0, t1):
    return ease((t - t0)/(t1 - t0)) if t1 > t0 else float(t >= t1)


def fade(t, t0, t1, inn=0.4, out=0.4):
    """0..1 visibility of something shown from t0 to t1."""
    if t < t0 or t > t1:
        return 0.0
    return min(1.0, (t - t0)/inn if inn else 1.0, (t1 - t)/out if out else 1.0)


def camera_at(t):
    T = TIMELINE
    if t < T['viewer']:
        return blend(OPEN_A, OPEN_B, (t - T['title'])/(T['viewer'] - T['title']))
    if t < T['pan']:
        return blend(APPROACH, HERO, span(t, T['viewer'], T['viewer'] + 4.6))
    if t < T['edit']:
        # Over to the meadow for the freehand mark, back to the bridge as
        # the Claude Code panel closes.
        return blend(HERO, MEADOW, span(t, T['pan'], T['pan'] + 2.2) - span(t, T['edit'] - 2.6, T['edit'] - 1.0))
    if t < T['edit'] + 7.6:
        return blend(HERO, PUSH, span(t, T['edit'] + 2.7, T['edit'] + 7.4))
    if t < T['follow']:
        return blend(PUSH, MEADOW_AFTER, span(t, T['edit'] + 7.8, T['ruins'] - 0.2))
    if t < T['ground'] - 1.8:
        # Aside for the Claude Code panel, then in close for the reload.
        return blend(MEADOW_AFTER, MEADOW_SIDE, span(t, T['follow'], T['follow'] + 1.4))
    if t < T['ground']:
        return blend(MEADOW_SIDE, MEADOW_CLOSE, span(t, T['ground'] - 1.8, T['ground'] - 0.3))
    if t < T['close']:
        return blend(MEADOW_CLOSE, MEADOW_CLOSE_B, (t - T['ground'])/(T['close'] - T['ground']))
    return blend(CLOSE_A, CLOSE_B, (t - T['close'])/(DURATION - T['close']))


def spec(c):
    return (f"target={c['x']:.2f},{c['y']:.2f} distance={c['distance']:.2f} "
            f"elevation={c['elevation']:.3f} heading={c['heading']:.3f}")


class Stage:
    """Renderers before and after the edit, a shared framebuffer and the overlay."""

    def __init__(self):
        shared = {}
        self.before = MapRenderer(MAP, shared=shared)
        self.ctx = self.before.ctx
        self.after = MapRenderer(MAP, ctx=self.ctx, shared=shared, objects=False)
        self.final = MapRenderer(MAP, ctx=self.ctx, shared=shared, objects=False)
        self.terrain = self.before.terrain
        color = self.ctx.renderbuffer((W, H), 4, samples=4)
        depth = self.ctx.depth_renderbuffer((W, H), samples=4)
        self.fbo = self.ctx.framebuffer([color], depth)
        self.resolve = self.ctx.framebuffer([self.ctx.renderbuffer((W, H), 4)])
        self.overlay = MarkOverlay(self.ctx)

    def cam(self, c):
        return parse_view(spec(c).split()).resolve(self.terrain, W/H)

    def _read(self):
        self.ctx.copy_framebuffer(self.resolve, self.fbo)
        return np.flipud(np.frombuffer(self.resolve.read(components=3), np.uint8).reshape(H, W, 3)).copy()

    def shot(self, renderer, c, t, marks=None):
        """(scene, scene with marks) for camera parameters c at time t."""
        cam = self.cam(c)
        renderer.draw(cam, (W, H), self.fbo, time=t)
        base = self._read()
        if not marks or not (marks[0] or marks[1]):
            return base, base
        self.fbo.use()
        self.overlay.draw(marks[0], marks[1], marks[2], cam, renderer.surface_at, (W, H), UI)
        return base, self._read()

    def pick(self, c, sx, sy):
        """Map point under a screen position (terrain ray march)."""
        cam = self.cam(c)
        inv = np.linalg.inv(cam['view_projection'])
        nx, ny = 2*sx/W - 1, 1 - 2*sy/H
        near = inv @ np.array([nx, ny, -1, 1.0]); near = near[:3]/near[3]
        far = inv @ np.array([nx, ny, 1, 1.0]); far = far[:3]/far[3]
        d = (far - near)/np.linalg.norm(far - near)
        ts = np.linspace(0, 40000, 4000)
        pts = near + np.outer(ts, d)
        below = np.nonzero(pts[:, 2] <= self.before.surface_at(pts[:, 0], pts[:, 1]))[0]
        return pts[below[0]][:2] if len(below) else None

    def screen(self, c, x, y):
        world = MarkOverlay.drape([[x, y]], self.before.surface_at)
        px, _ = MarkOverlay.project(world, self.cam(c)['view_projection'], (W, H))
        return tuple(px[0])


# --- the marking performance -------------------------------------------------------------
class Script:
    """Cursor path, clicks, tool changes and marks over time, all in screen space
    of the HERO camera."""

    def __init__(self, stage, main_bar, mark_bar):
        self.stage = stage
        bridge = next(o for o in stage.before.map.objects()
                      if o['template'] == 'GondorIthilienBridge2' and abs(o['x'] - 7040) < 5)
        self.bridge = bridge
        s = lambda x, y: stage.screen(HERO, x, y)
        p = lambda sx, sy: stage.pick(HERO, sx, sy)
        mark_btn = self.center(main_bar.boxes, ('toggle', 'marking'), 0)
        row = main_bar.height
        tool = lambda k: self.center(mark_bar.boxes, ('toggle', 'tool_' + k), row)
        self.pin_xy = (bridge['x'], bridge['y'])
        pin_px = s(*self.pin_xy)
        circle_px = (880, 790)
        self.circle_c = p(*circle_px)
        self.circle_r = 330.0
        edge_px = s(self.circle_c[0] + self.circle_r, self.circle_c[1])
        rect_a, rect_b = (1440, 470), (1780, 640)
        self.rect_a, self.rect_b = p(*rect_a), p(*rect_b)
        self.move_px = (95, 18)
        grab = (circle_px[0] - 40, circle_px[1] + 20)
        moved = p(grab[0] + self.move_px[0], grab[1] + self.move_px[1])
        start = p(*grab)
        self.move_xy = (moved[0] - start[0], moved[1] - start[1])
        # The freehand area on the meadow, drawn by hand after the pan: an
        # uneven loop that closes where it started.
        cx, cy = MEADOW_AREA
        rng = np.random.default_rng(7)
        wobble = np.convolve(rng.normal(0, 1, 70), np.ones(9)/9, mode='same')*np.sin(np.linspace(0, math.pi, 70))
        angles = np.linspace(math.pi*0.55, math.pi*0.55 - 2*math.pi, 70)
        self.loop_xy = [(cx + 360*math.cos(a)*(1 + .07*w) + 40*math.sin(2*a), cy + 255*math.sin(a)*(1 + .07*w))
                        for a, w in zip(angles, wobble)]
        loop = [stage.screen(MEADOW, x, y) for x, y in self.loop_xy]
        P = TIMELINE['pan']
        # (time, point) keys; the cursor eases between consecutive keys.
        self.keys = [(11.0, (1180, 660)), (12.3, mark_btn), (12.6, mark_btn),
                     (14.0, mark_btn), (15.1, pin_px), (15.5, pin_px),
                     (17.5, pin_px), (18.2, tool('circle')), (18.5, tool('circle')),
                     (19.3, circle_px), (19.45, circle_px), (20.9, edge_px), (21.2, edge_px),
                     (22.0, edge_px), (22.6, tool('rect')), (22.9, tool('rect')),
                     (23.5, rect_a), (23.6, rect_a), (24.9, rect_b), (25.2, rect_b),
                     (25.4, rect_b), (25.75, tool('select')), (26.0, tool('select')),
                     (26.45, grab), (26.6, grab),
                     (27.4, (grab[0] + self.move_px[0], grab[1] + self.move_px[1])),
                     (27.7, (grab[0] + self.move_px[0], grab[1] + self.move_px[1])),
                     (P + 1.2, tool('freehand')), (P + 2.1, tool('freehand')),
                     (P + 2.5, tool('freehand')), (P + 2.7, loop[0])]
        self.draw_span = (P + 2.8, P + 5.0)
        draw_t = np.linspace(*self.draw_span, len(loop))
        self.keys += [(float(tt), q) for tt, q in zip(draw_t, loop)]
        self.keys += [(P + 5.2, loop[-1]), (P + 6.2, (loop[-1][0] + 70, loop[-1][1] + 90))]
        self.clicks = [12.5, 15.3, 18.35, 19.45, 22.75, 23.6, 25.85, 26.55, P + 2.2, self.draw_span[0]]
        self.tools = [(0, 'pin'), (18.35, 'circle'), (22.75, 'rect'), (25.85, 'select'), (P + 2.2, 'freehand')]
        self.pressed = ((19.45, 21.0), (23.6, 25.0), (26.55, 27.5), (self.draw_span[0], self.draw_span[1] + 0.1))

    @staticmethod
    def center(boxes, target, top):
        x0, y0, x1, y1, _ = next(b for b in boxes if b[4] == target)
        return ((x0 + x1)/2, top + (y0 + y1)/2)

    def cursor(self, t):
        keys = self.keys
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, a), (t1, b) in zip(keys[:-1], keys[1:]):
            if t0 <= t <= t1:
                u = (t - t0)/(t1 - t0) if t1 > t0 else 1.0
                if t1 - t0 > 0.2:
                    u = ease(u)
                return (lerp(a[0], b[0], u), lerp(a[1], b[1], u))
        return keys[-1][1]

    def tool(self, t):
        return [k for s, k in self.tools if t >= s][-1]

    def marks(self, t):
        """(marks, preview, selected) at time t."""
        items, preview, selected = [], None, None
        if t >= 15.3:
            items.append(dict(id=1, kind='pin', points=[list(self.pin_xy)]))
        circle = dict(id=2, kind='circle', points=[list(self.circle_c)], radius=self.circle_r)
        if 19.45 <= t < 21.0:
            cx, cy = self.circle_c
            edge = self.stage.pick(HERO, *self.cursor(t))
            preview = dict(kind='circle', points=[[cx, cy]], radius=float(np.hypot(edge[0] - cx, edge[1] - cy)))
        elif t >= 21.0:
            u = span(t, 26.6, 27.4)
            circle['points'] = [[self.circle_c[0] + self.move_xy[0]*u, self.circle_c[1] + self.move_xy[1]*u]]
            items.append(circle)
        if 23.6 <= t < 25.0:
            b = self.stage.pick(HERO, *self.cursor(t))
            (x0, y0), (x1, y1) = self.rect_a, b
            preview = dict(kind='rect', points=[[min(x0, x1), min(y0, y1)], [max(x0, x1), max(y0, y1)]])
        elif t >= 25.0:
            (x0, y0), (x1, y1) = self.rect_a, self.rect_b
            items.append(dict(id=3, kind='rect', points=[[min(x0, x1), min(y0, y1)], [max(x0, x1), max(y0, y1)]]))
        a, b = self.draw_span
        if a <= t < b + 0.1:
            n = max(2, int(len(self.loop_xy)*(t - a)/(b - a)) + 1)
            preview = dict(kind='freehand', points=[list(q) for q in self.loop_xy[:n]])
        elif t >= b + 0.1:
            items.append(dict(id=4, kind='freehand', points=[list(q) for q in self.loop_xy]))
        if 26.55 <= t < 28.0:
            selected = 2
        return items, preview, selected

    def final_marks(self):
        return self.marks(TIMELINE['terminal'])[0]


# --- the edit ------------------------------------------------------------------------------
def edited_objects(stage, script):
    """The map's objects with the marked bridge removed, a forest in the circle
    and Osgiliath ruins in the freehand area, then the rubble the follow-up
    asks for. Returns (objects, rubble objects, trees, ruin positions)."""
    objects = [o for o in stage.before.map.objects() if o is not script.bridge and not (
        o['template'] == script.bridge['template'] and abs(o['x'] - script.bridge['x']) < 1
        and abs(o['y'] - script.bridge['y']) < 1)]
    circle = next(m for m in script.final_marks() if m['id'] == 2)
    (cx, cy), r = circle['points'][0], circle['radius']
    rng = random.Random(2026)
    templates = ['TreeEvergreen03', 'TreeEvergreen03b', 'TreeEvergreen01', 'TreeEvergreen02', 'Tree03a',
                 'TreeEvergreen03c', 'Tree01_L', 'TreeEvergreen01b']
    placed, index = [], max(o['index'] for o in objects) + 1
    for _ in range(4000):
        a, d = rng.uniform(0, 2*math.pi), r*math.sqrt(rng.random())
        x, y = cx + d*math.cos(a), cy + d*math.sin(a)
        if all(math.hypot(x - px, y - py) > 34 for px, py in placed):
            placed.append((x, y))
    for x, y in placed:
        objects.append(dict(index=index, template=rng.choice(templates), x=x, y=y, z=0.0,
                            angle=rng.uniform(0, 2*math.pi), flags=0, chunk=None,
                            properties=[('objectPrototypeScale', 2, round(rng.triangular(.95, 1.45, 1.2), 3))]))
        index += 1
    # Ruins: the larger pieces near the middle of the area, the smaller
    # fragments scattered round them, every one turned its own way.
    area = np.array(next(m for m in script.final_marks() if m['id'] == 4)['points'])
    mx, my = area.mean(axis=0)
    ruins = []
    for template in RUINS:
        for _ in range(400):
            reach = 0.35 if len(ruins) < 4 else 0.8
            x = mx + rng.uniform(-1, 1)*reach*(area[:, 0].max() - mx)
            y = my + rng.uniform(-1, 1)*reach*(area[:, 1].max() - my)
            if (marklib._point_in_polygon(np.array([x]), np.array([y]), area)[0]
                    and all(math.hypot(x - px, y - py) > 95 for px, py in ruins)):
                break
        else:
            continue
        ruins.append((x, y))
        objects.append(dict(index=index, template=template, x=x, y=y, z=0.0, angle=rng.uniform(0, 2*math.pi),
                            flags=0, chunk=None, properties=[]))
        index += 1
    # Rubble, fallen pillars and debris heaped round the standing pieces.
    rubble, extra = [], []
    for _ in range(600):
        if len(rubble) >= 26:
            break
        rx, ry = ruins[rng.randrange(len(ruins))]
        a, d = rng.uniform(0, 2*math.pi), rng.uniform(45, 120)
        x, y = rx + d*math.cos(a), ry + d*math.sin(a)
        if (all(math.hypot(x - px, y - py) > 50 for px, py in ruins + rubble)
                and marklib._point_in_polygon(np.array([x]), np.array([y]), area)[0]):
            rubble.append((x, y))
            extra.append(dict(index=index, template=rng.choice(RUBBLE), x=x, y=y, z=0.0,
                              angle=rng.uniform(0, 2*math.pi), flags=0, chunk=None, properties=[]))
            index += 1
    return objects, extra, len(placed), ruins


def ruin_ground(renderer, ruins, area):
    """Repaint the terrain under the ruins in the renderer's map: trodden
    Osgiliath dirt round every piece and broken paving round the larger ones,
    with the map's own corner blends. Only grass and dirt cells change."""
    from mapworkshop.mapkit.blank import set_materials
    m = renderer.map
    blend = m.blend(inspection=True)
    textures = blend['textures']
    tiles = blend['arrays']['tiles'].astype(np.int64)
    labels = np.zeros(tiles.shape, np.int64)
    for i, t in enumerate(textures):
        labels[(tiles >= t['tile_start']) & (tiles < t['tile_start'] + t['tile_count'])] = i
    palette = [t['name'] for t in textures]
    sizes = [t['cell_size'] for t in textures]
    for name in GROUND:
        palette.append(name)
        image = renderer.assets.image(renderer.assets.terrain_textures[name.lower()])
        sizes.append(max(1, min(image.shape[:2])//64))
    dirt, paving = len(textures), len(textures) + 1
    border = renderer.terrain.border
    rows, cols = np.indices(labels.shape)
    wx, wy = (cols - border)*10.0 + 5, (rows - border)*10.0 + 5
    rng = np.random.default_rng(11)

    def noise(radius):
        """Smooth noise with unit spread, features about `radius` cells wide."""
        a = np.array(Image.fromarray(rng.normal(128, 60, labels.shape).clip(0, 255).astype(np.uint8))
                     .filter(ImageFilter.GaussianBlur(radius)), float)
        return (a - a.mean())/a.std()
    n1 = 0.7*noise(4) + 0.3*noise(1.5)
    n2, n3 = noise(3), noise(2)
    near = np.full(labels.shape, 1e9)
    near_big = np.full(labels.shape, 1e9)
    for i, (x, y) in enumerate(ruins):
        d = np.hypot(wx - x, wy - y)
        near = np.minimum(near, d)
        if i < 5:
            near_big = np.minimum(near_big, d)
    soft = np.isin(labels, [palette.index(n) for n in ('GrassMediumType40', 'GrassMediumType44b',
                                                       'GrassMediumType46', 'GrassMediumType10c',
                                                       'IthilienDirt07', 'IthilienDirt11')])
    inside = marklib._point_in_polygon(wx, wy, np.asarray(area))
    # Overgrown: only scraps of earth at the stones' feet and a few slabs of
    # paving left showing through the grass.
    labels[soft & (near < 30 + 25*n1) & (n3 > 0.4)] = palette.index('IthilienDirt11')
    labels[soft & (near < 25) & (n3 > 1.0)] = dirt
    labels[soft & (near_big < 80) & (n2 > 1.3)] = paving
    set_materials(m, palette, labels, blend['arrays'].get('impassable'), cell_sizes=sizes, corner_blends=True)
    renderer.terrain = TerrainData(m)
    renderer._terrain_gpu()


# --- 2D layers -----------------------------------------------------------------------------
class Layers:
    def __init__(self, stage):
        self.title = font('georgiab.ttf', 104)
        self.title_small = font('georgiab.ttf', 64)
        self.sub = font('segoeuisl.ttf', 34)
        self.kicker = font('seguisb.ttf', 22)
        self.caption = font('segoeui.ttf', 38)
        self.mono = font('consola.ttf', 23)
        self.mono_b = font('consolab.ttf', 23)
        self.mono_small = font('consola.ttf', 19)
        self.ui = font('segoeui.ttf', round(13*UI))
        shade = np.zeros((H, W), np.float32)
        y = np.arange(H, dtype=np.float32)
        shade += np.clip((y - (H - 330))/330, 0, 1)[:, None]**1.6*0.72
        self.bottom_shade = shade
        vx = (np.arange(W) - W/2)/(W/2); vy = (y - H/2)/(H/2)
        self.vignette = np.clip(np.hypot(vx[None, :], vy[:, None]) - 0.55, 0, 1)**1.5*0.55

    @staticmethod
    def darken(img, mask, k=1.0):
        a = np.asarray(img, np.float32)
        a *= (1 - mask*k)[..., None]
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

    def text_center(self, draw, y, text, fnt, alpha, fill=(244, 238, 222), spacing=0):
        if spacing:
            width = sum(draw.textlength(ch, font=fnt) for ch in text) + spacing*(len(text) - 1)
            x = (W - width)/2
            for ch in text:
                draw.text((x + 2, y + 3), ch, font=fnt, fill=(0, 0, 0, int(140*alpha)))
                draw.text((x, y), ch, font=fnt, fill=fill + (int(255*alpha),))
                x += draw.textlength(ch, font=fnt) + spacing
        else:
            w = draw.textlength(text, font=fnt)
            draw.text(((W - w)/2 + 2, y + 3), text, font=fnt, fill=(0, 0, 0, int(140*alpha)))
            draw.text(((W - w)/2, y), text, font=fnt, fill=fill + (int(255*alpha),))

    def caption_block(self, draw, kicker, text, alpha):
        if alpha <= 0:
            return
        x, y = 92, H - 176
        draw.rectangle([x, y + 4, x + 46, y + 7], fill=GOLD + (int(255*alpha),))
        draw.text((x + 60, y - 9), kicker, font=self.kicker, fill=GOLD + (int(255*alpha),))
        draw.text((x + 2, y + 34), text, font=self.caption, fill=(0, 0, 0, int(150*alpha)))
        draw.text((x, y + 32), text, font=self.caption, fill=(246, 242, 232, int(255*alpha)))

    def cursor(self, draw, pos, alpha, pressed=False):
        if alpha <= 0:
            return
        x, y = pos
        k = 1.25
        arrow = [(0, 0), (0, 25), (6.5, 19), (11, 29), (15, 27.5), (10.5, 17.8), (19, 17.8)]
        pts = [(x + px*k, y + py*k) for px, py in arrow]
        shadow = [(px + 2, py + 3) for px, py in pts]
        draw.polygon(shadow, fill=(0, 0, 0, int(90*alpha)))
        draw.polygon(pts, fill=(255, 255, 255, int(255*alpha)), outline=(10, 10, 10, int(255*alpha)))
        if pressed:
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 255, 255, int(200*alpha)), width=2)

    @staticmethod
    def ripple(draw, pos, age):
        if 0 <= age < 0.5:
            r = 8 + age*70
            a = int(220*(1 - age/0.5))
            x, y = pos
            draw.ellipse([x - r, y - r, x + r, y + r], outline=(255, 255, 255, a), width=3)


def terminal_lines(stage, script, out):
    """The real `mw marks` output for the trailer's marks."""
    marklib.MARKS_DIR = out/'marks'
    marks = marklib.Marks(MAP)
    marks.clear()
    for m in script.final_marks():
        if m['kind'] == 'circle':
            marks.add('circle', m['points'], radius=m['radius'])
        else:
            marks.add(m['kind'], m['points'])
    result = marklib.describe(json.loads(marks.path.read_text(encoding='utf-8')), assets=stage.before.assets)
    return marklib.text(result).splitlines(), result


# --- the Claude Code session ---------------------------------------------------------------
REQUEST = 'Remove the bridge at pin 1, plant a forest in mark 2 and build Osgiliath ruins in mark 4.'
FOLLOW_UP = 'The ruins look too clean. Add rubble around them and only hints of worn ground, keep it overgrown.'


def claude_session(lines, result, bridge, trees, ruins, rubble):
    """The exchange in the Claude Code panel: (time, kind, text) entries,
    spinner spans and typed prompts (start, stop, submitted, text). The marks
    output is the real command output, cut short the way Claude Code shows it."""
    t0, t1 = TIMELINE['terminal'], TIMELINE['follow']
    marks = {m['id']: m for m in result['marks']}
    body = [line for line in lines if line.strip()][2:]
    shown = body[:4]
    say1 = (f"Pin 1 is {bridge['template']} at ({bridge['x']:.0f}, {bridge['y']:.0f}). Mark 2 is a circle of "
            f"radius {marks[2]['radius']:.0f} south of the river, and mark 4 outlines {marks[4]['area']:,} "
            "square units of the meadow on the central half-island. I'll script all three changes.")
    entries = [(t0 + 3.8, 'user', REQUEST), (t0 + 3.8, 'blank', ''),
               (t0 + 4.6, 'tool', ('Bash', 'mw marks'))]
    entries += [(t0 + 5.0 + 0.1*i, 'out', line.strip()) for i, line in enumerate(shown)]
    entries += [(t0 + 5.5, 'out', f'... +{len(body) - len(shown)} lines (ctrl+o to expand)'),
                (t0 + 5.5, 'blank', ''), (t0 + 6.0, 'say', say1), (t0 + 6.0, 'blank', ''),
                (t0 + 7.5, 'tool', ('Write', 'local/edits/greywater_marks.py')),
                (t0 + 7.8, 'out', 'Wrote 54 lines to local/edits/greywater_marks.py'), (t0 + 7.8, 'blank', ''),
                (t0 + 8.3, 'tool', ('Bash', 'python local/edits/greywater_marks.py'))]
    results = [f"removed {bridge['template']} at ({bridge['x']:.0f}, {bridge['y']:.0f})",
               f'planted {trees} trees in mark 2', f'placed {ruins} Osgiliath ruins in mark 4',
               'saved map mp bfmexbar greywater marches.map']
    entries += [(t0 + 8.7 + 0.15*i, 'out', line) for i, line in enumerate(results)]
    entries += [(t0 + 9.3, 'blank', ''),
                (t0 + 9.6, 'say', 'Done: the bridge is gone, mark 2 is a forest and the ruins stand in mark 4. '
                                  'The viewer reloads the map by itself.'), (t0 + 9.6, 'blank', '')]
    # The follow-up, after the first reveal.
    entries += [(t1 + 3.4, 'user', FOLLOW_UP), (t1 + 3.4, 'blank', ''),
                (t1 + 4.2, 'tool', ('Update', 'local/edits/greywater_marks.py')),
                (t1 + 4.5, 'out', 'Updated local/edits/greywater_marks.py with 38 additions'),
                (t1 + 4.5, 'blank', ''),
                (t1 + 5.0, 'tool', ('Bash', 'python local/edits/greywater_marks.py'))]
    results = [f'placed {rubble} pieces of rubble and fallen pillars in mark 4',
               'painted worn earth and a few paving slabs between them',
               'saved map mp bfmexbar greywater marches.map']
    entries += [(t1 + 5.4 + 0.15*i, 'out', line) for i, line in enumerate(results)]
    entries += [(t1 + 5.9, 'blank', ''),
                (t1 + 6.2, 'say', 'Done: rubble round the stones, and only scraps of earth and paving show '
                                  'through the grass.')]
    spinners = [(t0 + 3.9, t0 + 4.6, 'Reading the marks'), (t0 + 6.6, t0 + 7.5, 'Writing the edit'),
                (t0 + 8.4, t0 + 9.5, 'Editing the map'), (t1 + 3.5, t1 + 4.2, 'Reworking mark 4'),
                (t1 + 5.1, t1 + 6.1, 'Editing the map')]
    typing = [(t0 + 0.8, t0 + 3.6, t0 + 3.8, REQUEST), (t1 + 0.8, t1 + 3.2, t1 + 3.4, FOLLOW_UP)]
    return entries, spinners, typing


def mascot(d, x, y, cell):
    """Claude Code's pixel mascot, simplified."""
    rows = ['...XXXXXX...', '...X.XX.X...', '.XXXXXXXXXX.', '...XXXXXX...', '...X.XX.X...']
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == 'X':
                d.rectangle([x + i*cell, y + j*cell, x + (i + 1)*cell - 1, y + (j + 1)*cell - 1], fill=CLAUDE)


def wrap(text, width):
    rows, row = [], ''
    for word in text.split(' '):
        if row and len(row) + 1 + len(word) > width:
            rows.append(row)
            row = word
        else:
            row = f'{row} {word}' if row else word
    return rows + [row]


def draw_terminal(img, layers, t, session):
    """A simplified Claude Code session sliding in from the right."""
    T = TIMELINE
    entries, spinners, typing = session
    slide = max(span(t, start, start + 0.6) - span(t, end - 1.6, end - 1.1)
                for start, end in ((T['terminal'], T['edit']), (T['follow'], T['ground'])))
    if slide <= 0:
        return img
    pw, ph = 1010, 790
    x0, y0 = lerp(W + 10, W - 56 - pw, slide), 140
    mono, bold = layers.mono, layers.mono_b
    cw = mono.getlength('M')
    lh = 29
    bg = (12, 12, 12, 246)
    white, grey, dim = (236, 236, 236), (150, 150, 150), (110, 110, 110)
    panel = Image.new('RGBA', (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle([0, 0, pw - 1, ph - 1], radius=14, fill=bg, outline=(64, 64, 64, 255))
    pad = 28
    width = int((pw - 2*pad - 2*cw)/cw)
    # The prompt box at the bottom holds a request while it is typed.
    typed = ''
    for start, stop, sent, text in typing:
        if start - 0.8 <= t < sent:
            typed = text[:int(len(text)*span(t, start, stop))]
    box_rows = wrap(typed, width) if typed else ['']
    footer_y = ph - 38
    box_bottom = footer_y - 14
    box_top = box_bottom - 16 - lh*len(box_rows)
    # The conversation, scrolled so its newest line sits above the prompt.
    rows = [('head', ''), ('head+', ''), ('head+', ''), ('blank', '')]
    for start, kind, text in entries:
        if t < start:
            continue
        if kind == 'user':
            rows += [('user', ('> ' if i == 0 else '  ') + r) for i, r in enumerate(wrap(text, width))]
        elif kind == 'say':
            rows += [('say' if i == 0 else 'say+', r) for i, r in enumerate(wrap(text, width))]
        elif kind == 'out':
            first = rows[-1][0] not in ('out', 'out+')
            rows.append(('out' if first else 'out+', text if len(text) <= width - 3 else text[:width - 7] + '...'))
        else:
            rows.append((kind, text))
    spin = next((s for s in spinners if s[0] <= t < s[1]), None)
    top = 62
    bottom = box_top - 12 - (lh + 6 if spin else 0)
    shift = max(0, len(rows)*lh - (bottom - top))
    for i, (kind, text) in enumerate(rows):
        y = top + i*lh - shift
        if y < top:
            continue
        if kind == 'head':
            mascot(d, pad, y + 12, 8)
            d.text((pad + 120, y + 2), 'Claude Code', font=bold, fill=white)
            d.text((pad + 120, y + lh + 2), 'Opus 5.5', font=mono, fill=grey)
            d.text((pad + 120, y + 2*lh + 2), '~\\bfme2-map-workshop', font=mono, fill=grey)
        elif kind == 'user':
            d.rectangle([pad - 10, y - 1, pw - pad + 10, y + lh - 1], fill=(44, 44, 44))
            d.text((pad, y), text, font=mono, fill=white)
        elif kind == 'tool':
            name, arg = text
            d.ellipse([pad + 2, y + 9, pad + 12, y + 19], fill=(98, 200, 110))
            d.text((pad + 2*cw, y), name, font=bold, fill=white)
            d.text((pad + 2*cw + bold.getlength(name), y), f'({arg})', font=mono, fill=white)
        elif kind in ('out', 'out+'):
            if kind == 'out':
                d.line([pad + 2*cw + 4, y + 2, pad + 2*cw + 4, y + 14], fill=grey, width=2)
                d.line([pad + 2*cw + 4, y + 14, pad + 2*cw + 20, y + 14], fill=grey, width=2)
            d.text((pad + 5*cw, y), text, font=mono, fill=grey)
        elif kind in ('say', 'say+'):
            if kind == 'say':
                d.ellipse([pad + 2, y + 9, pad + 12, y + 19], fill=white)
            d.text((pad + 2*cw, y), text, font=mono, fill=white)
    if spin:
        y = box_top - 12 - lh
        k = t*6
        cx, cy, r = pad + 7, y + 14, 8
        for a in range(3):
            ang = math.pi*a/3 + k
            d.line([cx - r*math.cos(ang), cy - r*math.sin(ang), cx + r*math.cos(ang), cy + r*math.sin(ang)],
                   fill=CLAUDE, width=3)
        label = spin[2] + '.'*(1 + int(t*3) % 3)
        d.text((pad + 2*cw, y), label, font=mono, fill=CLAUDE)
        d.text((pad + 2*cw + mono.getlength(spin[2] + '...') + cw, y), '(esc to interrupt)', font=mono, fill=dim)
    # Title bar with a single tab.
    d.rounded_rectangle([0, 0, pw - 1, 44], radius=14, fill=(32, 32, 32, 255))
    d.rectangle([0, 30, pw - 1, 44], fill=(32, 32, 32, 255))
    d.rounded_rectangle([12, 8, 236, 44], radius=8, fill=bg[:3])
    d.rectangle([12, 30, 236, 44], fill=bg[:3])
    d.rounded_rectangle([26, 19, 39, 32], radius=3, fill=CLAUDE)
    d.text((50, 26), 'Claude Code', font=layers.kicker, fill=white, anchor='lm')
    # The prompt box and its footer.
    d.line([pad - 10, box_top, pw - pad + 10, box_top], fill=(96, 96, 96), width=2)
    d.line([pad - 10, box_bottom, pw - pad + 10, box_bottom], fill=(96, 96, 96), width=2)
    for i, row in enumerate(box_rows):
        y = box_top + 8 + i*lh
        if i == 0:
            d.text((pad, y), '>', font=bold, fill=white)
        d.text((pad + 2*cw, y), row, font=mono, fill=white)
    if not typed:
        d.text((pad + 2*cw, box_top + 8), 'Try "add a forest in mark 2"', font=mono, fill=dim)
    if int(t*2.5) % 2 == 0 and not any(a <= t < b for a, b, _ in spinners):
        cx = pad + 2*cw + (mono.getlength(box_rows[-1]) if typed else 0)
        d.rectangle([cx, box_top + 11, cx + cw - 2, box_top + 5 + lh], fill=(220, 220, 220))
    d.text((pad, footer_y), '? for shortcuts', font=layers.mono_small, fill=dim)
    d.text((pw - pad, footer_y), 'auto mode on', font=layers.mono_small, fill=CLAUDE, anchor='ra')
    base = img.convert('RGBA')
    shadow = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x0 + 10, y0 + 16, x0 + pw + 10, y0 + ph + 16], radius=18,
                                             fill=(0, 0, 0, 120))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(14)))
    base.alpha_composite(panel, (int(x0), y0))
    return base.convert('RGB')


def draw_loading(img, layers, t):
    T = TIMELINE
    at = T['edit'] if t < T['ruins'] else T['ground']
    a = fade(t, at - 1.1, at - 0.05, 0.15, 0.15)
    if a <= 0:
        return img
    base = img.convert('RGBA')
    dim = Image.new('RGBA', base.size, (12, 14, 18, int(130*a)))
    base = Image.alpha_composite(base, dim)
    w, h = round(420*UI), round(108*UI)
    card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=round(8*UI), fill=(255, 255, 255, int(255*a)),
                        outline=(210, 211, 216, int(255*a)))
    pad = round(18*UI)
    frac = span(t, at - 1.0, at - 0.15)
    steps = (['Objects: gbithbrdg2', 'Objects: ptree01_l', 'Objects: osgilruin01'] if at == T['edit'] else
             ['Terrain', 'Objects: osgilrubble01', 'Objects: piledebris02'])
    step = steps[min(2, int(frac*3))]
    d.text((pad, round(26*UI)), 'Greywater Marches', font=font('segoeuib.ttf', round(15*UI)),
           fill=(32, 34, 40, int(255*a)), anchor='lm')
    d.text((pad, round(52*UI)), step, font=font('segoeui.ttf', round(12*UI)), fill=(110, 114, 124, int(255*a)),
           anchor='lm')
    y0, y1 = round(74*UI), round(82*UI)
    d.rounded_rectangle([pad, y0, w - pad, y1], radius=round(4*UI), fill=(226, 228, 234, int(255*a)))
    d.rounded_rectangle([pad, y0, pad + max(8, frac*(w - 2*pad)), y1], radius=round(4*UI),
                        fill=(120, 160, 225, int(255*a)))
    base.alpha_composite(card, ((W - w)//2, (H - h)//2))
    return base.convert('RGB')


# --- frames --------------------------------------------------------------------------------
def wipe_at(t):
    """0..1 position of a before/after wipe running at time t, or None."""
    for start, length in ((TIMELINE['edit'], 2.5), (TIMELINE['ruins'], 2.2), (TIMELINE['ground'], 2.2)):
        if start <= t < start + length:
            return span(t, start, start + length)
    return None


def frame(t, stage, script, layers, bars, session):
    T = TIMELINE
    main_bar, mark_bar = bars
    c = camera_at(t)
    marks = script.marks(t)
    hide_marks = span(t, T['edit'] + 5.0, T['edit'] + 5.8)
    if t < T['edit']:
        base, marked = stage.shot(stage.before, c, t, marks)
        img = marked
    elif t < T['close']:
        current = stage.after if t < T['ground'] else stage.final
        base_a, marked_a = stage.shot(current, c, t, marks)
        after = (marked_a.astype(np.float32)*(1 - hide_marks) + base_a.astype(np.float32)*hide_marks)
        wipe = wipe_at(t)
        if wipe is not None:
            # Left of the edge the new state, right of it the old one.
            old = stage.after if t >= T['ground'] else stage.before
            base_b, marked_b = stage.shot(old, c, t, marks)
            edge = int(wipe*W)
            after[:, edge:] = (base_b if old is stage.after else marked_b)[:, edge:]
        img = after.astype(np.uint8)
    else:
        img, _ = stage.shot(stage.final, c, t)
        if t < T['close'] + 0.8:
            prev, _ = stage.shot(stage.final, camera_at(T['close'] - 0.01), t)
            u = span(t, T['close'], T['close'] + 0.8)
            img = (img.astype(np.float32)*u + prev.astype(np.float32)*(1 - u)).astype(np.uint8)
    pic = Image.fromarray(img)
    if wipe_at(t) is not None:
        d = ImageDraw.Draw(pic)
        edge = int(wipe_at(t)*W)
        d.rectangle([edge - 2, 0, edge + 2, H], fill=(255, 255, 255))
    # Title and end card sit over a darkened picture.
    if t < T['viewer'] + 0.6 or t >= T['close']:
        k = fade(t, -1, T['viewer'] + 0.6, 0.01, 0.8) if t < T['close'] else fade(t, T['close'], DURATION + 1, 0.8, 0.01)
        pic = Layers.darken(pic, layers.vignette + 0.28, k)
    # Viewer UI: toolbar, marking row, status.
    ui = fade(t, T['viewer'] + 0.3, T['close'] - 0.2, 0.6, 0.5)
    over = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    cur = script.cursor(t)
    if ui > 0:
        marking = t >= 12.5
        status = f'focus {c["x"]:.0f}, {c["y"]:.0f}   distance {c["distance"]:.0f}'
        for at, stamp in ((T['edit'], '21:14:03'), (T['ground'], '21:16:41')):
            if at - 1.4 <= t < at - 0.05:
                status = 'map changed - reloading...'
            elif at - 0.05 <= t < at + 3.0:
                status = f'reloaded {stamp} (0.9 s)'
        hover = None
        if T['mark'] <= t < T['terminal']:
            for x0, y0, x1, y1, target in main_bar.boxes:
                if x0 <= cur[0] < x1 and y0 <= cur[1] < y1:
                    hover = target
        main_bar.hover = hover
        top = main_bar._render(W, UI, dict(map='Greywater Marches', lod='Medium', weather="Map's own",
                                            sun="Weather's own", marking=marking, status=status))
        if marking:
            tool = script.tool(t)
            mark_bar.hover = None
            for x0, y0, x1, y1, target in mark_bar.boxes:
                if x0 <= cur[0] < x1 and y0 + main_bar.height <= cur[1] < y1 + main_bar.height:
                    mark_bar.hover = target
            count = len(script.marks(t)[0])
            hint = dict(pin='click the terrain to drop a pin', circle='drag from the centre outwards',
                        rect='drag from corner to corner', freehand='hold the left button and draw',
                        select='click a mark to select it, drag to move, Del to delete')[tool]
            row = mark_bar._render(W, UI, dict({f'tool_{k}': tool == k for k in
                                                ('pin', 'circle', 'rect', 'freehand', 'select')},
                                               hint=f'{hint}   |   {count} mark{"s" if count != 1 else ""}, '
                                                    'read with: mw marks'))
            slide = span(t, 12.5, 12.8)
            y = int(main_bar.height - row.height*(1 - slide))
            row.putalpha(row.getchannel('A').point(lambda v: int(v*ui)))
            over.alpha_composite(row, (0, max(0, y)))
        top.putalpha(top.getchannel('A').point(lambda v: int(v*ui)))
        over.alpha_composite(top, (0, 0))
    pic = pic.convert('RGBA')
    pic = Image.alpha_composite(pic, over).convert('RGB')
    pic = draw_terminal(pic, layers, t, session)
    pic = draw_loading(pic, layers, t)
    # Captions over a soft bottom shade.
    captions = [(6.7, 10.9, 'THE VIEWER', "Your map, live — the game's own assets and shaders"),
                (13.1, 17.4, 'MARK', 'Drop a pin on what you mean'),
                (17.5, 21.9, 'MARK', 'Drag a circle around a place'),
                (22.0, 25.4, 'MARK', 'Frame an area'),
                (25.5, 28.3, 'SELECT', 'Move, delete, clear'),
                (29.4, 34.4, 'MARK', 'Or draw it freehand'),
                (35.2, 45.2, 'HAND-OFF', 'Tell Claude Code what you want'),
                (T['edit'] + 2.6, T['edit'] + 7.6, 'THE EDIT', 'Bridge removed, forest planted, reloaded live'),
                (T['ruins'] + 0.6, T['follow'] - 0.1, 'THE EDIT', 'Osgiliath ruins raised on the meadow'),
                (T['follow'] + 0.7, T['ground'] - 1.7, 'FOLLOW-UP', 'Not quite there? Ask for more'),
                (T['ground'] + 0.8, T['close'] - 0.4, 'THE EDIT', 'Rubble and worn ground, still overgrown')]
    alpha = max((fade(t, a, b) for a, b, _, _ in captions), default=0)
    if alpha > 0:
        pic = Layers.darken(pic, layers.bottom_shade, alpha)
    over = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for a, b, kick, text in captions:
        layers.caption_block(d, kick, text, fade(t, a, b))
    # Cursor and click ripples.
    ca = fade(t, T['mark'], T['terminal'] + 0.4, 0.3, 0.4)
    for click in script.clicks:
        Layers.ripple(d, script.cursor(click), t - click)
    pressed = any(s <= t <= e for s, e in script.pressed)
    layers.cursor(d, cur, ca, pressed)
    # Title and end card.
    ta = fade(t, 1.0, T['viewer'] - 0.1, 0.9, 0.7)
    if ta > 0:
        layers.text_center(d, 395, 'MAP WORKSHOP', layers.title, ta, spacing=10)
        d.rectangle([W/2 - 60, 538, W/2 + 60, 541], fill=GOLD + (int(255*ta),))
        layers.text_center(d, 566, 'A live map viewer and editor for The Battle for Middle-earth II', layers.sub, ta)
    ea = fade(t, T['close'] + 0.6, DURATION + 1, 0.9, 0.01)
    if ea > 0:
        layers.text_center(d, 330, 'Point. Mark. Build.', layers.title_small, ea)
        d.rectangle([W/2 - 60, 432, W/2 + 60, 435], fill=GOLD + (int(255*ea),))
        layers.text_center(d, 470, 'MAP WORKSHOP', layers.title, ea, spacing=10)
        layers.text_center(d, 620, "Rendered like the game   ·   Live reload   ·   Marks for AI agents", layers.sub, ea,
                           fill=(226, 220, 204))
    pic = Image.alpha_composite(pic.convert('RGBA'), over).convert('RGB')
    # Fade from and to black.
    k = min(1.0, t/1.2, (DURATION - t)/1.2)
    if k < 1:
        pic = Image.fromarray((np.asarray(pic, np.float32)*max(k, 0)).astype(np.uint8))
    return pic


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--out', type=Path, default=OUT)
    parser.add_argument('--stills', help='Comma-separated times: render these frames as PNGs only')
    args = parser.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    started = clock.time()
    stage = Stage()
    main_items = [
        dict(kind='dropdown', id='map', label='Map'), dict(kind='gap'),
        dict(kind='dropdown', id='lod', label='Detail'), dict(kind='dropdown', id='weather', label='Weather'),
        dict(kind='dropdown', id='sun', label='Sun'), dict(kind='gap'),
        dict(kind='dropdown', id='view', title='View'), dict(kind='toggle', id='marking', label='Mark'),
        dict(kind='gap'),
        dict(kind='button', id='top', label='Top view'), dict(kind='button', id='reset', label='Reset view'),
        dict(kind='button', id='reload', label='Reload'), dict(kind='button', id='shot', label='Screenshot'),
        dict(kind='status', id='status')]
    main_bar = Toolbar(stage.ctx, main_items)
    tools = [('pin', 'Pin'), ('circle', 'Circle'), ('rect', 'Rectangle'), ('freehand', 'Freehand'), ('select', 'Select')]
    mark_bar = Toolbar(stage.ctx, [dict(kind='toggle', id='tool_' + k, label=l) for k, l in tools] +
                       [dict(kind='gap'), dict(kind='button', id='delete', label='Delete'),
                        dict(kind='button', id='clear', label='Clear all'), dict(kind='status', id='hint')])
    main_bar._render(W, UI, dict(map='Greywater Marches', lod='Medium', weather="Map's own", sun="Weather's own",
                                 marking=True, status=''))
    mark_bar._render(W, UI, dict(hint=''))
    script = Script(stage, main_bar, mark_bar)
    objects, extra, trees, spots = edited_objects(stage, script)
    ruins, rubble = len(spots), len(extra)
    stage.after.map.objects = lambda: iter(objects)
    stage.after.options['objects'] = True
    stage.after._objects_gpu()
    ruin_ground(stage.final, spots, next(m for m in script.final_marks() if m['id'] == 4)['points'])
    stage.final.map.objects = lambda: iter(objects + extra)
    stage.final.options['objects'] = True
    stage.final._objects_gpu()
    lines, result = terminal_lines(stage, script, out)
    session = claude_session(lines, result, script.bridge, trees, ruins, rubble)
    layers = Layers(stage)
    print(f'set up in {clock.time() - started:.1f} s: {trees} trees planted, {ruins} ruins and {rubble} rubble pieces placed')
    if args.stills:
        for s in args.stills.split(','):
            t = float(s)
            frame(t, stage, script, layers, (main_bar, mark_bar), session).save(out/f'still-{t:05.1f}.png')
            print('still', t)
        return 0
    video = out/'trailer-video.mp4'
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo',
                             '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                             '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', str(video)],
                            stdin=subprocess.PIPE)
    count = int(DURATION*FPS)
    for i in range(count):
        t = i/FPS
        proc.stdin.write(frame(t, stage, script, layers, (main_bar, mark_bar), session).tobytes())
        if i % 150 == 0:
            print(f'frame {i}/{count}  {clock.time() - started:.0f} s', flush=True)
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError('ffmpeg failed')
    typing = [(start, stop) for start, stop, _, _ in session[2]]
    wav = score(DURATION, out, clicks=script.clicks, typing=typing, cuts=TIMELINE,
                accents=[TIMELINE['ruins'], TIMELINE['ground']])
    master = out/'Map-Workshop-Trailer.mp4'
    encode(['-i', video, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
            '-shortest', master], out/'mux.log')
    report = dict(master=validate(master, expected_duration=DURATION, expected_frames=count))
    for name in ('mobile', 'under20mb'):
        target = out/f'Map-Workshop-Trailer-{name}.mp4'
        if target.exists():
            target.unlink()
        export_profile(master, target, PROFILES, name)
        report[name] = validate(target, expected_duration=DURATION)
    for second in (3, 16, 24, 32, 40, 50, 60, 66, 73, 79):
        encode(['-ss', str(second), '-i', master, '-frames:v', '1', out/f'frame-{second:02}.jpg'], out/'frames.log')
    report['marks'] = [dict(id=m['id'], kind=m['kind'], objects=[o['template'] for o in m['objects']])
                       for m in result['marks']]
    report['trees_planted'] = trees
    report['ruins_placed'] = ruins
    report['rubble_placed'] = rubble
    report['seconds'] = round(clock.time() - started)
    (out/'trailer.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
