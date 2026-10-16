"""Layout anchors and natural route geometry, x east and y north.

All sixteen numbered sites retain their reference positions. The sixty
connections follow gently warped routes through the mountain shoulders.
The 68 reference ridge shapes guide the base cirques and valley divides.
The SVG map rectangle is uniformly scaled into 28,500 units,
leaving mountain space at the edges. Its background is not elevation data.
"""
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import numpy as np

SCALE = 1.5  # Horizontal landscape scale; route widths and object sizes are fixed.
WIDTH = HEIGHT = round(1900*SCALE)
BORDER = 30
EXTENT = WIDTH*10.
CENTRE = (EXTENT/2, EXTENT/2)
ICE, LOW, MID, HIGH = 120., 220., 850., 1650.
PAD_HALF = 500.*SCALE
NS = {'s': 'http://www.w3.org/2000/svg'}


def world(x, y):
    return SCALE*(1500+(x-60)*16), SCALE*(1500+(1150-y)*16)


def path_points(data):
    """Sample the reference's absolute M/L/Q paths, retaining junctions."""
    tokens = re.findall(r'[MLQ]|-?\d+(?:\.\d+)?', data)
    points = []
    i = 0
    while i < len(tokens):
        command = tokens[i]
        i += 1
        if command in ('M', 'L'):
            points.append(np.array([float(tokens[i]), float(tokens[i+1])]))
            i += 2
        elif command == 'Q':
            control = np.array([float(tokens[i]), float(tokens[i+1])])
            end = np.array([float(tokens[i+2]), float(tokens[i+3])])
            start = points[-1]
            for t in np.linspace(0, 1, 7)[1:]:
                points.append((1-t)**2*start+2*(1-t)*t*control+t*t*end)
            i += 4
        else:
            raise ValueError(f'Unsupported reference path command {command}')
    return [world(*p) for p in points]


def reference():
    root = ET.parse(Path(__file__).parent/'references'/'layout.svg').getroot()
    bases = []
    for rect in root.findall('.//s:rect', NS):
        name = rect.get('id', '')
        if not name.startswith('base-area-'):
            continue
        number = int(name.rsplit('-', 1)[1])
        x = float(rect.get('x'))+float(rect.get('width'))/2
        y = float(rect.get('y'))+float(rect.get('height'))/2
        height = HIGH if number in (1, 4, 7, 10) else LOW if number >= 13 else MID
        wx, wy = world(x, y)
        bases.append(dict(number=number, x=wx, y=wy, height=height))
    routes = []
    for group, width in [('main-routes', 340.), ('secondary-routes', 180.)]:
        element = root.find(f"s:g[@id='{group}']", NS)
        for path in element.findall('s:path', NS):
            if path.get('id'):
                route_width = 300. if path.get('id').startswith('inner-forward-exit') else width
                routes.append(dict(name=path.get('id'), points=path_points(path.get('d')),
                                   width=route_width, main=group == 'main-routes'))
    assert sorted(b['number'] for b in bases) == list(range(1, 17))
    assert len(routes) == 60
    return sorted(bases, key=lambda b: b['number']), routes


BASES, REFERENCE_ROUTES = reference()


def natural_points(points, spacing=100.):
    """A shared, smooth geographic deformation preserves route junctions.

    All paths and crests use the same field, so crossing lines stay joined.
    Base anchors and the ice field are pinned; bends emerge between them.
    """
    points = np.asarray(points, float)
    samples = []
    for a, b in zip(points[:-1], points[1:]):
        count = max(1, int(np.ceil(np.linalg.norm(b-a)/spacing)))
        samples.extend(a+(b-a)*t for t in np.linspace(0, 1, count, endpoint=False))
    samples.append(points[-1])
    p = np.asarray(samples)
    x, y = p.T
    weight = np.clip((np.hypot(x-CENTRE[0], y-CENTRE[1])-2300)/1800, 0, 1)
    for base in BASES:
        weight = np.minimum(weight, np.clip((np.hypot(x-base['x'], y-base['y'])-1050)/1500, 0, 1))
    weight = weight*weight*(3-2*weight)
    dx = 520*np.sin(y/2350+.5*np.sin(x/4400))+180*np.sin((x+y)/1200+.4)
    dy = 470*np.sin(x/2600+1.1+.4*np.sin(y/3500))+160*np.sin((y-x)/1450)
    return (p+np.column_stack((dx*weight, dy*weight))).tolist()


def floor_height(radius):
    """Smooth monotone valley grades, without concentric slope-break stripes."""
    r = SCALE*np.array([0, 1500, 3520, 4800, 5920, 6984.5, 9842.9, 15000.])
    z = np.array([ICE, ICE, LOW, 480, 760, MID, HIGH, 1950.])
    secants = np.diff(z)/np.diff(r)
    slopes = np.zeros(len(r))
    slopes[-1] = secants[-1]
    for i in range(1, len(r)-1):
        if secants[i-1]*secants[i] > 0:
            slopes[i] = 2/(1/secants[i-1]+1/secants[i])
    k = np.clip(np.searchsorted(r, radius, side='right')-1, 0, len(r)-2)
    span = r[k+1]-r[k]
    t = np.clip((radius-r[k])/span, 0, 1)
    return ((2*t**3-3*t*t+1)*z[k]+(t**3-2*t*t+t)*span*slopes[k]
            +(-2*t**3+3*t*t)*z[k+1]+(t**3-t*t)*span*slopes[k+1])


def simplify(points, tolerance=24*SCALE):
    """Reduce redundant sampled SVG points within 1.5 reference pixels."""
    p = np.asarray(points)
    if len(p) < 3:
        return p
    vector = p[-1]-p[0]
    length2 = np.dot(vector, vector)
    t = np.clip((p-p[0])@vector/max(length2, 1e-12), 0, 1)
    distances = np.linalg.norm(p-(p[0]+t[:, None]*vector), axis=1)
    index = int(distances.argmax())
    if distances[index] <= tolerance:
        return p[[0, -1]]
    return np.vstack((simplify(p[:index+1], tolerance)[:-1], simplify(p[index:], tolerance)))


def mountain_ridges():
    """Read the clean reference's actual ridge crests, including every gap."""
    root = ET.parse(Path(__file__).parent/'references'/'layout.svg').getroot()
    ridges = []
    for group in root.find("s:g[@id='mountain-ridges']", NS):
        name = group.get('id')
        crest = group.findall('s:path', NS)[-1]
        p = simplify(natural_points(path_points(crest.get('d'))))
        if 'outer-corner' in name:
            rise, spread = 850., 740.
        elif 'outer-shoulder' in name:
            rise, spread = 1250., 740.
        elif 'inner-crown' in name:
            rise, spread = 850., 590.
        elif 'inner-toe' in name:
            rise, spread = 360., 340.
        elif 'divide' in name:
            rise, spread = 1000., 700.
        else:
            rise, spread = 800., 440.
        ridges.append(dict(name=name, points=p.tolist(), rise=rise, spread=spread*SCALE))
    assert len(ridges) == 68
    return ridges


RIDGES = mountain_ridges()
ROUTES = [dict(route, reference_points=route['points'],
               points=simplify(natural_points(route['points']), tolerance=5).tolist())
          for route in REFERENCE_ROUTES]
