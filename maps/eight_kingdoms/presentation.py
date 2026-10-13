"""Named lighting slots and serialized placement checks for Eight Kingdoms."""

import math
import numpy as np

from mapworkshop.formats.lighting import decode, encode


def daylight(m):
    """Warm sunlight with restrained fill; preserve unresolved lighting fields."""
    chunk=m.chunk('GlobalLighting')
    value=decode(chunk.data,chunk.version)
    for configuration in value['configurations']:
        for light in configuration:
            if light['light_index']==0 and light['target'] in ('terrain','objects'):
                light['ambient']=(.26,.29,.32)
                light['diffuse']=(.76,.74,.67) if light['target']=='terrain' else (.80,.77,.69)
    value['overbright_value']=1.
    chunk.data=encode(value,chunk.version)
    return dict(profile='warm-daylight-restrained-fill',
                edited_slots=['terrain:0','objects:0'],
                fill_and_third_array_preserved=True,overbright=1.)


def bridge_audit(k,m):
    """Check authored origins/axes against stored terrain; not a native test."""
    terrain=m.heightmap();heights=terrain['elevations']*.0390625
    objects={v:o for o in m.objects() for key,_,v in o['properties'] if key=='objectName'}
    checks=[]
    for bridge in k.BRIDGES:
        name='EK_Bridge_'+bridge['name'];obj=objects.get(name)
        if obj is None:raise ValueError('Missing named bridge '+name)
        expected=np.asarray(bridge['center'])+k.WORLD_SHIFT
        x,y=obj['x']/10+terrain['border'],obj['y']/10+terrain['border']
        ix,iy=int(x),int(y);fx,fy=x-ix,y-iy
        ground=float((1-fy)*((1-fx)*heights[iy,ix]+fx*heights[iy,ix+1])+
                     fy*((1-fx)*heights[iy+1,ix]+fx*heights[iy+1,ix+1]))
        origin=ground+obj['z']
        axis_angle=math.atan2(bridge['axis'][1],bridge['axis'][0])-math.pi/2
        angle_error=abs(math.atan2(math.sin(obj['angle']-axis_angle),math.cos(obj['angle']-axis_angle)))
        error=abs(origin-(k.GROUND-1))
        passed=(obj['template']=='GondorIthilienBridge2' and np.max(np.abs(expected-[obj['x'],obj['y']]))<.01
                and error<.1 and angle_error<1e-5)
        checks.append(dict(name=bridge['name'],ground_z=ground,relative_z=obj['z'],
                           origin_z=origin,origin_error=error,angle_error=angle_error,passed=bool(passed)))
    if not all(c['passed'] for c in checks):raise ValueError('Bridge placement audit failed: '+str(checks))
    return dict(scope='Serialized origins and orientation only; not native deck traversal',bridges=checks)
