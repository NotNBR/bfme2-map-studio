"""The Crown of Cardolan: an original eight-player landscape from an empty plane.

Build: mw build crown-of-cardolan [--phase functional|terrain|detail|polish]
Native assets are materials only; no stock map is read.
"""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import re
import struct

import numpy as np
from PIL import Image, ImageDraw

from mapworkshop.mapkit.blank import create, starts, set_heights, set_materials, add_object
from mapworkshop.mapkit.earth import fbm, thermal_erosion
from maps.ashen_march.build import smooth, route_field
from mapworkshop.formats.map import Map, sha
from mapworkshop.mapkit.cache import cache_entry

from mapworkshop.config import GAME_DATA
from mapworkshop.project import here
OUT=None   # set by the build pipeline (mapworkshop.project)
CHECK=None
TARGET=None
PROJECT=here(__file__)   # title, native name, players and description: map.toml
NAME=PROJECT.native_name
TITLE=PROJECT.title
SIZE=920;BORDER=30;CENTER=4600
ANGLES=np.arange(8)*math.pi/4+math.pi/8
STARTS=[(round(CENTER+3650*math.cos(a)),round(CENTER+3650*math.sin(a))) for a in ANGLES]
PALETTE=['DirtMordor18','DirtMordor09','RockEttenmoors01',
         'RockEttenmoors02','CliffEttenmoors01','RockMordor07']
REGIONS=[('East Barrows',6970,5040),('Black Pines',6370,6870),
         ('Northwatch',4440,7620),('Greywood',2310,6460),
         ('Old Quarry',2320,4380),('Kingsroad Village',4270,2200),
         ('Broken Causeway',6780,2620),('Sunken Court',7440,4260)]


def point(radius,angle):
    return (CENTER+radius*math.cos(angle),CENTER+radius*math.sin(angle))


def roads():
    result=[]
    for a,start in zip(ANGLES,STARTS):
        result.append([start,point(2800,a+.06),point(1850,a-.07),point(900,a),point(490,a)])
    return result


def landscape():
    yy,xx=np.indices((SIZE+2*BORDER,SIZE+2*BORDER))
    x=(xx-BORDER)*10.;y=(yy-BORDER)*10.
    dx=x-CENTER;dy=y-CENTER;r=np.hypot(dx,dy);angle=np.arctan2(dy,dx)
    broad=fbm(x,y,1800,610,4);small=fbm(x,y,330,730,4)
    wx=x+fbm(x,y,1150,810,3)*290;wy=y+fbm(x,y,1250,910,3)*290
    z=125+36*broad+13*small
    # Boundary shoulders are asymmetric chains, with low gaps behind the starts.
    masses=[(380,1700,500,2100,-.25,660),(700,7450,720,1550,.25,770),
            (2100,8900,1800,530,-.08,650),(7100,9000,1900,650,.13,820),
            (8920,6850,550,1700,-.1,760),(8730,1900,650,1950,-.26,680),
            (6700,350,1650,650,.2,720),(2100,500,1700,500,-.1,530)]
    hills=np.zeros_like(z)
    for cx,cy,sx,sy,a,h in masses:
        u=((wx-cx)*math.cos(a)+(wy-cy)*math.sin(a))/sx
        v=(-(wx-cx)*math.sin(a)+(wy-cy)*math.cos(a))/sy
        hills=np.maximum(hills,h*np.exp(-1.4*(u*u+v*v)))
    # Interior spurs separate adjacent marches without forming an unbroken wall.
    for j in range(8):
        a=j*math.pi/4+math.pi/4
        cx,cy=point(2100+160*math.sin(j*2.4),a)
        u=((wx-cx)*math.cos(a)+(wy-cy)*math.sin(a))/820
        v=(-(wx-cx)*math.sin(a)+(wy-cy)*math.cos(a))/370
        hills+= (155+65*math.sin(j*1.7)**2)*np.exp(-1.8*(u*u+v*v))
    z+=hills*(.9+.3*fbm(wx,wy,480,1040,4))
    z+=185*np.exp(-(r/1280)**2)
    z=thermal_erosion(z,iterations=22)
    route_dist=[]
    for route in roads():
        d,target=route_field(x,y,route,[135,145,170,240,280]);route_dist.append(d)
        w=1-smooth(175,410,d);z=z*(1-w)+(target+small*2)*w
    ring_r=2750+100*np.sin(3*angle)+65*np.sin(5*angle+.8)
    outer=np.abs(r-ring_r);w=1-smooth(145,390,outer)
    z=z*(1-w)+(145+8*np.sin(3*angle))*w
    inner=np.abs(r-700);w=1-smooth(150,320,inner)
    z=z*(1-w)+270*w
    # Equal useful base footprints; the surrounding ecology need not be mirrored.
    for cx,cy in STARTS:
        w=1-smooth(580,960,np.hypot(x-cx,y-cy));z=z*(1-w)+135*w
    # Small burial mounds give the eastern region a human scale.
    for cx,cy in [(6450,4740),(6650,4930),(6810,4700),(6940,5100)]:
        z+=45*np.exp(-((x-cx)/120)**2-((y-cy)/80)**2)
    # The keep's terrace and quarry cut are authored shapes, not noise stamps.
    w=1-smooth(180,400,np.hypot(x-4490,y-4690));z=z*(1-w)+305*w
    q=np.hypot((x-2320)/1.3,y-4380);w=1-smooth(170,350,q)
    z=z*(1-w)+105*w
    road=np.minimum.reduce([*route_dist,outer,inner])
    slope=np.hypot(*np.gradient(z,10))
    labels=np.zeros(z.shape,dtype='u2')
    labels[(road<26+8*small)&(slope<.3)]=1
    labels[(slope>.38)&(z>220)]=2
    labels[(slope>.72)&(z>360)]=3
    labels[(slope>1.0)&(z>430)]=4
    labels[(np.hypot(x-4490,y-4690)<150)&(slope<.25)]=5
    blocked=slope>.76
    grove=np.zeros_like(z)
    for cx,cy,sx,sy in [(6300,6770,950,650),(2320,6300,650,1050),
                         (6600,2880,820,500),(3950,2350,650,430),
                         (7050,4780,380,800),(4350,7240,700,430)]:
        grove=np.maximum(grove,np.exp(-((x-cx)/sx)**2-((y-cy)/sy)**2))
    return x,y,z,road,slope,labels,blocked,grove


def checkpoint(m,name,note):
    CHECK.mkdir(parents=True,exist_ok=True);data=m.encode();destination=CHECK/(name+'.map')
    if destination.exists() and destination.read_bytes()!=data:
        old=destination.read_bytes();history=CHECK/'history';history.mkdir(exist_ok=True)
        (history/(name+'-'+sha(old)[:16]+'.map')).write_bytes(old)
    destination.write_bytes(data)
    record=dict(phase=name,note=note,sha256=sha(data),objects=len(m.objects()))
    (CHECK/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record),flush=True)
    return record


def audit(z,road,blocked):
    result=[]
    for i,(cx,cy) in enumerate(STARTS):
        iy,ix=round(cy/10)+BORDER,round(cx/10)+BORDER
        patch=z[iy-45:iy+46,ix-45:ix+46]
        yy,xx=np.indices(patch.shape);disk=patch[(xx-45)**2+(yy-45)**2<=45**2]
        if np.ptp(disk)>8:raise ValueError(f'Base {i+1} insufficiently level')
        result.append(dict(start=i+1,position=[cx,cy],base_height_spread=float(np.ptp(disk))))
    # Flood the explicitly graded road band, from start 1 to all starts and city.
    from collections import deque
    walk=(road<120)&~blocked
    start=(round(STARTS[0][1]/10)+BORDER,round(STARTS[0][0]/10)+BORDER)
    seen=np.zeros(z.shape,dtype=bool);seen[start]=True;q=deque([start])
    while q:
        y,x=q.popleft()
        for dy,dx in [(0,1),(0,-1),(1,0),(-1,0)]:
            ny,nx=y+dy,x+dx
            if 0<=ny<len(z) and 0<=nx<z.shape[1] and walk[ny,nx] and not seen[ny,nx]:
                seen[ny,nx]=True;q.append((ny,nx))
    for entry in result:
        cx,cy=entry['position'];entry['route_connected']=bool(seen[round(cy/10)+BORDER,round(cx/10)+BORDER])
    if not all(e['route_connected'] for e in result):raise ValueError('Disconnected start in road network')
    return result


def decorate(m,z,road,slope,grove,polish):
    rng=random.Random(2026100808);used={};counts=Counter()
    ini='\n'.join(p.read_text(encoding='cp1252') for p in (GAME_DATA/'data/ini/object').rglob('*.ini'))
    valid=set(re.findall(r'^\s*(?:Object|ChildObject|ObjectReskin)\s+(\w+)',ini,re.M))
    def put(t,x,y,a=None,layer='Details',gap=40,protect=True):
        if t not in valid:raise ValueError('Unknown object '+t)
        if not 60<x<SIZE*10-60 or not 60<y<SIZE*10-60:return False
        ix,iy=round(x/10)+BORDER,round(y/10)+BORDER
        if protect and (road[iy,ix]<155 or min(math.hypot(x-bx,y-by) for bx,by in STARTS)<680):return False
        if slope[iy,ix]>.57:return False
        cell=(int(x//100),int(y//100));n=max(3,math.ceil(gap/100))
        for cy in range(cell[1]-n,cell[1]+n+1):
            for cx in range(cell[0]-n,cell[0]+n+1):
                if any(math.hypot(x-ox,y-oy)<max(gap,g) for ox,oy,g in used.get((cx,cy),[])):return False
        add_object(m,t,float(x),float(y),rng.random()*math.tau if a is None else a,layer)
        used.setdefault(cell,[]).append((x,y,gap));counts[layer]+=1
        return True
    # Main silhouette first. Keep most of the inner circulation ring empty.
    if not put('ForStronghold',4490,4690,.25,'Crown Citadel',210,False):raise ValueError('Missing focal keep')
    put('TowerHills_TowerA',4690,4470,.2,'Crown Citadel',110,False)
    put('Fornost_FallingTower',4800,4860,-.3,'Crown Citadel',95,False)
    put('FornostBrokenStatue1',4300,4390,.3,'Crown Citadel',55,False)
    put('FornostBrokenStatue2',4530,4270,-.4,'Crown Citadel',55,False)
    put('FireCampfire',4660,4780,0,'Crown Citadel',30,False)
    # Fragmented curtain wall: wide breaches correspond to the eight roads.
    for j in range(88):
        a=j*math.tau/88
        if min(abs(math.atan2(math.sin(a-b),math.cos(a-b))) for b in ANGLES)<.15 or rng.random()<.18:continue
        x,y=point(1020+rng.uniform(-20,20),a)
        put(rng.choice(['ForBWall1','ForBWall2','ForBWall3','GBWTopWall4']),x,y,a+math.pi/2,'Broken Curtain',85)
    # Eight gate districts, laid out along short streets with rubble behind walls.
    settlements=[]
    for j,a in enumerate(ANGLES):
        cx,cy=point(1500+(j%3)*90,a+.18);settlements.append((cx,cy,a))
        for side in (-1,1):
            for k in range(5):
                along=(k-2)*120;across=side*(95+rng.uniform(0,35))
                x=cx+along*math.cos(a)-across*math.sin(a)
                y=cy+along*math.sin(a)+across*math.cos(a)
                put(rng.choice(['OsgiliathRuin01','OsgiliathRuin02','OsgiliathRuin06','OsgiliathRuin08','OsgiliathRuin21b']),x,y,a+rng.uniform(-.12,.12),'Gate Districts',80)
        put('FornostBrokenStatue3',cx+290*math.cos(a),cy+290*math.sin(a),a,'Gate Districts',50)
    # Regional stories beyond the city: quarry, barrows, old watch and caravan.
    if not put('TowerHills_TowerB',4440,7620,.1,'Northwatch',100):raise ValueError('Northwatch location rejected')
    for j,(cx,cy) in enumerate([(6440,4740),(6650,4930),(6810,4700),(6940,5100)]):
        put('GBWTopStatue3',cx,cy,j*.4,'Eastern Barrows',50)
        for k in range(7):
            a=k*math.tau/7;put('DarkRockGrey07',cx+65*math.cos(a),cy+52*math.sin(a),a,'Eastern Barrows',18)
    for j in range(30):
        x=2170+(j%6)*65;y=4250+(j//6)*62
        put(rng.choice(['DarkRockGrey01','DarkRockGrey07','DarkRockGrey17']),x,y,rng.uniform(-.2,.2),'Abandoned Quarry',40)
    for cx,cy,a in [(4140,2250,.15),(2450,6270,-.5),(6710,2710,.8),(7430,4360,1.3)]:
        settlements.append((cx,cy,a))
        for j in range(8):
            x=cx+(j%4-1.5)*130;y=cy+(-1 if j<4 else 1)*140
            put(rng.choice(['OsgiliathRuin02','OsgiliathRuin06','OsgiliathRuin24','GBWTopRBud1']),x,y,a,'Outer Villages',85)
        put('CartWreck',cx+50,cy+15,a,'Outer Villages',30)
        put('FireCampfire',cx-50,cy-25,0,'Outer Villages',25)
    for cx,cy,a in settlements:
        for _ in range(35 if polish else 8):
            put(rng.choice(['CartWheel','Barrel','Crate01','MoriaRubble01','MoriaRubble02']),
                cx+rng.uniform(-330,330),cy+rng.uniform(-260,260),a+rng.uniform(-.5,.5),'Settlement Debris',22)
    # Ecological clusters follow regional masks and slope; bases remain open.
    for _ in range(160000):
        x=rng.uniform(100,9100);y=rng.uniform(100,9100);ix,iy=round(x/10)+30,round(y/10)+30
        g=grove[iy,ix];s=slope[iy,ix];p=rng.random()
        if g>.15 and s<.34 and p<g*.72:
            pool=['PTreePine01','PTreePine02','PTreeSpruce01'] if x>4600 else ['Tree01','Tree05','PTreeSpruce01']
            put(rng.choice(pool),x,y,layer='Woodlands',gap=42)
        elif z[iy,ix]>230 and .16<s<.60 and p<.16:
            put(rng.choice(['DarkRockGrey01','DarkRockGrey07','DarkRockGrey17','RockGrey21']),x,y,layer='Outcrops',gap=60)
        elif p<.004 and s<.3:
            put(rng.choice(['TreeDead01','TreeDead02','Tree01']),x,y,layer='Solitary Trees',gap=135)
    if polish:
        buildings=[o for o in m.objects() if o['template'].startswith(('Osgiliath','ForBWall','ForStronghold'))]
        for o in buildings:
            for _ in range(9):
                a=rng.random()*math.tau;r=rng.uniform(65,155)
                put(rng.choice(['MoriaRubble01','MoriaRubble02','DarkRockGrey07']),o['x']+r*math.cos(a),o['y']+r*math.sin(a),layer='Masonry Rubble',gap=20)
        for _ in range(65000):
            x=rng.uniform(100,9100);y=rng.uniform(100,9100);ix,iy=round(x/10)+30,round(y/10)+30
            if grove[iy,ix]>.25 and slope[iy,ix]<.32:
                put(rng.choice(['OptGrass08','OptGrass09','OptBush01','TreeLog','PTStump01']),x,y,layer='Forest Floor',gap=25)
    return dict(counts)


def preview(z,labels,path,annotated=False):
    dy,dx=np.gradient(z,10);light=np.clip((-.6*dx-.5*dy+.7)/np.sqrt(1+dx*dx+dy*dy),.12,1.2)
    colors=np.array([[93,94,70],[102,88,64],[105,105,95],[77,78,72],[126,128,122],[102,99,85]])
    rgb=np.clip(colors[labels]*(.5+.7*light[...,None]),0,255).astype('u1')
    im=Image.fromarray(rgb).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    if annotated:
        d=ImageDraw.Draw(im)
        def p(x,y):return (x/10+BORDER,SIZE+BORDER-y/10)
        for i,(x,y) in enumerate(STARTS,1):
            px,py=p(x,y);d.ellipse((px-13,py-13,px+13,py+13),fill='#d3bb88');d.text((px-3,py-5),str(i),fill='black')
        for label,x,y in REGIONS:d.text(p(x,y),label,fill='white',stroke_width=1,stroke_fill='black')
        d.text(p(4250,4830),'THE CROWN',fill='white',stroke_width=1,stroke_fill='black')
    im.save(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['functional','terrain','detail','polish'],default='polish');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    m=create(SIZE,SIZE,BORDER,TITLE,description=PROJECT.description,player_count=PROJECT.players);phases=[]
    phases.append(checkpoint(m,'00-empty','New uniform plane, no inherited terrain or objects.'))
    starts(m,STARTS);phases.append(checkpoint(m,'01-functional','Eight evenly spaced starts and matching player side records.'))
    x,y,z,road,slope,labels,blocked,grove=landscape()
    routes=audit(z,road,blocked)
    if args.phase!='functional':
        set_heights(m,z);set_materials(m,[PALETTE[0]],np.zeros_like(labels),blocked)
        phases.append(checkpoint(m,'03-landforms','Broken boundary shoulders, eight interior spurs, a raised city and graded ring/spoke routes.'))
        set_materials(m,PALETTE,labels,blocked)
        phases.append(checkpoint(m,'05-materials','Continuous muted moorland soil; road wear and slope-based stone.'))
    layers={}
    if args.phase in ('detail','polish'):
        layers=decorate(m,z,road,slope,grove,args.phase=='polish')
        phases.append(checkpoint(m,'07-polish' if args.phase=='polish' else '06-scenes','Citadel, breached curtain, eight gate districts, outer villages, barrows, quarry and clustered woodland.'))
    preview(z,labels,OUT/'terrain-plan.png',True);preview(z,labels,OUT/'terrain-relief.png')
    path=TARGET/(NAME+'.map');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(m.encode())
    (path.parent/'map.ini').write_text(f'; {TITLE}\nWeather\n  HardwareFogEnable = No\nEnd\nAIData\n  LowLodTreeName = TreeLowLODArnor\nEnd\n',encoding='ascii')
    radar=Image.open(OUT/'terrain-relief.png').crop((30,30,950,950)).resize((256,256),Image.Resampling.LANCZOS)
    for suffix in ['_art.tga','_pic.tga']:radar.save(path.parent/(NAME+suffix))
    cache_entry(path,m,NAME,TITLE,PROJECT.description,players=PROJECT.players)
    report=Map(path.read_bytes()).report();report.update(phase=args.phase,source_map=None,players=PROJECT.players,starts=STARTS,layers=layers,route_audit=routes,
        checkpoints=phases,worldbuilder_verified=False,native_horde_paths_verified=False,sha256=sha(path.read_bytes()))
    (OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(map=str(path),sha256=sha(path.read_bytes()),objects=report['objects'],layers=layers)),flush=True)


if __name__=='__main__':main()
