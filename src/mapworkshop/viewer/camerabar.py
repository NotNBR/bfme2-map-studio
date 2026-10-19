"""The camera bar: one row at the bottom left of the 3D view, and what it
opens above itself.

From the left: the camera mode (Edit, Photo), Views (the saved views, a list
with thumbnails) and Copy view; in Photo mode the lens (focal length,
aperture, focus distance, exposure) and the framing aids (Thirds, the frame's
aspect); then the camera readout. A lens field takes the wheel or a sideways
drag, and a click opens its presets.

Drawn with PIL into a texture like the toolbar and the marking palette
(viewer.toolbar, viewer.palette), and only redrawn when its state changes.
Clicks are hit-tested in framebuffer pixels: ('mode', 'edit' | 'photo'),
('menu', id) for a list, ('button', id), ('field', id), ('toggle', id), and
in an open list ('pick', menu, value), ('rename', name) and ('delete', name);
'camerabar' for the bar's own space and 'popover' for the list's.

The framing aids are drawn over the view by draw_frame(): darkened bands
outside the frame's aspect (frame_rect, which screenshots crop to), thirds
lines, and a focus mark at the centre while the lens blurs.
"""

import time

from PIL import Image, ImageDraw

from mapworkshop.render.photo import sharp_range
from mapworkshop.viewer.palette import icon
from mapworkshop.viewer.toolbar import FS, HOVER, LINE, MENU, MUTED, ON, ON_LINE, TEXT, VS, _font

# The frame's aspects: value, label, width / height (None: the whole window).
FRAMES = (('free', 'Free', None), ('16:9', '16:9', 16/9), ('21:9', '21:9', 21/9), ('3:2', '3:2', 1.5),
          ('4:3', '4:3', 4/3), ('1:1', '1:1', 1.0))
# The lens fields' presets.
FOCALS = (14, 18, 24, 28, 35, 50, 85, 135, 200, 400)
APERTURES = (None, 0.5, 0.7, 0.95, 1.2, 1.4, 2, 2.8, 4, 5.6, 8, 11, 16, 22)   # f/0.5: the limit of a lens in air
FOCUS_DISTANCES = (50, 100, 200, 500, 1000, 2000, 5000)
EXPOSURES = (-2, -1, -0.5, 0, 0.5, 1, 2)
# Photo mode's controls, shown above the bar (draw_help): key, what it does.
PHOTO_KEYS = (('Mouse', 'look'), ('Right drag', 'slide'),
              ('W A S D', 'fly'), ('Space / C', 'up / down'),
              ('Wheel', 'forward / back'), ('Q / E, R', 'roll, level'),
              ('Alt+wheel', 'focal length'), ('Shift+wheel', 'focus distance'),
              ('Middle click', 'focus on centre'), ('Shift / Ctrl', 'faster / slower'),
              ('Esc', 'free the mouse'), ('V', 'back to Edit'))


def frame_ratio(frame):
    return next((r for v, _, r in FRAMES if v == frame), None)


def frame_rect(size, ratio):
    """The frame of aspect `ratio` centred in a window `size`, (x0, y0, x1, y1)
    in pixels from the top left; the whole window for None."""
    w, h = size
    if not ratio:
        return 0, 0, w, h
    if w/h > ratio:
        fw = round(h*ratio)
        x0 = (w-fw)//2
        return x0, 0, x0+fw, h
    fh = round(w/ratio)
    y0 = (h-fh)//2
    return 0, y0, w, y0+fh


def aperture_text(aperture):
    return 'f/–' if not aperture else f'f/{aperture:g}'


def ev_text(ev):
    return f'EV {ev:+.1f}' if abs(ev) > 1e-6 else 'EV 0'


class CameraBar:
    def __init__(self, ctx):
        import moderngl
        self.ctx, self.mgl = ctx, moderngl
        self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        quad = ctx.buffer(bytes(__import__('array').array('f', [0, 0, 1, 0, 0, 1, 1, 1])))
        self.vao = ctx.vertex_array(self.program, [(quad, '2f', 'in_pos')])
        self.hover = None
        self.open = None                # (menu id, entries, anchor x in framebuffer pixels)
        self.texture = self.pop_texture = self.frame_texture = self.help_texture = None
        self.key = self.pop_key = self.frame_key = self.help_key = None
        self.boxes, self.pop_boxes = [], []
        self.rect = self.pop_rect = None
        self.thumbs = {}                # thumbnail path -> (mtime, image)

    # The bar ---------------------------------------------------------------
    @staticmethod
    def items(state):
        """(target, text, kind) left to right; kind: seg, menu, button, field,
        toggle, gap or text."""
        photo = state['mode'] == 'photo'
        out = [(('mode', 'edit'), 'Edit', 'seg'), (('mode', 'photo'), 'Photo', 'seg'), (None, '', 'gap'),
               (('menu', 'views'), 'Views', 'menu'), (('button', 'copy_view'), 'Copy view', 'button')]
        if photo:
            out += [(None, '', 'gap'),
                    (('field', 'focal'), f'{state["focal"]:.0f} mm', 'field'),
                    (('field', 'aperture'), aperture_text(state['aperture']), 'field'),
                    (('field', 'focus'), f'focus {state["focus"]:,.0f}', 'field'),
                    (('field', 'ev'), ev_text(state['ev']), 'field'),
                    (None, '', 'gap'),
                    (('toggle', 'thirds'), 'Thirds', 'toggle'),
                    (('menu', 'frame'), dict((v, l) for v, l, _ in FRAMES)[state['frame']], 'menu')]
        out += [(None, '', 'gap'), (None, state['readout'], 'text')]
        return out

    def _render(self, scale, state):
        font, bold = _font(round(12*scale)), _font(round(12*scale), True)
        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        text_w = lambda t, f=font: round(measure.textlength(t, font=f))
        pad, bh, gap, space = round(4*scale), round(30*scale), round(10*scale), round(2*scale)
        px, arrow = round(10*scale), round(12*scale)
        layout, x = [], pad
        for target, text, kind in self.items(state):
            if kind == 'gap':
                layout.append((x, x+gap, target, text, kind))
                x += gap
                continue
            f = bold if kind == 'field' else font
            w = text_w(text, f) + 2*px + (arrow if kind == 'menu' else 0) + (round(22*scale) if kind == 'button' else 0)
            if kind == 'text':
                w = text_w(text) + px
            layout.append((x, x+w, target, text, kind))
            x += w + space
        width, height = x + pad, bh + 2*pad
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rounded_rectangle([0, 0, width-1, height-1], radius=round(8*scale), fill=MENU+(245,), outline=LINE)
        boxes, y0, y1 = [], pad, pad+bh-1
        for x0, x1, target, text, kind in layout:
            if kind == 'gap':
                d.line([(x0+gap//2, y0+round(5*scale)), (x0+gap//2, y1-round(5*scale))], fill=LINE)
                continue
            pressed = (kind == 'seg' and target[1] == state['mode']) or \
                      (kind == 'toggle' and state.get(target[1])) or \
                      (kind == 'menu' and self.open and self.open[0] == target[1])
            box = [x0, y0, x1-1, y1]
            if pressed:
                d.rounded_rectangle(box, radius=round(6*scale), fill=ON, outline=ON_LINE)
            elif target is not None and self.hover == target:
                d.rounded_rectangle(box, radius=round(6*scale), fill=HOVER)
            tx = x0 + px
            if kind == 'button':
                size = round(16*scale)
                image.alpha_composite(icon('copy', size), (tx, y0+(bh-size)//2))
                tx += round(22*scale)
            colour = MUTED if kind == 'text' else TEXT
            d.text((tx, (y0+y1)/2), text, font=bold if kind == 'field' else font, fill=colour, anchor='lm')
            if kind == 'menu':
                ax, ay, s = x1-px-round(4*scale), (y0+y1)/2, round(3*scale)
                d.polygon([(ax-s, ay-s/2), (ax+s, ay-s/2), (ax, ay+s/2)], fill=MUTED)
            if target is not None:
                boxes.append((x0, y0, x1, y1+1, target))
        return image, boxes

    def draw(self, size, scale, state):
        """Draw the bar for `state` (mode, readout; in Photo mode focal,
        aperture, focus, ev, thirds and frame) and an open list above it."""
        key = (round(scale, 3), tuple(sorted((k, str(v)) for k, v in state.items())), self.hover,
               self.open[0] if self.open else None)
        if key != self.key:
            self.key = key
            image, boxes = self._render(scale, state)
            self.texture = self._upload(image, self.texture)
            self.size, self.local_boxes = image.size, boxes
        margin = round(10*scale)
        w, h = self.size
        x, y = margin, size[1]-margin-h
        self.rect = (x, y, x+w, y+h)
        self.boxes = [(x+x0, y+y0, x+x1, y+y1, t) for x0, y0, x1, y1, t in self.local_boxes]
        self._begin(size)
        self._blit(self.texture, self.rect, size)
        self.pop_rect, self.pop_boxes = None, []
        if self.open:
            self._draw_popover(size, scale)
        self.ctx.disable(self.mgl.BLEND)

    def anchor(self, target):
        """The left edge of a bar item, to open its list there."""
        return next((b[0] for b in self.boxes if b[4] == target), self.rect[0] if self.rect else 0)

    # The list above the bar --------------------------------------------------
    def toggle_list(self, menu, entries):
        """Open a list (or close it when it is open): entries are dicts with
        `target` (None for a heading), `text`, and optional `checked`, `hint`,
        `thumbnail` (a file) and `actions` (rename and delete for a view)."""
        if self.open and self.open[0] == menu:
            self.open = None
        else:
            self.open = (menu, entries, self.anchor(('menu', menu) if menu in ('views', 'frame') else ('field', menu)))
        self.pop_key = None

    def refresh_list(self, entries):
        if self.open:
            self.open = (self.open[0], entries, self.open[2])
            self.pop_key = None

    def _thumbnail(self, path, size):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cached = self.thumbs.get(path)
        if cached is None or cached[0] != mtime:
            try:
                image = Image.open(path).convert('RGBA')
            except OSError:
                return None
            cached = self.thumbs[path] = (mtime, image)
        return cached[1].resize(size, Image.LANCZOS)

    def _render_popover(self, scale, entries):
        font, small = _font(round(12*scale)), _font(round(11*scale))
        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        has_thumbs = any(e.get('thumbnail') is not None for e in entries)
        tw, th = (round(64*scale), round(36*scale)) if has_thumbs else (0, 0)
        row = max(round(26*scale), th + round(8*scale))
        head = round(22*scale)
        pad, px, act = round(4*scale), round(10*scale), round(22*scale)
        text_w = max([round(measure.textlength(e['text'], font=font)) for e in entries] + [round(120*scale)])
        hint_w = max([round(measure.textlength(e.get('hint', ''), font=small)) for e in entries] + [0])
        actions = any(e.get('actions') for e in entries)
        width = 2*pad + px + (tw + px if has_thumbs else 0) + text_w + px + hint_w + px + (2*act + px if actions else 0)
        heights = [head if e['target'] is None else row for e in entries]
        height = 2*pad + sum(heights)
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rounded_rectangle([0, 0, width-1, height-1], radius=round(8*scale), fill=MENU+(250,), outline=LINE)
        boxes, y = [], pad
        for entry, h in zip(entries, heights):
            target = entry['target']
            if target is None:
                d.text((pad+px, y+h/2), entry['text'], font=small, fill=MUTED, anchor='lm')
                y += h
                continue
            right = width-pad-(2*act + px if actions else 0)
            if self.hover == target:
                d.rounded_rectangle([pad, y, right, y+h-1], radius=round(5*scale), fill=HOVER)
            elif entry.get('checked'):
                d.rounded_rectangle([pad, y, right, y+h-1], radius=round(5*scale), fill=ON)
            x = pad + px
            if has_thumbs:
                if entry.get('thumbnail') is not None:
                    thumb = self._thumbnail(entry['thumbnail'], (tw, th))
                    ty = y + (h-th)//2
                    if thumb is not None:
                        image.alpha_composite(thumb, (x, ty))
                    d.rectangle([x, ty, x+tw-1, ty+th-1], outline=LINE)
                x += tw + px
            d.text((x, y+h/2), entry['text'], font=font, fill=TEXT, anchor='lm')
            if entry.get('hint'):
                d.text((right-px, y+h/2), entry['hint'], font=small, fill=MUTED, anchor='rm')
            boxes.append((pad, y, right, y+h, target))
            for i, (kind, glyph) in enumerate(entry.get('actions') or ()):
                ax0 = width-pad-(2-i)*act
                box = [ax0, y+(h-act)//2, ax0+act-2, y+(h+act)//2]
                action = (kind, entry['name'])
                if self.hover == action:
                    d.rounded_rectangle(box, radius=round(4*scale), fill=HOVER)
                d.text(((box[0]+box[2])/2, (box[1]+box[3])/2), glyph, font=font, fill=MUTED, anchor='mm')
                boxes.append((box[0], box[1], box[2], box[3], action))
            y += h
        return image, boxes

    def _draw_popover(self, size, scale):
        menu, entries, anchor = self.open
        key = (round(scale, 3), menu, repr(entries), self.hover)
        if key != self.pop_key:
            self.pop_key = key
            image, boxes = self._render_popover(scale, entries)
            self.pop_texture = self._upload(image, self.pop_texture)
            self.pop_size, self.pop_local = image.size, boxes
        w, h = self.pop_size
        x = min(anchor, size[0]-w-round(10*scale))
        y = self.rect[1]-round(6*scale)-h
        self.pop_rect = (x, y, x+w, y+h)
        self.pop_boxes = [(x+x0, y+y0, x+x1, y+y1, t) for x0, y0, x1, y1, t in self.pop_local]
        self._blit(self.pop_texture, self.pop_rect, size)

    # The controls above the bar ------------------------------------------------
    def _render_help(self, scale, keys, title):
        bold, font, small = _font(round(11*scale), True), _font(round(11*scale)), _font(round(11*scale))
        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        w = lambda t, f: round(measure.textlength(t, font=f))
        pad, gap, row = round(10*scale), round(8*scale), round(18*scale)
        pairs = [keys[i:i+2] for i in range(0, len(keys), 2)]
        columns = [(max(w(p[c][0], bold) for p in pairs if len(p) > c), max(w(p[c][1], font) for p in pairs if len(p) > c))
                   for c in range(2)]
        col_w = [k + gap + a for k, a in columns]
        width = 2*pad + col_w[0] + 2*pad + col_w[1]
        head = row + round(2*scale)
        height = 2*pad + head + row*len(pairs) - round(4*scale)
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rounded_rectangle([0, 0, width-1, height-1], radius=round(8*scale), fill=MENU+(235,), outline=LINE)
        d.text((pad, pad + row/2 - round(2*scale)), title, font=small, fill=MUTED, anchor='lm')
        for r, pair in enumerate(pairs):
            y = pad + head + r*row + row/2 - round(2*scale)
            x = pad
            for c, (key, action) in enumerate(pair):
                d.text((x, y), key, font=bold, fill=TEXT, anchor='lm')
                d.text((x + columns[c][0] + gap, y), action, font=font, fill=MUTED, anchor='lm')
                x += col_w[c] + 2*pad
        return image

    def draw_help(self, size, scale, keys=PHOTO_KEYS, title='Photo mode'):
        """A short list of `keys` (key, what it does) above the bar; nothing
        while a list is open there."""
        if self.rect is None or self.open:
            return
        key = (round(scale, 3), keys, title)
        if key != self.help_key:
            self.help_key = key
            image = self._render_help(scale, keys, title)
            self.help_texture = self._upload(image, self.help_texture)
            self.help_size = image.size
        w, h = self.help_size
        x, y = self.rect[0], self.rect[1] - round(6*scale) - h
        self._begin(size)
        self._blit(self.help_texture, (x, y, x+w, y+h), size)
        self.ctx.disable(self.mgl.BLEND)

    # The framing aids --------------------------------------------------------
    def draw_frame(self, size, ratio, thirds, reticle):
        """Bands outside the frame of aspect `ratio`, thirds lines in it and a
        focus mark at its centre."""
        if not ratio and not thirds and not reticle:
            return
        key = (size, ratio, thirds, reticle)
        if key != self.frame_key:
            self.frame_key = key
            w, h = size
            image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(image)
            x0, y0, x1, y1 = frame_rect(size, ratio)
            band = (0, 0, 0, 150)
            if y0 > 0:
                d.rectangle([0, 0, w, y0-1], fill=band)
                d.rectangle([0, y1, w, h], fill=band)
            if x0 > 0:
                d.rectangle([0, 0, x0-1, h], fill=band)
                d.rectangle([x1, 0, w, h], fill=band)
            line = (255, 255, 255, 90)
            if thirds:
                for k in (1, 2):
                    x = x0 + (x1-x0)*k//3
                    y = y0 + (y1-y0)*k//3
                    d.line([(x, y0), (x, y1)], fill=line, width=1)
                    d.line([(x0, y), (x1, y)], fill=line, width=1)
            if reticle:
                cx, cy, r = w//2, h//2, max(6, h//90)
                d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=(255, 255, 255, 170), width=1)
                d.point((cx, cy), fill=(255, 255, 255, 220))
            self.frame_texture = self._upload(image, self.frame_texture)
        self._begin(size)
        self._blit(self.frame_texture, (0, 0, *size), size)
        self.ctx.disable(self.mgl.BLEND)

    # Drawing and hit-testing ---------------------------------------------------
    def _begin(self, size):
        ctx = self.ctx
        ctx.viewport = (0, 0, *size)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)

    def _upload(self, image, old):
        if old is not None:
            old.release()
        texture = self.ctx.texture(image.size, 4, image.tobytes())
        texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        return texture

    def _blit(self, texture, rect, size):
        width, height = size
        x0, y0, x1, y1 = rect
        to_ndc = lambda x, y: (2*x/width-1, 1-2*y/height)
        a, b = to_ndc(x0, y1), to_ndc(x1, y0)
        self.program['rect'].value = (a[0], a[1], b[0], b[1])
        self.program['alpha'].value = 1.0
        texture.use(0)
        self.program['tex'].value = 0
        self.vao.render(self.mgl.TRIANGLE_STRIP)

    def target_at(self, x, y):
        """The item at framebuffer pixel (x, y), 'popover' or 'camerabar' for
        their own space, or None outside both."""
        for rect, boxes, space in ((self.pop_rect, self.pop_boxes, 'popover'), (self.rect, self.boxes, 'camerabar')):
            if rect is None:
                continue
            x0, y0, x1, y1 = rect
            if x0 <= x < x1 and y0 <= y < y1:
                # Actions sit on top of their row: the last box that holds the point.
                found = [t for bx0, by0, bx1, by1, t in boxes if bx0 <= x < bx1 and by0 <= y < by1]
                return found[-1] if found else space
        return None


def sharp_text(near, far):
    return f'sharp {near:,.0f} – ' + ('∞' if far == float('inf') else f'{far:,.0f}')


def readout(mode, camera, fly, aspect):
    """The camera bar's readout of the current camera in a window of `aspect`."""
    if mode == 'photo':
        e = fly.eye
        text = (f'x {e[0]:,.0f}  y {e[1]:,.0f}  z {e[2]:,.0f}   heading {fly.heading % 360:.0f}°   '
                f'tilt {fly.pitch:+.0f}°')
        if abs(fly.roll) >= 0.5:
            text += f'   roll {fly.roll:+.0f}°'
        text += f'   {fly.fov(aspect):.0f}° wide'
        if fly.aperture:
            text += '   ' + sharp_text(*sharp_range(fly.focus, fly.focal, fly.aperture, fly.frame_aspect(aspect)))
        return text
    c = camera.cur
    return (f'target {c["x"]:,.0f}, {c["y"]:,.0f}   distance {c["distance"]:,.0f}   '
            f'heading {c["heading"] % 360:.0f}°   tilt {c["elevation"]:.0f}°')


class Sampler:
    """A value worked out at most every `period` seconds (the readout)."""

    def __init__(self, period=0.1):
        self.period, self.value, self.next = period, None, 0.0

    def get(self, compute):
        now = time.perf_counter()
        if self.value is None or now >= self.next:
            self.value, self.next = compute(), now + self.period
        return self.value
