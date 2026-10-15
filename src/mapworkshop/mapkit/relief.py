"""Relief helpers, and Ithilien Frontier's authored landforms.

distance_to(mask): the eight-neighbour chamfer distance from every terrain
sample to the nearest masked one, in samples (the Greywater Marches build
uses it). smooth: smoothstep on [0, 1]. sculpt(m):
Ithilien Frontier's new relief over the stock map, with its river beds,
starts and road valleys protected.
"""

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.mapkit.checks.analyze import records
from mapworkshop.formats import sections
from mapworkshop.formats.map import tile_offset


def smooth(a):
    a=np.clip(a,0,1)
    return a*a*(3-2*a)


def distance_to(mask):
    """Two-pass eight-neighbour chamfer distance, in terrain samples."""
    h,w=mask.shape;x=np.arange(w,dtype=float)
    d=np.where(mask,0.,float(h+w))
    for y in range(h):
        if y:
            d[y]=np.minimum(d[y],d[y-1]+1)
            d[y,1:]=np.minimum(d[y,1:],d[y-1,:-1]+2**.5)
            d[y,:-1]=np.minimum(d[y,:-1],d[y-1,1:]+2**.5)
        d[y]=np.minimum.accumulate(d[y]-x)+x
    for y in range(h-1,-1,-1):
        if y<h-1:
            d[y]=np.minimum(d[y],d[y+1]+1)
            d[y,1:]=np.minimum(d[y,1:],d[y+1,:-1]+2**.5)
            d[y,:-1]=np.minimum(d[y,:-1],d[y+1,1:]+2**.5)
        d[y]=np.minimum.accumulate((d[y]+x)[::-1])[::-1]-x
    return d


def sculpt(m):
    t=m.heightmap();h,w=t['height'],t['width'];border=t['border']
    yy,xx=np.indices((h,w));x=(xx-border)*10.;y=(yy-border)*10.
    # Normalize design coordinates to the default authored dimensions.
    sx=(w-2*border)*10/8400;sy=(h-2*border)*10/9530
    u=x/sx;v=y/sy
    old=t['elevations'].astype(float)*.0390625
    water=Image.new('1',(w,h));draw=ImageDraw.Draw(water)
    for river in records(m,'RiverAreas'):
        strips=river['cross_sections']
        for a,b in zip(strips,strips[1:]):
            draw.polygon([(px/10+border,py/10+border) for px,py in
                          [(a[0],a[1]),(a[2],a[3]),(b[2],b[3]),(b[0],b[1])]],fill=1)
    wet=np.array(water,dtype=bool)
    for area in records(m,'StandingWaterAreas'):
        plane=Image.new('1',(w,h))
        ImageDraw.Draw(plane).polygon([(a/10+border,b/10+border) for a,b in area['points']],fill=1)
        wet |= np.array(plane,dtype=bool)&(old<area['water_height']+8)
    shore=distance_to(wet)*10
    weight=smooth((shore-100)/500)
    objects=m.objects();roads=[];pending=None
    for o in objects:
        if o['flags']&2:pending=o
        elif o['flags']&4 and pending:
            roads.append((pending['x'],pending['y'],o['x'],o['y']));pending=None
    road_distance=np.full((h,w),1e6)
    for ax,ay,bx,by in roads:
        dx=bx-ax;dy=by-ay
        q=np.clip(((x-ax)*dx+(y-ay)*dy)/max(1,dx*dx+dy*dy),0,1)
        road_distance=np.minimum(road_distance,np.hypot(x-ax-q*dx,y-ay-q*dy))
    weight*=smooth((road_distance-160)/900)
    starts=[o for o in objects if o['template']=='SkirmishSpawnPoint']
    # Long shoulders keep the protected base clearings from becoming circular
    # cliff bowls where a raised ridge meets the original start elevation.
    for o in starts:weight*=smooth((np.hypot(x-o['x'],y-o['y'])-700)/1800)
    # Broad geological forms, not per-tile random bumps. Heights are world units.
    features=[('western wooded ridge',1650,6650,580,1450,510,-.25),
              ('northern mountain wall',5050,8850,1750,600,740,.05),
              ('eastern escarpment',7700,5550,500,1850,610,.12),
              ('southern spur',4200,850,1100,500,440,-.15),
              ('northern forest hill',3500,6750,820,780,340,.25),
              ('central ridge',4750,5350,800,1150,280,-.5),
              ('eastern watch hill',6900,3450,700,650,300,.15)]
    lift=np.zeros((h,w))
    for name,cx,cy,rx,ry,peak,angle in features:
        dx=u-cx;dy=v-cy;c=np.cos(angle);s=np.sin(angle)
        a=(dx*c+dy*s)/rx;b=(-dx*s+dy*c)/ry
        lift+=peak*np.exp(-.5*(a*a+b*b))
    # A raised, broad ruin terrace and smaller rolling shoulders between ridges.
    r=np.hypot((u-1050)/700,(v-4700)/950)
    lift+=220*(1-smooth((r-.45)/1.2))
    lift+=38*(1+np.sin(u/430+.6*np.sin(v/650))*np.cos(v/530))
    lift+=17*(1+np.sin((u+v)/190)*np.cos((u-v)/310))
    # Recover some prominence lost when the stock hills were expanded laterally.
    lift+=np.maximum(old-95,0)*1.4
    new=old+lift*weight
    raw=np.rint(new/.0390625).clip(0,65535).astype('<u2')
    heights=sections.read(m,'HeightMapData');heights['elevations']=raw;sections.write(m,'HeightMapData',heights)
    dy,dx=np.gradient(new,10);slope=np.hypot(dx,dy)
    b=m.blend();texture=sections.read(m,'BlendTileData');arrays=dict(texture['arrays'])
    rock_threshold=.90+.10*np.sin(u/140)*np.cos(v/170)
    cliff=(slope>rock_threshold)&(new-old>80)&(weight>.2)
    rock=next(tex for tex in b['textures'] if tex['name']=='IthilienCliff03')
    tiles=b['arrays']['tiles'].copy()
    tiles[cliff]=rock['tile_start']+tile_offset(xx[cliff],yy[cliff],rock['cell_size'])
    arrays['tiles']=tiles
    for name in ('blends','three_way','cliffs'):
        arrays[name]=arrays[name].copy();arrays[name][cliff]=0
    blocked=b['arrays']['impassable']|((slope>1.05)&(weight>.2));arrays['impassable']=blocked
    texture['arrays']=arrays;sections.write(m,'BlendTileData',texture)
    playable=(xx>=border)&(xx<w-border)&(yy>=border)&(yy<h-border)
    return dict(features=[f[0] for f in features]+['western ruin terrace','rolling lowland shoulders'],
                old_height_percentiles=np.percentile(old[playable],[10,50,90,99]).tolist(),
                new_height_percentiles=np.percentile(new[playable],[10,50,90,99]).tolist(),
                maximum_height=float(new[playable].max()),
                water_samples_unchanged=bool(np.array_equal(raw[wet],t['elevations'][wet])),
                roads_protected=bool(np.array_equal(raw[road_distance<=160],t['elevations'][road_distance<=160])),
                added_impassable_samples=int(np.count_nonzero(blocked & ~b['arrays']['impassable'].astype(bool))),
                rock_face_samples=int(cliff.sum()))
