"""A clean top toolbar for the interactive viewer, drawn into the GL window.

Items are laid out left to right in groups: dropdowns (a muted caption and
the current value, opening a menu whose entries can carry a check mark),
buttons and toggles (pressed while on), with a status text at the right. The
bar is drawn with PIL into a texture and only redrawn when its state changes;
clicks are hit-tested in framebuffer pixels. An open menu is drawn by
draw_menu(), after everything else, and scrolls when it is taller than the
window.
"""

import time

from PIL import Image, ImageChops, ImageDraw, ImageFont
from functools import lru_cache

BAR = (243, 243, 245)
LINE = (210, 211, 216)
TEXT = (32, 34, 40)
MUTED = (110, 114, 124)
HOVER = (226, 228, 234)
ON = (220, 232, 250)
ON_LINE = (120, 160, 225)
MENU = (255, 255, 255)
GOOD = (46, 150, 88)
BAD = (196, 64, 60)

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
uniform float alpha;
in vec2 v_uv;
out vec4 frag;
void main() {
    frag = texture(tex, vec2(v_uv.x, 1.0 - v_uv.y));
    frag.a *= alpha;
}
"""


@lru_cache(maxsize=32)
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
    ('menu', id, value); a click on the arrow strip of a scrolling menu
    returns ('menu_scroll', id, -1 or 1), for scroll_menu().
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
        self.menu_key = None
        self.menu_for = None           # the menu menu_scroll belongs to
        self.menu_scroll = None        # pixels; None scrolls to the checked entry
        self.menu_row = 1
        self.panel_rect = None         # the panel drawn this frame, which takes clicks

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

        status_text = next((str(state.get(item['id'], '')) for item in self.items
                            if item['kind'] == 'status'), '')
        right = [item for item in self.items if item.get('align') == 'right']
        controls = tuple((item.get('id'), str(state.get(item.get('id'), '')))
                         for item in self.items if item['kind'] != 'status' and item not in right)
        base_key = (width, scale, controls, self._bar_hover(), self.open_menu and self.open_menu[0])
        cached = getattr(self, '_base_bar', None)
        if cached and cached[0] == base_key:
            image, boxes, x = cached[1].copy(), list(cached[2]), cached[3]
            d = ImageDraw.Draw(image)
        else:
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
            self._base_bar = (base_key, image.copy(), list(boxes), x)
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
        room = edge-(x+gap)
        if status_text and text_w(status_text, small) > room:
            # Shorten a status that does not fit rather than dropping it.
            lo, hi = 0, len(status_text)
            while lo < hi:
                mid = (lo+hi+1)//2
                if text_w(status_text[:mid].rstrip()+'…', small) <= room:
                    lo = mid
                else:
                    hi = mid-1
            status_text = status_text[:lo].rstrip()+'…' if lo >= 8 else ''
        if status_text:
            d.text((edge, y0+bh/2), status_text, font=small, fill=MUTED, anchor='rm')
        self.boxes, self.height = boxes, h
        return image

    def _render_menu(self, scale, menu_id, entries, room):
        """The open menu, at most `room` pixels tall: (image, boxes with x
        from the menu's left edge). A taller menu shows a window of its
        entries at menu_scroll, with arrow strips where more entries are."""
        font = _font(round(13*scale))
        row, sep = round(26*scale), round(9*scale)
        self.menu_row = row
        checks = any(e[2] is not None for e in entries)
        indent = round((30 if checks else 12)*scale)
        measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        width = max(round(160*scale), round(max(measure.textlength(e[1], font=font) for e in entries)+indent+20*scale))
        heights = [sep if e[0] is None else row for e in entries]
        total = sum(heights)+2
        visible = min(total, max(room, 4*row))
        strip = round(16*scale)
        ys = [1+sum(heights[:k]) for k in range(len(entries))]
        if self.menu_scroll is None:
            # Open at the checked entry (the current map in a long Map menu).
            checked = next((y for y, e in zip(ys, entries) if e[2]), 0)
            self.menu_scroll = checked-(visible-row)//2
        scroll = self.menu_scroll = max(0, min(self.menu_scroll, total-visible))
        image = Image.new('RGBA', (width, visible), MENU+(255,))
        d = ImageDraw.Draw(image)
        top = strip if scroll > 0 else 0
        bottom = visible-strip if scroll+visible < total else visible
        boxes = []
        for (value, text, checked), y, h in zip(entries, ys, heights):
            y -= scroll
            if y+h <= 0 or y >= visible:
                continue
            target = ('menu', menu_id, value)
            if value is None:
                d.line([(round(8*scale), y+h//2), (width-round(8*scale), y+h//2)], fill=LINE)
            else:
                if self.hover == target:
                    d.rectangle([1, y, width-2, y+h-1], fill=HOVER)
                if checked:
                    cx, cy, s = round(15*scale), y+h/2, 4*scale
                    d.line([(cx-s, cy), (cx-s/3, cy+s*0.7), (cx+s, cy-s*0.8)], fill=ON_LINE, width=max(2, round(2*scale)))
                d.text((indent, y+h/2), text, font=font, fill=TEXT, anchor='lm')
                if max(y, top) < min(y+h, bottom):
                    boxes.append((0, max(y, top), width, min(y+h, bottom), target))
        a = round(4*scale)
        for show, y0, y1, direction in ((top, 0, top, -1), (bottom < visible, bottom, visible, 1)):
            if not show:
                continue
            target = ('menu_scroll', menu_id, direction)
            d.rectangle([1, y0, width-2, y1-1], fill=HOVER if self.hover == target else MENU)
            d.line([(1, y1-1 if direction < 0 else y0), (width-2, y1-1 if direction < 0 else y0)], fill=LINE)
            cx, cy = width/2, (y0+y1)/2
            d.polygon([(cx-a, cy+a/2*direction*-1), (cx+a, cy+a/2*direction*-1), (cx, cy+a*direction)], fill=MUTED)
            boxes.append((0, y0, width, y1, target))
        d.rectangle([0, 0, width-1, visible-1], outline=LINE)
        return image, boxes

    def scroll_menu(self, rows):
        """Scroll an open menu by rows (positive: down); draw_menu() clamps it."""
        if self.open_menu and self.menu_scroll is not None:
            self.menu_scroll += round(rows*self.menu_row)

    def _upload(self, image, old):
        if old is not None:
            old.release()
        texture = self.ctx.texture(image.size, 4, image.tobytes())
        texture.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        return texture

    @staticmethod
    def _in_menu(target):
        return isinstance(target, tuple) and target[0] in ('menu', 'menu_scroll')

    def _bar_hover(self):
        return None if self._in_menu(self.hover) else self.hover

    def draw(self, size, scale, state):
        """Draw the bar over the top of the framebuffer. An open menu is
        drawn by draw_menu(), after everything else."""
        width, height = size
        key = (width, round(scale, 3), tuple(sorted((k, str(v)) for k, v in state.items())), self._bar_hover(),
               self.open_menu and self.open_menu[0])
        if key != self.key:
            self.key = key
            self.texture = self._upload(self._render(width, scale, state), self.texture)
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        top = self.offset()
        self._blit(self.texture, (0, top, width, top+self.height), size)
        ctx.disable(self.mgl.BLEND)

    def draw_menu(self, size, scale):
        """Draw the open menu, if any, below its button and over everything
        else: call it last. It fits the window, scrolling if it must."""
        if not self.open_menu:
            self.menu_rect, self.menu_boxes = None, []
            return
        width, height = size
        if self.open_menu[0] != self.menu_for:
            self.menu_for, self.menu_scroll = self.open_menu[0], None
        box = next((b for b in self.boxes if b[4] == ('dropdown', self.open_menu[0])), None)
        hover = self.hover if self._in_menu(self.hover) else None
        top = self.offset()+self.height
        key = (width, height, round(scale, 3), self.open_menu[0], tuple(self.open_menu[1]), hover, self.menu_scroll, box)
        if key != self.menu_key:
            image, boxes = self._render_menu(scale, *self.open_menu, height-top-round(8*scale))
            x = box[0] if box else 0
            if box and x+image.width > width:
                # Keep a menu inside the window: right-align it with its button.
                x = max(0, box[2]-image.width)
            self.menu_boxes = [(x+x0, top+y0, x+x1, top+y1, target) for x0, y0, x1, y1, target in boxes]
            self.menu_rect = (x, top, x+image.width, top+image.height)
            self.menu_texture = self._upload(image, self.menu_texture)
            self.menu_key = key[:6] + (self.menu_scroll, box)
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        self._blit(self.menu_texture, self.menu_rect, size)
        ctx.disable(self.mgl.BLEND)

    def _blit(self, texture, rect, size, alpha=1.0):
        width, height = size
        x0, y0, x1, y1 = rect
        to_ndc = lambda x, y: (2*x/width-1, 1-2*y/height)
        a, b = to_ndc(x0, y1), to_ndc(x1, y0)
        self.program['rect'].value = (a[0], a[1], b[0], b[1])
        self.program['alpha'].value = alpha
        texture.use(0)
        self.program['tex'].value = 0
        self.vao.render(self.mgl.TRIANGLE_STRIP)

    def draw_toast(self, size, scale, top, title, detail, fraction=None, kind='loading', alpha=1.0):
        """A small card at the top left, `top` pixels down: a spinner (kind
        'loading'), a check ('done') or a cross ('failed'), a bold title and a
        muted detail line; while loading, the percentage and a thin progress
        bar along its bottom edge."""
        phase = int(time.perf_counter()*12) % 12 if kind == 'loading' else 0
        percent = None if fraction is None else round(100*max(0.0, min(1.0, fraction)))
        key = (round(scale, 3), title, detail, percent, kind, phase)
        if key != getattr(self, 'toast_key', None):
            self.toast_key = key
            self._toast_card(scale, title, detail, percent, kind, phase)
        width, height = size
        w, h = self.toast_texture.size
        margin = round(10*scale)
        ctx = self.ctx
        ctx.viewport = (0, 0, width, height)
        ctx.disable(self.mgl.DEPTH_TEST)
        ctx.enable(self.mgl.BLEND)
        ctx.blend_func = (self.mgl.SRC_ALPHA, self.mgl.ONE_MINUS_SRC_ALPHA)
        self._blit(self.toast_texture, (margin, top+margin, margin+w, top+margin+h), size, alpha)
        ctx.disable(self.mgl.BLEND)

    def _toast_card(self, scale, title, detail, percent, kind, phase):
        # The Marks panel's width, padding, corners and fonts.
        w, h = round(380*scale), round(58*scale)
        radius = round(8*scale)
        card = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(card)
        d.rounded_rectangle([0, 0, w-1, h-1], radius=radius, outline=LINE, fill=MENU+(245,))
        pad = round(12*scale)
        # The icon, drawn four times larger and scaled down for smooth edges.
        icon = round(18*scale)
        big = Image.new('RGBA', (icon*4, icon*4), (0, 0, 0, 0))
        b = ImageDraw.Draw(big)
        line = max(4, round(2*scale*4))
        box = [line//2, line//2, icon*4-line//2-1, icon*4-line//2-1]
        if kind == 'loading':
            b.ellipse(box, outline=HOVER, width=line)
            b.arc(box, start=phase*30, end=phase*30+100, fill=ON_LINE, width=line)
        else:
            b.ellipse(box, fill=GOOD if kind == 'done' else BAD)
            c, s = icon*2, icon*4
            if kind == 'done':
                b.line([(s*0.28, s*0.52), (s*0.44, s*0.68), (s*0.73, s*0.36)], fill=MENU, width=line, joint='curve')
            else:
                b.line([(s*0.33, s*0.33), (s*0.67, s*0.67)], fill=MENU, width=line)
                b.line([(s*0.67, s*0.33), (s*0.33, s*0.67)], fill=MENU, width=line)
        card.alpha_composite(big.resize((icon, icon), Image.LANCZOS), (pad, (h-icon)//2))
        x = pad+icon+round(10*scale)
        right = w-pad
        bold, small = _font(round(13*scale), bold=True), _font(round(12*scale))
        if percent is not None:
            label = f'{percent}%'
            d.text((right, round(21*scale)), label, font=small, fill=MUTED, anchor='rm')
            right -= d.textlength(label, font=small)+round(8*scale)

        def fit(text, font, room):
            if d.textlength(text, font=font) > room:
                while text and d.textlength(text+'…', font=font) > room:
                    text = text[:-1]
                text += '…'
            return text
        d.text((x, round(21*scale)), fit(title, bold, right-x), font=bold, fill=TEXT, anchor='lm')
        d.text((x, round(39*scale)), fit(detail, small, w-pad-x), font=small,
               fill=BAD if kind == 'failed' else MUTED, anchor='lm')
        if percent is not None:
            # A thin bar inside the bottom edge, clipped to the card's corners.
            bar = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            bd = ImageDraw.Draw(bar)
            y0 = h-round(3*scale)
            bd.rectangle([0, y0, w, h], fill=HOVER+(255,))
            bd.rectangle([0, y0, round(w*percent/100), h], fill=ON_LINE+(255,))
            mask = Image.new('L', (w, h), 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, w-1, h-1], radius=radius, fill=255)
            bar.putalpha(ImageChops.darker(bar.getchannel('A'), mask))
            card.alpha_composite(bar)
        self.toast_texture = self._upload(card, getattr(self, 'toast_texture', None))

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
        self.panel_rect = (width-w-margin, top+margin, width-margin, top+margin+h)
        self._blit(self.panel_texture, self.panel_rect, size)
        ctx.disable(self.mgl.BLEND)

    # Input -------------------------------------------------------------------
    def target_at(self, x, y):
        """Toolbar target at framebuffer pixel (x, y), 'bar' for empty bar
        space, 'menu' inside an open menu, 'panel' on the panel, or None."""
        if self.open_menu and self.menu_rect:
            x0, y0, x1, y1 = self.menu_rect
            if x0 <= x < x1 and y0 <= y < y1:
                for bx0, by0, bx1, by1, target in self.menu_boxes:
                    if by0 <= y < by1:
                        return target or 'menu'
                return 'menu'
        top = self.offset()
        if top <= y < top+self.height:
            # Right-aligned items are drawn last, over anything they overlap.
            for x0, y0, x1, y1, target in reversed(self.boxes):
                if x0 <= x < x1 and y0 <= y-top < y1:
                    return target
            return 'bar'
        if self.panel_rect:
            x0, y0, x1, y1 = self.panel_rect
            if x0 <= x < x1 and y0 <= y < y1:
                return 'panel'
        return None
