"""A clean top toolbar for the interactive viewer, drawn into the GL window.

Items are laid out left to right in groups: dropdowns (a muted caption and
the current value, opening a menu whose entries can carry a check mark),
buttons and toggles (pressed while on), with a status text at the right. The
bar is drawn with PIL into a texture and only redrawn when its state changes;
clicks are hit-tested in framebuffer pixels.
"""

from PIL import Image, ImageDraw, ImageFont

BAR = (243, 243, 245)
LINE = (210, 211, 216)
TEXT = (32, 34, 40)
MUTED = (110, 114, 124)
HOVER = (226, 228, 234)
ON = (220, 232, 250)
ON_LINE = (120, 160, 225)
MENU = (255, 255, 255)

VS = """
#version 430
in vec2 in_pos;
out vec2 v_uv;
uniform vec4 rect;      // x0, y0, x1, y1 in NDC
void main() {
    v_uv = in_pos;
    gl_Position = vec4(mix(rect.xy, rect.zw, in_pos), 0.0, 1.0);
}
"""
FS = """
#version 430
uniform sampler2D tex;
in vec2 v_uv;
out vec4 frag;
void main() { frag = texture(tex, vec2(v_uv.x, 1.0 - v_uv.y)); }
"""


def _font(size, bold=False):
    for name in (('segoeuib.ttf' if bold else 'segoeui.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


class Toolbar:
    """items: list of dicts, in order:
      dict(kind='button', id, label)
      dict(kind='toggle', id, label)               state[id] -> bool
      dict(kind='dropdown', id, label[, title])    shows title, or state[id] as text;
                                                   align='right' puts it at the right edge
      dict(kind='gap') / dict(kind='status', id)   right-aligned text

    A dropdown click returns ('dropdown', id); the caller sets open_menu to
    (id, entries), entries being (value, text, checked) with checked None for
    no check column and value None for a separator. A menu click returns
    ('menu', id, value).
    """

    def __init__(self, ctx, items, top=0):
        """`top`: the row's offset from the top of the window in framebuffer
        pixels (a second row sits below the first), or a callable giving it."""
        import moderngl
        self.ctx, self.mgl, self.items = ctx, moderngl, items
        self.top = top
        self.program = ctx.program(vertex_shader=VS, fragment_shader=FS)
        quad = ctx.buffer(bytes(__import__('array').array('f', [0, 0, 1, 0, 0, 1, 1, 1])))
        self.vao = ctx.vertex_array(self.program, [(quad, '2f', 'in_pos')])
        self.texture = None
        self.menu_texture = None
        self.key = None
        self.hover = None
        self.open_menu = None          # (dropdown id, entries)
        self.boxes = []                # (x0, y0, x1, y1, target)
        self.menu_boxes = []
        self.height = 0
        self.menu_rect = None

    def offset(self):
        return self.top() if callable(self.top) else self.top

    # Layout and drawing ----------------------------------------------------
    def _render(self, width, scale, state):
        h = round(36*scale)
        pad, gap = round(8*scale), round(14*scale)
        font, small = _font(round(13*scale)), _font(round(11*scale))
        image = Image.new('RGBA', (width, h), BAR+(255,))
        d = ImageDraw.Draw(image)
        d.line([(0, h-1), (width, h-1)], fill=LINE)
        x = pad
        boxes = []
        bh = h-2*round(6*scale)
        y0 = (h-bh)//2

        def text_w(t, f=font):
            return d.textlength(t, font=f)

        def button(x, label, target, pressed=False, hovered=False, arrow=False):
            w = round(text_w(label)+(30 if arrow else 16)*scale)
            fill = ON if pressed else (HOVER if hovered else None)
            if fill or pressed:
                d.rounded_rectangle([x, y0, x+w, y0+bh], radius=round(4*scale), fill=fill,
                                    outline=ON_LINE if pressed else None)
            d.text((x+round(8*scale), y0+bh/2), label, font=font, fill=TEXT, anchor='lm')
            if arrow:
                ax, ay = x+w-round(10*scale), y0+bh/2
                s = round(3*scale)
                d.polygon([(ax-s, ay-s/2), (ax+s, ay-s/2), (ax, ay+s)], fill=MUTED)
            boxes.append((x, y0, x+w, y0+bh, target))
            return x+w

        status_text = None
        right = [item for item in self.items if item.get('align') == 'right']
        for item in self.items:
            kind = item['kind']
            if item.get('align') == 'right':
                continue
            if kind == 'gap':
                d.line([(x+gap//2, y0+3), (x+gap//2, y0+bh-3)], fill=LINE)
                x += gap
            elif kind == 'button':
                x = button(x, item['label'], ('button', item['id']), hovered=self.hover == ('button', item['id']))+round(2*scale)
            elif kind == 'toggle':
                on = bool(state.get(item['id']))
                x = button(x, item['label'], ('toggle', item['id']), pressed=on,
                           hovered=self.hover == ('toggle', item['id']))+round(2*scale)
            elif kind == 'dropdown':
                title = item.get('title')
                if item.get('label') and not title:
                    d.text((x, y0+bh/2), item['label'], font=small, fill=MUTED, anchor='lm')
                    x += round(text_w(item['label'], small)+6*scale)
                label = title or str(state.get(item['id'], ''))
                if len(label) > 30:
                    label = label[:29]+'…'
                x = button(x, label, ('dropdown', item['id']), pressed=self.open_menu is not None and self.open_menu[0] == item['id'],
                           hovered=self.hover == ('dropdown', item['id']), arrow=True)+round(4*scale)
            elif kind == 'status':
                status_text = str(state.get(item['id'], ''))
        # Right-aligned dropdowns from the right edge inwards, then the status
        # text to their left when there is room for it.
        edge = width-pad
        for item in reversed(right):
            label = str(state.get(item['id'], ''))
            w = round(text_w(label)+30*scale)
            target = ('dropdown', item['id'])
            button(edge-w, label, target, pressed=self.open_menu is not None and self.open_menu[0] == item['id'],
                   hovered=self.hover == target, arrow=True)
            edge -= w+round(6*scale)
        if status_text and edge-text_w(status_text, small) > x+gap:
            d.text((edge, y0+bh/2), status_text, font=small, fill=MUTED, anchor='rm')
        self.boxes, self.height = boxes, h
        return image

    def _render_menu(self, scale, menu_id, entries, anchor_x):
        font = _font(round(13*scale))
        row, sep = round(26*scale), round(9*scale)
        checks = any(e[2] is not None for e in entries)
        indent = round((30 if checks else 12)*scale)
        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        width = max(round(160*scale), round(max(measure.textlength(e[1], font=font) for e in entries)+indent+20*scale))
        heights = [sep if e[0] is None else row for e in entries]
        image = Image.new('RGBA', (width, sum(heights)+2), MENU+(255,))
        d = ImageDraw.Draw(image)
        d.rectangle([0, 0, width-1, image.height-1], outline=LINE)
        boxes = []
        y = 1
        for (value, text, checked), h in zip(entries, heights):
            target = ('menu', menu_id, value)
            if value is None:
                d.line([(8, y+h//2), (width-8, y+h//2)], fill=LINE)
            else:
                if self.hover == target:
                    d.rectangle([1, y, width-2, y+h-1], fill=HOVER)
                if checked:
                    cx, cy, s = round(15*scale), y+h/2, 4*scale
                    d.line([(cx-s, cy), (cx-s/3, cy+s*0.7), (cx+s, cy-s*0.8)], fill=ON_LINE, width=max(2, round(2*scale)))
                d.text((indent, y+h/2), text, font=font, fill=TEXT, anchor='lm')
            base = self.offset()+self.height
            boxes.append((anchor_x, base+y, anchor_x+width, base+y+h, target if value is not None else None))
            y += h
        self.menu_boxes = boxes
        self.menu_rect = (anchor_x, self.offset()+self.height, anchor_x+width, self.offset()+self.height+image.height)
        return image

    def _upload(self, image, old):
        if old is not None:
            old.release()
        texture = self.ctx.texture(image.size, 4, image.tobytes())
        texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        return texture

    def draw(self, size, scale, state):
        """Draw the bar (and an open menu) over the top of the framebuffer."""
        width, height = size
        key = (width, round(scale, 3), tuple(sorted((k, str(v)) for k, v in state.items())), self.hover,
               self.open_menu and (self.open_menu[0], tuple(self.open_menu[1])))
        if key != self.key:
            self.key = key
            self.texture = self._upload(self._render(width, scale, state), self.texture)
            if self.open_menu:
                box = next((b for b in self.boxes if b[4] == ('dropdown', self.open_menu[0])), None)
                image = self._render_menu(scale, *self.open_menu, box[0] if box else 0)
                if box and box[0]+image.width > width:
                    # Keep a menu inside the window: right-align it with its button.
                    image = self._render_menu(scale, *self.open_menu, max(0, box[2]-image.width))
                self.menu_texture = self._upload(image, self.menu_texture)
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        top = self.offset()
        self._blit(self.texture, (0, top, width, top+self.height), size)
        if self.open_menu and self.menu_texture is not None:
            self._blit(self.menu_texture, self.menu_rect, size)
        ctx.disable(self.mgl.BLEND)

    def _blit(self, texture, rect, size):
        width, height = size
        x0, y0, x1, y1 = rect
        to_ndc = lambda x, y: (2*x/width-1, 1-2*y/height)
        a, b = to_ndc(x0, y1), to_ndc(x1, y0)
        self.program['rect'].value = (a[0], a[1], b[0], b[1])
        texture.use(0)
        self.program['tex'].value = 0
        self.vao.render(self.mgl.TRIANGLE_STRIP)

    def draw_loading(self, size, scale, title, step, fraction):
        """Dim the frame and show a centred loading card with a progress bar."""
        width, height = size
        w, h = round(420*scale), round(108*scale)
        card = Image.new('RGBA', (w, h), MENU+(255,))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w-1, h-1], radius=round(8*scale), outline=LINE, fill=MENU)
        pad = round(18*scale)
        if len(title) > 44:
            title = title[:43]+'…'
        d.text((pad, round(26*scale)), title, font=_font(round(15*scale), bold=True), fill=TEXT, anchor='lm')
        d.text((pad, round(52*scale)), step, font=_font(round(12*scale)), fill=MUTED, anchor='lm')
        y0, y1 = round(74*scale), round(82*scale)
        d.rounded_rectangle([pad, y0, w-pad, y1], radius=round(4*scale), fill=HOVER)
        fill_x = pad+max(0.0, min(1.0, fraction))*(w-2*pad)
        if fill_x > pad+2:
            d.rounded_rectangle([pad, y0, fill_x, y1], radius=round(4*scale), fill=ON_LINE)
        d.text((w-pad, round(52*scale)), f'{round(100*max(0.0, min(1.0, fraction)))}%',
               font=_font(round(12*scale)), fill=MUTED, anchor='rm')
        self.card_texture = self._upload(card, getattr(self, 'card_texture', None))
        if getattr(self, 'dim_texture', None) is None:
            self.dim_texture = self._upload(Image.new('RGBA', (1, 1), (12, 14, 18, 150)), None)
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        self._blit(self.dim_texture, (0, self.height, width, height), size)
        x0, y0 = (width-w)//2, (height-h)//2
        self._blit(self.card_texture, (x0, y0, x0+w, y0+h), size)
        ctx.disable(self.mgl.BLEND)

    def draw_panel(self, size, scale, title, lines, top):
        """A card at the top right, `top` pixels down, with a bold title and
        text lines: (text, style) with style 'head', 'body' or 'muted'."""
        width, height = size
        key = (round(scale, 3), title, tuple(lines))
        if key != getattr(self, 'panel_key', None):
            self.panel_key = key
            pad, line = round(12*scale), round(18*scale)
            fonts = dict(head=_font(round(12*scale), bold=True), body=_font(round(12*scale)),
                         muted=_font(round(11*scale)))
            w = round(380*scale)
            h = pad*2 + round(22*scale) + line*len(lines)
            card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(card)
            d.rounded_rectangle([0, 0, w-1, h-1], radius=round(8*scale), outline=LINE, fill=MENU+(245,))
            d.text((pad, pad), title, font=_font(round(13*scale), bold=True), fill=TEXT)
            y = pad + round(22*scale)
            for text, style in lines:
                if d.textlength(text, font=fonts[style]) > w - 2*pad:
                    while text and d.textlength(text + '…', font=fonts[style]) > w - 2*pad:
                        text = text[:-1]
                    text += '…'
                d.text((pad, y), text, font=fonts[style], fill=MUTED if style == 'muted' else TEXT)
                y += line
            self.panel_texture = self._upload(card, getattr(self, 'panel_texture', None))
            self.panel_size = card.size
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        w, h = self.panel_size
        margin = round(10*scale)
        self._blit(self.panel_texture, (width-w-margin, top+margin, width-margin, top+margin+h), size)
        ctx.disable(self.mgl.BLEND)

    # Input -------------------------------------------------------------------
    def target_at(self, x, y):
        """Toolbar target at framebuffer pixel (x, y), 'bar' for empty bar
        space, 'menu' inside an open menu, or None outside both."""
        if self.open_menu and self.menu_rect:
            x0, y0, x1, y1 = self.menu_rect
            if x0 <= x < x1 and y0 <= y < y1:
                for bx0, by0, bx1, by1, target in self.menu_boxes:
                    if by0 <= y < by1:
                        return target or 'menu'
                return 'menu'
        top = self.offset()
        if top <= y < top+self.height:
            for x0, y0, x1, y1, target in self.boxes:
                if x0 <= x < x1 and y0 <= y-top < y1:
                    return target
            return 'bar'
        return None
