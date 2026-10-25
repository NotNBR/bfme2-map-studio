"""Placement plans for any map: numbered starts, objectives, lairs and flag footprints.

`mw placements [MAP ...] --out plan.png` reads project builds, stock maps or
loose .map files without changing them or starting the game. Multiple maps
make a comparison. The JSON beside the PNG keeps positions, angles, counts
and proximity-based flag associations; it does not claim gameplay reachability.
"""
import argparse
from collections import Counter
import colorsys
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import textwrap

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop import project
from mapworkshop.assets.library import GameAssets
from mapworkshop.config import RENDERS
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.graphics import font, slug, water_mask
from mapworkshop.mapkit.pathing import template_data, footprint_cells
from mapworkshop.mapkit.sites import LAIRS, LINKED
from mapworkshop.render.godot import starting_positions

BACKGROUND, INK, MUTED = '#152027', '#f2f5f7', '#b8c8d1'
COLOURS = {'outpost': '#ffd566', 'inn': '#ffaa66', 'signalfire': '#6ddfff', 'shipwright': '#83c9ff',
           'cavetrolllair': '#ff7b7b', 'moriargoblinlair': '#b1e784', 'firedrakelair': '#d9a5ff'}
ABBREVIATIONS = {'outpost': 'O', 'inn': 'I', 'signalfire': 'S', 'shipwright': 'W',
                 'cavetrolllair': 'T', 'moriargoblinlair': 'G', 'firedrakelair': 'D'}
FLAG_RANGE = 250.0
PANEL = (900, 700)


@dataclass
class Plan:
    """The serializable inventory and the playable terrain used to draw it."""
    data: dict
    heights: np.ndarray
    blocked: np.ndarray
    water: np.ndarray


def _colour(template):
    name = template.lower()
    if name in COLOURS:
        return COLOURS[name]
    hue = int.from_bytes(hashlib.sha256(name.encode()).digest()[:2], 'big')/65535
    return tuple(round(v*255) for v in colorsys.hsv_to_rgb(hue, .43, .95))


def _local(obj, point):
    dx, dy = point[0]-obj['x'], point[1]-obj['y']
    c, s = math.cos(obj['angle']), math.sin(obj['angle'])
    return dx*c+dy*s, -dx*s+dy*c


def _inside(shapes, point):
    for shape in shapes:
        x, y = point[0]-shape['offset'][0], point[1]-shape['offset'][1]
        if shape['type'] == 'BOX' and abs(x) <= shape['major'] and abs(y) <= shape['minor']:
            return True
        if shape['type'] in ('CYLINDER', 'SPHERE') and math.hypot(x, y) <= shape['major']:
            return True
    return False


def _cells(obj, shapes, size):
    return {(int(y), int(x)) for shape in shapes
            for ys, xs in [footprint_cells(shape, obj, size)] for y, x in zip(ys, xs)}


def analyse(m, name, source='', *, assets=None, scenery=False, farms=False):
    """Read a map, including local INI geometry supplied through `assets`.

    Capturable structures are paired one-to-one with flags by shortest distance,
    within FLAG_RANGE. Unknown geometry stays explicit; no fake footprint is drawn.
    """
    hm = m.heightmap()
    b, rows, columns = hm['border'], hm['height'], hm['width']
    crop = np.s_[b:rows-b, b:columns-b]
    z = hm['elevations'][crop].astype(float)*.0390625
    blocked = m.blend(inspection=True)['arrays']['impassable'][crop].astype(bool)
    objects = m.objects()
    cache, warnings, sites, flags = {}, set(), [], []
    known = {name.lower() for name in (*LINKED, *LAIRS)}
    shapes_by_index = {}
    for obj in objects:
        name_key = obj['template'].lower()
        data = template_data(assets, obj['template'], cache) if assets is not None else None
        kinds = data['kinds'] if data else set()
        shapes = [shape for shape in data['shapes'] if shape['enabled'] and shape['offset'][2] <= 10
                  and shape['type'] in ('BOX','CYLINDER','SPHERE')] if data else []
        # Object prototype scale affects the game's models, not this static geometry estimate (mapkit.pathing).
        shapes_by_index[obj['index']] = shapes
        if obj['flags'] & 0x30:
            continue
        if name_key == 'captureflag' or 'CAPTUREFLAG' in kinds:
            flags.append(obj)
            continue
        owner = next((str(v) for k, _, v in obj['properties'] if k == 'originalOwner'), '')
        linked = name_key in {k.lower() for k in LINKED} or 'LINKED_TO_FLAG' in kinds
        gameplay = name_key in known or linked or name_key.endswith('lair') or (
            'STRUCTURE' in kinds and (re.search(r'Player_\d+', owner, re.I) or
                                    kinds & {'FS_FACTORY', 'ECONOMY_STRUCTURE', 'BASE_FOUNDATION', 'CASTLE_CENTER'}))
        selected = gameplay or (scenery and 'STRUCTURE' in kinds) or (farms and name_key == 'farmtemplate')
        if not selected:
            continue
        if data is None:
            warnings.add('No geometry definition: '+obj['template'])
        sites.append(dict(id=len(sites)+1, index=obj['index'], template=obj['template'], x=obj['x'], y=obj['y'],
                          angle=obj['angle'], angle_degrees=math.degrees(obj['angle']), linked=bool(linked),
                          geometry=shapes, flag=None))
    # Greedy global proximity matching avoids silently assigning the same flag to two sites.
    candidates = sorted((math.hypot(s['x']-f['x'], s['y']-f['y']), s['id'], f['index'])
                        for s in sites if s['linked'] for f in flags)
    by_id, by_flag, taken = {s['id']: s for s in sites}, {f['index']: f for f in flags}, set()
    for distance, sid, fid in candidates:
        site = by_id[sid]
        if distance > FLAG_RANGE or site['flag'] is not None or fid in taken:
            continue
        flag = by_flag[fid]
        taken.add(fid)
        point = _local(site, (flag['x'], flag['y']))
        flag_shapes = shapes_by_index[fid]
        overlap = _cells(site, site['geometry'], z.shape) & _cells(flag, flag_shapes, z.shape)
        site['flag'] = dict(x=flag['x'], y=flag['y'], angle=flag['angle'], distance=distance,
                            geometry=flag_shapes, centre_inside=_inside(site['geometry'], point),
                            overlap_cells=len(overlap), geometry_known=bool(site['geometry'] and flag_shapes))
    counts = dict(sorted(Counter(o['template'] for o in objects).items()))
    data = dict(name=name, source=str(source), size=[z.shape[1]*10, z.shape[0]*10],
                starts=starting_positions(m), sites=sites, counts=counts,
                displayed_counts=dict(sorted(Counter(s['template'] for s in sites).items())),
                unmatched_flags=[dict(x=f['x'], y=f['y']) for f in flags if f['index'] not in taken],
                missing_flags=[s['id'] for s in sites if s['linked'] and s['flag'] is None],
                flag_association=f'One-to-one nearest proximity within {FLAG_RANGE:g} map units; estimate, not an engine link',
                footprint_method='10-unit static geometry grid; overlaps do not prove a capture is impossible',
                warnings=sorted(warnings))
    return Plan(data, z, blocked, water_mask(m, z))


def load(name=None, *, assets=None, scenery=False, farms=False):
    """Resolve a project build, stock map or .map file and read its local geometry overrides."""
    path = project.map_path(name).resolve()
    m = Map(path.read_bytes())
    owner = project.for_map_file(path)
    ini = path.with_name('map.ini')
    if assets is not None and ini.is_file() and hasattr(assets, 'for_map'):
        base=dict(assets.templates)
        assets = assets.for_map(ini.read_text(encoding='cp1252'))
        # Map-local Object ExistingName patches retain omitted retail fields.
        for key,entry in list(assets.templates.items()):
            if key in base and entry is not base[key] and not entry.get('parent'):
                parent='__placement_base_'+key
                assets.templates[parent]=base[key]
                entry['parent']=parent
    plan = analyse(m, owner.title if owner else path.stem, path, assets=assets, scenery=scenery, farms=farms)
    plan.data['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return plan


def _text(draw, at, text, size, width, colour=INK, max_lines=None):
    lines = textwrap.wrap(text, max(8, int(width/(size*.53)))) or ['']
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(' .')+'…'
    draw.multiline_text(at, '\n'.join(lines), font=font(size), fill=colour, spacing=4)
    return len(lines)*(size+4)


def _overlap(a, b):
    return max(0, min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))


def _label(draw, point, text, colour, bounds, occupied):
    """Choose a nearby label box inside the panel, avoiding earlier labels where possible."""
    x, y = point
    box = draw.textbbox((0,0), text, font=font(15))
    w, h = box[2]-box[0]+4, 22
    candidates = []
    for dx,dy in ((9,-10),(9,8),(-w-9,-10),(-w-9,8),(0,-28),(0,20)):
        px = max(bounds[0], min(bounds[2]-w, x+dx))
        py = max(bounds[1], min(bounds[3]-h, y+dy))
        rect = (px,py,px+w,py+h)
        candidates.append((sum(_overlap(rect,b) for b in occupied),rect))
    rect = min(candidates,key=lambda candidate:candidate[0])[1]
    occupied.append(rect)
    draw.text((rect[0]+2,rect[1]),text,font=font(15),fill=colour,stroke_width=2,stroke_fill=BACKGROUND)


def _panel(image, plan, origin):
    x0,y0 = origin
    draw = ImageDraw.Draw(image)
    d = plan.data
    _text(draw,(x0+20,y0+12),d['name'],24,PANEL[0]-40,max_lines=2)
    draw.text((x0+20,y0+75),f'{d["size"][0]:,} × {d["size"][1]:,} units · {len(d["starts"])} starts',font=font(17),fill=MUTED)
    z = plan.heights
    normal = (z-z.min())/max(1,float(np.ptp(z)))
    rgb = np.stack((52+normal*100,72+normal*89,54+normal*70),axis=2).astype(np.uint8)
    rgb[plan.blocked] = (rgb[plan.blocked]*.43).astype(np.uint8)
    rgb[plan.water] = (45,98,128)
    scale = min((PANEL[0]-40)/d['size'][0], 500/d['size'][1])
    width,height = [max(1,round(v*scale)) for v in d['size']]
    left,top = x0+20,y0+110
    image.paste(Image.fromarray(np.flipud(rgb)).resize((width,height)),(left,top))
    pixel = lambda x,y: (left+x*scale, top+height-1-y*scale)
    bounds,occupied = (left,top,left+width,top+height),[]
    for start in d['starts']:
        x,y = pixel(start['x'],start['y'])
        draw.ellipse((x-12,y-12,x+12,y+12),fill=BACKGROUND,outline='#b5eeff',width=2)
        draw.text((x,y),str(start['number']),font=font(15),fill=INK,anchor='mm')
        occupied.append((x-14,y-14,x+14,y+14))
    for site in d['sites']:
        x,y = pixel(site['x'],site['y'])
        if not (bounds[0] <= x < bounds[2] and bounds[1] <= y < bounds[3]):
            continue
        colour = _colour(site['template'])
        draw.rectangle((x-4,y-4,x+4,y+4),fill=colour)
        angle=site['angle']
        end=(x+math.cos(angle)*15,y-math.sin(angle)*15)
        draw.line((x,y,*end),fill=colour,width=2)
        draw.ellipse((end[0]-2,end[1]-2,end[0]+2,end[1]+2),fill=colour)
        abbreviation=ABBREVIATIONS.get(site['template'].lower(),site['template'][:2])
        _label(draw,(x,y),abbreviation+str(site['id']),colour,bounds,occupied)
    counts=' · '.join(f'{name}: {count}' for name,count in d['displayed_counts'].items()) or 'No selected buildings or lairs'
    _text(draw,(x0+20,y0+625),counts,15,PANEL[0]-40,MUTED,max_lines=3)


def _details(plans):
    kinds=sorted({s['template'] for p in plans for s in p.data['sites'] if s['flag']})
    result=[]
    for kind in kinds:
        for plan in plans:
            candidates=[s for s in plan.data['sites'] if s['template']==kind and s['flag'] and s['geometry']]
            if candidates:
                site=max(candidates,key=lambda s:(s['flag']['centre_inside'],s['flag']['overlap_cells']))
                result.append((plan.data['name'],site))
    return result


def _detail(draw, name, site, origin, scale):
    x0,y0=origin
    _text(draw,(x0,y0),name+' · '+site['template'],16,280,max_lines=2)
    cx,cy=x0+140,y0+170
    draw.rectangle((x0,y0+50,x0+280,y0+290),fill='#22333d',outline='#52636d')
    for shape in site['geometry']:
        ox,oy,_=shape['offset']; a,b=shape['major'],shape['minor']
        box=(cx+(ox-a)*scale,cy-(oy+b)*scale,cx+(ox+a)*scale,cy-(oy-b)*scale)
        if shape['type']=='BOX':draw.rectangle(box,fill='#7a868a',outline='#d8e0e3',width=2)
        elif shape['type'] in ('CYLINDER','SPHERE'):draw.ellipse(box,fill='#7a868a',outline='#d8e0e3',width=2)
    flag=site['flag']
    # Transform every flag shape into this building's local frame, preserving its own angle.
    for shape in flag['geometry']:
        major,minor=shape['major'],shape['minor']
        points=[(major*math.cos(a),major*math.sin(a)) for a in np.linspace(0,2*math.pi,40)] if shape['type'] != 'BOX' else [(-major,-minor),(major,-minor),(major,minor),(-major,minor)]
        transformed=[]
        for x,y in points:
            x+=shape['offset'][0];y+=shape['offset'][1]
            c,s=math.cos(flag['angle']),math.sin(flag['angle'])
            px,py=_local(site,(flag['x']+x*c-y*s,flag['y']+x*s+y*c))
            transformed.append((cx+px*scale,cy-py*scale))
        draw.polygon(transformed,fill='#ff6868' if flag['centre_inside'] else '#62dfff',outline=INK,width=2)
    if not flag['geometry']:
        px,py=_local(site,(flag['x'],flag['y']))
        draw.ellipse((cx+px*scale-4,cy-py*scale-4,cx+px*scale+4,cy-py*scale+4),fill='#62dfff')
    text=f'Flag offset {flag["distance"]:.1f} units'
    if flag['centre_inside']:text+=' · centre inside'
    elif flag['overlap_cells']:text+=' · grid overlap'
    _text(draw,(x0,y0+300),text,15,280,'#ffb4a7' if flag['centre_inside'] or flag['overlap_cells'] else MUTED)


def draw(plans, columns=2, details=True):
    """Draw one plan or an atlas, with one representative flag inset per kind and map."""
    if not plans or not 1 <= columns <= 4:
        raise ValueError('Supply at least one map and 1..4 columns')
    columns=min(columns,len(plans))
    rows=math.ceil(len(plans)/columns)
    width=columns*PANEL[0]
    insets=_details(plans) if details else []
    detail_columns=max(1,width//300)
    detail_rows=math.ceil(len(insets)/detail_columns)
    heading=75
    templates=sorted({s['template'] for p in plans for s in p.data['sites']})
    legend=' · '.join(f'{ABBREVIATIONS.get(t.lower(),t[:2])}: {t}' for t in templates)
    explanation='Numbered circles: player starts. Squares: buildings and lairs. Arrows: object local +X (model entrances may face another direction). IDs match the JSON.'
    foot=35+len(textwrap.wrap(explanation,max(8,int((width-40)/(17*.53)))))*21
    foot+=len(textwrap.wrap(legend,max(8,int((width-40)/(15*.53)))))*19
    height=heading+rows*PANEL[1]+foot+(55+detail_rows*355 if insets else 0)
    image=Image.new('RGB',(width,height),BACKGROUND)
    ink=ImageDraw.Draw(image)
    ink.text((20,20),'Placement plan' if len(plans)==1 else 'Placement comparison',font=font(30),fill=INK)
    for index,plan in enumerate(plans):
        _panel(image,plan,((index%columns)*PANEL[0],heading+(index//columns)*PANEL[1]))
    y=heading+rows*PANEL[1]+8
    used=_text(ink,(20,y),explanation,17,width-40,MUTED)
    _text(ink,(20,y+used+7),legend,15,width-40,MUTED)
    if insets:
        y+=foot
        ink.text((20,y),'Capture flags and footprints · same world scale in every inset',font=font(20),fill=INK)
        extent=120.0
        for _,site in insets:
            for shape in site['geometry']:
                extent=max(extent,abs(shape['offset'][0])+shape['major'],abs(shape['offset'][1])+shape['minor'])
            fx,fy=_local(site,(site['flag']['x'],site['flag']['y']))
            extent=max(extent,abs(fx)+25,abs(fy)+25)
        scale=105/extent
        for index,(name,site) in enumerate(insets):
            _detail(ink,name,site,(20+(index%detail_columns)*(width-40)/detail_columns,y+45+(index//detail_columns)*355),scale)
    return image


def default_output(path):
    return RENDERS/'placements'/(slug(Path(path).stem)+'.png')


def export(names, out=None, *, columns=2, details=True, scenery=False, farms=False, assets=None):
    """Write a PNG and JSON inventory. Map files and neighbouring INIs remain unchanged."""
    if assets is None:
        try:
            assets=GameAssets()
        except RuntimeError:
            assets=None
    plans=[load(name,assets=assets,scenery=scenery,farms=farms) for name in (names or [None])]
    if out is None:
        out=default_output(plans[0].data['source'])
        if len(plans)>1:
            out=out.with_stem(out.stem+'-comparison')
    out=Path(out)
    if out.suffix.lower() != '.png':
        raise ValueError('The output must be a .png file')
    out=out.resolve()
    metadata=out.with_suffix('.json').resolve()
    inputs={Path(p.data['source']).resolve() for p in plans}
    inputs.update(path.resolve() for p in plans for path in Path(p.data['source']).parent.iterdir()
                  if path.suffix.lower() in ('.map','.ini','.str','.tga'))
    if out in inputs or metadata in inputs:
        raise ValueError('Choose an output separate from the source map')
    out.parent.mkdir(parents=True,exist_ok=True)
    draw(plans,columns,details).save(out)
    metadata.write_text(json.dumps(dict(maps=[p.data for p in plans],image=str(out)),indent=2),encoding='utf-8')
    return out,metadata


def main(argv=None):
    parser=argparse.ArgumentParser(prog='mw placements',description=__doc__)
    parser.add_argument('maps',nargs='*',help='Projects, stock maps or .map files (default: the last map)')
    parser.add_argument('--out',type=Path,help='PNG to save (JSON beside it; default local/renders/placements/<map>.png)')
    parser.add_argument('--columns',type=int,default=2,choices=range(1,5),help='Maps per row, 1..4 (2)')
    parser.add_argument('--no-details',action='store_true',help='Leave out capture-flag footprint closeups')
    parser.add_argument('--scenery',action='store_true',help='Also label other structures, including decorative buildings')
    parser.add_argument('--farms',action='store_true',help='Also label invisible AI FarmTemplate hints')
    args=parser.parse_args(argv)
    try:
        out,metadata=export(args.maps,args.out,columns=args.columns,details=not args.no_details,scenery=args.scenery,farms=args.farms)
    except (ValueError,OSError) as error:
        parser.error(str(error))
    print(out)
    print(metadata)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
