"""Compose scenery around geology, forest edges and the neutral settlements."""

import math
import random
import numpy as np


def populate(k,m,t,put,rng):
    counts={};scenes=[]
    def place(template,x,y,layer,**kwargs):
        if put(template,x,y,layer,**kwargs):
            counts[layer]=counts.get(layer,0)+1
            return True
        return False
    # Buildings align to a settlement street, with openings on the main road.
    for site_index,o in enumerate(list(m.objects())):
        if o['template'] not in ('Outpost','Inn'):continue
        cx,cy=o['x'],o['y'];iy,ix=k.grid_point((cx,cy))
        nearest=min(k.STARTS,key=lambda p:math.dist(p,(cx,cy)))
        site_rng=random.Random(k.SEED+site_index*7919)
        angle=math.atan2(nearest[1]-cy,nearest[0]-cx)+site_rng.uniform(-.25,.25)
        c,s=math.cos(angle),math.sin(angle);actual=[]
        plots=[(-185,-180),(-195,165),(170,-200),(185,205),(-340,-65),(345,80)]
        templates=['OsgiliathRuin01','OsgiliathRuin02','OsgiliathRuin06',
                   'OsgiliathRuin24','GondorBuildingIthilien17','OsgiliathRuin21b']
        site_rng.shuffle(templates)
        # Uneven setbacks and a missing outer plot break the repeated six-house
        # pattern, without filling the route through the settlement.
        omitted=site_rng.choice((4,5))
        for i,(u,v) in enumerate(plots):
            if i==omitted:continue
            u+=site_rng.uniform(-45,45);v+=site_rng.uniform(-30,30)
            px=cx+u*c-v*s;py=cy+u*s+v*c
            tpl=templates[i]
            # Move a plot locally to find a sound foundation on the existing
            # terrain; never level a hillside merely to fit a decorative ruin.
            offsets=[(0,0)]+[(r*math.cos(a),r*math.sin(a))
                            for r in (35,70,105) for a in np.arange(0,math.tau,math.pi/4)]
            rotation=angle+site_rng.uniform(-.22,.22)
            for ox,oy in offsets:
                if place(tpl,px+ox,py+oy,'SettlementBuildings',angle=rotation,
                         gap=95,footprint=65,max_rise=7,clearance=100):
                    actual.append((px+ox,py+oy))
                    break
        for px,py in actual:
            for _ in range(12):
                a=rng.random()*math.tau;r=rng.uniform(90,150)
                place(rng.choice(['MoriaRubble01','MoriaRubble02','CartWheel','Crate01','Barrel']),
                      px+r*math.cos(a),py+r*math.sin(a),'SettlementDebris',
                      angle=angle+rng.uniform(-.4,.4),gap=22,footprint=12,max_rise=5,z=-1)
        # Low boundary fragments; the street and bridge approaches stay open.
        for side in (-1,1):
            for j in (-2,-1,1,2):
                if site_rng.random()<.3:continue
                u,v=j*70+site_rng.uniform(-15,15),side*site_rng.uniform(260,315)
                place('GBWTopWall4',cx+u*c-v*s,cy+u*s+v*c,'BrokenBoundaries',
                      angle=angle,gap=45,footprint=30,max_rise=6,clearance=110)
        scenes.append(dict(template=o['template'],center=[cx,cy],street_angle=angle,
                           buildings=len(actual)))
    # Scree groups follow cliff toes and river terraces. Natural geology uses
    # natural rock assets; masonry rubble is confined to the ruins above.
    anchors=[]
    dy,dx=np.gradient(t['z'],10)
    candidates=np.column_stack(np.nonzero(t['scree']&(t['slope']<.5)&(t['z']>k.WATER+25)))
    candidates=candidates[np.random.default_rng(k.SEED+71).permutation(len(candidates))]
    for iy,ix in candidates:
        px,py=t['x'][iy,ix],t['y'][iy,ix]
        if t['road'][iy,ix]<190 or any(math.hypot(px-a,py-b)<170 for a,b in anchors):continue
        if place(rng.choice(['DarkRockGrey03','DarkRockGrey04','DarkRockGrey05','DarkRockGrey18']),
                 px,py,'RockfallAnchors',gap=48,footprint=33,max_rise=18,z=-3,clearance=135):
            anchors.append((px,py))
            for _ in range(rng.randint(3,7)):
                # Debris fans out down the local slope rather than forming a
                # ring around each boulder. Nearly flat toes have no preferred axis.
                downhill=math.atan2(-dy[iy,ix],-dx[iy,ix])
                a=downhill+rng.uniform(-.85,.85) if t['slope'][iy,ix]>.05 else rng.random()*math.tau
                r=rng.uniform(48,135)
                place(rng.choice(['DarkRockGrey02','DarkRockGrey07','DarkRockGrey17','DarkRockGrey02']),
                      px+r*math.cos(a),py+r*math.sin(a),'TalusFragments',
                      gap=20,footprint=12,max_rise=9,z=-1.5,clearance=125)
        if len(anchors)>=250:break
    # Deciduous valley woodland and evergreen foothills form separate stands.
    for _ in range(220000):
        px=rng.uniform(70,8930);py=rng.uniform(70,9530);iy,ix=k.grid_point((px,py))
        slope=t['slope'][iy,ix];g=t['grove'][iy,ix];z=t['z'][iy,ix]
        if g<.23 or slope>.43 or t['blocked'][iy,ix] or z>415:continue
        if rng.random()>g*.78:continue
        # Mixed edges between valley woods and foothills, with no artificial
        # north/south species boundary through the middle of the map.
        evergreen_chance=float(np.clip((z-175)/150+(g-.5)*.3,.08,.94))
        evergreen=rng.random()<evergreen_chance
        pool=['TreeEvergreen03','TreeEvergreen03b','TreeEvergreen03c'] if evergreen else ['Tree01_L','Tree03a_L','Tree03a','Tree03aL_L']
        if place(rng.choice(pool),px,py,'EvergreenStands' if evergreen else 'ValleyWoodland',
                 gap=42 if evergreen else 40,footprint=6,max_rise=7,clearance=145):
            # Understory sits just outside the trunk, not at arbitrary map points.
            if rng.random()<.33:
                a=rng.random()*math.tau;r=rng.uniform(44,69)
                place(rng.choice(['Fern01','OptBush01','OptBush03']),px+r*math.cos(a),py+r*math.sin(a),
                      'Understory',gap=22,footprint=8,max_rise=5,clearance=120)
        if counts.get('EvergreenStands',0)+counts.get('ValleyWoodland',0)>=3900:break
    # A sparse fringe follows each grove; most of the open meadow remains clear.
    for _ in range(30000):
        px=rng.uniform(80,8920);py=rng.uniform(80,9520);iy,ix=k.grid_point((px,py))
        g=t['grove'][iy,ix]
        if not .12<g<.35 or t['slope'][iy,ix]>.27 or t['near_rock'][iy,ix]>.16:continue
        place(rng.choice(['OptGrass08','OptGrass09','Fern01','PTStump01']),
              px,py,'WoodlandFringe',gap=38,footprint=7,max_rise=4,clearance=120)
        if counts.get('WoodlandFringe',0)>=430:break
    from maps.eight_kingdoms.vegetation import populate as vegetation
    vegetation_report=vegetation(k,t,place)
    return dict(layers=counts,settlement_scenes=scenes,rockfall_groups=len(anchors),
                vegetation=vegetation_report)
