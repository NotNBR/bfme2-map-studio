"""Generate diagnostic map graphics without changing maps or launching BFME2.

Run: mw graphics --help
"""
import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import html
import inspect
import json
import math
import os
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from mapworkshop.formats.big import BigArchive
from mapworkshop.formats.map import Map
from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.config import GAME_DATA

COLORS = {'tree':'#7bcb59', 'understory':'#348660', 'rock':'#b8bab3',
          'deadwood':'#987a59', 'building/ruin':'#ffbc67', 'bridge':'#ed9f57',
          'other prop':'#b896be', 'neutral':'#efdd8b'}
START_COLORS = ('#e35548','#438fe5','#55bd56','#e3cb51','#b56bea','#42c6c3','#e89447','#da72a3')
BACKGROUND = '#10181d'


def font(size):
    for path in ('C:/Windows/Fonts/segoeui.ttf', 'DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def slug(name):
    value = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not value:
        raise ValueError('Map name needs at least one ASCII letter or digit')
    return value


def resolve(path, base):
    path = Path(path).expanduser()
    # Normalize '..' before resolving filesystem aliases (also works under the
    # Windows sandbox's path translation).
    return Path(os.path.abspath(path if path.is_absolute() else base/path)).resolve()


class Templates:
    """Classify inherited native object templates; unknowns stay explicit."""
    def __init__(self, directory):
        if not directory.is_dir():
            raise ValueError(f'Object INI directory does not exist: {directory}')
        self.definitions = {}
        self.cache = {}
        for path in sorted(directory.rglob('*.ini')):
            text = path.read_text(encoding='cp1252')
            matches = list(re.finditer(r'^(Object|ObjectReskin|ChildObject)\s+(\w+)(?:[ \t]+(\w+))?', text, re.M))
            for i, match in enumerate(matches):
                body = text[match.end():matches[i+1].start() if i+1<len(matches) else len(text)]
                kind = re.search(r'^\s*KindOf\s*=\s*([^;\r\n]+)', body, re.M|re.I)
                self.definitions[match[2].lower()] = (
                    path.name, match[3] if match[1]!='Object' else None,
                    kind[1].upper().split() if kind else None)
        if not self.definitions:
            raise ValueError(f'No object definitions found in {directory}')

    def definition(self, name, seen=None):
        key = name.lower()
        if key in self.cache:
            return self.cache[key]
        seen = set() if seen is None else seen
        if key not in self.definitions or key in seen:
            return '', []
        seen.add(key)
        file, parent, kinds = self.definitions[key]
        if parent and kinds is None:
            _, kinds = self.definition(parent, seen)
        result = file, kinds or []
        self.cache[key] = result
        return result

    def category(self, obj):
        name = obj['template'].lower()
        file, kinds = self.definition(obj['template'])
        if obj['flags'] & 6:
            return 'road'
        if ('stump' in name or ('log' in name and file.startswith('nature'))
                or ('dead' in name and 'TREE' in kinds)):
            return 'deadwood'
        if 'TREE' in kinds:
            return 'tree'
        if file == 'naturerocks.ini':
            return 'rock'
        if 'SHRUB' in kinds or (file=='natureprop.ini' and 'SHRUBBERY' in kinds):
            return 'understory'
        if 'bridge' in name:
            return 'bridge'
        if file.endswith('buildings.ini') or 'ruin' in name:
            return 'building/ruin'
        if file in ('civilianprop.ini', 'natureprop.ini'):
            return 'other prop'
        if obj['template'] in ('Outpost','Inn','SignalFire','WargLair','GoblinLair','TrollLair'):
            return 'neutral'
        return 'gameplay/other'


def xy(objects):
    return np.array([(o['x'], o['y']) for o in objects], dtype=float).reshape(-1,2)


def spacing(a, b, same=False):
    """Exact distances in bounded-memory blocks, including maps with 0–4 trees."""
    if not len(a) or not len(b) or (same and len(a)<2):
        return None
    nearest, fifth, within, matches = [], [], [], []
    targets = xy(b)
    for start in range(0,len(a),128):
        points = xy(a[start:start+128])
        d = np.sum((points[:,None,:]-targets[None,:,:])**2, axis=2)
        if same:
            d[np.arange(len(points)), np.arange(start,start+len(points))] = np.inf
        idx = np.argmin(d, axis=1)
        nearest.extend(np.sqrt(d[np.arange(len(points)),idx]).tolist())
        if same:
            within.extend(np.sum(d<100**2,axis=1).tolist())
            matches.extend(a[start+i]['template']==b[j]['template'] for i,j in enumerate(idx))
            if len(a)>5:
                fifth.extend(np.sqrt(np.partition(d,4,axis=1)[:,4]).tolist())
    return dict(nearest_p10_p50_p90=np.percentile(nearest,[10,50,90]).round(2).tolist(),
                fraction_within_50=round(float(np.mean(np.asarray(nearest)<50)),3),
                median_fifth_neighbor=round(float(np.median(fifth)),2) if fifth else None,
                median_neighbors_100=float(np.median(within)) if within else None,
                same_template_nearest_fraction=round(float(np.mean(matches)),3) if matches else None,
                individual_nearest=nearest if not same else None)


def water_mask(m, z):
    mask = np.zeros(z.shape, dtype=bool)
    names = {m.names[c.name_id] for c in m.chunks}
    for chunk in ('StandingWaterAreas','RiverAreas'):
        if chunk not in names:
            continue
        for area in records(m,chunk):
            points = area.get('points')
            if points is None:
                sections = area['cross_sections']
                points = [p[:2] for p in sections]+[p[2:] for p in reversed(sections)]
            if len(points)<3:
                continue
            image = Image.new('1',(z.shape[1],z.shape[0]))
            ImageDraw.Draw(image).polygon([(x/10,y/10) for x,y in points],fill=1)
            mask |= np.asarray(image) & (z<area['water_height'])
    return mask


def source_bytes(spec, base, default_archive=None):
    if bool(spec.get('file')) == bool(spec.get('entry')):
        raise ValueError('Each map must specify exactly one of file or entry')
    if spec.get('file'):
        path = resolve(spec['file'],base)
        return path.read_bytes(), str(path)
    archive_path = spec.get('archive') or default_archive
    if not archive_path:
        raise ValueError('Archive entry requires --archive or an archive path in the config')
    archive = BigArchive(resolve(archive_path,base))
    query = spec['entry'].replace('\\','/').lower()
    if query in archive.entries:
        key = query
    else:
        # Short names must be unambiguous; never silently select a similarly named map.
        stem = query.removesuffix('.map')
        found = [k for k in archive.entries if k.endswith('/'+stem+'.map')]
        if len(found)!=1:
            raise ValueError(f'Expected one archive map for {query!r}; found {len(found)}')
        key = found[0]
    return archive.read_bytes(key), str(archive.path)+'::'+key


@dataclass
class Scene:
    name: str
    source: str
    z: np.ndarray
    water: np.ndarray
    blocked: np.ndarray
    materials: np.ndarray
    objects: list
    starts: list
    roads: list
    metrics: dict
    plan: dict

    @property
    def extent(self):
        return self.z.shape[1]*10, self.z.shape[0]*10


def load_scene(spec, base, templates, archive=None):
    data, origin = source_bytes(spec,base,archive)
    m = Map(data)
    terrain = m.heightmap()
    blend = m.blend(inspection=True) if 'inspection' in inspect.signature(m.blend).parameters else m.blend()
    b, w, h = terrain['border'], terrain['width'], terrain['height']
    crop = np.s_[b:h-b,b:w-b]
    z = terrain['elevations'][crop].astype(float)*.0390625
    width, height = z.shape[1]*10, z.shape[0]*10
    objects = m.objects()
    playable = [dict(o,category=templates.category(o)) for o in objects
                if 0<=o['x']<width and 0<=o['y']<height]
    starts = [o for o in playable if any(k=='waypointName' and
              re.fullmatch(r'Player_\d+_Start',str(v),re.I) for k,_,v in o['properties'])]
    starts.sort(key=lambda o:int(next(v for k,_,v in o['properties'] if k=='waypointName').split('_')[1]))
    trees = [o for o in playable if o['category']=='tree']
    under = [o for o in playable if o['category']=='understory']
    counts = Counter(o['category'] for o in playable)
    area = width*height/1e6
    water = water_mask(m,z)
    materials = np.zeros((*z.shape,3),dtype=np.uint8)
    covered = np.zeros(z.shape,bool)
    tiles = blend['arrays']['tiles'][crop]
    palette = []
    for texture in blend['textures']:
        color = material_color(texture['name'])
        selected = (tiles>=texture['tile_start'])&(tiles<texture['tile_start']+texture['tile_count'])
        materials[selected] = color
        covered |= selected
        palette.append(dict(name=texture['name'],color=color,cells=int(selected.sum())))
    materials[~covered] = (190,60,180)
    roads, pending = [], None
    # Preserve native endpoint order; boundary roads can have an endpoint outside the rectangle.
    for obj in objects:
        if obj['flags']&2:
            pending = obj
        elif obj['flags']&4 and pending is not None:
            roads.append([(pending['x'],pending['y']),(obj['x'],obj['y'])])
            pending = None
    scales = [v for o in trees for k,_,v in o['properties'] if 'scale' in k.lower() and isinstance(v,(int,float))]
    metrics = dict(name=spec['name'],source=spec.get('source','map'),path=origin,
                   sha256=hashlib.sha256(data).hexdigest(),world_size=[width,height],
                   height_range=[float(z.min()),float(z.max())],objects_all=len(objects),
                   objects_playable=len(playable),outside_playable=len(objects)-len(playable),
                   categories=dict(counts),area_million=area,water_fraction=round(float(water.mean()),3),
                   trees_per_million=round(len(trees)/area,1),rocks_per_million=round(counts['rock']/area,1),
                   tree_spacing=spacing(trees,trees,True),base_to_tree=spacing(starts,trees),
                   understory_to_tree=spacing(under,trees),understory_per_tree=round(len(under)/len(trees),2) if trees else None,
                   tree_templates=Counter(o['template'] for o in trees).most_common(12),
                   scale_range=np.percentile(scales,[0,50,100]).round(3).tolist() if scales else [1,1,1],
                   palette=palette,texture_inspection_issues=blend.get('inspection_issues',{}),
                   invalid_texture_cells=int((~covered).sum()))
    plan = spec.get('plan',{})
    if isinstance(plan,str):
        plan = json.loads(resolve(plan,base).read_text(encoding='utf-8'))
    validate_plan(plan)
    return Scene(spec['name'],spec.get('source','map'),z,water,blend['arrays']['impassable'][crop].astype(bool),
                 materials,playable,starts,roads,metrics,plan)


def material_color(name):
    name = name.lower()
    for key, color in (('snow',(222,230,230)),('cliff',(137,139,131)),('rock',(121,125,113)),
                       ('sand',(174,153,107)),('dirt',(141,116,78)),('road',(158,136,100)),
                       ('water',(38,85,105)),('mud',(102,91,70)),('grass',(108,123,72))):
        if key in name:
            return color
    return (108,123,72)


def validate_plan(plan):
    if not isinstance(plan,dict):
        raise ValueError('plan must be an object or a path to a JSON object')
    for kind, minimum in (('routes',2),('regions',3)):
        for item in plan.get(kind,[]):
            points = item.get('points',[])
            if len(points)<minimum or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
                raise ValueError(f'{kind} need at least {minimum} finite XY points')
            if kind=='routes' and (not math.isfinite(item.get('width',0)) or item.get('width',0)<0):
                raise ValueError('Route width must be nonnegative and finite')
    for item in plan.get('markers',[]):
        p = item.get('position',[])
        if len(p)!=2 or not all(math.isfinite(v) for v in p):
            raise ValueError('Markers need a finite XY position')


def terrain_rgb(scene, mode='materials', contour_step=0):
    z = scene.z
    dy, dx = np.gradient(z,10)
    if mode=='materials':
        light = np.clip((.78-.45*dx-.5*dy)/np.sqrt(dx*dx+dy*dy+1),.08,1.10)
        rgb = scene.materials.astype(float)*(.43+.72*light[...,None])
    elif mode=='relief':
        gray = 40+(z-z.min())/max(1,float(np.ptp(z)))*50
        rgb = np.stack((gray,gray+7,gray+3),axis=-1)
    elif mode=='slope':
        value = np.clip(np.hypot(dx,dy),0,1.5)/1.5
        rgb = np.stack((45+value*200,135-value*95,75-value*40),axis=-1)
    elif mode=='passability':
        rgb = np.empty((*z.shape,3));rgb[:] = (74,112,79);rgb[scene.blocked] = (170,63,59)
    else:
        raise ValueError('Unknown terrain mode: '+mode)
    if contour_step:
        levels = np.floor(z/contour_step)
        edges = np.zeros(z.shape,bool)
        edges[1:] |= levels[1:]!=levels[:-1]
        edges[:,1:] |= levels[:,1:]!=levels[:,:-1]
        rgb[edges] *= .65
    rgb[scene.water] = (35,76,98)
    return np.uint8(np.flipud(np.clip(rgb,0,255)))


def viewport(scene, max_width, max_height, mode='materials', contour_step=0):
    w,h = scene.extent
    scale = min(max_width/w,max_height/h)
    size = max(1,round(w*scale)),max(1,round(h*scale))
    image = Image.fromarray(terrain_rgb(scene,mode,contour_step)).resize(size,Image.Resampling.LANCZOS)
    # XY origin is the lower-left, including the vertical raster flip.
    def pixel(p):
        return p[0]/w*size[0], size[1]-1-p[1]/h*size[1]
    return image, pixel, scale


def dots(image, scene, pixel, scale, crown=16, landmarks=False):
    draw = ImageDraw.Draw(image)
    for obj in scene.objects:
        cat = obj['category']
        if cat not in COLORS:
            continue
        if not landmarks and cat in ('other prop','neutral'):
            continue
        x,y = pixel((obj['x'],obj['y']))
        radius = max(.8,crown*scale) if cat=='tree' else max(.8,8*scale)
        draw.ellipse((x-radius,y-radius,x+radius,y+radius),fill=COLORS[cat])


def start_markers(image, scene, pixel, labels=False):
    draw = ImageDraw.Draw(image)
    for i,obj in enumerate(scene.starts):
        x,y = pixel((obj['x'],obj['y']))
        r = 11 if labels else 4
        draw.ellipse((x-r,y-r,x+r,y+r),fill=START_COLORS[i%len(START_COLORS)] if labels else None,outline='white',width=2)
        if labels:
            number = next(v for k,_,v in obj['properties'] if k=='waypointName').split('_')[1]
            draw.text((x,y),number,fill='white',font=font(13),anchor='mm')


def atlas(scenes, output, columns=3, crown=16):
    panel_w,panel_h = 500,490
    canvas = Image.new('RGB',(columns*panel_w,math.ceil(len(scenes)/columns)*panel_h),BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for i,scene in enumerate(scenes):
        x,y = (i%columns)*panel_w+20,(i//columns)*panel_h+55
        image,pixel,scale = viewport(scene,460,355,'relief')
        dots(image,scene,pixel,scale,crown)
        start_markers(image,scene,pixel)
        canvas.paste(image,(x,y))
        r = scene.metrics
        draw.text((x,y-37),f'{scene.name} ({scene.source})',font=font(18),fill='white')
        med = r['tree_spacing']['nearest_p10_p50_p90'][1] if r['tree_spacing'] else 'n/a'
        draw.text((x,y+365),f'{scene.extent[0]:,} x {scene.extent[1]:,} | {r["categories"].get("tree",0):,} trees',font=font(14),fill='#dddddd')
        draw.text((x,y+389),f'{r["trees_per_million"]} trees / million area | median spacing {med}',font=font(14),fill='#dddddd')
        draw.text((x,y+413),'Green trees; gray rocks; orange landmarks; white starts',font=font(13),fill='#aabbba')
    canvas.save(output/'placement-atlas.png')


def forest_patches(scenes, output, columns=3, world_size=1000, crown=16):
    canvas = Image.new('RGB',(columns*500,math.ceil(len(scenes)/columns)*515),BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    for i,scene in enumerate(scenes):
        trees = [o for o in scene.objects if o['category']=='tree']
        points = xy(trees)
        if len(points):
            counts = np.zeros(len(points),int)
            for j in range(0,len(points),128):
                counts[j:j+128] = np.sum(np.sum((points[j:j+128,None,:]-points[None,:,:])**2,axis=2)<(world_size/4)**2,axis=1)
            cx,cy = points[np.argmax(counts)]
        else:
            cx,cy = np.asarray(scene.extent)/2
        left,bottom = cx-world_size/2,cy-world_size/2
        scale = 420/world_size
        patch = Image.new('RGB',(420,420),'#303d33')
        def pixel(p):
            return (p[0]-left)*scale,419-(p[1]-bottom)*scale
        local = [o for o in scene.objects if left<=o['x']<left+world_size and bottom<=o['y']<bottom+world_size]
        draw_patch = ImageDraw.Draw(patch)
        for obj in local:
            if obj['category'] not in COLORS:
                continue
            px,py = pixel((obj['x'],obj['y']))
            radius = crown*scale if obj['category']=='tree' else max(1,5*scale)
            draw_patch.ellipse((px-radius,py-radius,px+radius,py+radius),fill=COLORS[obj['category']])
        x,y = (i%columns)*500+20,(i//columns)*515+50
        canvas.paste(patch,(x,y))
        draw.text((x,y-34),scene.name,font=font(18),fill='white')
        draw.text((x,y+430),f'{world_size:g} x {world_size:g} world units | '+('dense-area sample' if trees else 'no living trees'),font=font(14),fill='#aabbba')
        scene.metrics['forest_patch'] = dict(center=[float(cx),float(cy)],world_size=world_size,
                                           selection='most trees within patch-width / 4; first object breaks ties')
    canvas.save(output/'equal-scale-forest-patches.png')


def overlays(image, scene, pixel, scale):
    layer = Image.new('RGBA',image.size)
    draw = ImageDraw.Draw(layer)
    for region in scene.plan.get('regions',[]):
        points = [pixel(p) for p in region['points']]
        color = region.get('color','#738ec0')
        rgb = Image.new('RGB',(1,1),color).getpixel((0,0))
        draw.polygon(points,fill=(*rgb,55),outline=(*rgb,210),width=2)
        draw.text(points[0],region.get('name','region'),fill='white',font=font(14))
    for route in scene.plan.get('routes',[]):
        points = [pixel(p) for p in route['points']]
        color = route.get('color','#80cbd7')
        rgb = Image.new('RGB',(1,1),color).getpixel((0,0))
        width = max(1,round(route.get('width',0)*scale))
        if width>1:
            draw.line(points,fill=(*rgb,55),width=width,joint='curve')
            for x,y in points:
                draw.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=(*rgb,55))
        draw.line(points,fill=(*rgb,230),width=2,joint='curve')
        draw.text(points[0],route.get('name','planned route'),fill='white',font=font(14))
    result = Image.alpha_composite(image.convert('RGBA'),layer).convert('RGB')
    draw = ImageDraw.Draw(result)
    for marker in scene.plan.get('markers',[]):
        x,y = pixel(marker['position'])
        draw.ellipse((x-5,y-5,x+5,y+5),fill=marker.get('color','#ffbc67'),outline='white')
        draw.text((x+8,y),marker.get('name','marker'),font=font(14),fill='white')
    return result


def per_map(scene, output, contour_step):
    directory = output/slug(scene.name)
    directory.mkdir(exist_ok=True)
    w,h = scene.extent
    for mode,filename in (('materials','terrain-overview.png'),('slope','slope.png'),('passability','passability.png')):
        image,pixel,scale = viewport(scene,1400,1100,mode)
        if mode=='materials':
            dots(image,scene,pixel,scale,landmarks=True)
        image.save(directory/filename)
    gray = ((scene.z-scene.z.min())/max(1,float(np.ptp(scene.z)))*255).astype(np.uint8)
    Image.fromarray(np.flipud(gray)).save(directory/'heightmap.png')
    image,pixel,scale = viewport(scene,1400,1100,'materials',contour_step)
    draw = ImageDraw.Draw(image)
    for road in scene.roads:
        draw.line([pixel(p) for p in road],fill='#c9b287',width=3)
    dots(image,scene,pixel,scale,landmarks=True)
    image = overlays(image,scene,pixel,scale)
    start_markers(image,scene,pixel,True)
    plan = Image.new('RGB',(image.width+40,image.height+155),BACKGROUND)
    plan.paste(image,(20,70));draw = ImageDraw.Draw(plan)
    draw.text((20,13),scene.name+' | TERRAIN PLAN',font=font(22),fill='white')
    draw.text((20,43),f'{w:,} x {h:,} world units | contours {contour_step:g} | diagnostic, not a native screenshot',font=font(14),fill='#b4c4bc')
    draw.text((20,image.height+82),'Numbered starts | green trees | gray rocks | orange landmarks | blue water',font=font(14),fill='#dddddd')
    draw.text((20,image.height+108),'Tan: stored roads. Other route/region overlays: supplied design intent, not navigation proof.',font=font(13),fill='#aabbba')
    plan.save(directory/'terrain-plan.png')
    scene.metrics['graphics_directory'] = slug(scene.name)
    scene.metrics['plan_overlay'] = scene.plan


def report(scenes, output, options):
    measurements = dict(schema_version=1,options=options,maps=[s.metrics for s in scenes],
        interpretation='Diagnostic diagrams. Approximate material colors; schematic object sizes; no native rendering or navigation validation.')
    (output/'metrics.json').write_text(json.dumps(measurements,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    rows,links = [],[]
    for scene in scenes:
        r = scene.metrics
        median = r['tree_spacing']['nearest_p10_p50_p90'][1] if r['tree_spacing'] else 'n/a'
        values = (scene.name,scene.source,r['categories'].get('tree',0),median,r['understory_per_tree'],r['categories'].get('rock',0))
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')
        links.append('<h3>'+html.escape(scene.name)+'</h3><p>'+ ' · '.join(
            f'<a href="{slug(scene.name)}/{file}.png">{label}</a>' for file,label in
            (('terrain-plan','Terrain plan'),('terrain-overview','Terrain overview'),('heightmap','Heightmap'),('slope','Slope'),('passability','Stored passability')))+
            '</p><img loading="lazy" src="'+slug(scene.name)+'/terrain-plan.png">')
    page = '''<!doctype html><meta charset="utf-8"><title>Map graphics</title>
<style>body{background:#10181d;color:#e2e8e6;font:17px/1.6 Segoe UI,sans-serif;max-width:1400px;margin:30px auto;padding:20px}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #3c4a49}img{max-width:100%;height:auto}a{color:#91d7d1}</style>
<h1>Map graphics</h1><p>Read-only graphics from serialized native map data. Tree spacing is the median nearest-neighbor distance in world units. Ground cover includes grass, shrubs and ferns. Full-area density includes water and impassable terrain. Unknown templates remain gameplay/other.</p>
<table><tr><th>Map</th><th>Source</th><th>Trees</th><th>Tree spacing</th><th>Ground cover / tree</th><th>Rocks</th></tr>'''+''.join(rows)+'''</table>
<h2>Placement atlas</h2><p>Each map fits its own panel. Object dots are schematic, not model footprints. White rings mark starts.</p><img src="placement-atlas.png">
<h2>Equal-scale forest patches</h2><p>All panels cover the same world extent. Centers select a locally dense area, not average forest coverage; circle size is illustrative and equal between maps.</p><img src="equal-scale-forest-patches.png">
<h2>Terrain plans</h2><p>Material colors approximate texture categories and omit native blends, lighting and art. Contours describe elevation. Slope is geometric rise/run, capped at 1.5 for coloring. Stored passability shows the native terrain flag, with water overlaid; it excludes unit footprints, props and bridge deck traversal. Heightmap images normalize each map to 8-bit grayscale; recover the range from metrics.json. Design overlays do not establish actual routes.</p>'''+''.join(links)+'''<p><a href="metrics.json">Measurements, map hashes and settings</a></p>'''
    (output/'index.html').write_text(page,encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--map',type=Path,help='Single native .map file')
    source.add_argument('--config',type=Path,help='JSON list of maps and optional plan overlays')
    parser.add_argument('--name',help='Title for --map')
    parser.add_argument('--plan',type=Path,help='Optional overlay JSON for --map')
    parser.add_argument('--archive',type=Path,help='Maps.big used by archive entries')
    parser.add_argument('--ini',type=Path,default=GAME_DATA/'data/ini/object',help='Effective object INI directory')
    parser.add_argument('--out',required=True,type=Path,help='Output directory; never writes into input maps')
    parser.add_argument('--columns',type=int,default=3)
    parser.add_argument('--patch-size',type=float,default=1000,help='World extent of equal-scale panels')
    parser.add_argument('--crown-radius',type=float,default=16,help='Illustrative tree-dot radius in world units')
    parser.add_argument('--contour-step',type=float,default=25,help='Elevation interval, or 0 to disable contours')
    parser.add_argument('--overwrite',action='store_true',help='Replace generated graphics in a nonempty output directory')
    args = parser.parse_args(argv)
    if not 1<=args.columns<=6:
        parser.error('--columns must be between 1 and 6')
    for name,minimum in (('patch_size',1),('crown_radius',0),('contour_step',0)):
        value = getattr(args,name)
        if not math.isfinite(value) or value<minimum:
            parser.error(f'--{name.replace("_","-")} must be finite and >= {minimum}')
    if args.config and (args.name or args.plan):
        parser.error('--name and --plan apply only to --map')
    if args.config:
        config = json.loads(args.config.read_text(encoding='utf-8-sig'))
        base = resolve(args.config,Path.cwd()).parent
        specs = config['maps']
    else:
        config = {};base = Path.cwd()
        specs = [dict(name=args.name or args.map.stem,file=str(resolve(args.map,base)),source='map',
                      plan=str(resolve(args.plan,base)) if args.plan else {})]
    if not specs:
        parser.error('Config contains no maps')
    identifiers = [slug(s['name']) for s in specs]
    if len(set(identifiers))!=len(identifiers):
        parser.error('Map names must produce unique output directory names')
    archive = str(resolve(args.archive,Path.cwd())) if args.archive else config.get('archive')
    output = resolve(args.out,Path.cwd())
    if output.exists() and any(output.iterdir()) and not args.overwrite:
        parser.error('Output directory is not empty; choose a new directory or use --overwrite')
    templates = Templates(resolve(args.ini,Path.cwd()))
    scenes = [load_scene(s,base,templates,archive) for s in specs]
    selected = config.get('patch_maps',[s.name for s in scenes])
    if not selected or any(n not in {s.name for s in scenes} for n in selected):
        parser.error('patch_maps must name at least one map from maps')
    output.mkdir(parents=True,exist_ok=True)
    atlas(scenes,output,args.columns,args.crown_radius)
    forest_patches([next(s for s in scenes if s.name==n) for n in selected],output,
                   args.columns,args.patch_size,args.crown_radius)
    for scene in scenes:
        per_map(scene,output,args.contour_step)
    report(scenes,output,dict(columns=args.columns,patch_size=args.patch_size,
           illustrative_crown_radius=args.crown_radius,contour_step=args.contour_step,
           ini_directory=str(resolve(args.ini,Path.cwd()))))
    print(json.dumps(dict(output=str(output),maps=len(scenes),report=str(output/'index.html'))))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
