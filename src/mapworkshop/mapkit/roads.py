"""Adjacent road endpoint records; no terrain or pathability is implied.

Endpoint pairing is verified across retail Maps.big. Modifier names come from
the SAGE source family, not native BFME2 rendering experiments. Unknown object
flags remain visible and are never cleared by inspection.
"""

import math



START, END = 2, 4
ANGLED, TIGHT_CURVE, ALPHA_JOIN = 8, 64, 128
OPTIONS = ANGLED | TIGHT_CURVE | ALPHA_JOIN
BRIDGE_POINTS = 0x10 | 0x20      # spanned bridge endpoints (mapkit.bridges), not roads


def inspect(objects):
    """Report adjacent pairs and malformed records without repairing the input."""
    pairs, issues, unknown = [], [], []
    consumed = set()
    for index, obj in enumerate(objects):
        flags = obj['flags']
        if flags & ~(START | END | OPTIONS | BRIDGE_POINTS):
            unknown.append(dict(index=index, flags=flags,
                                uninterpreted_bits=flags & ~(START | END | OPTIONS | BRIDGE_POINTS)))
        if not flags & (START | END):
            continue
        if flags & (START | END) == (START | END):
            issues.append(dict(index=index, reason='both endpoint bits set'))
            continue
        if flags & START:
            if index+1 >= len(objects) or objects[index+1]['flags'] & (START | END) != END:
                issues.append(dict(index=index, reason='start not immediately followed by end'))
                continue
            end = objects[index+1]
            consumed.add(index+1)
            if obj['template'] != end['template']:
                issues.append(dict(index=index, reason='endpoint templates differ'))
            points = [[o[k] for k in ('x','y','z')] for o in (obj,end)]
            if not all(math.isfinite(v) for p in points for v in p):
                issues.append(dict(index=index, reason='nonfinite endpoint'))
            elif points[0][:2] == points[1][:2]:
                issues.append(dict(index=index, reason='zero XY length'))
            pairs.append(dict(indices=[index,index+1], template=obj['template'],
                              positions=points, flags=[flags,end['flags']]))
        elif index not in consumed:
            issues.append(dict(index=index, reason='end has no adjacent start'))
    return dict(pairs=pairs, issues=issues, uninterpreted_flags=unknown,
                modifier_semantics='Source-family names; native rendering validation pending')


def add_segment(m, template, start, end, *, name, start_options=0, end_options=0, layer='Roads'):
    """Append an original Object v3 pair; XY/Z are map world coordinates.

Does not flatten terrain, add a bridge, or modify navigation. Both endpoints
share one road template, which must exist in the user's TerrainRoads INI.
"""
    if not template or not name or any('\0' in s for s in (template,name,layer)):
        raise ValueError('Road template, unique name and layer must be valid strings')
    points = [tuple(p) for p in (start,end)]
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('Road endpoints require three finite coordinates')
    if points[0][:2] == points[1][:2]:
        raise ValueError('Road must have nonzero XY length')
    for value in (start_options,end_options):
        if not isinstance(value,int) or value<0 or value & ~OPTIONS:
            raise ValueError('Only angled, tight-curve and alpha-join options can be authored')
    identities = {v for o in m.objects() for k,_,v in o['properties'] if k=='uniqueID'}
    if any(f'{name}_{suffix}' in identities for suffix in ('start','end')):
        raise ValueError('Road endpoint uniqueID already exists')
    encoded=[]
    for point,flag,option,suffix in zip(points,(START,END),(start_options,end_options),('start','end')):
        props=[('originalOwner',3,'/team'),('uniqueID',3,f'{name}_{suffix}'),('objectLayer',3,layer)]
        x,y,z=point
        encoded.append(m.encode_object(dict(template=template,x=x,y=y,z=z,angle=0.,flags=flag|option,
                                            properties=props)).encode())
    m.chunk('ObjectsList').data+=b''.join(encoded)
