"""Game objects rendered on their own: one item, or a labelled collage of many.

    mw item TEMPLATE [--heading H] [--elevation E] [--rotation R] [--distance D] [--top]
    mw item TEMPLATE --info
    mw items PATTERN... [--from-map MAP [--layer L]] [--views 3q,side,top] [--columns N]

`mw item TEMPLATE --info` renders nothing: it prints what the game says about
the template (render.catalog.describe). To find names, `mw find`.

An item stands alone on a plain background (white unless --background) with
a soft ground shadow, lit by the game's renderer: the same models, materials
and textures as in the map renders and the viewer. Each image is cropped to
the object and its shadow and scaled to fill the tile, so a scale bar in its
corner gives the size (map units, measured at the object's centre; exact in
top views). `--heading` (the way the camera faces: 0 north, 90 east) and
`--elevation` (degrees above the horizon) change it, `--rotation` turns the
object itself (degrees, as its angle on a map).

PATTERN is a template name or a wildcard (`*bridge*`, case-insensitive) over
the game's object templates that have a model. `--from-map` takes the
templates placed in a map (a project, stock map or .map file), most used
first, `--layer` only those of one layer.

Views (`--views`, comma-separated): 3q (three-quarter, the default), front,
back, left, right, side (= right), top, or HEADING/ELEVATION such as 135/20.
Several views give one row per item.

Each run writes a PNG and a JSON file beside it: per item its model, scale,
size in map units (width x depth x height of the model's box, as placed) and
pixels per map unit in each view, and the templates left out and why.
"""
import argparse
import fnmatch
import json
import math
from pathlib import Path
import re
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from mapworkshop.config import ROOT

OUT = ROOT/'local/renders/items'
GROUND = 100.0          # the flat stand's height
FOV = 30.0              # narrow: little perspective distortion
SHADOW = .38            # darkest ground shadow, 0..1
MARGIN = .06            # free space around the cropped object, of the tile
OVERSAMPLE = 2.5        # render this much larger than the tile, then crop
VIEWS = {'3q': (45, 25), 'front': (0, 15), 'back': (180, 15), 'left': (270, 15), 'right': (90, 15),
         'side': (90, 15)}


# Selection ------------------------------------------------------------------
def drawable(assets, name):
    """The template's own name and draw information, or (name, None)."""
    entry = assets.templates.get(name.lower())
    return (entry['name'] if entry else name), assets.template_model(name)


def select(assets, patterns=(), from_map=None, layer=None):
    """Template names to render, in order, and [(name, reason)] left out."""
    chosen, skipped = [], []
    if from_map is not None:
        from mapworkshop.formats.map import Map
        from collections import Counter
        m = Map(Path(from_map).read_bytes())
        counts = Counter(o['template'] for o in m.objects()
                         if layer is None or any(k == 'objectLayer' and v == layer for k, _, v in o['properties']))
        for name, _ in counts.most_common():
            if name.startswith('*'):
                skipped.append((name, 'not an object (road, waypoint)'))
            elif name.lower() in {c.lower() for c in chosen}:
                continue
            else:
                chosen.append(name)
    for pattern in patterns:
        if any(ch in pattern for ch in '*?['):
            found = sorted(entry['name'] for key, entry in assets.templates.items()
                           if fnmatch.fnmatch(key, pattern.lower()) and assets.template_model(key))
            if not found:
                skipped.append((pattern, 'no template with a model matches'))
            chosen += [f for f in found if f.lower() not in {c.lower() for c in chosen}]
        else:
            chosen.append(pattern)
    result = []
    for name in chosen:
        own, info = drawable(assets, name)
        if name.lower() not in assets.templates:
            skipped.append((name, 'no such template'))
        elif info is None:
            skipped.append((own, 'template has no model'))
        else:
            result.append(own)
    return result, skipped


# Rendering ------------------------------------------------------------------
def parse_views(text):
    views = []
    for word in text.split(','):
        word = word.strip().lower()
        if word in VIEWS or word == 'top':
            views.append(word)
        elif re.fullmatch(r'-?\d+(\.\d+)?/-?\d+(\.\d+)?', word):
            views.append(word)
        else:
            raise ValueError(f'Unknown view {word!r}: use 3q, front, back, left, right, side, top or HEADING/ELEVATION')
    return views


class ItemRenderer:
    """Renders templates one at a time on a private GPU context; models and
    textures loaded once are kept for the next item."""

    def __init__(self, assets=None, lod='high'):
        import moderngl
        from mapworkshop.render.assets import GameAssets
        self.assets = assets or GameAssets()
        self.ctx = moderngl.create_standalone_context(require=430)
        self.ctx.gc_mode = 'auto'      # free each item's GPU objects once it is done
        self.shared = {}
        self.lod = lod

    def measure(self, template):
        """Model, scale and the box of the model as placed: (min, max) in map units."""
        from mapworkshop.render.w3d import ModelCache
        info = self.assets.template_model(template)
        cache = self.shared.setdefault('model_cache', ModelCache(self.assets))
        model = cache.load(info['model']) if info else None
        if not model:
            return None
        low, high = (np.asarray(v, float) * info['scale'] for v in model['bounds'])
        return dict(model=info['model'], scale=info['scale'], low=low, high=high,
                    size=[round(float(v)) for v in high - low])

    def render(self, template, views=('3q',), size=640, background=(1., 1., 1.), rotation=0.,
               heading=None, elevation=None, distance=None, shadow=True, scale_bar=True):
        """{view: dict(image=RGBA uint8 size x size, pixels_per_unit)} for one
        template, cropped to the object and its shadow, and its measurements."""
        from mapworkshop.mapkit.blank import add_object, create
        from mapworkshop.render.camera import OrbitView, TopView
        from mapworkshop.render.engine import MapRenderer
        measured = self.measure(template)
        if measured is None:
            return None, None
        low, high = measured['low'], measured['high']
        angle = math.radians(rotation)
        # A sphere around the foot point that holds the model's box at any
        # rotation (turning about the vertical keeps each corner's reach).
        reach = max(math.hypot(x, y) for x in (low[0], high[0]) for y in (low[1], high[1]))
        radius = max(math.hypot(reach, (high[2] - low[2]) / 2), 20.)
        cells = max(64, math.ceil(radius * 4 / 10))
        m = create(cells, cells, 3, elevation=GROUND)
        cx = cy = cells * 5.
        add_object(m, template, cx, cy, angle)
        renderer = MapRenderer(m.encode(), assets=self.assets, ctx=self.ctx, shared=self.shared, lod=self.lod,
                               clouds=False, macro=False)
        renderer.visible.update(terrain=False, weather=False)
        centre = (cx, cy, GROUND + float(low[2] + high[2]) / 2)
        # The shadow lies under the model's lowest point: bridges and docks
        # reach below the ground they stand on.
        floor = GROUND + min(0., float(low[2]))
        work = min(2048, max(512, round(size * OVERSAMPLE)))
        images = {}
        for name in views:
            if name == 'top':
                view = TopView(region=(cx - radius, cy - radius, cx + radius, cy + radius))
                per_unit = work / (2 * radius)
            else:
                h, e = VIEWS[name] if name in VIEWS else (float(v) for v in name.split('/'))
                if name == '3q':
                    h = h if heading is None else heading
                    e = e if elevation is None else elevation
                d = distance or radius / math.sin(math.radians(FOV / 2)) * 1.06
                view = OrbitView(target=centre, distance=d, elevation=e, heading=h, fov=FOV)
                per_unit = work / 2 / math.tan(math.radians(FOV / 2)) / d
            image, content = self._compose(renderer, view, work, background, shadow, (cx, cy), radius, floor)
            image, zoom = fit(image, content, size, background)
            if scale_bar:
                draw_scale_bar(image, per_unit * zoom, background)
            images[name] = dict(image=image, pixels_per_unit=round(per_unit * zoom, 4))
        return images, measured

    def _matte(self, renderer, view, size):
        """The objects' premultiplied colour and coverage, from a render on
        white and one on black (exact for translucent leaves and glass too)."""
        white = renderer.render(view, size, background=(1., 1., 1.)).astype(np.float32) / 255
        black = renderer.render(view, size, background=(0., 0., 0.)).astype(np.float32) / 255
        alpha = np.clip(1 - (white - black).mean(axis=2), 0, 1)
        return black, alpha

    def _shadow(self, renderer, view, size, centre, radius, floor):
        """A soft contact shadow: the object's footprint seen from above,
        blurred and laid onto the ground under it in this view."""
        from mapworkshop.render.camera import TopView
        cx, cy = centre
        span = radius * 1.6
        n = 256
        _, top = self._matte(renderer, TopView(region=(cx - span, cy - span, cx + span, cy + span)), (n, n))
        mask = Image.fromarray(np.uint8(top * 255)).filter(ImageFilter.GaussianBlur(n * radius * .05 / (2 * span) + 2))
        camera = view.resolve(renderer.terrain, size[0] / size[1])
        world = [(cx - span, cy + span), (cx + span, cy + span), (cx + span, cy - span), (cx - span, cy - span)]
        pixels = []
        for x, y in world:
            clip = camera['view_projection'] @ np.array([x, y, floor, 1.])
            if clip[3] <= 0:
                return np.zeros(size[::-1], np.float32)
            ndc = clip[:3] / clip[3]
            pixels.append(((ndc[0] + 1) / 2 * size[0], (1 - ndc[1]) / 2 * size[1]))
        source = [(0, 0), (n, 0), (n, n), (0, n)]
        coeffs = _perspective(pixels, source)
        laid = mask.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR)
        return np.asarray(laid, np.float32) / 255

    def _compose(self, renderer, view, size, background, shadow, centre, radius, floor):
        """The object and its shadow on the background (RGBA uint8), and the
        pixels that show either (for cropping)."""
        size = (size, size)
        colour, alpha = self._matte(renderer, view, size)
        darkness = self._shadow(renderer, view, size, centre, radius, floor) * SHADOW if shadow else np.zeros(size[::-1], np.float32)
        content = (alpha > .02) | (darkness > .03)
        if background is None:
            # Transparent: the shadow as black at its strength, the object over it.
            cover = alpha + (1 - alpha) * darkness
            rgb = np.where(cover[..., None] > 1e-4, colour / np.maximum(cover, 1e-4)[..., None], 0)
            return np.uint8(np.clip(np.dstack([rgb, cover]), 0, 1) * 255 + .5), content
        ground = np.asarray(background, np.float32)[None, None, :] * (1 - darkness)[..., None]
        rgb = colour + ground * (1 - alpha)[..., None]
        return np.uint8(np.dstack([np.clip(rgb, 0, 1), np.ones(size[::-1])]) * 255 + .5), content


def _fill(background):
    return (0, 0, 0, 0) if background is None else tuple(int(v * 255 + .5) for v in background) + (255,)


def fit(image, content, size, background):
    """Crop an RGBA image to its content (a boolean mask) with a margin, keep
    the aspect, centre it on a size x size tile; the tile and the zoom factor."""
    rows, cols = np.nonzero(content)
    if not len(rows):
        return np.asarray(Image.fromarray(image).resize((size, size), Image.Resampling.LANCZOS)), size / image.shape[1]
    y0, y1, x0, x1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    side = max(y1 - y0, x1 - x0) / (1 - 2 * MARGIN)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    box = [round(cx - side / 2), round(cy - side / 2)]
    box += [box[0] + round(side), box[1] + round(side)]
    canvas = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]), _fill(background))
    canvas.paste(Image.fromarray(image), (-box[0], -box[1]))
    zoom = size / canvas.width
    return np.asarray(canvas.resize((size, size), Image.Resampling.LANCZOS)).copy(), zoom


def bar_length(pixels_per_unit, tile):
    """A round length in map units (1, 2 or 5 x 10^n) about a quarter of the tile wide."""
    target = tile * .25 / pixels_per_unit
    step = 10 ** math.floor(math.log10(target))
    return min((k * step for k in (1, 2, 5, 10)), key=lambda length: abs(math.log(length / target)))


def draw_scale_bar(image, pixels_per_unit, background):
    """A scale bar in the tile's lower right corner, drawn into the RGBA array."""
    tile = image.shape[1]
    length = bar_length(pixels_per_unit, tile)
    pixels = max(1, round(length * pixels_per_unit))
    picture = Image.fromarray(image)
    draw = ImageDraw.Draw(picture)
    font = _font(max(10, tile // 26))
    ink = (90, 90, 90, 255)
    right, bottom = tile - max(8, tile // 30), tile - max(8, tile // 30)
    left = right - pixels
    tick = max(3, tile // 80)
    width = max(1, tile // 200)
    draw.line([(left, bottom), (right, bottom)], fill=ink, width=width)
    for x in (left, right):
        draw.line([(x, bottom - tick), (x, bottom)], fill=ink, width=width)
    text = f'{length:g} units'
    draw.text((right - draw.textlength(text, font=font), bottom - tick - font.size - 4), text, fill=ink, font=font)
    image[...] = np.asarray(picture)


def _perspective(target, source):
    """PIL PERSPECTIVE coefficients mapping output points `target` to input points `source`."""
    rows, rhs = [], []
    for (x, y), (u, v) in zip(target, source):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    return np.linalg.solve(np.array(rows, float), np.array(rhs, float)).tolist()


# Collage --------------------------------------------------------------------
def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def collage(tiles, columns, tile, background, title=None):
    """tiles: [(RGBA array, [label lines])] in reading order -> one RGBA image."""
    pad, gap = 16, 12
    font, small = _font(max(12, tile // 22)), _font(max(11, tile // 28))
    line = max(14, tile // 18)
    label = line * 2 + 6
    rows = math.ceil(len(tiles) / columns)
    head = line + 12 if title else 0
    width = pad * 2 + columns * tile + (columns - 1) * gap
    height = pad * 2 + head + rows * (tile + label) + (rows - 1) * gap
    fill = _fill(background)
    sheet = Image.new('RGBA', (width, height), fill)
    draw = ImageDraw.Draw(sheet)
    ink, faint = (40, 40, 40, 255), (110, 110, 110, 255)
    if title:
        draw.text((pad, pad), title, fill=ink, font=font)
    for i, (image, lines) in enumerate(tiles):
        r, c = divmod(i, columns)
        x, y = pad + c * (tile + gap), pad + head + r * (tile + label + gap)
        picture = Image.fromarray(image)
        sheet.alpha_composite(picture.resize((tile, tile), Image.Resampling.LANCZOS) if picture.width != tile else picture,
                              (x, y))
        for k, text in enumerate(lines[:2]):
            face = small if k else font
            draw.text((x + 2, y + tile + 3 + k * line), _fit(draw, text, face, tile - 4),
                      fill=faint if k else ink, font=face)
    return sheet


def _fit(draw, text, font, width):
    """The text, shortened with an ellipsis to fit `width` pixels."""
    while len(text) > 1 and draw.textlength(text, font=font) > width:
        text = text.rstrip('…')[:-1] + '…'
    return text


# Command line ---------------------------------------------------------------
def _common(parser):
    parser.add_argument('--heading', type=float, help='Way the camera faces in degrees: 0 north, 90 east (3q: 45)')
    parser.add_argument('--elevation', type=float, help='Camera degrees above the horizon (3q: 25)')
    parser.add_argument('--rotation', type=float, default=0., help="The object's own angle in degrees (0)")
    parser.add_argument('--distance', type=float, help='Camera distance in map units (default: framed to the model)')
    parser.add_argument('--background', default='white',
                        help='white (default), transparent, or a colour as #rrggbb')
    parser.add_argument('--no-shadow', action='store_true', help='Leave out the soft ground shadow')
    parser.add_argument('--lod', choices=['low', 'medium', 'high'], default='high', help='Game detail level (high)')
    parser.add_argument('--out', type=Path, help=f'PNG to write (default: in {OUT.relative_to(ROOT).as_posix()}/)')


def _background(text):
    text = text.strip().lower()
    if text in ('transparent', 'none'):
        return None
    if text == 'white':
        return (1., 1., 1.)
    if re.fullmatch(r'#?[0-9a-f]{6}', text):
        text = text.lstrip('#')
        return tuple(int(text[i:i + 2], 16) / 255 for i in (0, 2, 4))
    raise SystemExit('--background is white, transparent or #rrggbb')


def _slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')[:60] or 'items'


def _size_text(measured):
    w, d, h = measured['size']
    return f'{w} x {d} x {h}'


def main_item(argv=None):
    parser = argparse.ArgumentParser(prog='mw item', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('template', help='Object template, e.g. GenericTreeBridge')
    parser.add_argument('--top', action='store_true', help='Look straight down (the footprint)')
    parser.add_argument('--size', type=int, default=800, help='Image width and height in pixels (800)')
    parser.add_argument('--info', action='store_true',
                        help='Print what the game says about it (INI file, KindOf, footprint, stock-map use) instead of rendering')
    _common(parser)
    args = parser.parse_args(argv)
    if args.info:
        from mapworkshop.render import catalog
        from mapworkshop.render.assets import GameAssets
        assets = GameAssets()
        print('\n'.join(catalog.describe(assets, args.template, catalog.load(assets, progress=lambda text: print(text, flush=True)))))
        return 0
    started = time.time()
    renderer = ItemRenderer(lod=args.lod)
    names, skipped = select(renderer.assets, [args.template])
    if not names:
        raise SystemExit(f'mw item: {skipped[0][0]}: {skipped[0][1]}')
    view = 'top' if args.top else '3q'
    images, measured = renderer.render(names[0], [view], args.size, _background(args.background), args.rotation,
                                       args.heading, args.elevation, args.distance, not args.no_shadow)
    if images is None:
        raise SystemExit(f'mw item: {names[0]}: the model could not be loaded')
    out = args.out or OUT/f'{_slug(names[0])}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(images[view]['image']).save(out)
    record = dict(template=names[0], model=measured['model'], scale=measured['scale'], size=measured['size'],
                  view=view, pixels_per_unit=images[view]['pixels_per_unit'], rotation=args.rotation, image=str(out),
                  seconds=round(time.time() - started, 1))
    out.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'{out}\n{names[0]} ({measured["model"]}): {_size_text(measured)} map units (width x depth x height)')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog='mw items', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('patterns', nargs='*', help='Template names or wildcards, e.g. "*bridge*"')
    parser.add_argument('--from-map', help='Also the templates placed in this map (project, stock map or .map file)')
    parser.add_argument('--layer', help='With --from-map: only objects of this layer')
    parser.add_argument('--views', default='3q', help='Comma-separated views (3q)')
    parser.add_argument('--columns', type=int, help='Tiles per row (default: about square; one per view with --views)')
    parser.add_argument('--tile', type=int, default=384, help='Tile size in pixels (384)')
    _common(parser)
    args = parser.parse_args(argv)
    if not args.patterns and not args.from_map:
        parser.error('name templates or wildcards, or --from-map MAP')
    try:
        views = parse_views(args.views)
    except ValueError as error:
        parser.error(str(error))
    background = _background(args.background)
    started = time.time()
    renderer = ItemRenderer(lod=args.lod)
    source = None
    if args.from_map:
        from mapworkshop.render.cli import resolve_map
        source = resolve_map(args.from_map)
    names, skipped = select(renderer.assets, args.patterns, source, args.layer)
    if not names:
        raise SystemExit('mw items: nothing to render' + ''.join(f'\n  {n}: {why}' for n, why in skipped))
    print(f'Rendering {len(names)} item{"s" if len(names) != 1 else ""} x {len(views)} view{"s" if len(views) != 1 else ""}...',
          flush=True)
    tiles, items = [], []
    for i, name in enumerate(names, 1):
        images, measured = renderer.render(name, views, args.tile, background, args.rotation, args.heading,
                                           args.elevation, args.distance, not args.no_shadow)
        if images is None:
            skipped.append((name, 'the model could not be loaded'))
            continue
        items.append(dict(template=name, model=measured['model'], scale=measured['scale'], size=measured['size'],
                          pixels_per_unit={view: images[view]['pixels_per_unit'] for view in views}))
        for view in views:
            second = _size_text(measured) + ('' if len(views) == 1 else f'  ·  {view}')
            tiles.append((images[view]['image'], [name, second]))
        if i % 10 == 0:
            print(f'  {i}/{len(names)}', flush=True)
    columns = args.columns or (len(views) if len(views) > 1 else max(1, min(8, math.ceil(math.sqrt(len(tiles))))))
    label = ' '.join(args.patterns) or ''
    if args.from_map:
        label = (label + ' ' if label else '') + f'{Path(str(source)).stem}' + (f' [{args.layer}]' if args.layer else '')
    title = f'{label}  -  {len(items)} item{"s" if len(items) != 1 else ""}, size in map units (width x depth x height)'
    sheet = collage(tiles, columns, args.tile, background, title)
    out = args.out or OUT/f'{_slug(label)}.png'
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    record = dict(image=str(out), views=views, items=items, skipped=[dict(template=n, reason=r) for n, r in skipped],
                  seconds=round(time.time() - started, 1))
    out.with_suffix('.json').write_text(json.dumps(record, indent=2) + '\n')
    print(f'{out}\n{len(items)} items in {record["seconds"]} s' + (f'; {len(skipped)} left out (see the .json)' if skipped else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
