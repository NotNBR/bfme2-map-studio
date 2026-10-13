"""Deterministic landscape operators: gradient fBm, domain warp and talus erosion.

Original NumPy implementation of public algorithmic ideas; see the research
notes in docs/reference/mapping/file-structure/ashen-march-findings.md. This is not a hydraulic solver.
"""

import numpy as np


def gradient_noise(x,y,scale,seed):
    rng=np.random.default_rng(seed)
    angles=rng.uniform(0,2*np.pi,(256,256))
    gx,gy=np.cos(angles),np.sin(angles)
    px,py=x/scale,y/scale
    ix,iy=np.floor(px).astype(int),np.floor(py).astype(int)
    u,v=px-ix,py-iy
    def dot(dx,dy):
        return gx[(iy+dy)%256,(ix+dx)%256]*(u-dx)+gy[(iy+dy)%256,(ix+dx)%256]*(v-dy)
    a,b,c,d=dot(0,0),dot(1,0),dot(0,1),dot(1,1)
    fu=u*u*u*(u*(u*6-15)+10);fv=v*v*v*(v*(v*6-15)+10)
    return ((a*(1-fu)+b*fu)*(1-fv)+(c*(1-fu)+d*fu)*fv)*1.45


def fbm(x,y,scale=900,seed=100,octaves=4):
    value=np.zeros_like(x,dtype=float);weight=1.;total=0.
    for i in range(octaves):
        value+=weight*gradient_noise(x,y,scale,seed+i*37);total+=weight
        # Rotate successive octaves to suppress shared lattice directions.
        x,y=.8*x-.6*y+.173*scale,.6*x+.8*y-.317*scale
        scale*=.5;weight*=.52
    return value/total


def thermal_erosion(height,iterations=28,spacing=10,talus=.72):
    """Conservative eight-neighbour talus relaxation, with a closed boundary."""
    z=height.astype(float).copy()
    for _ in range(iterations):
        delta=np.zeros_like(z)
        for dy,dx in [(0,1),(1,0),(1,1),(1,-1)]:
            ya=slice(0,-dy) if dy else slice(None);yb=slice(dy,None) if dy else slice(None)
            xa=slice(0,-dx) if dx>0 else slice(-dx,None) if dx<0 else slice(None)
            xb=slice(dx,None) if dx>0 else slice(0,dx) if dx<0 else slice(None)
            a,b=z[ya,xa],z[yb,xb];difference=a-b
            transfer=np.sign(difference)*np.maximum(np.abs(difference)-talus*spacing*np.hypot(dx,dy),0)*.09
            delta[ya,xa]-=transfer;delta[yb,xb]+=transfer
        z+=delta
    return z
