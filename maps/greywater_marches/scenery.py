"""Sheltered woods, varied edges, slope-toe geology and small outpost scenes.

Uses native optimized tree assets and preserves broad navigable corridors.
Placement is deterministic and checked against terrain and model footprints.
"""
from collections import Counter
import heapq
import json
import math
import random

import numpy as np
from PIL import Image, ImageDraw


def corridors(k,t,sites):
    walk=(~t['blocked'])|t['decks']
    stride=4;coarse=walk[::stride,::stride]
    z=t['z'][::stride,::stride];slope=t['slope'][::stride,::stride]
    from mapworkshop.mapkit.earth import fbm
    wander=fbm(t['x'][::stride,::stride],t['y'][::stride,::stride],scale=500,seed=k.SEED+511,octaves=3)
    cost=1+slope*4+np.maximum(z-250,0)/35+.8*(wander+1)
    h,w=coarse.shape
    def node(p):
        yy,xx=k.cell(p);a,b=round(yy/stride),round(xx/stride)
        candidates=[(math.hypot(c-a,d-b),c,d) for c in range(max(0,a-6),min(h,a+7))
                    for d in range(max(0,b-6),min(w,b+7)) if coarse[c,d]]
        if not candidates:raise ValueError('No route endpoint near '+str(p))
        _,a,b=min(candidates);return a,b
    def path(a,b):
        start,goal=node(a),node(b)
        queue=[(0,0,start)];distances={start:0};previous={}
        while queue:
            _,score,current=heapq.heappop(queue)
            if score!=distances.get(current):continue
            if current==goal:
                nodes=[current]
                while current!=start:current=previous[current];nodes.append(current)
                return [(d*stride,c*stride) for c,d in reversed(nodes)]
            c,d=current
            for e,f in ((c-1,d),(c+1,d),(c,d-1),(c,d+1),(c-1,d-1),(c-1,d+1),(c+1,d-1),(c+1,d+1)):
                if not (0<=e<h and 0<=f<w and coarse[e,f]):continue
                # A sampled node pair may straddle a narrow water/sloped barrier.
                segment=walk[min(c,e)*stride:max(c,e)*stride+1,min(d,f)*stride:max(d,f)*stride+1]
                if not segment.all():continue
                step=1.4142 if (e!=c and f!=d) else 1.0
                candidate=score+.5*(cost[c,d]+cost[e,f])*step
                if candidate<distances.get((e,f),math.inf):
                    distances[e,f]=candidate;previous[e,f]=current
                    heapq.heappush(queue,(candidate+math.hypot(e-goal[0],f-goal[1]),candidate,(e,f)))
        raise ValueError('No protected terrain route between '+str((a,b)))
    pairs=[(p,k.STARTS[(i+1)%6]) for i,p in enumerate(k.STARTS)]
    # Routes from each site's nearest start keep its approach clear.
    pairs += [(min(k.STARTS,key=lambda p:math.dist(p,s['position'])),s['position']) for s in sites]
    pairs += [(b['ends'][0],b['ends'][1]) for b in t['bridges']]
    mask=Image.new('L',(walk.shape[1],walk.shape[0]));draw=ImageDraw.Draw(mask)
    track=Image.new('L',(walk.shape[1],walk.shape[0]));worn=ImageDraw.Draw(track)
    routes=[]
    for i,(a,b) in enumerate(pairs):
        points=path(a,b);draw.line(points,fill=255,width=36)
        routes.append(dict(source=a,destination=b,length=sum(math.dist(p,q)*10 for p,q in zip(points,points[1:]))))
        # Worn tracks: base-to-base roads are wider than spurs to outposts.
        routes[-1]['points']=chaikin(points[::3]+[points[-1]],4)
    main=[r['points'] for r in routes[:6]]
    main_mask=Image.new('L',(walk.shape[1],walk.shape[0]));ImageDraw.Draw(main_mask).line([],fill=0)
    md=ImageDraw.Draw(main_mask)
    for pts in main:md.line(pts,fill=255,width=24)
    near_main=np.asarray(main_mask)>0
    for i,r in enumerate(routes):
        pts=r['points']
        if i>=6:
            # Spurs and bridge approaches are drawn only where they leave the
            # main road network, so no doubled-back hairpins appear.
            keep=[p for p in pts if not near_main[min(int(p[1]),near_main.shape[0]-1),min(int(p[0]),near_main.shape[1]-1)]]
            if len(keep)<2:continue
            pts=keep
        worn.line(pts,fill=255 if i<6 else 170,width=5 if i<6 else 3,joint='curve')
    t['tracks']=np.asarray(track,float)/255
    return np.array(mask)>0,routes


def chaikin(points, rounds):
    for _ in range(rounds):
        out=[points[0]]
        for (ax,ay),(bx,by) in zip(points,points[1:]):
            out += [(.75*ax+.25*bx,.75*ay+.25*by),(.25*ax+.75*bx,.25*ay+.75*by)]
        out.append(points[-1]);points=out
    return points


def paint_tracks(k,t):
    """Worn dirt tracks along the main routes, broken and feathered by noise."""
    from mapworkshop.mapkit.earth import fbm
    soft=k.gaussian(t['tracks'],1.6)
    grain=fbm(t['x'],t['y'],scale=60,seed=k.SEED+501,octaves=2)
    gaps=fbm(t['x'],t['y'],scale=400,seed=k.SEED+502,octaves=2)
    ground=(t['z']>k.WATER+2)&~np.isin(t['labels'],[4,5,6,8])&(t['slope']<.45)
    worn=soft*(1+.6*grain)*np.clip(1.1+gaps,0.3,1.2)
    # Roads fade out at the edge of each construction area.
    for px,py in k.STARTS:
        worn*=1-np.exp(-((np.hypot(t['x']-px,t['y']-py)/420)**4))
    # Trampled fringe: dry grass breaking into the earth at the edges.
    fray=fbm(t['x']+77,t['y']-55,scale=28,seed=k.SEED+503,octaves=2)
    t['labels'][ground&(worn>.18)&(worn<=.34)&(fray>.05)]=10
    t['labels'][ground&(worn>.30+.10*fray)]=12
    t['labels'][ground&(worn>.55+.08*fray)]=2
    return int((ground&(worn>.30)).sum())


# Farmland marked in the map viewer (freehand mark 2): the outline in map
# units, x east and y north. It is a guide: fields are laid out as straight
# plots and keep or lose whole rows where they meet it.
FARMLAND=[(5878,4425),(5762,4458),(5661,4464),(5553,4456),(5449,4466),(5389,4594),(5318,4699),(5230,4789),
          (5122,4873),(5007,4897),(4903,4860),(4791,4832),(4675,4800),(4560,4805),(4464,4861),(4402,4946),
          (4358,5084),(4345,5208),(4393,5333),(4484,5454),(4564,5528),(4655,5618),(4762,5658),(4898,5678),
          (5009,5682),(5135,5750),(5246,5786),(5341,5730),(5429,5597),(5505,5471),(5586,5389),(5692,5328),
          (5773,5242),(5830,5150),(5870,5029),(5886,4898),(5935,4802),(5985,4692)]
# The farmstead at pin 1, on the south edge of the fields: a levelled yard,
# buildings around it and a fenced paddock in the hollow to the south.
FARMSTEAD=(4872,4869)
# Buildings: template, offset east and north of the farmstead centre.
FARM_BUILDINGS=[('RohanHouse04',-80,55),('RohanHouse01',85,60),('RohanHouse05',110,-40),
                ('RohanHouse03',-110,-35),('RohanHouse02',-175,60)]
# Paddock corners as offsets: west, south, east, north.
PADDOCK=(-170,-330,40,-180)


def level_farmstead(k,t):
    """Level the farmyard and ease it into the surrounding ground."""
    px,py=FARMSTEAD;d=np.hypot(t['x']-px,t['y']-py)
    target=float(np.median(t['z'][d<150]))
    blend=1-k.smooth(150,280,d)
    t['z']=t['z']*(1-blend)+target*blend


def farmstead_area(t):
    px,py=FARMSTEAD;a,b,c,d=PADDOCK
    yard=np.hypot(t['x']-px,t['y']-py)<250
    paddock=(t['x']>=px+a-40)&(t['x']<px+c+40)&(t['y']>=py+b-40)&(t['y']<py+d+40)
    return yard|paddock


def longest_run(keep):
    """Start and end of the longest run of True values."""
    best=(0,0);start=None
    for i,v in enumerate(list(keep)+[False]):
        if v and start is None:start=i
        elif not v and start is not None:
            if i-start>best[1]-best[0]:best=(start,i)
            start=None
    return best


def farmland_plan(k,t):
    """Plots for the marked farmland, and the area they reserve.

    Columns of plots run north-south, each split into fields of its own
    lengths, some worked as two or three narrow strips, with grass balks
    between them. A plot near the marked outline keeps only the rows and
    columns that lie mostly inside it, so field ends are straight edges,
    stepped plot by plot, rather than the drawn curve. Steep ground, water,
    worn tracks and the farmstead stay clear. The textures' furrows run
    east-west. A separate random stream keeps the rest of the map unchanged.
    """
    from mapworkshop.mapkit.relief import distance_to
    rng=random.Random(k.SEED+800)
    h,w=t['z'].shape
    outline=Image.new('L',(w,h))
    ImageDraw.Draw(outline).polygon([(x/10+k.BORDER,y/10+k.BORDER) for x,y in FARMLAND],fill=255)
    area=np.asarray(outline)>0
    farm=farmstead_area(t)
    ground=(t['z']>k.WATER+10)&(t['slope']<.32)&(t['tracks']<.2)&~t['protected']&(distance_to(farm)*10>50)
    usable=area&ground
    xs,ys=[p[0] for p in FARMLAND],[p[1] for p in FARMLAND]
    crops=[k.PLOUGHED,k.SPROUTS,k.CROPS,k.CROPS_RIPE,k.GRASS_FRESH]   # the last is fallow
    def fit(x0,y0,x1,y1):
        """The plot's cell rectangle, trimmed to the rows and columns mostly inside."""
        r0,r1=round(y0/10)+k.BORDER,round(y1/10)+k.BORDER
        c0,c1=round(x0/10)+k.BORDER,round(x1/10)+k.BORDER
        sub=usable[r0:r1,c0:c1]
        if sub.size==0 or sub.mean()<.25:return None
        a,b=longest_run(sub.mean(1)>.6)
        c,d=longest_run(sub[a:b].mean(0)>.6) if b>a else (0,0)
        if b-a<9 or d-c<8:return None
        return (r0+a,r0+b,c0+c,c0+d)
    plots=[];x=min(xs)-rng.uniform(0,150)
    while x<max(xs):
        width=rng.uniform(110,300);y=min(ys)-rng.uniform(0,300)
        while y<max(ys):
            length=rng.uniform(200,460)
            strips=rng.choices([1,2,3],weights=[6,2,1])[0] if width>180 else 1
            for i in range(strips):
                # Balks: the two outer cell rows of each plot stay grass.
                cells=fit(x+width*i/strips+20,y+20,x+width*(i+1)/strips,y+length)
                if cells:plots.append(dict(cells=cells,crop=rng.choices(crops,weights=[3,3,2,2,1.5])[0]))
            y+=length
        x+=width
    fields=np.zeros(area.shape,bool)
    for p in plots:
        r0,r1,c0,c1=p['cells'];fields[r0:r1,c0:c1]|=ground[r0:r1,c0:c1]
    reserve=(distance_to(fields)*10<40)|farm
    return dict(plots=plots,fields=fields,reserve=reserve)


def marked_farmland(k,t,plan,place):
    """Paint the planned plots, with hay rows on ploughed and sprouting plots,
    crop piles in the green ones and fence runs along outer field edges."""
    rng=random.Random(k.SEED+803)
    fields=plan['fields']
    for p in plan['plots']:
        r0,r1,c0,c1=p['cells']
        t['labels'][r0:r1,c0:c1][fields[r0:r1,c0:c1]]=p['crop']
    def field(x,y):
        iy,ix=k.cell((x,y));return bool(fields[iy,ix])
    fences=0
    for p in plan['plots']:
        r0,r1,c0,c1=p['cells']
        a,b,c,d=(c0-k.BORDER)*10,(r0-k.BORDER)*10,(c1-k.BORDER)*10,(r1-k.BORDER)*10
        if p['crop'] in (k.PLOUGHED,k.SPROUTS) and rng.random()<.5:
            # A row of hay across the middle of the plot.
            y=rng.uniform(b+.35*(d-b),b+.65*(d-b));step=rng.uniform(38,55)
            for x in np.arange(a+30,c-25,step):
                if field(x,y):
                    place(rng.choice(['Haystack','CropBundle2','CropBundle3','CropBundle']),x+rng.uniform(-6,6),
                          y+rng.uniform(-8,8),'Farmland',gap=30,footprint=12,max_rise=6,soft=True)
        elif p['crop'] in (k.CROPS,k.CROPS_RIPE) and rng.random()<.3:
            x,y=rng.uniform(a+30,c-30),rng.uniform(b+30,d-30)
            if field(x,y):place('CropPile',x,y,'Farmland',gap=30,footprint=12,max_rise=6,soft=True)
        # Fences along edges that face open ground, not a neighbouring field.
        for (ex0,ey0,ex1,ey1),(ox,oy),angle in [((a,b,c,b),(0,-1),0.),((a,d,c,d),(0,1),0.),
                                                 ((a,b,a,d),(-1,0),math.pi/2),((c,b,c,d),(1,0),math.pi/2)]:
            n=max(1,round(math.hypot(ex1-ex0,ey1-ey0)/32))
            points=[(ex0+(ex1-ex0)*(i+.5)/n+ox*10,ey0+(ey1-ey0)*(i+.5)/n+oy*10) for i in range(n)]
            outer=[q for q in points if not field(q[0]+ox*30,q[1]+oy*30)]
            if len(outer)<.7*n or rng.random()>.45:continue
            for x,y in outer:
                if place(rng.choices(['ShireFence01','ShireFence02','ShireFence03'],weights=[4,2,1])[0],x,y,
                         'Farmland',gap=20,footprint=14,max_rise=8,angle=angle):
                    fences+=1
    return dict(plots=len(plan['plots']),cells=int(fields.sum()),fence_segments=fences,
                crops=dict(Counter(k.PALETTE[p['crop']] for p in plan['plots'])))


def farmstead(k,t,place):
    """Farmhouse, barn and outbuildings around a worn yard, carts, hay and
    stores, chickens, and sheep, cows, pigs and horses in a fenced paddock,
    composed like the farms on the retail Rohan map."""
    from mapworkshop.mapkit.earth import fbm
    rng=random.Random(k.SEED+810)
    px,py=FARMSTEAD
    d=np.hypot(t['x']-px,t['y']-py)
    wear=fbm(t['x']+600,t['y']-300,scale=90,seed=k.SEED+811,octaves=3)
    ground=(t['z']>k.WATER+2)&(t['slope']<.45)
    t['labels'][ground&(d<175+50*wear)]=k.TRACK
    t['labels'][ground&(d<120+45*wear)]=k.DIRT
    placed=Counter()
    def add(template,x,y,**kw):
        if place(template,px+x,py+y,'Farmstead',**kw):placed[template]+=1
    for template,x,y in FARM_BUILDINGS:
        # The long side faces the yard.
        add(template,x,y,gap=60,footprint=45,max_rise=12,solid=45,angle=math.atan2(y,x))
    for template,x,y,angle in [('Cart01',30,95,.3),('Cart02',-35,-80,2.0),('FeedingTroughs',140,10,math.pi/2)]:
        add(template,x,y,gap=25,footprint=20,max_rise=8,angle=angle,soft=True)
    for template,n,(x,y),spread in [('Haystack',3,(120,105),30),('CropBundle3',2,(150,70),20),('CropPile',2,(-25,105),25),
                                    ('Barrel',4,(-45,25),18),('Crate01',3,(55,-15),18),('Chicken',5,(-20,0),35)]:
        for _ in range(n):
            for _try in range(12):
                if place(template,px+x+rng.gauss(0,spread),py+y+rng.gauss(0,spread),'Farmstead',
                         gap=16,footprint=8,max_rise=8,soft=True):
                    placed[template]+=1;break
    add('Amb_VillageChickens',-20,0,gap=0,footprint=4,max_rise=99,soft=True)
    # The paddock: a fence round it with a gate towards the yard.
    a,b,c,e=PADDOCK
    edges=[((a,b),(c,b),0.),((a,e),(c,e),0.),((a,b),(a,e),math.pi/2),((c,b),(c,e),math.pi/2)]
    for (x0,y0),(x1,y1),angle in edges:
        n=max(1,round(math.hypot(x1-x0,y1-y0)/32))
        for i in range(n):
            x,y=x0+(x1-x0)*(i+.5)/n,y0+(y1-y0)*(i+.5)/n
            if y0==y1==e and abs(x-(a+c)/2)<35:continue
            add(rng.choice(['ShireFence01','ShireFence01','ShireFence02']),x,y,gap=20,footprint=14,max_rise=10,angle=angle)
    for template,n in [('Sheep',6),('Cow',3),('Pig',3),('HorseGrazing2',2),('FeedingTroughs',2)]:
        for _ in range(n):
            for _try in range(20):
                x,y=rng.uniform(a+25,c-25),rng.uniform(b+25,e-25)
                if place(template,px+x,py+y,'Farmstead',gap=22,footprint=10,max_rise=10,soft=True):
                    placed[template]+=1;break
    return dict(centre=FARMSTEAD,objects=dict(placed))


def populate(k,m,t,put,rng,sites):
    # Height thresholds below are measured from the waterline. They were tuned
    # for water at 135; after raising it to 156 they keep the same absolute
    # dry-ground heights (e.g. woodland above 183).
    level_farmstead(k,t)
    dy,dx=np.gradient(t['z'],10);t['slope']=np.hypot(dx,dy)
    t['blocked']=(t['z']<k.WATER+8)|(t['slope']>.82)
    routes,route_report=corridors(k,t,sites)
    track_cells=paint_tracks(k,t)
    # The marked farmland is reserved; only its own fields and props go there.
    farm_plan=farmland_plan(k,t);t['farmland']=farm_plan['reserve']
    t['scenery_solids']=np.zeros(t['z'].shape,bool)
    counts=Counter();checks=[]
    def place(template,x,y,layer,gap=50,footprint=8,max_rise=7,solid=0,angle=None,offset=0,site=False,soft=False):
        if not (100<x<k.WIDTH*10-100 and 100<y<k.HEIGHT*10-100):return False
        iy,ix=k.cell((x,y));r=max(1,math.ceil(footprint/10))
        selection=np.s_[iy-r:iy+r+1,ix-r:ix+r+1]
        patch=t['z'][selection]
        # Soft ground cover (shrubs, tufts) never blocks movement, so it may
        # sit inside route corridors, but not on the worn track itself.
        on_route=(t['tracks'][selection]>.2).any() if soft else routes[selection].any()
        if patch.min()<k.WATER+10 or t['blocked'][selection].any() or on_route:return False
        if t['protected'][selection].any() and not site:return False
        if t['farmland'][selection].any() and layer not in ('Farmland','Farmstead'):return False
        if site:
            if any(math.dist((x,y),p)<760+footprint for p in k.STARTS):return False
            for b in t['bridges']:
                vx,vy=b['axis'];px,py=b['center']
                if abs((x-px)*vx+(y-py)*vy)<760+footprint and abs(-(x-px)*vy+(y-py)*vx)<210+footprint:return False
        relief=float(np.ptp(patch))
        if relief>max_rise:return False
        if not put(template,x,y,layer,gap=gap,z=offset,angle=angle):return False
        counts[layer]+=1
        checks.append(dict(template=template,position=(x,y),layer=layer,footprint=footprint,
                           relief=relief,max_relief=max_rise,solid_radius=solid))
        if solid:
            radius=math.ceil(solid/10)+1
            yy,xx=np.indices((radius*2+1,radius*2+1))
            disk=((xx-radius)*10)**2+((yy-radius)*10)**2<=(solid+7)**2
            t['scenery_solids'][iy-radius:iy+radius+1,ix-radius:ix+radius+1]|=disk
        return True
    eligible=(t['z']>k.WATER+27)&(t['z']<280)&(t['slope']<.27)&(~t['protected'])&(~routes)
    centers=[]
    desired=[]
    for i,p in enumerate(k.STARTS):
        heading=math.atan2(k.HEIGHT*5-p[1],k.WIDTH*5-p[0])+.70*(-1 if i%2 else 1)
        desired.append((p[0]+math.cos(heading)*1230,p[1]+math.sin(heading)*1230))
    desired += [(u*k.WIDTH*10,v*k.HEIGHT*10) for u,v in
                [(.29,.79),(.48,.63),(.71,.78),(.81,.60),(.32,.27),(.51,.18),(.78,.24),(.56,.46)]]
    for i,(px,py) in enumerate(desired):
        candidates=[]
        for oy in range(-800,801,80):
            for ox in range(-800,801,80):
                x,y=px+ox,py+oy
                if not (350<x<k.WIDTH*10-350 and 350<y<k.HEIGHT*10-350):continue
                iy,ix=k.cell((x,y))
                if not eligible[iy,ix] or any(math.dist((x,y),a['center'])<650 for a in centers):continue
                candidates.append((math.hypot(ox,oy)+t['slope'][iy,ix]*300,x,y))
        if not candidates:raise ValueError('No sheltered woodland near '+str((px,py)))
        _,x,y=min(candidates)
        centers.append(dict(center=(x,y),radii=(rng.uniform(480,790),rng.uniform(340,590)),
                            rotation=rng.random()*math.tau,strength=.83 if i<6 else 1.08,trees=0))
    grove=np.zeros(t['z'].shape)
    for c in centers:
        px,py=c['center'];a=c['rotation'];rx,ry=c['radii']
        u=(t['x']-px)*math.cos(a)+(t['y']-py)*math.sin(a)
        v=-(t['x']-px)*math.sin(a)+(t['y']-py)*math.cos(a)
        grove=np.maximum(grove,c['strength']*np.exp(-.5*((u/rx)**2+(v/ry)**2)))
    from mapworkshop.mapkit.earth import fbm
    grove*=np.clip(.93+.55*fbm(t['x'],t['y'],scale=350,seed=k.SEED+331,octaves=3),.45,1.35)
    t['labels'][(grove>.45)&(t['slope']<.25)&(t['z']>k.WATER+19)&(~t['protected'])]=1
    # Reserve small outpost scenes before woodland fills their surroundings.
    settlements=[]
    for s in sites:
        if s['template']!='Outpost':continue
        px,py=s['position'];placed=0
        for _ in range(200):
            if placed>=2:break
            a=rng.random()*math.tau;r=rng.uniform(300,550);x,y=px+math.cos(a)*r,py+math.sin(a)*r
            if place(rng.choice(['OsgiliathRuin01','OsgiliathRuin02','OsgiliathRuin21b']),x,y,
                     'OldOutpostRuins',gap=130,footprint=60,max_rise=14,solid=75,angle=a,site=True):
                placed+=1
                for _ in range(8):
                    b=rng.random()*math.tau;rr=rng.uniform(105,170)
                    place(rng.choice(['CartWheel','Crate01','Barrel','MoriaRubble01']),x+math.cos(b)*rr,y+math.sin(b)*rr,
                          'OutpostDebris',gap=28,footprint=15,max_rise=6,solid=18,site=True)
        settlements.append(dict(player=s.get('player'),position=s['position'],ruins=placed))
    deciduous=['Tree01_L','Tree03a_L','Tree03a','Tree03aL_L','Tree01_L','Tree03a_L',
               'TreeBanyan3','TreeBanyan2']
    evergreen=['TreeEvergreen03','TreeEvergreen03b','TreeEvergreen03c','TreeEvergreen01']
    tree_count=0
    # Stands and glades: trees gather where the clump field is high and leave
    # open glades where it is low, so woods are not an even scatter.
    clump=fbm(t['x']+911,t['y']-377,scale=170,seed=k.SEED+401,octaves=3)
    for density,low,high,target,gap in [('Dense',.60,2,1800,34),('Open',.30,.60,700,64),('Fringe',.10,.30,300,115)]:
        placed=0
        for _ in range(160000):
            if placed>=target:break
            index=rng.randrange(len(centers));c=centers[index]
            px,py=c['center'];rx,ry=c['radii'];a=c['rotation']
            u,v=rng.gauss(0,rx*.9),rng.gauss(0,ry*.9)
            x,y=px+u*math.cos(a)-v*math.sin(a),py+u*math.sin(a)+v*math.cos(a)
            if not (100<x<k.WIDTH*10-100 and 100<y<k.HEIGHT*10-100):continue
            iy,ix=k.cell((x,y));g=grove[iy,ix]
            if not low<=g<high or t['z'][iy,ix]>300 or t['slope'][iy,ix]>.38:continue
            cl=float(clump[iy,ix])
            if density!='Fringe' and rng.random()>np.clip(.55+1.8*cl,.04,1):continue
            gap=max(24,round({'Dense':34,'Open':64,'Fringe':115}[density]*(1.15-.5*np.clip(cl,0,.6))))
            probability=float(np.clip((t['z'][iy,ix]-210)/80,.12,.85))
            conifer=rng.random()<probability
            if place(rng.choice(evergreen if conifer else deciduous),x,y,
                     ('Foothill' if conifer else 'Valley')+'Woodland'+density,gap=gap,footprint=6,max_rise=8,solid=8):
                c['trees']+=1;placed+=1;tree_count+=1
                if rng.random()<.11:
                    b=rng.random()*math.tau;r=rng.uniform(35,68)
                    place(rng.choice(['Fern01','OptBush01','OptBush03']),x+math.cos(b)*r,y+math.sin(b)*r,
                          'ForestUnderstory',gap=22,footprint=6,max_rise=5)
    # Boulder anchors and downhill fragments at the toes of actual rocky terrain.
    rock_groups=[]
    candidates=np.column_stack(np.nonzero((t['slope']>.15)&(t['slope']<.48)&(t['z']>205)&(~routes)&(~t['protected'])))
    candidates=candidates[np.random.default_rng(k.SEED+71).permutation(len(candidates))]
    for iy,ix in candidates:
        if len(rock_groups)>=130:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),p)<185 for p in rock_groups):continue
        if place(rng.choice(['DarkRockGrey03','DarkRockGrey04','DarkRockGrey05']),x,y,'BoulderGroups',
                 gap=75,footprint=55,max_rise=27,solid=60,offset=-2):
            rock_groups.append((x,y))
            heading=math.atan2(-dy[iy,ix],-dx[iy,ix])
            for _ in range(rng.randint(3,6)):
                a=heading+rng.uniform(-1.15,1.15);r=rng.uniform(75,190)
                place(rng.choice(['DarkRockGrey02','DarkRockGrey07','DarkRockGrey17','DarkRockGrey18']),
                      x+math.cos(a)*r,y+math.sin(a)*r,'ScreeFragments',gap=30,footprint=14,max_rise=10,offset=-1)
    # Site scenes: worn ground around each outpost and lair, a farmstead
    # around outposts and bones and dead trees around warg lairs.
    from mapworkshop.mapkit.earth import fbm as _fbm
    wear=_fbm(t['x']+300,t['y']-200,scale=110,seed=k.SEED+701,octaves=3)
    for s in sites:
        px,py=s['position']
        d=np.hypot(t['x']-px,t['y']-py)
        ground=(t['z']>k.WATER+2)&(t['slope']<.45)
        t['labels'][ground&(d<170+130*wear)]=12
        t['labels'][ground&(d<100+80*wear)]=2
        site_rng=random.Random(k.SEED+hash(s['template'])%997+int(px))
        if s['template']=='Outpost':
            props=[('Haystack',4),('Tent01',2),('FirePit',1),('Crate01',3),('Barrel',3),('CartWheel',1)]
            # A fence run along an arc on one side of the farmstead.
            a0=site_rng.random()*math.tau
            for j in range(6):
                a=a0+j*.13;r=245
                x,y=px+math.cos(a)*r,py+math.sin(a)*r
                place(site_rng.choice(['ShireFence01','ShireFence02']),x,y,'SiteScenes',gap=20,footprint=14,
                      max_rise=8,angle=a+math.pi/2,site=True,soft=True)
            radius=(140,260)
        else:
            props=[('GiantSkull01',1),('GiantSkull02',1),('PolesSkull01',2),('PolesSkull02',2),
                   ('TreeDead01',3),('TreeDead02',2),('DarkRockGrey03',2),('DarkRockGrey02',4)]
            radius=(120,240)
        for template,n in props:
            for _ in range(n):
                for _try in range(30):
                    a=site_rng.random()*math.tau;r=site_rng.uniform(*radius)
                    x,y=px+math.cos(a)*r,py+math.sin(a)*r
                    face=math.atan2(py-y,px-x)
                    if place(template,x,y,'SiteScenes',gap=34,footprint=14,max_rise=8,site=True,soft=True):break
    # River rocks: boulders where banks steepen and a few stones breaking the
    # surface of the shallows (water is already impassable).
    banks=(np.abs(t['z']-k.WATER)<8)&(t['slope']>.30)&(~t['protected'])
    seeds=np.column_stack(np.nonzero(banks))
    seeds=seeds[np.random.default_rng(k.SEED+641).permutation(len(seeds))]
    spots=[]
    for iy,ix in seeds:
        if counts['RiverRocks']>=260:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),q)<220 for q in spots[-80:]):continue
        spots.append((x,y))
        for _ in range(rng.randint(2,5)):
            a=rng.random()*math.tau;r=abs(rng.gauss(0,30))
            px,py=x+math.cos(a)*r,y+math.sin(a)*r
            if not (100<px<k.WIDTH*10-100 and 100<py<k.HEIGHT*10-100):continue
            jy,jx=k.cell((px,py))
            if t['z'][jy,jx]<k.WATER-6:continue
            if put(rng.choice(['DarkRockGrey03','DarkRockGrey04','DarkRockGrey02','DarkRockGrey18','DarkRockGrey07']),
                   px,py,'RiverRocks',gap=30,z=-2):
                counts['RiverRocks']+=1
    # Rush clumps along gentle waterlines, a few standing in the shallows.
    # Shrubs do not block movement; bases and bridge approaches stay clear.
    shoreline=(np.abs(t['z']-k.WATER)<3)&(t['slope']<.35)&(~t['protected'])
    candidates=np.column_stack(np.nonzero(shoreline))
    candidates=candidates[np.random.default_rng(k.SEED+311).permutation(len(candidates))]
    clumps=[]
    for iy,ix in candidates:
        if len(clumps)>=170:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),c)<170 for c in clumps):continue
        added=0
        for _ in range(rng.randint(5,11)):
            a=rng.random()*math.tau;r=abs(rng.gauss(0,28))
            px,py=x+math.cos(a)*r,y+math.sin(a)*r
            if not (100<px<k.WIDTH*10-100 and 100<py<k.HEIGHT*10-100):continue
            jy,jx=k.cell((px,py))
            if not (abs(t['z'][jy,jx]-k.WATER)<3.5 and t['slope'][jy,jx]<.4):continue
            template=rng.choices(['GladdenFieldsShrub01','GladdenFieldsShrub02','GladdenFieldsShrub03','OptGrass02'],
                                 weights=[3,3,2,2])[0]
            if put(template,px,py,'ShoreRushes',gap=13):
                counts['ShoreRushes']+=1;added+=1
        if added:clumps.append((x,y))
    # Small river stones collect on dry terraces rather than uniform map scatter.
    shore=k.gaussian(t['water'].astype(float),8)
    candidates=np.column_stack(np.nonzero((shore>.008)&(t['z']>k.WATER+8)&(t['slope']<.3)))
    candidates=candidates[np.random.default_rng(k.SEED+217).permutation(len(candidates))]
    for iy,ix in candidates:
        if counts['RiverTerraceStones']>=70:break
        place(rng.choice(['DarkRockGrey02','DarkRockGrey07','DarkRockGrey17','DarkRockGrey18']),
              t['x'][iy,ix],t['y'][iy,ix],'RiverTerraceStones',gap=65,footprint=12,max_rise=9,offset=-1)
    for _ in range(25000):
        if counts['MeadowDetail']>=300 and counts['WoodlandDeadwood']>=70:break
        x,y=rng.uniform(100,k.WIDTH*10-100),rng.uniform(100,k.HEIGHT*10-100)
        iy,ix=k.cell((x,y));g=grove[iy,ix]
        if .18<g<.70 and counts['WoodlandDeadwood']<70:
            place(rng.choice(['PTStump01','TreeLog','TreeSpruceStump']),x,y,'WoodlandDeadwood',
                  gap=65,footprint=15,max_rise=6,offset=-.5)
        elif counts['MeadowDetail']<300 and g<.3 and t['slope'][iy,ix]<.18:
            place(rng.choice(['OptGrass08','OptGrass09','OptBush01']),x,y,'MeadowDetail',gap=85,footprint=7,max_rise=4)
    # Mountain conifers: stands climb the lower and middle slopes, gathering
    # in valley folds (concave ground) and thinning out towards a treeline.
    zs=k.gaussian(t['z'],3.0)
    concave=k.gaussian(t['z'],8.0)-zs
    slopefold=fbm(t['x']+2200,t['y']-1300,scale=210,seed=k.SEED+611,octaves=3)
    treeline=430+45*slopefold
    mountain_pines=['TreeEvergreen01','TreeEvergreen01b','TreeEvergreen02','TreeEvergreen02b','TreeEvergreen02']
    massif=k.gaussian((t['z']>380).astype(float),25.0)
    mountain=(t['z']>215)&(t['z']<treeline)&(t['slope']>.15)&(t['slope']<.62)&(~t['protected'])&(massif>.05)
    weight=np.clip(.30+concave/10+.9*slopefold,0,1)*(1-np.clip((t['z']-(treeline-90))/90,0,1))
    seeds=np.column_stack(np.nonzero(mountain&(weight>.35)))
    seeds=seeds[np.random.default_rng(k.SEED+612).permutation(len(seeds))]
    for iy,ix in seeds:
        if counts['MountainConifers']>=1800:break
        if rng.random()>weight[iy,ix]:continue
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        for _ in range(rng.randint(5,10)):
            a=rng.random()*math.tau;r=abs(rng.gauss(0,42))
            px,py=x+math.cos(a)*r,y+math.sin(a)*r
            if not (100<px<k.WIDTH*10-100 and 100<py<k.HEIGHT*10-100):continue
            place(rng.choice(mountain_pines),px,py,'MountainConifers',gap=30,footprint=6,max_rise=22,solid=8)
    # Landmark ruins: a handful of broken towers and walls on hill shoulders
    # with a view, away from bases, sites and routes.
    shoulders=(t['z']>205)&(t['z']<340)&(t['slope']<.11)&(~t['protected'])&(~routes)
    view=k.gaussian(t['z'],12.0)
    seeds=np.column_stack(np.nonzero(shoulders&(t['z']>view-1)))
    seeds=seeds[np.random.default_rng(k.SEED+631).permutation(len(seeds))]
    landmarks=[]
    ruin_types=['OsgiliathRuin06','OsgiliathRuin24','GondorBuildingIthilien17','OsgiliathRuin21b','OsgiliathRuin02','OsgiliathRuin01']
    for iy,ix in seeds:
        if len(landmarks)>=7:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),p)<1700 for p in landmarks):continue
        if min(x,y,k.WIDTH*10-x,k.HEIGHT*10-y)<700:continue
        if any(math.dist((x,y),s_['position'])<900 for s_ in sites):continue
        if any(math.dist((x,y),p)<1100 for p in k.STARTS):continue
        tpl=ruin_types[len(landmarks)%len(ruin_types)]
        if place(tpl,x,y,'LandmarkRuins',gap=60,footprint=50,max_rise=18,solid=70,angle=rng.random()*math.tau,site=True):
            landmarks.append((x,y))
            for _ in range(10):
                a=rng.random()*math.tau;r=rng.uniform(80,180)
                place(rng.choice(['MoriaRubble01','DarkRockGrey02','DarkRockGrey17','GBWTopWall4']),
                      x+math.cos(a)*r,y+math.sin(a)*r,'LandmarkRuins',gap=30,footprint=14,max_rise=8,angle=rng.random()*math.tau)
            for _ in range(4):
                a=rng.random()*math.tau;r=rng.uniform(120,220)
                place(rng.choice(['TreeDead01','OptBushLG06','GladdenFieldsShrub03']),x+math.cos(a)*r,y+math.sin(a)*r,
                      'LandmarkRuins',gap=40,footprint=8,max_rise=8,soft=True)
    # Parkland: lone trees and small copses break up the open meadows, kept
    # out of routes and bases so armies still have clear ground.
    open_ground=np.isin(t['labels'],[0,1,9,10])&(t['slope']<.22)&(~t['protected'])&(t['z']>k.WATER+6)&(grove<.15)&(~routes)
    seeds=np.column_stack(np.nonzero(open_ground))
    seeds=seeds[np.random.default_rng(k.SEED+621).permutation(len(seeds))]
    copses=[]
    for iy,ix in seeds:
        if len(copses)>=110:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),c)<420 for c in copses):continue
        n=rng.choice([1,1,2,3,4,5])
        pool=deciduous if rng.random()<.7 else evergreen[:2]
        added=0
        for _ in range(n*3):
            if added>=n:break
            a=rng.random()*math.tau;r=0 if added==0 else abs(rng.gauss(0,40))
            if place(rng.choice(pool),x+math.cos(a)*r,y+math.sin(a)*r,'Parkland',gap=34,footprint=6,max_rise=7,solid=8):
                added+=1
                if rng.random()<.5:
                    b=rng.random()*math.tau;rr=rng.uniform(25,50)
                    place(rng.choice(['OptBush01','OptBush03','Fern01','GladdenFieldsShrub03']),
                          x+math.cos(b)*rr,y+math.sin(b)*rr,'Parkland',gap=18,footprint=6,max_rise=5,soft=True)
        if added:copses.append((x,y))
    # Tors: lone hills outside the big ranges get scattered pines and shrubs
    # on their shoulders so they sit in the landscape rather than on it.
    edge=np.minimum(np.minimum(t['x'],k.WIDTH*10-t['x']),np.minimum(t['y'],k.HEIGHT*10-t['y']))
    big_range=k.gaussian((t['z']>380).astype(float),45.0)>.12
    tor=(t['z']>220)&(~big_range)&(t['slope']>.10)&(t['slope']<.75)&(~t['protected'])&(~routes)&(edge>700)
    seeds=np.column_stack(np.nonzero(tor))
    seeds=seeds[np.random.default_rng(k.SEED+651).permutation(len(seeds))]
    for iy,ix in seeds:
        if counts['TorVegetation']>=700:break
        x0,y0=t['x'][iy,ix],t['y'][iy,ix]
        for _ in range(rng.randint(2,5)):
            a=rng.random()*math.tau;r=abs(rng.gauss(0,28))
            x,y=x0+math.cos(a)*r,y0+math.sin(a)*r
            if rng.random()<.55:
                place(rng.choice(mountain_pines+['TreeEvergreen03b']),x,y,'TorVegetation',gap=32,footprint=6,max_rise=24,solid=8)
            else:
                place(rng.choice(['OptBushLG06','OptBushLG07','GladdenFieldsShrub03','EttenmoorsShrub03']),x,y,
                      'TorVegetation',gap=26,footprint=6,max_rise=18,soft=True)
    # Meadow ground cover: tufts gather in loose drifts, thinning to bare
    # grass; denser in damp lowland, absent on worn tracks and bare rock.
    drift=fbm(t['x']-1700,t['y']+900,scale=260,seed=k.SEED+601,octaves=3)
    grassy=np.isin(t['labels'],[0,1,9,10])&(t['slope']<.3)&(~t['protected'])&(t['z']>k.WATER+3)
    seeds=np.column_stack(np.nonzero(grassy&(drift>.12)))
    seeds=seeds[np.random.default_rng(k.SEED+602).permutation(len(seeds))]
    tufts=['OptGrass04','OptGrass05','OptGrass01','OptBushLG02','OptBushLG06','OptBushLG07']
    shrubs=['GladdenFieldsShrub03','ForlindonShrub02','ForlindonShrub03','EttenmoorsShrub03','OptBush01']
    large=['OldForestShrub01','OldForestShrub02','OldForestShrub03']
    drifts=[]
    for iy,ix in seeds:
        if counts['MeadowTufts']>=2400:break
        x,y=t['x'][iy,ix],t['y'][iy,ix]
        if any(math.dist((x,y),d)<170 for d in drifts[-80:]):continue
        drifts.append((x,y))
        # A clump: an occasional large bush at the core, shrubs, tufts around.
        if rng.random()<.25:
            place(rng.choice(large),x,y,'MeadowTufts',gap=60,footprint=30,max_rise=8,soft=True)
        for _ in range(rng.randint(5,11)):
            a=rng.random()*math.tau;r=abs(rng.gauss(0,45))
            px,py=x+math.cos(a)*r,y+math.sin(a)*r
            place(rng.choice(shrubs if r<35 and rng.random()<.5 else tufts),px,py,'MeadowTufts',gap=20,footprint=8,max_rise=5,soft=True)
    # Loose stones on gravel and scree aprons and along track shoulders.
    stony=np.isin(t['labels'],[7])&(t['slope']>.15)&(t['slope']<.5)&(~t['protected'])
    seeds=np.column_stack(np.nonzero(stony))
    seeds=seeds[np.random.default_rng(k.SEED+603).permutation(len(seeds))]
    for iy,ix in seeds:
        if counts['ApronStones']>=220:break
        place(rng.choice(['DarkRockGrey02','DarkRockGrey07','DarkRockGrey17','DarkRockGrey18']),
              t['x'][iy,ix],t['y'][iy,ix],'ApronStones',gap=55,footprint=12,max_rise=10,offset=-1)
    farmland=marked_farmland(k,t,farm_plan,place)
    farmland['farmstead']=farmstead(k,t,place)
    if tree_count<1600:raise ValueError('Insufficient varied woodland: '+str(tree_count))
    (k.OUT/'detail-placement.json').write_text(json.dumps(dict(placements=checks),indent=2)+'\n')
    return dict(layers=dict(counts),trees=tree_count,track_cells=track_cells,woodland_centers=centers,rock_groups=len(rock_groups),
                outpost_scenes=settlements,farmland=farmland,protected_routes=route_report,corridor_width_world=360,
                solid_footprints_checked=True,tree_rendering='native W3DTreeDraw / optimized-tree templates')
