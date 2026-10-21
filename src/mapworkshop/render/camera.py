"""The views of mw render and the viewer: OrbitView and TopView, cameras built
for clear framing.

World coordinates: X east, Y north, Z up, origin at the playable map's
south-west corner, 10 units per terrain cell.

Orbit view (default):
    target    = X,Y[,Z]   point looked at; Z defaults to the terrain height
    distance  = units     eye distance from the target            (1500)
    elevation = degrees   above the horizon; 90 looks straight down (45)
    heading   = degrees   compass direction the camera faces:
                          0 north, 90 east, 180 south, 270 west    (0)
    fov       = degrees   horizontal field of view                 (50)
    eye       = X,Y,Z     optional explicit eye; overrides distance,
                          elevation and heading
    roll      = degrees   the camera turned about its view direction,
                          positive to the right (0)

Photo keys (render.photo; the viewer's Photo mode writes them):
    focal     = mm        focal length on a full-frame sensor's crop of the
                          image's aspect (render.photo.sensor), in place of fov
    aperture  = f-number  depth of field (none: everything sharp)
    focus     = units     the distance in focus along the view (default: to
                          the target)
    ev        = stops     exposure, brighter above 0 (0)

Top view (orthographic, north up):
    region    = X0,Y0,X1,Y1   world rectangle; default is the playable map
                              (the whole grid when the border is shown)

Specs are written as key=value words, e.g.
    target=5500,1090 distance=1800 elevation=40 heading=30
"""

from dataclasses import dataclass, field, asdict
import math

import numpy as np


def _normalize(v):
    v = np.asarray(v, float)
    return v / max(np.linalg.norm(v), 1e-9)


def look_at(eye, target, up=(0, 0, 1)):
    f = _normalize(np.subtract(target, eye))
    if abs(np.dot(f, up)) > 0.999:
        up = (0, 1, 0)
    s = _normalize(np.cross(f, up))
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def perspective(fov_y, aspect, near, far):
    f = 1/math.tan(math.radians(fov_y)/2)
    m = np.zeros((4, 4))
    m[0, 0], m[1, 1] = f/aspect, f
    m[2, 2], m[2, 3] = (far+near)/(near-far), 2*far*near/(near-far)
    m[3, 2] = -1
    return m


def orthographic(left, right, bottom, top, near, far):
    m = np.eye(4)
    m[0, 0], m[1, 1], m[2, 2] = 2/(right-left), 2/(top-bottom), -2/(far-near)
    m[:3, 3] = -(right+left)/(right-left), -(top+bottom)/(top-bottom), -(far+near)/(far-near)
    return m


def _floats(text, count, name):
    values = [float(v) for v in str(text).replace(';', ',').split(',') if v.strip()]
    if len(values) not in count:
        raise ValueError(f'{name} needs {" or ".join(map(str, count))} comma-separated numbers: {text}')
    return values


@dataclass
class OrbitView:
    target: tuple
    distance: float = 1500.0
    elevation: float = 45.0
    heading: float = 0.0
    fov: float = 50.0
    eye: tuple = None
    near: float = None                 # near clip; default 1% of the distance
    roll: float = 0.0
    focal: float = None                # photo keys (render.photo)
    aperture: float = None
    focus: float = None
    ev: float = 0.0
    kind: str = field(default='orbit', init=False)

    def resolve(self, terrain, aspect):
        from mapworkshop.render.photo import focal_from_fov, fov_from_focal, sensor
        tx, ty = self.target[:2]
        tz = self.target[2] if len(self.target) > 2 else float(terrain.height_at(tx, ty))
        target = np.array([tx, ty, tz], float)
        if self.eye is not None:
            eye = np.array(self.eye, float)
        else:
            e, h = math.radians(self.elevation), math.radians(self.heading)
            back = np.array([-math.sin(h)*math.cos(e), -math.cos(h)*math.cos(e), math.sin(e)])
            eye = target + back*self.distance
        distance = float(np.linalg.norm(eye-target))
        # A focal length is on the image's crop of the sensor (render.photo).
        width = sensor(aspect)[0]
        fov = fov_from_focal(self.focal, width) if self.focal else self.fov
        fov_y = 2*math.degrees(math.atan(math.tan(math.radians(fov)/2)/aspect))
        near = self.near if self.near is not None else max(2.0, distance*0.01)
        far = distance*20+30000
        proj = perspective(fov_y, aspect, near, far)
        view = rolled(look_at(eye, target), self.roll)
        return dict(view_projection=proj @ view, eye=eye, target=target, near=near, far=far, sensor=width,
                    photo=dict(focal=self.focal or focal_from_fov(fov, width), aperture=self.aperture, ev=self.ev,
                               focus=self.focus if self.focus is not None else distance))

    def describe(self):
        return {k: v for k, v in asdict(self).items() if v is not None and not (k in ('roll', 'ev') and v == 0)}


def rolled(view, roll):
    """A view matrix turned `roll` degrees about the view direction, the camera
    to the right (clockwise as seen from behind it) for a positive roll, so the
    picture turns to the left."""
    if not roll:
        return view
    a = math.radians(roll)
    # The camera's axes turn clockwise by a, so what it sees turns the other way.
    turn = np.eye(4)
    turn[0, 0], turn[0, 1], turn[1, 0], turn[1, 1] = math.cos(a), -math.sin(a), math.sin(a), math.cos(a)
    return turn @ view


@dataclass
class TopView:
    region: tuple = None
    kind: str = field(default='top', init=False)

    border: bool = False

    def bounds(self, terrain, border=None):
        if self.region:
            return self.region
        b = terrain.border*10
        if border if border is not None else self.border:
            return (-b, -b, (terrain.width-1)*10-b, (terrain.height-1)*10-b)    # every sample
        return (0, 0, *terrain.playable)

    def resolve(self, terrain, aspect=None):
        x0, y0, x1, y1 = self.bounds(terrain)
        top = terrain.max_height+2000
        eye = np.array([(x0+x1)/2, (y0+y1)/2, top])
        view = look_at(eye, eye-np.array([0, 0, 1.0]), up=(0, 1, 0))
        proj = orthographic(-(x1-x0)/2, (x1-x0)/2, -(y1-y0)/2, (y1-y0)/2, 1.0, top+500)
        return dict(view_projection=proj @ view, eye=eye, target=eye-np.array([0, 0, top]))

    def describe(self):
        return dict(kind='top', region=list(self.region) if self.region else 'map')


def parse_view(words):
    """Build a view from key=value words (see the module documentation)."""
    spec = {}
    for word in words:
        if '=' not in word:
            raise ValueError(f'Expected key=value, got: {word}')
        key, value = word.split('=', 1)
        spec[key.strip().lower()] = value.strip()
    return view_from_dict(spec)


def view_from_dict(spec):
    spec = dict(spec)
    if spec.pop('kind', None) == 'top' or 'region' in spec and 'target' not in spec:
        region = spec.pop('region', None)
        if spec:
            raise ValueError('Unknown top-view keys: '+', '.join(spec))
        if region is not None and not isinstance(region, (list, tuple)):
            region = _floats(region, (4,), 'region')
        return TopView(tuple(float(v) for v in region) if region is not None else None)
    if 'target' not in spec:
        raise ValueError('An orbit view needs target=X,Y[,Z]')
    known = {'target', 'distance', 'elevation', 'heading', 'fov', 'eye', 'near', 'roll', 'focal', 'aperture', 'focus',
             'ev'}
    unknown = set(spec) - known
    if unknown:
        raise ValueError('Unknown view keys: '+', '.join(sorted(unknown))+'; use '+', '.join(sorted(known)))
    as_list = lambda v, n, name: tuple(v) if isinstance(v, (list, tuple)) else tuple(_floats(v, n, name))
    number = lambda key: float(spec[key]) if spec.get(key) not in (None, '', 'none', 'off') else None
    return OrbitView(target=as_list(spec['target'], (2, 3), 'target'),
                     distance=float(spec.get('distance', 1500)),
                     elevation=float(spec.get('elevation', 45)),
                     heading=float(spec.get('heading', 0)),
                     fov=float(spec.get('fov', 50)),
                     eye=as_list(spec['eye'], (3,), 'eye') if 'eye' in spec else None,
                     near=number('near'), roll=number('roll') or 0.0, focal=number('focal'),
                     aperture=number('aperture'), focus=number('focus'), ev=number('ev') or 0.0)
