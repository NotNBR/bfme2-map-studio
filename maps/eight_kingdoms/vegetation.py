"""Small, seeded vegetation pockets that leave useful space between them."""

import math
import random


def base_layout(k):
    scenes=[]
    for index,(x,y) in enumerate(k.STARTS):
        rng=random.Random(k.SEED+2903+index*103)
        inward=math.atan2(k.HEIGHT*5-y,k.WIDTH*5-x)
        pockets=[(x+475*math.cos(inward+a),y+475*math.sin(inward+a),140)
                 for a in (-.55,.55)]
        clusters=[]
        for offset in (-1.45,1.55,2.85):
            angle=inward+offset+rng.uniform(-.28,.28)
            radius=rng.uniform(430,610)
            clusters.append((x+radius*math.cos(angle),y+radius*math.sin(angle),
                             rng.uniform(75,115),rng.uniform(65,100),angle))
        scenes.append(dict(player=index+1,center=(x,y),clusters=clusters,building_pockets=pockets))
    return scenes


def populate(k,t,place):
    """Add bounded pockets, not a uniform scatter or a planted ring at each base."""
    bases=[]
    for scene in base_layout(k):
        rng=random.Random(k.SEED+3907+scene['player']*109)
        trees=groundcover=inside_old_clearing=0
        for attempt in range(1000):
            cx,cy,sx,sy,angle=rng.choice(scene['clusters'])
            u=max(-2,min(2,rng.gauss(0,1)))*sx
            v=max(-2,min(2,rng.gauss(0,1)))*sy
            x=cx+u*math.cos(angle)-v*math.sin(angle)
            y=cy+u*math.sin(angle)+v*math.cos(angle)
            is_tree=trees<18 and (groundcover>=24 or rng.random()<.45)
            if not is_tree and groundcover>=24:continue
            pool=['Tree01_L','Tree03a_L','Tree03aL_L'] if is_tree else [
                'OptBush01','OptBush03','Fern01','OptGrass08','OptGrass09','PTStump01']
            if place(rng.choice(pool),x,y,'BaseTrees' if is_tree else 'BaseUndergrowth',
                     gap=58 if is_tree else 28,footprint=18 if is_tree else 8,
                     max_rise=6,clearance=95,start_radius=300):
                trees+=int(is_tree);groundcover+=int(not is_tree)
                inside_old_clearing+=int(math.dist((x,y),scene['center'])<550)
            if trees>=18 and groundcover>=24:break
        if trees<5 or inside_old_clearing<3:
            raise ValueError('Insufficient natural base vegetation for player '+str(scene['player']))
        bases.append(dict(player=scene['player'],trees=trees,groundcover=groundcover,
                          inside_former_clearing=inside_old_clearing,
                          building_pockets=scene['building_pockets']))
    # Small patches at woodland edges and rocky shoulders; leave open fields
    # between patches and reserve crates/masonry for actual settlements.
    rng=random.Random(k.SEED+4909);groups=[];total=0
    for _ in range(2500):
        x=rng.uniform(100,k.WIDTH*10-100);y=rng.uniform(100,k.HEIGHT*10-100)
        iy,ix=k.grid_point((x,y))
        if t['blocked'][iy,ix] or t['slope'][iy,ix]>.25:continue
        if not (.08<t['grove'][iy,ix]<.38 or .06<t['near_rock'][iy,ix]<.22):continue
        if any(math.dist((x,y),p)<300 for p in groups):continue
        added=0
        for _ in range(14):
            px=x+rng.gauss(0,55);py=y+rng.gauss(0,40)
            pool=['OptBush01','OptBush03','Fern01','OptGrass08','OptGrass09',
                  'PTStump01','DarkRockGrey02']
            template=rng.choice(pool)
            if place(template,px,py,'MeadowPockets',gap=30,footprint=10,
                     max_rise=5,clearance=115,z=-1 if template=='DarkRockGrey02' else 0):
                added+=1;total+=1
            if added>=5:break
        if added:groups.append((x,y))
        if len(groups)>=36:break
    return dict(bases=bases,meadow_groups=len(groups),meadow_objects=total,
                fortress_clear_radius=300,building_pocket_radius=140)
