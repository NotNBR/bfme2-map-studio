"""The marking palette: a column of icon buttons at the top left of the 3D
view. Navigate and the four mark tools, then Undo, Delete and Clear all,
then Copy for agent; hovering one shows its name beside it.

Drawn with PIL into a texture like the toolbar (viewer.toolbar) and only
redrawn when its state changes. Icons are drawn four times larger and
scaled down, for smooth edges. Clicks are hit-tested in framebuffer pixels:
('tool', key) for a tool (key None for Navigate), ('button', id) for the
others.
"""

from PIL import Image, ImageDraw

from mapworkshop.viewer.toolbar import FS, HOVER, LINE, MENU, ON, ON_LINE, TEXT, VS, _font

ITEMS = (('tool', None, 'Navigate and select', 'navigate'),
         None,
         ('tool', 'pin', 'Pin', 'pin'),
         ('tool', 'circle', 'Circle', 'circle'),
         ('tool', 'rect', 'Rectangle', 'rect'),
         ('tool', 'freehand', 'Freehand', 'freehand'),
         None,
         ('button', 'undo', 'Undo   Ctrl+Z', 'undo'),
         ('button', 'delete', 'Delete the selected mark   Del', 'delete'),
         ('button', 'clear', 'Clear all marks', 'clear'),
         None,
         ('button', 'copy', 'Copy for agent: the marks, their coordinates and objects', 'copy'))


def icon(name, size, color=TEXT):
    """An icon `size` pixels square, drawn on a 24-unit grid."""
    big = size*4
    image = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    u = big/24
    w = max(2, round(1.8*u))
    p = lambda *points: [(x*u, y*u) for x, y in points]
    line = lambda *points: d.line(p(*points), fill=color, width=w, joint='curve')
    box = lambda x0, y0, x1, y1: [x0*u, y0*u, x1*u, y1*u]
    if name == 'navigate':
        d.polygon(p((6, 3), (6, 19), (10, 15.5), (12.5, 21), (15, 20), (12.5, 14.5), (18, 14.5)), outline=color, width=w)
    elif name == 'pin':
        d.arc(box(6, 3, 18, 15), 145, 395, fill=color, width=w)
        line((7.1, 12.4), (12, 21), (16.9, 12.4))
        d.ellipse(box(10.2, 7.2, 13.8, 10.8), fill=color)
    elif name == 'circle':
        d.ellipse(box(4, 4, 20, 20), outline=color, width=w)
    elif name == 'rect':
        d.rectangle(box(4, 6, 20, 18), outline=color, width=w)
    elif name == 'freehand':
        line((3, 17), (5.5, 12), (8, 8.5), (10.5, 9), (11, 13), (12.5, 16), (15.5, 15), (18, 10.5), (21, 8))
    elif name == 'undo':
        line((8, 5), (3, 10), (8, 15))
        line((3, 10), (14, 10))
        d.arc(box(8, 10, 20, 22), -90, 90, fill=color, width=w)
        line((14, 22), (9, 22))
    elif name == 'delete':
        line((4, 7), (20, 7))
        line((9.5, 7), (9.5, 4), (14.5, 4), (14.5, 7))
        line((6, 7), (7, 20.5), (17, 20.5), (18, 7))
        line((10, 11), (10, 17))
        line((14, 11), (14, 17))
    elif name == 'clear':
        d.rounded_rectangle(box(4, 4, 20, 20), radius=2.5*u, outline=color, width=w)
        line((8.5, 8.5), (15.5, 15.5))
        line((15.5, 8.5), (8.5, 15.5))
    elif name == 'copy':
        d.rounded_rectangle(box(5, 5, 19, 21.5), radius=2*u, outline=color, width=w)
        d.rounded_rectangle(box(9, 2.5, 15, 7), radius=1.2*u, fill=MENU, outline=color, width=w)
        line((8.5, 12), (15.5, 12))
        line((8.5, 16), (13.5, 16))
    return image.resize((size, size), Image.LANCZOS)


class Palette:
    """`top`: the palette's offset from the top of the window in framebuffer
    pixels, or a callable giving it."""

    def __init__(self, ctx, top=0):
        import moderngl
        self.ctx, self.mgl, self.top = ctx, moderngl, top
        self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        quad = ctx.buffer(bytes(__import__('array').array('f', [0, 0, 1, 0, 0, 1, 1, 1])))
        self.vao = ctx.vertex_array(self.program, [(quad, '2f', 'in_pos')])
        self.texture = self.tip_texture = None
        self.key = self.tip_key = None
        self.hover = None
        self.boxes = []                # (x0, y0, x1, y1, target) in framebuffer pixels
        self.rect = None               # where the palette was drawn this frame

    def offset(self):
        return self.top() if callable(self.top) else self.top

    def _render(self, scale, tool):
        button, pad, gap, space = round(34*scale), round(4*scale), round(9*scale), round(2*scale)
        heights = [gap if item is None else button for item in ITEMS]
        width = button + 2*pad
        height = 2*pad + sum(heights) + space*(len(ITEMS)-1)
        image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rounded_rectangle([0, 0, width-1, height-1], radius=round(8*scale), fill=MENU+(245,), outline=LINE)
        size = round(18*scale)
        boxes, y = [], pad
        for item, h in zip(ITEMS, heights):
            if item is None:
                d.line([(pad+round(4*scale), y+h//2), (width-pad-round(4*scale), y+h//2)], fill=LINE)
            else:
                kind, key, _, name = item
                target = (kind, key)
                box = [pad, y, pad+button-1, y+h-1]
                if kind == 'tool' and key == tool:
                    d.rounded_rectangle(box, radius=round(6*scale), fill=ON, outline=ON_LINE)
                elif self.hover == target:
                    d.rounded_rectangle(box, radius=round(6*scale), fill=HOVER)
                glyph = icon(name, size)
                image.alpha_composite(glyph, (pad+(button-size)//2, y+(h-size)//2))
                boxes.append((pad, y, pad+button, y+h, target))
            y += h + space
        return image, boxes

    def _render_tip(self, scale, text):
        font = _font(round(12*scale))
        pad_x, h = round(8*scale), round(24*scale)
        w = round(ImageDraw.Draw(Image.new('RGB', (1, 1))).textlength(text, font=font)) + 2*pad_x
        image = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(image)
        d.rounded_rectangle([0, 0, w-1, h-1], radius=round(5*scale), fill=TEXT+(235,))
        d.text((pad_x, h/2), text, font=font, fill=(255, 255, 255), anchor='lm')
        return image

    def _upload(self, image, old):
        if old is not None:
            old.release()
        texture = self.ctx.texture(image.size, 4, image.tobytes())
        texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        return texture

    def draw(self, size, scale, tool):
        """Draw the palette with `tool` (a mark tool key, None for Navigate)
        pressed, and the hovered item's name beside it."""
        key = (round(scale, 3), tool, self.hover)
        if key != self.key:
            self.key = key
            image, boxes = self._render(scale, tool)
            self.texture = self._upload(image, self.texture)
            self.size, self.local_boxes = image.size, boxes
        margin = round(10*scale)
        x, y = margin, self.offset() + margin
        w, h = self.size
        self.rect = (x, y, x+w, y+h)
        self.boxes = [(x+x0, y+y0, x+x1, y+y1, target) for x0, y0, x1, y1, target in self.local_boxes]
        ctx = self.ctx
        ctx.viewport = (0, 0, *size)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        self._blit(self.texture, self.rect, size)
        label = next((item[2] for item in ITEMS if item and (item[0], item[1]) == self.hover), None)
        hovered = next((b for b in self.boxes if b[4] == self.hover), None)
        if label and hovered:
            if (label, round(scale, 3)) != self.tip_key:
                self.tip_key = (label, round(scale, 3))
                self.tip_texture = self._upload(self._render_tip(scale, label), self.tip_texture)
            tw, th = self.tip_texture.size
            tx, ty = self.rect[2] + round(6*scale), (hovered[1]+hovered[3])//2 - th//2
            self._blit(self.tip_texture, (tx, ty, tx+tw, ty+th), size)
        ctx.disable(self.mgl.BLEND)

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
        """The item at framebuffer pixel (x, y), 'palette' for the palette's
        own space, or None outside it."""
        if self.rect is None:
            return None
        x0, y0, x1, y1 = self.rect
        if not (x0 <= x < x1 and y0 <= y < y1):
            return None
        return next((t for bx0, by0, bx1, by1, t in self.boxes if bx0 <= x < bx1 and by0 <= y < by1), 'palette')
