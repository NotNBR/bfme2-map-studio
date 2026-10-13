"""The Greywater Marches: six-player native terrain from the supplied references."""
from collections import Counter, deque
import json
import math
from pathlib import Path
import random
import re

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from mapworkshop.config import GAME_DATA
from mapworkshop.formats.map import Map, sha
from mapworkshop.mapkit.blank import create, starts, set_heights, set_materials, add_object, terrain_cell_sizes, set_world, water_plane
from mapworkshop.mapkit.cache import cache_entry
from mapworkshop.mapkit.checks.analyze import analyze
from mapworkshop.mapkit.earth import fbm
from mapworkshop.mapkit.variety import spot_random

PROJECT = Path(__file__).parent
OUT = None   # this build's folder for reports (b.work); scenery.py writes there
SCALE = 1.5
WIDTH, HEIGHT, BORDER = 1350, 900, 30
WATER, GROUND, SEED = 145., 195., 101026
STARTS = [(1970,7250),(6470,7690),(11270,7090),(10520,1770),(6100,1390),(1300,2150)]
PALETTE = ['GrassMediumType40', 'GrassMediumType44b', 'IthilienDirt07',
           'SandType3wet', 'RockRohan04', 'CliffMediumType16b', 'CliffMediumType15', 'RocksType3',
           'SnowType1', 'GrassMediumType46', 'GrassMediumType10c', 'RockIthilien01', 'IthilienDirt11',
           'PelargirCrops01', 'PelargirCrops02', 'CropsType3', 'CropsType1']
COLORS = [(123,130,74), (95,110,60), (148,130,92), (154,145,112),
          (113,116,110), (104,107,104), (157,160,151), (129,126,109), (226,228,224),
          (88,98,52), (112,128,66), (121,112,92), (116,98,72),
          (72,64,59), (60,58,45), (112,120,63), (132,133,81)]


def smooth(a, b, v):
    t = np.clip((v-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def blur(a, radius):
    return np.array(Image.fromarray(np.uint8(np.clip(a, 0, 255))).filter(ImageFilter.GaussianBlur(radius)), float)


def gaussian(a, sigma):
    """Float-preserving separable smoothing, with closed map boundaries."""
    radius=math.ceil(sigma*3)
    offsets=np.arange(-radius,radius+1)
    weights=np.exp(-.5*(offsets/sigma)**2);weights/=weights.sum()
    result=a.astype(float)
    for axis in (0,1):
        padding=[(0,0),(0,0)];padding[axis]=(radius,radius)
        padded=np.pad(result,padding,mode='edge');filtered=np.zeros_like(result)
        for i,weight in enumerate(weights):
            selection=[slice(None),slice(None)];selection[axis]=slice(i,i+result.shape[axis])
            filtered+=padded[tuple(selection)]*weight
        result=filtered
    return result


def world(p):
    return p[0]*10, (HEIGHT-1-p[1])*10


def cell(p):
    return round(p[1]/10)+BORDER, round(p[0]/10)+BORDER


def components(mask):
    labels = np.zeros(mask.shape, dtype=np.int32)
    sizes = []
    h, w = mask.shape
    for y, x in zip(*np.nonzero(mask)):
        if labels[y, x]:
            continue
        label = len(sizes)+1
        labels[y, x] = label
        queue = deque([(y, x)])
        size = 0
        while queue:
            a, b = queue.popleft(); size += 1
            for c, d in ((a-1,b), (a+1,b), (a,b-1), (a,b+1)):
                if 0 <= c < h and 0 <= d < w and mask[c,d] and not labels[c,d]:
                    labels[c,d] = label; queue.append((c,d))
        sizes.append(size)
    return labels, sizes


SHORE_CLEARANCE = 3     # dry bank above the waterline stays walkable


def shore_profile(raw, land):
    """Natural river banks from the reference's river mask.

    The bank eases from the land height down to the waterline over a band of
    55..280 units that varies along the river; where it is narrow and
    'steep' it forms a short earth bank, elsewhere a gentle shelf. Below
    the waterline a shallow shelf leads into a channel about 40 units deep.
    """
    from mapworkshop.mapkit.relief import distance_to
    river=blur(raw,1.2)<18          # smoothed edge, no pixel staircase
    outside=distance_to(river)*10
    inside=distance_to(~river)*10
    signed=gaussian(np.where(river,-inside,outside),1.2)
    yy,xx=np.indices(raw.shape); x=xx*10.; y=(raw.shape[0]-1-yy)*10.
    width_noise=fbm(x,y,scale=520,seed=SEED+11,octaves=3)
    steep_noise=fbm(x,y,scale=280,seed=SEED+12,octaves=2)
    width=np.clip(150+120*width_noise,55,280)
    steep=smooth(-.10,.40,steep_noise)
    t=np.clip(signed/width,0,1)
    ease=(t**1.8)*(1-steep)+(1-(1-t)**2.5)*steep
    edge=WATER-1.0
    bank=np.where(land>edge,edge+(land-edge)*ease,land)
    shelf=np.clip(-signed/np.clip(80+45*width_noise,40,140),0,1)
    channel=WATER-1.0-(36+10*steep_noise)*shelf*shelf*(3-2*shelf)
    elevation=np.where(signed>0,bank,channel)
    return elevation,dict(distance=signed,width=width,steep=steep)


(GRASS, GRASS_DARK, DIRT, SAND, ROCK, CLIFF, CRAG, SCREE, SNOW, GRASS_LUSH, GRASS_FRESH, GRAVEL, TRACK,
 PLOUGHED, SPROUTS, CROPS, CROPS_RIPE) = range(17)


def ground_materials(z, slope, x, y):
    """Meadow mosaic of four grasses at several scales, small worn patches,
    and scree/gravel only below actually exposed rock."""
    broad=fbm(x,y,scale=1100,seed=SEED,octaves=3)
    mid=fbm(x+3000,y,scale=330,seed=SEED+61,octaves=3)
    fine=fbm(x,y+3000,scale=95,seed=SEED+62,octaves=2)
    v=.65*broad+.35*mid+.10*fine
    labels=np.full(z.shape,GRASS,dtype='u2')
    labels[v<-.06]=GRASS_DARK
    labels[v>.16]=GRASS_FRESH
    # Darkest grass only in small damp hollows near water, broken by fine noise.
    labels[(z<WATER+22)&(v<.05)&(fine<-.02)&(slope<.25)]=GRASS_LUSH
    # Small worn patches where the meadow dries out.
    labels[(v>.30)&(fine>.22)&(slope<.3)]=DIRT
    # Exposure: rock on steep ground, gravel and scree fanning below it.
    exposed=slope>.55
    near=gaussian(exposed.astype(float),3.0)*smooth(.04,.14,gaussian(exposed.astype(float),18.0))
    broken=fbm(x-800,y+400,scale=70,seed=SEED+63,octaves=2)
    labels[(near>.10+.12*broken)&(slope>.16)&(broken>-.30)]=GRAVEL
    labels[(near>.30+.10*broken)&(slope>.28)&(broken>-.15)]=SCREE
    labels[(slope>.45)&(near>.25)]=ROCK
    labels[slope>.75]=CLIFF
    return labels


def mountain_aprons(labels, z, slope, x, y):
    """Scree and gravel fans around the foot of rock, broken by noise, so
    mountains settle into the meadow instead of ending at a contour."""
    rock=np.isin(labels,[ROCK,CLIFF,CRAG,SNOW])|(z>360)
    # Only real massifs shed aprons; isolated knolls stay grassy.
    massif=gaussian(rock.astype(float),22.0)
    reach=gaussian(rock.astype(float),6.0)*smooth(.06,.18,massif)
    grain=fbm(x,y,scale=120,seed=SEED+71,octaves=3)
    meadow=np.isin(labels,[GRASS,GRASS_DARK,GRASS_LUSH,GRASS_FRESH,DIRT])
    labels[meadow&(reach>.05+.08*grain)&(grain>-.30)]=GRAVEL
    labels[meadow&(reach>.16+.10*grain)&(slope>.10)&(grain>-.20)]=SCREE
    labels[meadow&(reach>.30+.10*grain)&(slope>.22)]=ROCK
    # Lowland hills (outside the big ranges) keep grass on their lower
    # flanks; rock shows only on the steeper upper slopes and tops.
    lowland=(z<330)&(massif<.25)
    hillside=np.isin(labels,[ROCK,SCREE,GRAVEL,CRAG])&lowland
    green=hillside&(slope<.62+.10*grain)&(z<WATER+95+40*grain)
    labels[green&(grain>.15)]=GRASS_DARK
    labels[green&(grain<=.15)]=GRASS
    labels[hillside&~green&(slope<.45)&(grain<-.1)]=GRASS_DARK


def ridged(x, y, scale, seed, octaves=5):
    """Ridged multifractal: sharp crests where the gradient noise crosses zero."""
    total=np.zeros_like(x); weight=1.; norm=0.; signal_weight=np.ones_like(x)
    for i in range(octaves):
        n=1-np.abs(fbm(x,y,scale=scale,seed=seed+i*17,octaves=1))
        n=n*n*signal_weight
        signal_weight=np.clip(n*1.6,0,1)
        total+=n*weight; norm+=weight
        x,y=.8*x-.6*y+.31*scale,.6*x+.8*y-.17*scale
        scale*=.5; weight*=.55
    return total/norm


def meadow_rolling(elevation, shore, mountains):
    """Gentle swells and hollows on the open grassland (up to ~18 units),
    fading out near rivers, starts and the mountain bodies."""
    h,w=elevation.shape
    yy,xx=np.indices(elevation.shape); x=xx*10.; y=(h-1-yy)*10.
    swell=fbm(x+1300,y-900,scale=900,seed=SEED+101,octaves=3)
    ripple=fbm(x-400,y+2100,scale=260,seed=SEED+102,octaves=2)
    keep=smooth(200,600,shore['distance'])*(1-smooth(.05,.35,mountains['body']))
    for px,py in STARTS:
        keep*=smooth(700,1200,np.hypot(x-px,y-py))
    return elevation+(14*swell+4*ripple)*keep


def mountain_relief(raw, elevation, shore):
    """Raise the reference's ranges into ridged mountains.

    Height grows towards each range's core and with the size of the massif,
    so the large edge ranges peak around 700-900 while isolated small hills
    stay hills. Bases, river banks and bridge reaches are left untouched.
    """
    from mapworkshop.mapkit.earth import thermal_erosion
    from mapworkshop.mapkit.relief import distance_to
    yy,xx=np.indices(raw.shape); x=xx*10.; y=(raw.shape[0]-1-yy)*10.
    lum=blur(raw,2.5)
    body=smooth(135,215,lum)
    mass=gaussian(body,25)
    core=distance_to(lum<165)*10
    # Domain warp bends the ridge lines so crests read as natural spurs.
    wx=x+260*fbm(x,y,scale=900,seed=SEED+41,octaves=3)
    wy=y+260*fbm(x+5000,y,scale=900,seed=SEED+42,octaves=3)
    crest=ridged(wx,wy,scale=780,seed=SEED+43,octaves=4)
    height=(55+905*smooth(.12,.55,mass))*smooth(0,650,core)**.85
    uplift=height*(.30+.70*crest)+55*body
    keep=smooth(120,420,shore['distance'])
    for px,py in STARTS:
        keep*=smooth(650,1150,np.hypot(x-px,y-py))
    uplift*=keep
    raised=elevation+uplift
    # A light talus pass removes single-cell spikes without rounding crests.
    eroded=thermal_erosion(raised,iterations=14,talus=1.25)
    raised=raised*(1-body)+eroded*body
    # Isolated knolls away from the big ranges become rounded grassy hills.
    knoll=(1-smooth(.10,.30,mass))*smooth(.02,.10,gaussian(body,6))*keep
    rounded=gaussian(raised,4.5)
    raised=raised*(1-knoll)+np.minimum(raised,rounded+12)*knoll
    return raised,dict(uplift=uplift,body=body)


def mountain_materials(labels, z, slope, x, y):
    """Rock follows steepness; high gentle ground keeps alpine grass with
    scree patches. Thresholds wander with noise so no contour line shows."""
    grain=fbm(x,y,scale=160,seed=SEED+51,octaves=3)
    wander=fbm(x,y,scale=420,seed=SEED+52,octaves=3)
    high=z>330+60*wander
    steep=slope>.42+.12*grain
    labels[high&~steep&(grain>.18)]=SCREE           # scree patches on shelves
    labels[high&~steep&(grain<-.22)]=GRASS_FRESH    # alpine grass pockets
    labels[high&steep]=ROCK                         # broken rock
    labels[high&steep&(grain>.10)]=CRAG             # pale crags
    cliff=gaussian((slope>.95+.15*grain).astype(float),1.2)>.5
    labels[cliff]=CLIFF                             # cliff faces
    snowline=530+50*grain
    # Snow only in coherent fields; single-cell crest strips would blend into
    # a saw-tooth edge (one directional blend per cell).
    snow=((z>snowline)&(slope<.85))|((z>snowline+90)&(slope<1.2))
    snow=gaussian(snow.astype(float),1.6)>.35
    labels[snow]=SNOW


def edge_rim(z, wet, x, y, protected):
    """Rough hills along the playable edge so the land does not stop at a
    cut; river mouths, bases and bridge reaches stay open."""
    from mapworkshop.mapkit.relief import distance_to
    w,h=WIDTH*10,HEIGHT*10
    edge=np.minimum(np.minimum(x,w-x),np.minimum(y,h-y))
    river=distance_to(wet)*10
    keep=smooth(150,420,river)*np.clip(1-4*gaussian(protected.astype(float),20),0,1)
    crest=ridged(x+400,y-700,scale=420,seed=SEED+81,octaves=4)
    along=fbm(x*.6,y*.6,scale=900,seed=SEED+82,octaves=3)
    reach=np.clip(320+300*along,120,650)
    height=(40+190*crest)*np.clip(.55+.9*along,.15,1.2)*(1-smooth(.1,1.,edge/reach))
    lift=height*keep
    return z+lift


def relax_shores(z, wet, x, y, starts, bridges, talus=.40):
    """Talus-relax walls left near the water by grading (bridge abutments,
    base edges); bases and the bridge ramp corridors keep their heights."""
    from mapworkshop.mapkit.earth import thermal_erosion
    from mapworkshop.mapkit.relief import distance_to
    relaxed=thermal_erosion(z,iterations=40,talus=talus)
    near=1-smooth(150,260,distance_to(wet)*10)
    keep=np.zeros(z.shape)
    for px,py in starts:
        keep=np.maximum(keep,1-smooth(420,520,np.hypot(x-px,y-py)))
    for b in bridges:
        px,py=b['center'];vx,vy=b['axis']
        along=np.abs((x-px)*vx+(y-py)*vy);across=np.abs(-(x-px)*vy+(y-py)*vx)
        keep=np.maximum(keep,(1-smooth(300,380,along))*(1-smooth(70,110,across)))
    weight=near*(1-keep)
    return z*(1-weight)+relaxed*weight


def shore_materials(labels, z, slope, x, y):
    """Wet sand at the waterline, a damp earth band with pebbles, then grass.

    Bands follow horizontal distance from the water with broken, noise-driven
    edges; steep banks keep their rock.
    """
    from mapworkshop.mapkit.relief import distance_to
    dist=distance_to(z<WATER)*10
    edge=fbm(x,y,scale=90,seed=SEED+21,octaves=3)
    patches=fbm(x,y,scale=150,seed=SEED+22,octaves=2)
    width=fbm(x,y,scale=600,seed=SEED+23,octaves=2)
    soft=~np.isin(labels,[ROCK,CLIFF,CRAG])
    # Narrow land (islands, spits) keeps a grassy core: the earth band never
    # covers more than the outer third of the way to the land's centre.
    core=gaussian(distance_to(z<WATER)*10,4.0)
    band=np.minimum(55+35*width+20*edge,np.maximum(14,core))
    mud=(dist<band)&soft
    labels[mud]=TRACK
    labels[mud&(patches>.30)&(dist>12)]=SCREE
    labels[(dist<22+12*edge)&soft]=DIRT
    labels[(dist<8+6*edge)&(slope<.5)]=SAND
    # Under water: dark silt with gravel patches; sand only in the shallowest
    # fringe so the transparent edge does not glow orange.
    under=z<WATER-1.5
    labels[under]=TRACK
    labels[under&(patches>.25)]=GRAVEL


def choose_starts(z, water):
    # Clockwise open layout. Search low, dry ground within each reference region.
    anchors = [(round(x*SCALE),round(y*SCALE)) for x,y in
               [(110,115), (390,88), (750,125), (720,460), (365,525), (125,455)]]
    search=round(65*SCALE)
    result = []
    for ax, ay in anchors:
        choices = []
        for py in range(max(65,ay-search), min(HEIGHT-65,ay+search+1), 5):
            for px in range(max(65,ax-search), min(WIDTH-65,ax+search+1), 5):
                region = z[py-55:py+56,px-55:px+56]
                if water[py-55:py+56,px-55:px+56].any():
                    continue
                score = math.hypot(px-ax,py-ay) + .5*np.ptp(region) + .1*region.mean()
                choices.append((score,px,py))
        if not choices:
            raise ValueError(f'No dry construction area near {(ax,ay)}')
        _,px,py = min(choices)
        result.append(world((px,py)))
    return result


def world_anchor(name, x, y, angle, search=60, bank=(30,38,46,54), hop=False):
    """Bridge search anchor from world units: resized-reference pixels (y down)
    and the span direction in pixel space. Island hops search the finished
    shoreline, where the islands they land on exist."""
    return (name, round(x/10), round(HEIGHT-1-y/10), round(-angle) % 180, search, bank, hop)


def crossing_plan(water, raw, hops=False):
    # Search natural narrow reaches near authored strategic crossings.
    # Three lanes per side of the shared middle band, mirrored through the map
    # centre: outer lanes between neighbouring bases, one central lane, and
    # island hops (two short bridges) where no single reach spans a channel.
    # Entries: name, world x, y, world angle of the span, search radius, bank.
    anchors = [world_anchor('northwest',3150,7790,0), world_anchor('upper-east',6750,5985,90),
               world_anchor('northeast',8100,7190,0), world_anchor('western-bend',3075,4865,45),
               world_anchor('lower-west',5625,3665,90), world_anchor('eastern-bend',11850,3815,90),
               world_anchor('east-hop',11990,4300,40,search=18,bank=(3,6),hop=True),
               world_anchor('southeast-hop-north',8220,2250,40,search=18,bank=(3,6),hop=True),
               world_anchor('southeast-hop-south',7775,1770,70,search=18,bank=(3,6),hop=True)]
    result = []
    for name, ax, ay, direction, search, bank, hop in anchors:
        if hop != hops:
            continue
        candidates = []
        for py in range(max(60,ay-search), min(HEIGHT-60,ay+search+1), 3):
            for px in range(max(60,ax-search), min(WIDTH-60,ax+search+1), 3):
                if not water[py,px]:
                    continue
                for angle in range(direction-30, direction+31, 15):
                    a = math.radians(angle); vx,vy = math.cos(a),math.sin(a)
                    ends=[]
                    for sign in (-1,1):
                        for d in range(1,36):
                            y=round(py+sign*vy*d); x=round(px+sign*vx*d)
                            if not water[y,x]:
                                ends.append((d,x,y)); break
                    if len(ends)!=2 or not 8 <= sum(e[0] for e in ends) <= 44:
                        continue
                    # Full banks and low foothills on both sides, not little river islets.
                    valid=True
                    for sign,end in zip((-1,1),ends):
                        # Hops check ground just past each shore; island banks
                        # are short, so their offsets count from the shoreline.
                        for d in ([end[0]+k for k in bank] if hop else bank):
                            for cross in ((-4,0,4) if hop else (-6,0,6)):
                                y=round(py+sign*vy*d+vx*cross); x=round(px+sign*vx*d-vy*cross)
                                if not (0<=y<HEIGHT and 0<=x<WIDTH) or water[y,x] or raw[y,x]>225:
                                    valid=False; break
                            if not valid:break
                        if not valid:break
                    if not valid:continue
                    midpoint = .5*(ends[1][0]-ends[0][0])
                    cx,cy = px+vx*midpoint,py+vy*midpoint
                    score=math.hypot(cx-ax,cy-ay)+abs(sum(e[0] for e in ends)-32)*.7
                    candidates.append((score,cx,cy,vx,vy,sum(e[0] for e in ends)))
        if not candidates:
            raise ValueError('No natural bridge reach near '+name)
        _,px,py,vx,vy,span=min(candidates)
        center=world((px,py)); axis=(vx,-vy)
        result.append(dict(name=name,center=center,axis=axis,water_span=span*10,
                           ends=[(center[0]+axis[0]*d,center[1]+axis[1]*d) for d in (-340,340)]))
    return result


def meander(raw):
    """Gently bend the reference's straight river reaches.

    The luminance image is resampled through a smooth displacement field
    (up to ~110 units) that fades out away from the rivers and around the
    starts, so bases and the land between rivers keep their shape.
    """
    from mapworkshop.mapkit.relief import distance_to
    h,w=raw.shape
    yy,xx=np.indices(raw.shape).astype(float)
    x=xx*10.;y=(h-1-yy)*10.
    river=blur(raw,1.0)<18
    near=1-smooth(150,450,distance_to(river)*10)
    for px,py in STARTS:
        near*=smooth(600,1100,np.hypot(x-px,y-py))
    dx=11*fbm(x,y,scale=1400,seed=SEED+91,octaves=2)*near
    dy=11*fbm(x+7000,y,scale=1400,seed=SEED+92,octaves=2)*near
    sx=np.clip(xx+dx,0,w-1.001);sy=np.clip(yy+dy,0,h-1.001)
    ix,iy=sx.astype(int),sy.astype(int);fx,fy=sx-ix,sy-iy
    return ((1-fy)*((1-fx)*raw[iy,ix]+fx*raw[iy,ix+1])+fy*((1-fx)*raw[iy+1,ix]+fx*raw[iy+1,ix+1]))


def terrain():
    reference=Image.open(PROJECT/'references/heightmap.png').convert('L').resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS)
    raw=meander(np.array(reference,float))
    water=raw<18
    # Reference luminance is elevation, not an exposure mask. A linear transfer
    # retains the mid-grey hills instead of isolating white pixels into needles.
    low=blur(raw,.65)
    elevation=70+1.15*low
    elevation,shore=shore_profile(raw,elevation)
    # Remove short ground ripples selectively. Weighted land-only filtering
    # prevents river beds leaking into the banks; high ridges stay untouched.
    original=elevation.copy()
    valid=(~water).astype(float)
    softened=gaussian(elevation*valid,3.5)/np.maximum(gaussian(valid,3.5),1e-9)
    broad=gaussian(elevation,6)
    by,bx=np.gradient(broad,10);broad_slope=np.hypot(bx,by)
    weight=.88*(1-smooth(.28,.65,broad_slope))*(1-smooth(255,310,elevation))
    weight*=smooth(WATER+22,WATER+52,elevation)*(~water)
    elevation=elevation+np.clip((softened-elevation)*weight,-16,16)
    # The standing water is one plane over the whole map; only the river
    # channels should hold it. Inland hollows below the waterline are lifted
    # to a dry floor, fading in from 60 to 220 units away from the rivers.
    elevation,mountains=mountain_relief(raw,elevation,shore)
    elevation=meadow_rolling(elevation,shore,mountains)
    floor=WATER+14
    lift=smooth(shore['width']+20,shore['width']+180,shore['distance'])
    elevation=elevation+np.maximum(floor-elevation,0)*lift
    measured=(weight>.6)&(original>WATER+50)
    before=(original-gaussian(original,3.5))[measured]
    after=(elevation-gaussian(elevation,3.5))[measured]
    smoothing=dict(radius_world_units=35,strength=.88,measured_cells=int(measured.sum()),
        ripple_rms_before=float(np.sqrt(np.mean(before**2))),
        ripple_rms_after=float(np.sqrt(np.mean(after**2))),
        maximum_change=float(np.max(np.abs(elevation-original))),
        preserved='river beds and shores, high ridges; existing six start positions')
    start_positions=STARTS
    z=np.pad(np.flipud(elevation),BORDER,mode='edge')
    wet=np.pad(np.flipud(water),BORDER,mode='edge')
    yy,xx=np.indices(z.shape); x=(xx-BORDER)*10.; y=(yy-BORDER)*10.
    protected=np.zeros(z.shape,bool); decks=np.zeros(z.shape,bool)
    for px,py in start_positions:
        dist=np.hypot(x-px,y-py)
        target=float(np.median(z[dist<330]))
        blend=(1-smooth(360,820,dist)**.7)*(~wet)
        z=z*(1-blend)+target*blend
        protected|=dist<760
    # Finish the shoreline first (edge hills, slumped banks and the islands
    # they leave), then plan bridges: main reaches on the composed river,
    # island hops on the water as it will be built.
    composed=np.flipud(z[BORDER:-BORDER,BORDER:-BORDER])<WATER
    z=edge_rim(z,wet,x,y,protected)
    z=relax_shores(z,wet,x,y,start_positions,[])
    bridges=[]
    # Main reaches first; island hops are searched on the water left after
    # the main abutments, so they land on the islands as built.
    for hops in (False,True):
        new_bridges=crossing_plan(np.flipud(z[BORDER:-BORDER,BORDER:-BORDER])<WATER if hops else composed,low,hops)
        bridges+=new_bridges
        for b in new_bridges:
            px,py=b['center'];vx,vy=b['axis']
            along=(x-px)*vx+(y-py)*vy; across=-(x-px)*vy+(y-py)*vx
            # Native ramp ends sit on graded stone abutments. River remains below
            # the deck. The embankment fades out wide so it meets the lower,
            # gentler river banks as a natural causeway rather than a wall.
            bank=(1-smooth(390,720,np.abs(along)))*(1-smooth(85,300,np.abs(across)))
            bank*=smooth(160,275,np.abs(along))
            z=z*(1-bank)+GROUND*bank
            # A soft oval scour keeps the river deep under the deck without a
            # rectangular trench showing through the clear shallows.
            oval=np.hypot(along/250,across/150)
            bed=1-smooth(.55,1.0,oval)
            z=z*(1-bed)+np.minimum(z,WATER-35)*bed
            decks|=(np.abs(along)<=285)&(np.abs(across)<=60)
            protected|=(np.abs(along)<760)&(np.abs(across)<210)
    # A nearby approach may feather into a base's outer edge. Restore the dry
    # construction circle last, keeping its bank at the same elevation.
    for px,py in start_positions:
        dist=np.hypot(x-px,y-py)
        target=float(np.median(z[dist<300]))
        blend=(1-smooth(360,820,dist)**.7)*(~wet)
        z=z*(1-blend)+target*blend
    z=relax_shores(z,wet,x,y,start_positions,bridges)
    dy,dx=np.gradient(z,10); slope=np.hypot(dx,dy)
    blocked=(z<WATER+SHORE_CLEARANCE)|(slope>.82)
    proxy=(~blocked)|decks
    # All six bases must share a sizeable land/deck component, no diagonal corner joins.
    connectivity,sizes=components(proxy)
    groups=[int(connectivity[cell(p)]) for p in start_positions]
    if not groups[0] or len(set(groups))!=1:
        raise ValueError('Disconnected six-player terrain: '+str(groups))
    labels=ground_materials(z,slope,x,y)
    mountain_materials(labels,z,slope,x,y)
    mountain_aprons(labels,z,slope,x,y)
    shore_materials(labels,z,slope,x,y)
    return dict(z=z,water=wet,slope=slope,blocked=blocked,labels=labels,x=x,y=y,
                protected=protected,starts=start_positions,bridges=bridges,decks=decks,
                audit=dict(start_components=groups,connected_cells=sizes[groups[0]-1],
                           method='four-neighbour terrain proxy with native bridge footprints',
                           native_paths_verified=False),smoothing=smoothing)


OWN_OUTPOST = 2400      # walking distance from each base to its own outpost
OWN_MARGIN = 1000       # it must be at least this much closer to its owner
# Move vegetation past the game's buffers to full-model templates in map.ini.
# Off: the game crashes loading the map with them (see README, Known issue).
VEGETATION_OVERFLOW = False
# Title, native name, players, description and weather are in map.toml; the
# environment variable GREYWATER_WEATHER overrides the weather for variant builds.
# Per-tree size variety as retail maps carry it: an objectPrototypeScale on
# each tree and shrub (WorldBuilder rolls it from InstanceScaleFuzziness;
# hand-tuned maps such as Fords of Isen II and Isengard spread 0.7..1.3).
# (low, mode, high) of a triangular distribution, drawn like the rotation from
# each object's own spot_random, so neither changes when other placements do.
VEGETATION_SCALE = dict(tree=(0.75, 1.0, 1.3), shrub=(0.8, 1.0, 1.2))


def walk_fields(t, points):
    """Walking-distance fields (20-unit cells) from points over dry land and decks."""
    from mapworkshop.mapkit.checks.strategy import distance_field, STEP
    blocked=t['blocked'][BORDER:-BORDER,BORDER:-BORDER]; decks=t['decks'][BORDER:-BORDER,BORDER:-BORDER]
    s=int(STEP/10); gh,gw=blocked.shape[0]//s,blocked.shape[1]//s
    walk=blocked[:gh*s,:gw*s].reshape(gh,s,gw,s).mean(axis=(1,3))<.5
    walk|=decks[:gh*s,:gw*s].reshape(gh,s,gw,s).any(axis=(1,3))
    return walk,[distance_field(walk,p) for p in points],STEP


def plan_sites(t):
    """Outposts and lairs placed by walking distance, equal for every player.

    Each player gets one outpost about OWN_OUTPOST away that is clearly theirs
    (OWN_MARGIN closer than to anyone else), one contested outpost sits where
    all six walking distances are most even, and a warg lair sits midway on
    the walking route between each pair of neighbouring bases.
    """
    starts=t['starts'];n=len(starts)
    walk,fields,step=walk_fields(t,starts)
    stack=np.stack(fields)
    H,W=walk.shape
    yy,xx=np.indices((H,W));wx=(xx+.5)*step;wy=(yy+.5)*step
    # Foundation-friendly cells: flat, dry, away from bridges and the map edge.
    ok=walk&np.isfinite(stack).all(0)
    zc=t['z'][BORDER:-BORDER,BORDER:-BORDER][::int(step/10),::int(step/10)][:H,:W]
    from mapworkshop.mapkit.relief import distance_to
    rough=np.zeros_like(zc)
    for dy in range(-6,7,3):
        for dx in range(-6,7,3):
            rough=np.maximum(rough,np.abs(np.roll(np.roll(zc,dy,0),dx,1)-zc))
    ok&=(rough<22)&(distance_to(~walk)*step>220)
    edge=np.minimum(np.minimum(wx,W*step-wx),np.minimum(wy,H*step-wy));ok&=edge>500
    # Outposts keep well clear of bridges; creep lairs may guard a bridgehead.
    bridge=np.full((H,W),np.inf)
    for b in t['bridges']:
        bridge=np.minimum(bridge,np.hypot(wx-b['center'][0],wy-b['center'][1]))
    lair_ok=ok&(bridge>450); ok&=bridge>800
    sites=[];taken=[]
    def far(x,y,gap=900):return all(math.hypot(x-a,y-b)>gap for a,b in taken)
    for i in range(n):
        d=stack[i];other=np.min(np.delete(stack,i,axis=0),axis=0)
        cost=np.abs(d-OWN_OUTPOST)+np.where(other-d<OWN_MARGIN,5000,0)+rough*8
        cost[~ok]=np.inf
        for _ in range(400):
            k=np.unravel_index(np.argmin(cost),cost.shape)
            if not np.isfinite(cost[k]):raise ValueError(f'No outpost site for player {i+1}')
            x,y=float(wx[k]),float(wy[k])
            if far(x,y):break
            cost[k]=np.inf
        taken.append((x,y))
        sites.append(dict(player=i+1,template='Outpost',role='own',position=(x,y),
                          distance=round(float(d[k])),margin=round(float(other[k]-d[k]))))
    # Contested centre: most even distances to all players, not too far.
    spread=stack.max(0)-stack.min(0)+.15*stack.mean(0)
    spread[~ok]=np.inf
    for _ in range(400):
        k=np.unravel_index(np.argmin(spread),spread.shape);x,y=float(wx[k]),float(wy[k])
        if far(x,y,1500):break
        spread[k]=np.inf
    taken.append((x,y))
    sites.append(dict(player=0,template='Outpost',role='contested',position=(x,y),
                      distances=[round(float(v)) for v in stack[:,k[0],k[1]]]))
    # Lairs midway between ring neighbours on their shortest walking route.
    for i in range(n):
        j=(i+1)%n
        ring=float(stack[i][tuple(int(v) for v in (starts[j][1]//step,starts[j][0]//step))])
        on_path=stack[i]+stack[j]
        cost=np.abs(stack[i]-stack[j])*3+np.maximum(on_path-ring-600,0)+rough*8
        cost[~lair_ok]=np.inf
        for _ in range(600):
            k=np.unravel_index(np.argmin(cost),cost.shape);x,y=float(wx[k]),float(wy[k])
            if far(x,y,700) and all(math.hypot(x-sx,y-sy)>1400 for sx,sy in starts):break
            cost[k]=np.inf
        taken.append((x,y))
        sites.append(dict(player=i+1,neighbour=j+1,template='WargLair',role='between',position=(x,y),
                          distances=[round(float(stack[i][k])),round(float(stack[j][k]))]))
    return sites


def decorate(m,t):
    rng=random.Random(SEED); placed=Counter(); occupied=[];buckets={};largest_gap=0
    from mapworkshop.render.assets import GameAssets
    assets=GameAssets(); kinds={}
    def vegetation(template):
        if template not in kinds:
            r=assets.template_model(template)
            kinds[template]=None if not r or not r['tree'] else                 'tree' if 'TREE' in r['kinds'] else 'shrub' if 'SHRUB' in r['kinds'] else None
        return kinds[template]
    valid=set(re.findall(r'(?m)^\s*(?:Object|ChildObject|ObjectReskin)\s+(\w+)',
                        '\n'.join(p.read_text(encoding='cp1252') for p in (GAME_DATA/'data/ini/object').rglob('*.ini'))))
    def put(template,px,py,layer,gap=55,extra=(),z=0,angle=None):
        nonlocal largest_gap
        if template not in valid:raise ValueError('Unknown installed template: '+template)
        cx,cy=int(px//100),int(py//100);reach=math.ceil(max(gap,largest_gap)/100)
        if any(math.hypot(px-a,py-b)<max(gap,g) for yy in range(cy-reach,cy+reach+1)
               for xx in range(cx-reach,cx+reach+1) for a,b,g in buckets.get((xx,yy),[])):return False
        kind=vegetation(template);local=spot_random(SEED,template,px,py)
        if kind:
            low,mode,high=VEGETATION_SCALE[kind]
            extra=list(extra)+[('objectPrototypeScale',2,round(local.triangular(low,high,mode),3))]
        add_object(m,template,px,py,local.random()*math.tau if angle is None else angle,
                   layer=layer,extra=extra,z=z)
        occupied.append((px,py,gap));buckets.setdefault((cx,cy),[]).append((px,py,gap))
        largest_gap=max(gap,largest_gap);placed[template]+=1; return True
    for b in t['bridges']:
        px,py=b['center'];vx,vy=b['axis']
        iy,ix=cell((px,py))
        put('GondorIthilienBridge2',px,py,'Bridges',z=GROUND-1-t['z'][iy,ix],
            angle=math.atan2(vy,vx)-math.pi/2,
            extra=[('objectName',3,'Greywater_Bridge_'+b['name'])])
    capture=[('originalOwner',3,'PlyrNeutral/teamPlyrNeutral'),('objectTargetable',0,1)]
    creeps=[('originalOwner',3,'PlyrCreeps/teamPlyrCreeps'),('objectTargetable',0,1)]
    sites=plan_sites(t)
    for site in sites:
        px,py=site['position']
        dist=np.hypot(t['x']-px,t['y']-py); blend=1-smooth(105,160,dist)
        target=float(t['z'][cell((px,py))]);t['z']=t['z']*(1-blend)+target*blend
        t['protected']|=dist<300
        put(site['template'],px,py,'NeutralSites',gap=200,extra=capture if site['template']=='Outpost' else creeps)
    import sys
    from maps.greywater_marches.scenery import populate
    detail=populate(sys.modules[__name__],m,t,put,rng,sites)
    return dict(templates=dict(placed),neutral_sites=sites,total=sum(placed.values()),detail=detail)


def preview(t,m,out,title):
    z=t['z'];dy,dx=np.gradient(z,10);norm=np.sqrt(dx*dx+dy*dy+1)
    light=np.clip((-.45*dx-.5*dy+.78)/norm,.08,1.10)
    rgb=np.array(COLORS)[t['labels']].astype(float)*(.43+.72*light[...,None])
    wet=z<WATER;rgb[wet]=(38,85,105)
    im=Image.fromarray(np.uint8(np.clip(rgb,0,255))).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    def pixel(p):return (p[0]/10+BORDER,z.shape[0]-1-(p[1]/10+BORDER))
    draw=ImageDraw.Draw(im)
    for o in m.objects():
        if o['template'].startswith(('Tree','PTree')):
            px,py=pixel((o['x'],o['y']))
            draw.ellipse((px-2,py-2,px+2,py+2),fill=(44,77,40))
    for b in t['bridges']:draw.line([pixel(p) for p in b['ends']],fill=(190,181,153),width=9)
    im.save(out/'terrain-overview.png')
    radar=im.crop((BORDER,BORDER,WIDTH+BORDER,HEIGHT+BORDER))
    annotated=im.copy();draw=ImageDraw.Draw(annotated)
    colors=['#e35548','#438fe5','#55bd56','#e3cb51','#b56bea','#42c6c3']
    for i,p in enumerate(t['starts']):
        px,py=pixel(p);draw.ellipse((px-9,py-9,px+9,py+9),fill=colors[i],outline='white',width=2)
        draw.text((px-3,py-5),str(i+1),fill='white')
    draw.rectangle((40,38,407,80),fill='#1d2827')
    draw.text((50,45),f'{title.upper()} | {len(t["starts"])} PLAYERS',fill='#f0e7cb')
    draw.text((50,61),'TERRAIN PLAN - NOT AN IN-GAME SCREENSHOT',fill='#b4c4bc')
    annotated.save(out/'layout.png')
    return radar


def build(b):
    """Build the map (see mapworkshop.project): the .map, map.ini and minimap
    go to b.out, plans and height comparisons to b.work, the report to b.report."""
    global OUT
    OUT=b.work
    print('Sculpting the supplied heightmap and grading six construction areas...',flush=True)
    t=terrain()
    project=b.project
    m=create(WIDTH,HEIGHT,BORDER,title=project.title,description=project.description,player_count=project.players)
    starts(m,t['starts'])
    scenery=decorate(m,t)
    # Recheck the final foundations; grading must not cut any approach off.
    dy,dx=np.gradient(t['z'],10)
    t['blocked']=(t['z']<WATER+SHORE_CLEARANCE)|(np.hypot(dx,dy)>.82)
    connected,sizes=components(((~t['blocked'])|t['decks'])&(~t['scenery_solids']))
    groups=[int(connected[cell(p)]) for p in t['starts']]
    if not groups[0] or len(set(groups))!=1:raise ValueError('Disconnected final terrain')
    for site in scenery['neutral_sites']:
        if int(connected[cell(site['position'])])!=groups[0]:raise ValueError('Inaccessible neutral site')
    t['audit']['start_components']=groups
    t['audit']['connected_cells']=sizes[groups[0]-1]
    t['audit']['neutral_sites_connected']=True
    t['audit']['construction_areas']=[]
    for p in t['starts']:
        region=np.hypot(t['x']-p[0],t['y']-p[1])<=350
        relief=float(np.ptp(t['z'][region]))
        if relief>.01 or t['blocked'][region].any():raise ValueError('Uneven or blocked construction area')
        t['audit']['construction_areas'].append(dict(center=p,radius=350,relief=relief))
    set_heights(m,t['z']);set_materials(m,PALETTE,t['labels'],t['blocked'],cell_sizes=terrain_cell_sizes(PALETTE),corner_blends=True)
    water_plane(m,'Greywater rivers',WATER,uv_speed=.035)
    import os
    from mapworkshop.mapkit.weather import ini_block, apply_weather, add_sky
    weather=os.environ.get('GREYWATER_WEATHER',project.weather)
    sky=add_sky(m,weather,WIDTH*10,HEIGHT*10,BORDER*10,
                drop=float(t['z'][cell((WIDTH*5,HEIGHT*5))]-t['z'].min()))
    set_world(m,cameraMaxHeight=30000.)
    # Retail-style rig: low ambient, warm afternoon sun and a cool
    # sky fill from the opposite side give shape to the relief.
    apply_weather(m,weather,sun=dict(ambient=(.16,.16,.15),diffuse=(.90,.81,.66)),
                  fill=dict(ambient=(0.,0.,0.),diffuse=(.17,.27,.35),direction=(-.64,-.54,-.55)))
    # Vegetation past the game's optimized buffers would not be drawn; move
    # the overflow to map-local full-model templates (see mapkit.vegetation).
    from mapworkshop.mapkit.vegetation import plan as vegetation_plan, rename as vegetation_rename
    from mapworkshop.render.assets import GameAssets
    assets=GameAssets()
    def model_texture(model):
        key=assets.model_key(model)
        found=re.search(rb'([A-Za-z0-9_]+\.(?:tga|dds))',assets.read(key),re.I) if key else None
        return found.group(1).decode() if found else None
    renamed,vegetation_ini,vegetation=vegetation_plan(m.objects(),assets.templates,model_texture)
    if VEGETATION_OVERFLOW:
        vegetation_rename(m,renamed)
    else:
        vegetation_ini='';vegetation['full_models']=vegetation['templates']=0
    data=m.encode();report=analyze(data)
    report['vegetation']=vegetation
    report['sky']=sky
    if report['unresolved_sections']:raise ValueError(report['unresolved_sections'])
    ini=(ini_block(weather)+
        f'WaterTransparency\n  ReflectionPlaneZ = {WATER:g}\n  ReflectionOn = No\nEnd\n'
        +('; Vegetation beyond the 1,200-tree and 2,000-shrub buffers, drawn as full models.\n'
          +vegetation_ini+'\n' if vegetation_ini else ''))
    plan=preview(t,m,b.work,project.title)
    path=b.save(data,ini=ini)
    if not (b.out/(project.native_name+'_art.tga')).exists():
        # No GPU for the minimap render: use the terrain plan instead.
        b.save(data,ini=ini,minimap=plan)
    cache_entry(path,m,project.native_name,project.title,project.description,players=project.players)
    report.update(title=project.title,seed=SEED,starts=t['starts'],bridges=t['bridges'],scenery=scenery,
        grid_audit=t['audit'],source_map=None,reference_height_sha256=sha((PROJECT/'references/heightmap.png').read_bytes()),
        reference_landscape_sha256=sha((PROJECT/'references/landscape.png').read_bytes()),
        native_validation_status='pending',worldbuilder_verified=False,smoothing=t['smoothing'])
    # Publish the actual native heights alongside the input so terrain fidelity
    # can be reviewed independently of textures, lighting and perspective.
    native=t['z'][BORDER:BORDER+HEIGHT,BORDER:BORDER+WIDTH]
    normalized=np.uint8(np.clip((np.flipud(native)-70)/1.15,0,255))
    b.image('actual-heightmap.png',Image.fromarray(normalized))
    supplied=Image.open(PROJECT/'references/heightmap.png').convert('L').resize((WIDTH,HEIGHT),Image.Resampling.LANCZOS)
    comparison=Image.new('RGB',(WIDTH*2,HEIGHT+30),'#202623')
    comparison.paste(supplied.convert('RGB'),(0,30))
    comparison.paste(Image.fromarray(normalized).convert('RGB'),(WIDTH,30))
    draw=ImageDraw.Draw(comparison)
    draw.text((15,10),'SUPPLIED HEIGHTMAP',fill='white')
    draw.text((WIDTH+15,10),'ACTUAL MAP HEIGHTS - LOCAL BASE / BRIDGE GRADING',fill='white')
    b.image('heightmap-comparison.png',comparison)
    report['height_conversion']=dict(method='linear: z = 70 + 1.15 * luminance',
        reference_smoothing_pixels=.65,local_edits='selective playable-ground ripple smoothing, river shores, bases, bridge banks and neutral foundations')
    # Walking-distance fairness: free-for-all rush distances must stay even
    # and every player's own outpost must stay clearly theirs.
    from mapworkshop.mapkit.checks.strategy import analyse
    strategy=analyse(Map(data),[[1,2,3],[4,5,6]])[0]
    rush=[p['nearest_opponent'] for p in strategy['players']]
    margins=[max(p['Outpost']['owned_margins'] or [0]) for p in strategy['players']]
    report['strategy']=dict(nearest_opponent=rush,own_outpost_margin=margins,
        territory_share=[p['territory_share'] for p in strategy['players']],
        team_nearest_enemy=[t['nearest_enemy'] for t in strategy['teams']])
    if max(rush)-min(rush)>400 or min(margins)<OWN_MARGIN:
        raise ValueError(f'Unfair layout: rush {rush}, own outpost margins {margins}')
    b.report.update(report)
    print(json.dumps(dict(map=str(path),sha256=sha(data),objects=report['objects'],
                         height_range=report['height_range'],bridges=len(t['bridges'])),indent=2))


def sites_position(scenery,player):
    return next(s['position'] for s in scenery['neutral_sites'] if s.get('player')==player and s['template']=='Outpost')
