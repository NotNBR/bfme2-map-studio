"""Convert the supplied height illustration into a playable native terrain grid.

This is terrain-data ingestion, not a replacement/reference image rendering.
Printed labels are excluded; luminance is interpreted as relative relief, with
bridge beds, construction clearings and graded routes authored separately.
"""

from collections import deque
import numpy as np
from PIL import Image, ImageFilter
from mapworkshop.mapkit.earth import fbm, thermal_erosion


def build(k):
    yy,xx=np.indices(k.SHAPE)
    x=(xx-k.BORDER)*10.;y=(yy-k.BORDER)*10.
    with Image.open(k.REFERENCE) as im:
        raw=np.asarray(im.convert('L'),dtype=float).copy()
    # Header obscures the NW skyline; use the corresponding southern outline.
    # Everything to the right of the map (legend and compass) is outside bounds.
    for py in range(100):
        source_y=min(raw.shape[0]-1,1262-py)
        raw[py,:480]=raw[source_y,:480]
    x0,y0,x1,y1=k.REFERENCE_BOUNDS
    sample=Image.fromarray(raw[y0:y1,x0:x1].astype('uint8'))
    source=sample.resize((k.WIDTH,k.HEIGHT),Image.Resampling.BILINEAR)
    # The illustration includes point markers and highlights, not just pure
    # elevation. Blur over their footprint so they cannot become needle peaks.
    luminance=np.asarray(source.filter(ImageFilter.GaussianBlur(4.2)),dtype=float)[::-1].copy()
    inside=np.asarray(source,dtype=float)>53
    # Printed scale ticks and detached characters must never become tiny islands.
    seen=np.zeros(inside.shape,dtype=bool)
    for sy,sx in zip(*np.nonzero(inside)):
        if seen[sy,sx]:continue
        component=[];queue=deque([(sy,sx)]);seen[sy,sx]=True
        while queue:
            py,px=queue.popleft();component.append((py,px))
            for ny,nx in ((py-1,px),(py+1,px),(py,px-1),(py,px+1)):
                if 0<=ny<inside.shape[0] and 0<=nx<inside.shape[1] and inside[ny,nx] and not seen[ny,nx]:
                    seen[ny,nx]=True;queue.append((ny,nx))
        if len(component)<250:
            for py,px in component:inside[py,px]=False
    land_image=Image.fromarray((inside*255).astype('uint8'))
    # Close single-pixel outline cracks; retain the wider waterways and bays.
    land_image=land_image.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    alpha=np.asarray(land_image.filter(ImageFilter.GaussianBlur(1.8)),dtype=float)[::-1]/255
    gray=np.pad(luminance,k.BORDER,constant_values=0)
    shore=np.pad(alpha,k.BORDER,constant_values=0)
    broad=fbm(x,y,820,k.SEED,3)
    fine=fbm(x,y,150,k.SEED+1,3)
    # Broad grayscale foothills carry most of the elevation. High luminance
    # becomes rugged ridges; low-gray valley floors remain suitable for armies.
    relief=480*k.smooth(118,224,gray)**1.18
    z=20+shore*(k.GROUND-20+relief+16*broad+6*fine)
    z=thermal_erosion(z,iterations=6)
    road=np.full(k.SHAPE,np.inf)
    for path in k.reference_routes():
        road=np.minimum(road,k.distance(x,y,path))
    # Grade only narrow passes. Retain the reference's rolling ground around them.
    grade=(1-k.smooth(80,210,road))*k.smooth(.78,.98,shore)
    target=k.GROUND+np.minimum(relief*.18,45)+4*broad
    z=z*(1-grade)+target*grade
    for cx,cy in k.STARTS:
        d=np.hypot(x-cx,y-cy);weight=1-k.smooth(550,800,d)
        z=z*(1-weight)+k.GROUND*weight
    deck=np.zeros(k.SHAPE,dtype=bool)
    abutment=np.zeros(k.SHAPE,dtype=bool)
    for bridge in k.BRIDGES:
        cx,cy=bridge['center'];vx,vy=bridge['axis']
        along=(x-cx)*vx+(y-cy)*vy;across=-(x-cx)*vy+(y-cy)*vx
        for sign in (-1,1):
            longitudinal=along*sign
            weight=(1-k.smooth(85,170,np.abs(across)))*k.smooth(160,240,longitudinal)*(1-k.smooth(390,660,longitudinal))
            z=z*(1-weight)+k.GROUND*weight
            abutment|=(np.abs(across)<70)&(longitudinal>240)&(longitudinal<390)
        bed=(np.abs(along)<155)&(np.abs(across)<92)
        z[bed]=20
        # Conservative authoring-grid proxy inside the documented 76 x 275
        # model half-extents. This is not a replacement for native ramp layers.
        deck|=(np.abs(along)<=275)&(np.abs(across)<=64)
        road=np.minimum(road,k.distance(x,y,bridge['ends']))
    # Preserve the internal hollows without the former bridge's rectangular bed
    # or level abutments. Uneven oval rims blend into the surrounding rock slopes.
    for gap in k.ISLAND_GAPS:
        cx,cy=gap['center']
        radius=np.hypot((x-cx)/190,(y-cy)/235)+.10*fine+.05*broad
        weight=1-k.smooth(.45,1.24,radius)
        for sx,sy in k.STARTS:
            weight*=k.smooth(570,680,np.hypot(x-sx,y-sy))
        z=z*(1-weight)+20*weight
    # Carve a modest inner court, retaining the raised, broken rim of the island.
    cx,cy=k.reference_world((583,631));dist=np.hypot(x-cx,y-cy)
    weight=1-k.smooth(170,330,dist)
    z=z*(1-weight)+k.GROUND*weight
    # Sanctuary buildings receive just enough level terrain for their footprint.
    for p in [(583,466),(583,791)]:
        px,py=k.reference_world(p);d=np.hypot(x-px,y-py)
        w=1-k.smooth(100,185,d);z=z*(1-w)+k.GROUND*w
    dy,dx=np.gradient(z,10);slope=np.hypot(dx,dy)
    blocked=(z<k.WATER+8)|(slope>.78)|((z>470)&(slope>.35))
    blocked[abutment]=False
    labels=np.zeros(k.SHAPE,dtype='u2')
    # Quiet grass is the continuous base; dirt is selective wear, not a road web.
    labels[(road<15+8*fine)&(z>k.WATER)&(slope<.35)&(fine>-.02)]=2
    labels[(z<k.GROUND-35)&(z>k.WATER-18)]=3
    labels[(slope>.36)&(z>k.GROUND+48)]=4
    labels[(slope>.72)&(z>k.GROUND+100)]=5
    labels[(z>455)&(slope<1.6)]=6
    labels[z>550+25*fine]=7
    labels[dist<150]=8
    # Forest bands follow sheltered shoulders and river bends visible in the
    # colored reference. Broad irregular pockets replace small circular groves.
    grove=np.zeros(k.SHAPE)
    centers=[(148,315,77,42),(263,152,43,66),(271,398,48,55),
             (398,545,32,75),(457,111,54,43),(523,364,46,45),
             (103,535,42,36),(212,683,65,28),(650,655,28,41)]
    for cx,cy,rx,ry in centers:
        for sx in (1,-1):
            for sy in (1,-1):
                px,py=k.reference_world((583+(cx-583)*sx,631+(cy-631)*sy))
                g=np.exp(-((x-px)/(rx*7.9))**2-((y-py)/(ry*7.8))**2)
                grove=np.maximum(grove,g)
    grove=np.clip(grove+fbm(x+70*broad,y,270,k.SEED+40,3)*.45,0,1)
    labels[(grove>.58)&(slope<.30)&(road>100)&(z>k.GROUND-20)]=1
    return dict(x=x,y=y,z=z,slope=slope,labels=labels,blocked=blocked,
                deck=deck,road=road,grove=grove)
