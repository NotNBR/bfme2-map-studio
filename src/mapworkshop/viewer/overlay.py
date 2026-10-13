"""Screen-space overlay for map marks (render.marks) in the viewer.

Mark outlines are draped on the terrain in map coordinates, projected with
the camera every frame and drawn on top of the scene as thick lines, a
translucent fill for areas, discs for pins and a numbered tag per mark.
Red marks; the one under the cursor is lighter, the selected one is yellow
with square handles to resize it (circles and rectangles) and, for a
rectangle, a round handle on a stem to rotate it.
"""

import math

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.viewer import marks as marklib
from mapworkshop.viewer.toolbar import FS as BLIT_FS, VS as BLIT_VS, _font

VS = """
#version 430
uniform vec2 size;                  // framebuffer pixels
in vec2 in_pos;                     // pixels, origin top-left
in vec4 in_color;
out vec4 v_color;
void main() {
    v_color = in_color;
    gl_Position = vec4(in_pos.x / size.x * 2.0 - 1.0, 1.0 - in_pos.y / size.y * 2.0, 0.0, 1.0);
}
"""
FS = """
#version 430
in vec4 v_color;
out vec4 frag;
void main() { frag = v_color; }
"""

RED = (0.92, 0.12, 0.10)
HOVER = (1.0, 0.42, 0.30)
YELLOW = (1.0, 0.85, 0.15)
WHITE = (1.0, 1.0, 1.0)


class MarkOverlay:
    def __init__(self, ctx):
        import moderngl
        self.ctx, self.mgl = ctx, moderngl
        self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        self.buffer = ctx.buffer(reserve=6*4*4096, dynamic=True)
        self.vao = ctx.vertex_array(self.program, [(self.buffer, '2f 4f', 'in_pos', 'in_color')])
        self.blit = ctx.program(vertex_shader=BLIT_VS, fragment_shader=BLIT_FS)
        quad = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], 'f4').tobytes())
        self.blit_vao = ctx.vertex_array(self.blit, [(quad, '2f', 'in_pos')])
        self.labels = {}
        self.screen = {}                 # mark id -> (pixel outline, closed)
        self.tags = {}                   # mark id -> tag pixel rect
        self.handles = []                # (pixel, handle index or 'rotate') of the selected mark
        self.centre = None               # pixel centre of the selected mark

    # Geometry -------------------------------------------------------------
    @staticmethod
    def drape(points, surface, lift=3.0):
        pts = np.asarray(points, float).reshape(-1, 2)
        z = np.asarray(surface(pts[:, 0], pts[:, 1]), float) + lift
        return np.column_stack([pts, z])

    @staticmethod
    def project(world, view_projection, size):
        """Pixel positions (origin top-left) and a visibility mask."""
        h = np.column_stack([world, np.ones(len(world))]) @ np.asarray(view_projection, float).T
        ok = h[:, 3] > 1e-3
        w = np.where(ok, h[:, 3], 1.0)
        px = (h[:, 0]/w*0.5 + 0.5)*size[0]
        py = (1.0 - (h[:, 1]/w*0.5 + 0.5))*size[1]
        return np.column_stack([px, py]), ok

    def _outline_world(self, mark, surface):
        cached = mark.get('_world')
        if cached is None:
            pts, closed = marklib.outline(mark)
            cached = mark['_world'] = (self.drape(pts, surface), closed)
        return cached

    # Drawing --------------------------------------------------------------
    def draw(self, marks, preview, selected, camera, surface, size, scale=1.0, hovered=None):
        """`marks`: the mark dicts; `preview`: a mark being drawn, or None;
        `selected` and `hovered`: mark ids."""
        tris, self.screen, self.tags, self.handles = [], {}, {}, []
        width = 3.0*scale
        tags = []
        for mark in list(marks) + ([preview] if preview else []):
            if mark is preview:
                pts, closed = marklib.outline(mark)
                world = (self.drape(pts, surface), closed)
            else:
                world = self._outline_world(mark, surface)
            pix, ok = self.project(world[0], camera['view_projection'], size)
            color = YELLOW if mark.get('id') == selected else HOVER if mark.get('id') == hovered else RED
            if mark['kind'] == 'pin':
                if ok[0]:
                    self._disc(tris, pix[0], 9*scale, WHITE, 1.0)
                    self._disc(tris, pix[0], 6.5*scale, color, 1.0)
                    tags.append((mark, pix[0] + (9*scale, -20*scale), color))
                self.screen[mark.get('id')] = (pix[:1] if ok[0] else pix[:0], False)
                continue
            closed = world[1]
            if closed and ok.all() and len(pix) > 2:
                c = pix.mean(axis=0)
                for a, b in zip(pix, np.roll(pix, -1, axis=0)):
                    tris += [(c, color, 0.16), (a, color, 0.16), (b, color, 0.16)]
            self._polyline(tris, pix, ok, closed, width, color)
            if mark is not preview:
                self.screen[mark['id']] = (pix[ok], closed and ok.all())
                visible = pix[ok]
                if len(visible):
                    top = visible[np.argmin(visible[:, 1])]
                    tags.append((mark, top + (6*scale, -24*scale), color))
            if mark is not preview and mark['id'] == selected:
                self._handles(tris, mark, surface, camera, size, scale, color)
        if tris:
            data = np.array([(*p, *c, a) for p, c, a in tris], 'f4')
            if data.nbytes > self.buffer.size:
                self.buffer.orphan(data.nbytes*2)
            else:
                self.buffer.orphan()
            self.buffer.write(data.tobytes())
            ctx = self.ctx
            ctx.viewport = (0, 0, *size)
            ctx.disable(self.mgl.DEPTH_TEST)
            ctx.disable(self.mgl.CULL_FACE)
            ctx.enable(self.mgl.BLEND)
            ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
            self.program['size'].value = tuple(float(v) for v in size)
            self.vao.render(self.mgl.TRIANGLES, vertices=len(data))
            for mark, at, color in tags:
                if 'id' in mark:
                    self.tags[mark['id']] = self._tag(str(mark['id']), at, color, size, scale)
            ctx.disable(self.mgl.BLEND)

    def _handles(self, tris, mark, surface, camera, size, scale, color):
        """The selected mark's handles: squares to resize it; for a
        rectangle also a round one on a stem beyond the side that faced north
        before rotation, to rotate it."""
        spots = marklib.handles(mark)
        if not len(spots):
            return
        n = len(spots)
        extra = [marklib.center(mark)]
        if mark['kind'] == 'rect':
            extra.append(marklib.rotate_anchor(mark)[1])
        pix, ok = self.project(self.drape(np.vstack([spots, extra]), surface), camera['view_projection'], size)
        self.centre = pix[n] if ok[n] else None
        if mark['kind'] == 'rect' and ok[n:].all():
            side = pix[n + 1]
            d = side - pix[n]
            length = math.hypot(*d)
            knob = side + (d/length if length > 1e-6 else np.array([0.0, -1.0]))*26*scale
            self._polyline(tris, np.array([side, knob]), np.array([True, True]), False, 2*scale, color)
            self._disc(tris, knob, 7*scale, WHITE, 1.0)
            self._disc(tris, knob, 4.5*scale, color, 1.0)
            self.handles.append((knob, 'rotate'))
        for i in np.flatnonzero(ok[:n]):
            self._square(tris, pix[i], 6*scale, WHITE)
            self._square(tris, pix[i], 4*scale, color)
            self.handles.append((pix[i], int(i)))

    def _polyline(self, tris, pix, ok, closed, width, color):
        n = len(pix)
        pairs = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed and n > 2 else [])
        half = width/2
        for i, j in pairs:
            if not (ok[i] and ok[j]):
                continue
            a, b = pix[i], pix[j]
            d = b - a
            length = math.hypot(*d)
            if length < 1e-6:
                continue
            nrm = np.array([-d[1], d[0]])/length*half
            tris += [(a + nrm, color, 0.95), (a - nrm, color, 0.95), (b + nrm, color, 0.95),
                     (b + nrm, color, 0.95), (a - nrm, color, 0.95), (b - nrm, color, 0.95)]
            self._disc(tris, b, half, color, 0.95, segments=6)

    @staticmethod
    def _square(tris, center, half, color):
        (x, y), a = center, 1.0
        p = [np.array(v) for v in ((x-half, y-half), (x+half, y-half), (x+half, y+half), (x-half, y+half))]
        tris += [(p[0], color, a), (p[1], color, a), (p[2], color, a),
                 (p[0], color, a), (p[2], color, a), (p[3], color, a)]

    @staticmethod
    def _disc(tris, center, radius, color, alpha, segments=16):
        a = np.linspace(0, 2*math.pi, segments + 1)
        ring = np.column_stack([np.cos(a), np.sin(a)])*radius + center
        for p, q in zip(ring[:-1], ring[1:]):
            tris += [(center, color, alpha), (p, color, alpha), (q, color, alpha)]

    def _tag(self, text, at, color, size, scale):
        key = (text, color, round(scale, 2))
        texture = self.labels.get(key)
        if texture is None:
            font = _font(round(13*scale), bold=True)
            w = int(ImageDraw.Draw(Image.new('RGB', (1, 1))).textlength(text, font=font)) + round(12*scale)
            h = round(20*scale)
            image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(image)
            d.rounded_rectangle([0, 0, w - 1, h - 1], radius=round(5*scale),
                                fill=tuple(int(c*255) for c in color) + (235,), outline=(255, 255, 255, 235))
            d.text((w/2, h/2), text, font=font, fill=(40, 30, 0, 255) if color == YELLOW else (255, 255, 255, 255),
                   anchor='mm')
            texture = self.ctx.texture(image.size, 4, image.tobytes())
            self.labels[key] = texture
        w, h = texture.size
        x0, y0 = at
        to_ndc = lambda x, y: (2*x/size[0] - 1, 1 - 2*y/size[1])
        a, b = to_ndc(x0, y0 + h), to_ndc(x0 + w, y0)
        self.blit['rect'].value = (a[0], a[1], b[0], b[1])
        texture.use(0)
        self.blit['tex'].value = 0
        self.blit_vao.render(self.mgl.TRIANGLE_STRIP)
        return (x0, y0, x0 + w, y0 + h)

    # Picking --------------------------------------------------------------
    def handle_at(self, pos, scale=1.0):
        """The selected mark's handle at a framebuffer pixel: its index,
        'rotate', or None."""
        p = np.asarray(pos, float)
        near = [(float(np.hypot(*(pix - p))), key) for pix, key in self.handles]
        near = [h for h in near if h[0] <= 9.0*scale]
        return min(near, key=lambda h: h[0])[1] if near else None

    def handle_direction(self, key):
        """How a handle moves on screen: 'rotate', or 'ew', 'nesw', 'ns' or
        'nwse' for a resize handle, from the mark's centre outwards."""
        if key == 'rotate' or self.centre is None:
            return 'rotate' if key == 'rotate' else 'ew'
        dx, dy = dict((k, pix) for pix, k in self.handles)[key] - self.centre
        a = math.degrees(math.atan2(-dy, dx)) % 180
        return ('ew', 'nesw', 'ns', 'nwse')[int((a + 22.5)//45) % 4]

    def _picks(self, pos, scale):
        """(the mark whose tag, pin or outline is at a pixel, or None;
        [(screen area, id)] of the areas that contain it)."""
        p = np.asarray(pos, float)
        for mark_id, (x0, y0, x1, y1) in self.tags.items():
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                return mark_id, []
        best, best_d = None, 10.0*scale
        inside = []
        for mark_id, (pix, closed) in self.screen.items():
            if mark_id is None or not len(pix):
                continue
            if len(pix) == 1:
                d = float(np.hypot(*(pix[0] - p)))
            else:
                path = np.vstack([pix, pix[:1]]) if closed else pix
                d = float(marklib._distance_to_path(p[0], p[1], path))
                if closed and marklib._point_in_polygon(p[0], p[1], pix):
                    x, y = pix[:, 0], pix[:, 1]
                    inside.append((abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))), mark_id))
            if d < best_d:
                best, best_d = mark_id, d
        return best, inside

    def grab_at(self, pos, selected=None, scale=1.0):
        """The mark a drag from a framebuffer pixel would move: its tag, pin
        or outline is there, or it is the selected area and contains it."""
        best, inside = self._picks(pos, scale)
        if best is None and any(mark_id == selected for _, mark_id in inside):
            best = selected
        return best

    def mark_at(self, pos, scale=1.0):
        """The id of the mark under a framebuffer pixel position, or None:
        tags, pins and outlines within a few pixels, then the smallest area
        that contains the position."""
        best, inside = self._picks(pos, scale)
        if best is None and inside:
            best = min(inside)[1]
        return best
