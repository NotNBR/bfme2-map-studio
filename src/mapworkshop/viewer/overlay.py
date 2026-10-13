"""Screen-space overlay for map marks (render.marks) in the viewer.

Mark outlines are draped on the terrain in map coordinates, projected with
the camera every frame and drawn on top of the scene as thick lines, a
translucent fill for areas, discs for pins and a numbered tag per mark.
Red marks; the selected one is yellow.
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
    def draw(self, marks, preview, selected, camera, surface, size, scale=1.0):
        """`marks`: the mark dicts; `preview`: a mark being drawn, or None."""
        tris, self.screen = [], {}
        width = 3.0*scale
        tags = []
        for mark in list(marks) + ([preview] if preview else []):
            if mark is preview:
                pts, closed = marklib.outline(mark)
                world = (self.drape(pts, surface), closed)
            else:
                world = self._outline_world(mark, surface)
            pix, ok = self.project(world[0], camera['view_projection'], size)
            color = YELLOW if mark.get('id') == selected else RED
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
                    self._tag(str(mark['id']), at, color, size, scale)
            ctx.disable(self.mgl.BLEND)

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
            d.text((w/2, h/2), text, font=font, fill=(255, 255, 255, 255) if color == RED else (40, 30, 0, 255),
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

    # Picking --------------------------------------------------------------
    def mark_at(self, pos, scale=1.0):
        """The id of the mark under a framebuffer pixel position, or None:
        pins and outlines within a few pixels, then the smallest area that
        contains the position."""
        best, best_d = None, 10.0*scale
        inside = []
        p = np.asarray(pos, float)
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
        if best is None and inside:
            best = min(inside)[1]
        return best
