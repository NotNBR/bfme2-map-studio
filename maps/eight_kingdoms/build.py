"""Build Eight Kingdoms from a blank native BFME2 document and authored geometry.

The grayscale illustration guides the shoreline and elevation field; the colored
illustration guides woodland and landmarks. Layout coordinates use reference
pixels or a 1000-square drawing, north at the top.
Native water, materials, scenery and walk-on-wall bridges use installed assets.
"""

from mapworkshop.config import GAME_DATA
import argparse
from collections import Counter, deque
import json
import math
from pathlib import Path
import random
import re
import sys
import zipfile

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.mapkit.blank import create, starts, set_heights, set_materials, add_object, water_plane
from mapworkshop.formats import sections
from mapworkshop.formats.map import Map, sha
from mapworkshop.mapkit.checks.analyze import analyze
from mapworkshop.mapkit.cache import cache_entry
from mapworkshop.project import here

PROJECT=here(__file__)   # title, native name, players and description: map.toml
CONFIG=PROJECT.config
NAME=CONFIG['native_name']
TITLE=CONFIG['title']
# Keep the reference terrain at its original scale; expose 120 extra ocean
# tiles on each side inside the native boundary. Larger grids exhausted D3D memory.
WIDTH,HEIGHT,BORDER=(CONFIG[k] for k in ('width','height','border'))
NATIVE_BORDER=CONFIG['native_border']
WORLD_SHIFT = (BORDER-NATIVE_BORDER)*10
SHAPE = (HEIGHT + BORDER * 2, WIDTH + BORDER * 2)
WATER, GROUND = 60., 160.
SEED=CONFIG['seed']
OUT = None   # set by the build pipeline (mapworkshop.project)
CHECK = None
TARGET = None
MOD = GAME_DATA
REFERENCE_BOUNDS = (8, 24, 1148, 1256)
REFERENCE = PROJECT.folder/'references/reference-height.jpg'
START_PIXELS = [(582,109),(1001,218),(1072,628),(1000,1020),
                (582,1149),(171,1020),(94,628),(170,224)]
START_PLAN = [((x-8)/1.14,(y-24)/1.232) for x,y in START_PIXELS]
from maps.eight_kingdoms.materials import PALETTE, COLORS, classify



def world(p):
    return p[0] * WIDTH / 100., (1000 - p[1]) * HEIGHT / 100.


def reference_world(p):
    return world(((p[0]-8)/1.14,(p[1]-24)/1.232))


STARTS = [world(p) for p in START_PLAN]


def smooth(a, b, x):
    t = np.clip((x-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def distance(x, y, points):
    """Minimum distance to an explicitly authored polyline, in world units."""
    result = np.full(x.shape, np.inf)
    for a,b in zip(points, points[1:]):
        ax,ay = a; bx,by = b
        vx,vy = bx-ax,by-ay
        t = np.clip(((x-ax)*vx+(y-ay)*vy)/max(vx*vx+vy*vy, 1), 0, 1)
        result = np.minimum(result, np.hypot(x-ax-t*vx, y-ay-t*vy))
    return result


def bridges():
    # Centers traced from the reference, reflected around its composition center.
    # Native bridge long axis is local Y. Abutments use native, unscaled meshes.
    seeds = [('outer-north',(343,244),(1,0)),
             ('inner-north',(463,426),(1,-1)),
             ('outer-west',(185,500),(.7,-1)),
             ('inner-west',(317,556),(.28,-1)),
             ('citadel-diagonal',(491,563),(1,.65))]
    result = []
    for label,p,v in seeds:
        for sx in (1,-1):
            for sy in (1,-1):
                center = reference_world((583+(p[0]-583)*sx,631+(p[1]-631)*sy))
                direction = np.array([v[0]*sx*9000/1140, -v[1]*sy*9600/1232], dtype=float)
                direction /= np.linalg.norm(direction)
                result.append(dict(name=f'{label}-{sx}-{sy}', center=center,
                    axis=direction.tolist(), ends=[(np.array(center)+direction*d).tolist() for d in (-280,280)]))
    for label,p,v in [('citadel-west',(455,631),(1,0)), ('citadel-east',(711,631),(1,0)),
                      ('north-sanctuary',(583,414),(0,1)), ('south-sanctuary',(583,848),(0,1))]:
        center=reference_world(p);direction=np.array([v[0],-v[1]],dtype=float)
        result.append(dict(name=label,center=center,axis=direction.tolist(),
            ends=[(np.array(center)+direction*d).tolist() for d in (-280,280)]))
    return result


BRIDGES = bridges()
# Retain two irregular internal hollows, without bridge objects or virtual decks.
ISLAND_GAPS = [dict(name=name,center=reference_world(p))
    for name,p in [('north-gap',(583,218)),('south-gap',(583,1044))]]


def reference_routes():
    corner=[[(170,224),(240,260),(277,321),(340,370),(391,418),(428,480),(406,553),(402,631)],
            [(170,224),(242,211),(288,240),(323,244)],
            [(277,321),(244,374),(224,431),(185,500)],
            [(391,418),(420,425),(463,426)],
            [(428,480),(375,507),(335,530),(317,556)],
            [(402,631),(455,631)],[(406,553),(448,539),(491,563)]]
    north=[[(582,109),(569,162),(583,218),(594,267),(582,325),(583,414)],
           [(582,109),(493,138),(454,185),(408,217),(363,244)],
           [(582,325),(531,345),(488,385),(463,426)]]
    west=[[(94,628),(167,597),(217,550),(185,500)],
          [(94,628),(188,615),(263,590),(317,556)]]
    paths=[]
    for raw in (corner,north,west):
        for sx in (1,-1):
            for sy in (1,-1):
                for route in raw:
                    points=[reference_world((583+(px-583)*sx,631+(py-631)*sy)) for px,py in route]
                    # Interpolated paths have gentle bends instead of angular junctions.
                    v=np.array([points[0],*points,points[-1]])
                    curve=[]
                    for i in range(1,len(v)-2):
                        a,b,c,d=v[i-1:i+3]
                        for t in np.linspace(0,1,4,endpoint=False):
                            curve.append(.5*((2*b)+(-a+c)*t+(2*a-5*b+4*c-d)*t*t+(-a+3*b-3*c+d)*t*t*t))
                    paths.append([*curve,points[-1]])
    center=reference_world((583,631))
    for bridge in BRIDGES:
        if bridge['name'].startswith('citadel'):
            paths.append([center,bridge['center']])
    return paths


def terrain():
    import sys
    from maps.eight_kingdoms.terrain import build
    return build(sys.modules[__name__])


def add_water(m):
    # Continue the ocean beyond the heightmap, so tilted and strategic views
    # see surrounding sea instead of the renderer's black clear background.
    points=[(-16000,-16000),(25000,-16000),(25000,25600),(-16000,25600)]
    water_plane(m,'Eight Kingdoms waterways',WATER,points=points,uv_speed=.035)



def grid_point(p):
    return round(p[1]/10)+BORDER, round(p[0]/10)+BORDER


def expose_ocean(m,native_border=NATIVE_BORDER):
    """Include the padded sea inside the engine's visible map boundary."""
    h=sections.read(m,'HeightMapData');shift=(h['border']-native_border)*10
    if shift<0 or len(h['borders'])!=1:raise ValueError('Expected one padded boundary')
    h['border']=native_border;h['borders']=[(h['width']-2*native_border,h['height']-2*native_border)]
    sections.write(m,'HeightMapData',h)
    m.set_objects([dict(o,x=o['x']+shift,y=o['y']+shift) for o in m.objects()])
    return shift


def audit(t):
    """Connectivity including intended bridge decks, not native pathfinding proof."""
    walk=(~t['blocked'])|t['deck']
    seen=np.zeros(SHAPE,dtype=bool)
    root=grid_point(STARTS[0]);seen[root]=True;queue=deque([root])
    while queue:
        y,x=queue.popleft()
        for ny,nx in ((y-1,x),(y+1,x),(y,x-1),(y,x+1)):
            if 0<=ny<SHAPE[0] and 0<=nx<SHAPE[1] and walk[ny,nx] and not seen[ny,nx]:
                seen[ny,nx]=True;queue.append((ny,nx))
    base_checks=[]
    for i,p in enumerate(STARTS,1):
        region=(t['x']-p[0])**2+(t['y']-p[1])**2<=550**2
        base_checks.append(dict(player=i,reachable=bool(seen[grid_point(p)]),
            clear_radius=550,blocked_samples=int(t['blocked'][region].sum()),
            elevation_range=[float(t['z'][region].min()),float(t['z'][region].max())]))
    bridge_checks=[]
    for bridge in BRIDGES:
        bridge_checks.append(dict(name=bridge['name'],
            banks_reachable=[bool(seen[grid_point(p)]) for p in bridge['ends']]))
    result=dict(starts=base_checks,bridges=bridge_checks,
        citadel_reachable=bool(seen[grid_point(reference_world((583,631)))]),
        reachable_samples=int(seen.sum()),native_horde_paths_verified=False)
    if any(not b['reachable'] or b['blocked_samples'] for b in base_checks):
        raise ValueError('A start is disconnected or lacks building space: '+json.dumps(result))
    if not result['citadel_reachable'] or any(not all(b['banks_reachable']) for b in bridge_checks):
        raise ValueError('A bridge bank or the citadel is disconnected: '+json.dumps(result))
    return result


def start_clearance(px,py,footprint):
    """Distance from the conservative sampled footprint to the nearest start."""
    return footprint_clearance(px,py,footprint,STARTS)


def footprint_clearance(px,py,footprint,centers):
    radius=max(1,math.ceil(footprint/10))*10+5
    return min(math.hypot(max(abs(px-x)-radius,0),max(abs(py-y)-radius,0))
               for x,y in centers)


def decorate(m,t):
    rng=random.Random(SEED);placed=Counter();occupied={};placement_checks=[]
    from maps.eight_kingdoms.vegetation import base_layout
    pockets=[p for scene in base_layout(sys.modules[__name__]) for p in scene['building_pockets']]
    text='\n'.join(p.read_text(encoding='cp1252') for p in (MOD/'data/ini/object').rglob('*.ini'))
    valid=set(re.findall(r'^\s*(?:Object|ChildObject|ObjectReskin)\s+(\w+)',text,re.M))
    def put(template,px,py,layer,angle=None,gap=40,protected=True,extra=(),z=0,
            footprint=0,max_rise=None,clearance=130,start_radius=550):
        if template not in valid:raise ValueError('Unknown native asset: '+template)
        if not 20<px<WIDTH*10-20 or not 20<py<HEIGHT*10-20:return False
        iy,ix=grid_point((px,py))
        if protected:
            if t['blocked'][iy,ix] or t['road'][iy,ix]<clearance:return False
            if any(math.hypot(px-a,py-b)<start_radius+60 for a,b in STARTS):return False
            if footprint and start_clearance(px,py,footprint)<=start_radius:return False
            if any(footprint_clearance(px,py,footprint,[(x,y)])<=r for x,y,r in pockets):return False
        rise=0.
        if footprint:
            radius=max(1,math.ceil(footprint/10))
            ground=t['z'][iy-radius:iy+radius+1,ix-radius:ix+radius+1]
            if ground.shape!=(radius*2+1,radius*2+1) or ground.min()<WATER+12:return False
            if protected:
                area=np.s_[iy-radius:iy+radius+1,ix-radius:ix+radius+1]
                if t['blocked'][area].any() or t['road'][area].min()<clearance:return False
            rise=float(np.ptp(ground))
            if max_rise is not None and rise>max_rise:return False
        cell=(int(px//100),int(py//100));n=max(2,math.ceil(gap/100))
        if any(math.hypot(px-a,py-b)<max(gap,g) for yy in range(cell[1]-n,cell[1]+n+1)
               for xx in range(cell[0]-n,cell[0]+n+1) for a,b,g in occupied.get((xx,yy),[])):return False
        add_object(m,template,px,py,rng.random()*math.tau if angle is None else angle,
                   layer=layer,extra=extra,z=z)
        occupied.setdefault(cell,[]).append((px,py,gap));placed[template]+=1
        if footprint:placement_checks.append(dict(template=template,x=px,y=py,footprint=footprint,
            relief=rise,max_relief=max_rise,layer=layer,start_clearance=start_clearance(px,py,footprint),
            required_start_clearance=start_radius,route_clearance=clearance))
        return True
    # Runtime-verified stock bridge model, 550 world units long, native ramp meshes.
    for bridge in BRIDGES:
        px,py=bridge['center'];vx,vy=bridge['axis']
        elevation=t['z'][grid_point((px,py))]
        if not put('GondorIthilienBridge2',px,py,'Bridges',
            angle=math.atan2(vy,vx)-math.pi/2,gap=90,protected=False,z=GROUND-elevation-1,
            extra=[('objectName',3,'EK_Bridge_'+bridge['name'])]):
            raise ValueError('Missing bridge '+bridge['name'])
    # Centerpiece is a neutral keep with a capturable signal fire in its forecourt.
    for tpl,p in [('DolGoldurCastle',(583,624)),('OsgiliathRuin01',(562,607)),
                  ('OsgiliathRuin02',(606,608)),('OsgiliathRuin06',(603,652))]:
        put(tpl,*reference_world(p),'Citadel',angle=0,gap=120 if tpl=='DolGoldurCastle' else 65,protected=False)
    capture=[('originalOwner',3,'PlyrNeutral/teamPlyrNeutral'),('objectTargetable',0,1)]
    put('SignalFire',*reference_world((570,650)),'CentralObjective',gap=70,protected=False,extra=capture)
    for p in [(583,466),(583,791)]:
        put('Inn',*reference_world(p),'Sanctuary',gap=100,protected=False,extra=capture)
    def neutral_site(template,p,layer,extra):
        # Keep each expansion near its intended site while rejecting water,
        # steep foundations and the protected construction circles.
        px,py=p
        offsets=sorted(((dx,dy) for dx in range(-400,401,25) for dy in range(-400,401,25)),
                       key=lambda q:q[0]*q[0]+q[1]*q[1])
        for dx,dy in offsets:
            x,y=px+dx,py+dy;iy,ix=grid_point((x,y));r=8
            if not r<iy<SHAPE[0]-r or not r<ix<SHAPE[1]-r:continue
            region=t['z'][iy-r:iy+r+1,ix-r:ix+r+1]
            if t['blocked'][iy-r:iy+r+1,ix-r:ix+r+1].any() or np.ptp(region)>24:continue
            if any(math.hypot(x-a,y-b)<610 for a,b in STARTS):continue
            if put(template,x,y,layer,gap=115,protected=False,extra=extra):return x,y
        raise ValueError('No safe foundation near '+str(p)+' for '+template)
    # Equal expansion opportunities: one outpost and one creep lair per kingdom.
    expansion=[(447,132),(803,221),(823,492),(803,779),
               (553,868),(197,779),(177,508),(197,221)]
    camps=[(564,140),(770,282),(193,551),(770,718),
           (436,860),(230,718),(807,449),(230,282)]
    for i,p in enumerate(expansion):
        px,py=neutral_site('Outpost',world(p),'ExpansionOutposts',capture)
    for p in camps:
        neutral_site('WargLair',world(p),'CreepCamps',
            [('originalOwner',3,'PlyrCreeps/teamPlyrCreeps'),('objectTargetable',0,1)])
    from maps.eight_kingdoms.scenery import populate
    detail_report=populate(sys.modules[__name__],m,t,put,rng)
    detail_report['foundation_checks']=placement_checks
    (OUT/'detail-placement.json').write_text(json.dumps(detail_report,indent=2))
    return dict(placed)


def preview(t,m=None):
    z=t['z'];dy,dx=np.gradient(z,10);norm=np.sqrt(dx*dx+dy*dy+1)
    shade=np.clip((-.45*dx-.55*dy+.76)/norm,.10,1.15)
    colors=np.array(COLORS)
    rgb=colors[t['labels']].astype(float)*(.45+.72*shade[...,None])
    water=z<WATER
    rgb[water]=np.stack([np.full(z.shape,37.),65+(z/4),76+(z/3)],axis=-1)[water]
    rgb=np.clip(rgb,0,255).astype('u1')
    im=Image.fromarray(rgb).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    draw=ImageDraw.Draw(im)
    def pixel(p):return (p[0]/10+BORDER,SHAPE[0]-1-(p[1]/10+BORDER))
    if m:
        for o in m.objects():
            tpl=o['template'];px,py=pixel((o['x']-WORLD_SHIFT,o['y']-WORLD_SHIFT))
            if tpl.startswith(('Tree','PTree')):
                draw.ellipse((px-2,py-2,px+2,py+2),fill=(35,65,35))
            elif tpl.startswith('Osgiliath') or tpl=='DolGoldurCastle':
                draw.rectangle((px-3,py-3,px+3,py+3),fill=(164,158,134))
    for b in BRIDGES:draw.line([pixel(p) for p in b['ends']],fill=(183,176,154),width=12)
    OUT.mkdir(parents=True,exist_ok=True)
    im.save(OUT/'terrain-overview.png')
    radar=im.crop((NATIVE_BORDER,NATIVE_BORDER,SHAPE[1]-NATIVE_BORDER,SHAPE[0]-NATIVE_BORDER))
    annotated=im.copy();draw=ImageDraw.Draw(annotated)
    colors=['#d74437','#408fe2','#50ba3c','#e1c72e','#982bda','#23c7ba','#e79432','#c644c5']
    for i,p in enumerate(STARTS):
        px,py=pixel(p);draw.ellipse((px-10,py-10,px+10,py+10),fill=colors[i],outline='white',width=2)
        draw.text((px-3,py-5),str(i+1),fill='white')
    draw.rectangle((20,20,350,70),fill='#152127')
    draw.text((31,29),f'{TITLE.upper()}  |  {PROJECT.players} PLAYERS',fill='#e8dfbd')
    draw.text((31,48),'AUTHORED TERRAIN PLAN - NOT A GAME SCREENSHOT',fill='#b6c7c6')
    annotated.save(OUT/'layout.png')
    gray=np.rint(np.clip((z-20)/720,0,1)*255).astype('u1')
    Image.fromarray(gray).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(OUT/'heightmap.png')
    return radar


def checkpoint(m,name):
    data=m.encode();check=Map(data);check.report()
    CHECK.mkdir(parents=True,exist_ok=True);path=CHECK/(name+'.map')
    if path.exists() and path.read_bytes()!=data:
        old=path.read_bytes();history=CHECK/'history';history.mkdir(exist_ok=True)
        (history/(name+'-'+sha(old)[:16]+'.map')).write_bytes(old)
    path.write_bytes(data)
    return dict(stage=name,sha256=sha(data),bytes=len(data))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--terrain-only',action='store_true')
    args=p.parse_args()
    if not (MOD/'data/ini/terrain.ini').exists():
        p.error('Prepare this worktree runtime with tools/bfme_host/prepare_eight_kingdoms.py')
    OUT.mkdir(parents=True,exist_ok=True)
    m=create(WIDTH,HEIGHT,BORDER,title=TITLE,description=PROJECT.description,elevation=GROUND,player_count=PROJECT.players)
    stages=[checkpoint(m,'00-empty')]
    starts(m,STARTS);stages.append(checkpoint(m,'01-eight-starts'))
    print('Sculpting eight realms, ridges and waterways...',flush=True)
    t=terrain();checks=audit(t);material_report=classify(sys.modules[__name__],t)
    set_heights(m,t['z']);add_water(m)
    from maps.eight_kingdoms.presentation import daylight, bridge_audit
    lighting_report=daylight(m)
    set_materials(m,PALETTE,t['labels'],t['blocked'])
    stages.append(checkpoint(m,'02-terrain-water-materials'))
    print('Terrain connectivity and eight construction areas pass.',flush=True)
    placed={} if args.terrain_only else decorate(m,t)
    expose_ocean(m)
    stages.append(checkpoint(m,'03-detailed' if not args.terrain_only else '03-terrain-only'))
    data=m.encode();report=analyze(data)
    bridge_placement=bridge_audit(sys.modules[__name__],Map(data)) if not args.terrain_only else None
    if report['unresolved_sections']:raise ValueError(report['unresolved_sections'])
    target=TARGET
    path=target/(NAME+'.map');path.write_bytes(data)
    (target/'map.ini').write_text(f'; {TITLE}\nWeather\n  HardwareFogEnable = No\nEnd\n'
        'WaterTransparency\n  ReflectionPlaneZ = 60\n  ReflectionOn = Yes\nEnd\n'
        'AIData\n  LowLodTreeName = TreeLowLODGreyHavens\nEnd\n',encoding='ascii')
    radar=preview(t,m).resize((256,256),Image.Resampling.LANCZOS)
    for suffix in ('_art.tga','_pic.tga'):radar.save(target/(NAME+suffix))
    cache_entry(path,m,NAME,TITLE,PROJECT.description,players=PROJECT.players)
    with zipfile.ZipFile(OUT/'Eight-Kingdoms.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(target.iterdir()):
            if item.is_file():archive.write(item,Path(NAME)/item.name)
    report.update(seed=SEED,source_map=None,reference_height_sha256=sha(REFERENCE.read_bytes()),checkpoints=stages,grid_audit=checks,
                  scenery=placed,bridges=BRIDGES,materials=material_report,lighting=lighting_report,
                  bridge_placement=bridge_placement,world_coordinate_offset=WORLD_SHIFT,worldbuilder_verified=False,
                  native_validation_status='not-run-for-this-build',
                  native_horde_paths_verified=False)
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    probes=[]
    for bridge in [BRIDGES[0],BRIDGES[12]]:
        center=np.array(bridge['center'])+WORLD_SHIFT;axis=np.array(bridge['axis'])
        probes.append(dict(name=bridge['name'],source=[*(center-axis*340),GROUND],
                           destination=[*(center+axis*340),GROUND],center=[*center,GROUND]))
    print(json.dumps(dict(map=str(path),sha256=sha(data),objects=report['objects'],
        height_range=report['height_range'],bridges=len(BRIDGES)),indent=2))


if __name__=='__main__':main()
