"""Landform-aware native materials for the existing landscape."""

import numpy as np
from PIL import Image, ImageFilter
from mapworkshop.mapkit.earth import fbm

PALETTE = ['GrassMediumType40', 'GrassMediumType44b', 'IthilienDirt07',
           'SandType3wet', 'RockRohan04', 'CliffMediumType16b',
           'CliffMediumType15', 'SnowCaradhras03', 'StoneAmon_Hen01',
           'SandType3dark', 'RocksType3']
COLORS = [[113,126,76],[78,104,62],[139,124,88],[105,95,70],
          [120,123,99],[127,139,132],[157,164,151],[216,219,205],
          [148,145,128],[92,84,62],[132,142,125]]


def classify(k,t):
    x,y,z,slope=t['x'],t['y'],t['z'],t['slope']
    road,grove=t['road'],t['grove']
    grain=fbm(x,y,220,k.SEED+301,3)
    labels=np.zeros(z.shape,dtype='u2')
    dry=z>k.WATER+12
    # Shaded, damp forest soil is local to woodland interiors.
    labels[(grove>.5)&(slope<.42)&dry]=1
    labels[(grove>.72)&(grain>.14)&(slope<.3)&dry]=9
    labels[(road<16+8*grain)&(slope<.35)&dry]=2
    labels[z<k.WATER+22]=3
    exposure=(slope>.62)&dry
    near_rock=np.asarray(Image.fromarray((exposure*255).astype('uint8')).filter(
        ImageFilter.GaussianBlur(9)),dtype=float)/255
    # Deposited fragments gather below exposed slopes and along rocky banks.
    scree=(near_rock>.14+grain*.05)&(slope>.10)&(slope<.72)&dry
    labels[scree]=4
    labels[(z<k.GROUND-28)&(slope<.60)&dry]=10
    # Steep ground exposes bedrock even below the mountain elevation threshold.
    labels[exposure]=5
    labels[(z>300)&(slope>.35)&dry]=5
    labels[(z>380)&(slope<.52)&(near_rock>.14)]=6
    # Snow collects on high ledges; steep faces retain exposed rock.
    snow=(z>555+55*grain)&(slope<.58)
    labels[snow]=7
    cx,cy=k.reference_world((583,631))
    labels[(x-cx)**2+(y-cy)**2<140**2]=8
    # Broad meadow variation breaks the conspicuous solid grass disks without
    # changing the flat starting terrain or adding a ring of dirt around it.
    meadow=fbm(x+31,y-73,370,k.SEED+302,3)
    for px,py in k.STARTS:
        d=np.hypot(x-px,y-py)
        base=(d<550+80*grain)&dry&(slope<.35)
        labels[base]=0
        labels[base&(meadow>.13)]=1
    t.update(labels=labels,scree=scree,near_rock=near_rock)
    return dict(material_samples={name:int(np.count_nonzero(labels==i)) for i,name in enumerate(PALETTE)},
                grass_on_steep_dry=int(np.count_nonzero((slope>1)&dry&np.isin(labels,[0,1]))),
                snow_on_steep=int(np.count_nonzero(snow&(slope>.58))))
