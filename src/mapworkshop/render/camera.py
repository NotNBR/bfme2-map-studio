"""Preview cameras, plus the game's own tactical camera for comparisons.

World coordinates: X east, Y north, Z up, origin at the playable map's
south-west corner, 10 units per terrain cell.

OrbitView and TopView are preview cameras built for clear framing.
GameCamera reproduces where BFME2 puts its camera for a focus point and a
height above ground (see its documentation).

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
import re

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


def _ini_float(text, key, default):
    match = re.search(r'(?im)^\s*' + key + r'\s*=\s*(-?[\d.]+)', text or '')
    return float(match.group(1)) if match else default


def camera_height_field(heights, smoothness, low=-9999999.0, high=9999999.0):
    """SmoothCameraHeightField::Initialize (game.dat 0x0030E961).

    `heights` is the full height grid (rows = y, border included) in world
    units. Each output sample is the maximum (at least 0) of a 4 x 4 block of
    terrain samples, so samples are 40 units apart; then every sample is
    raised to its 8 neighbours minus smoothness x 40 x 0.6 (x 1.4
    diagonally) until nothing changes. Returns a float32 [rows, columns] grid.
    """
    f32 = np.float32
    h, w = heights.shape
    rows, cols = (h + 3)//4, (w + 3)//4
    padded = np.full((rows*4, cols*4), -np.inf, f32)
    padded[:h, :w] = np.clip(np.asarray(heights, f32), f32(low), f32(high))
    data = np.maximum(padded.reshape(rows, 4, cols, 4).max(axis=(1, 3)), f32(0.0))
    step = f32(f32(f32(smoothness)*f32(40.0))*f32(0.6))
    diagonal = f32(step*f32(1.4))
    # The game sweeps in place for up to max(rows, cols) passes; repeating
    # whole-grid sweeps until nothing changes reaches the same fixed point.
    for _ in range(rows*cols):
        raised = data.copy()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == dy == 0:
                    continue
                shifted = np.full_like(data, -np.inf)
                ys = slice(max(dy, 0), rows+min(dy, 0)); yd = slice(max(-dy, 0), rows+min(-dy, 0))
                xs = slice(max(dx, 0), cols+min(dx, 0)); xd = slice(max(-dx, 0), cols+min(-dx, 0))
                shifted[yd, xd] = data[ys, xs]
                np.maximum(raised, shifted - (diagonal if dx and dy else step), out=raised)
        if np.array_equal(raised, data):
            break
        data = raised
    return data


class GameCamera:
    """BFME2's tactical camera (W3DView, game.dat 1.06) over one map.

    The capture tools call W3DView::lookAt (0x0008D55D) on a focus point and
    setHeightAboveGround (0x0008D2B8) with the requested height. From the
    matched code:

    - lookAt keeps the focus x/y with z = 0 and sets the ground level G to the
      map's smoothed camera height at the focus (SmoothCameraHeightField,
      sampled by 0x0030E67C), or without that field to getHeightAroundPos
      (0x00085677: the highest of the focus and four corners
      +-CameraTerrainSampleRadiusForHeight away).
    - The camera offset (Rva00BCF670CameraSettings::getCameraOffset
      0x001018CD) points back and up at the pitch angle above the horizon,
      offset.z = cameraMaxHeight (map WorldInfo, else GameData
      DefaultCameraMaxHeight); the yaw turns it about Z.
    - W3DView::update (0x0008C3AC) moves the zoom towards
      (height + G) / offset.z by CameraAdjustSpeed per frame and stops once a
      step is below 0.0001, so the eye ends a few units off (up to
      0.0001 / speed x offset.z, on the side it came from).
    - The transform solver (0x00102F83, as in Zero Hour's buildCameraTransform)
      places the eye at zoom x offset scaled by 1 - G / (zoom x offset.z)
      above (focus x, focus y, G) and looks at that point: eye z = zoom x
      offset.z, target z = G.
    - setCameraTransform (0x0008BE6B): near clip 10; setWidth (0x00087B81):
      50 degrees horizontal field of view, aspect from the viewport.
    """

    NEAR = 10.0
    FOV = 50.0

    def __init__(self, game_map, terrain, gamedata_text=''):
        from mapworkshop.formats.map import Reader
        try:
            props = {k: v for k, _, v in game_map.properties(Reader(game_map.chunk('WorldInfo').data))}
        except ValueError:
            props = {}
        g = lambda key, default: _ini_float(gamedata_text, key, default)
        self.max_height = float(props.get('cameraMaxHeight', g('DefaultCameraMaxHeight', 300.0)))
        self.min_height = float(props.get('cameraMinHeight', g('DefaultCameraMinHeight', 120.0)))
        self.pitch = float(props.get('cameraPitchAngle', g('DefaultCameraPitchAngle', 37.5)))
        self.yaw = float(props.get('cameraYawAngle', g('DefaultCameraYawAngle', 0.0)))
        self.adjust_speed = g('CameraAdjustSpeed', 0.3)
        self.sample_radius = g('CameraTerrainSampleRadiusForHeight', 0.0)
        # GlobalData +0xDE4 has no INI key; its constructor sets 1.0.
        smoothness = float(props.get('cameraMapHeightSmoothnessScalar', 1.0))
        self.terrain = terrain
        self.field = None
        if smoothness != 0.0:
            low = float(props.get('cameraGroundMinHeight', -9999999.0))
            high = float(props.get('cameraGroundMaxHeight', 9999999.0))
            self.field = camera_height_field(terrain.heights, smoothness, *sorted((low, high)))

    def offset(self):
        """(offset x, y, z, yaw radians) as getCameraOffset returns them."""
        custom = (self.pitch != 37.5 or self.yaw != 0.0 or self.min_height != 120.0 or self.max_height != 300.0)
        p = math.radians(self.pitch)
        if custom:
            distance = self.max_height*1.642665
            return 0.0, -math.cos(p)*distance, math.sin(p)*distance, math.radians(self.yaw)
        y = -(self.max_height/math.tan(p))
        return -(math.tan(math.radians(self.yaw))*y), y, self.max_height, 0.0

    def ground(self, x, y):
        """Camera ground level G at a focus point."""
        if self.field is None:
            r = self.sample_radius
            h = lambda px, py: float(self.terrain.height_at(px, py))
            return max(h(x, y), h(x-r, y+r), h(x+r, y+r), h(x-r, y-r), h(x+r, y-r))
        f32 = np.float32
        data = self.field
        rows, cols = data.shape
        border = f32(self.terrain.border)*f32(10.0)
        inverse = f32(1.0)/f32(40.0)
        gx = (f32(x)+border)*inverse
        gy = (f32(y)+border)*inverse
        ix, iy = int(math.floor(gx)), int(math.floor(gy))
        fx, fy = gx-f32(ix), gy-f32(iy)
        ix = min(max(ix, 0), cols-1); iy = min(max(iy, 0), rows-1)
        if ix > cols-2 or iy > rows-2:
            return float(data[iy, ix])
        p00, p11 = data[iy, ix], data[iy+1, ix+1]
        if fy > fx:
            c = data[iy+1, ix]
            return float((p00-c)*(f32(1.0)-fy) + (p11-c)*fx + c)
        c = data[iy, ix+1]
        return float((p00-c)*(f32(1.0)-fx) + (p11-c)*fy + c)

    def eye_height(self, x, y, height, start=None):
        """World z where W3DView::update leaves the eye, starting from eye z
        `start` (default: from above, at the maximum height)."""
        f32 = np.float32
        height = min(max(height, self.min_height), self.max_height)
        oz = f32(self.offset()[2])
        under = f32(self.ground(x, y))
        desired = f32((f32(height)+under)/oz)
        zoom = f32(f32(start if start is not None else self.max_height+float(under))/oz)
        speed = f32(self.adjust_speed)
        for _ in range(10000):
            step = f32((zoom-desired)*speed)
            if abs(step) < 0.0001:
                break
            zoom = f32(zoom-step)
        return float(zoom*oz)

    def view(self, x, y, height, eye_z=None, start=None):
        """OrbitView of the game camera focused on (x, y) at `height` above
        ground. `eye_z` (a recorded eye height) skips the convergence model."""
        ground = self.ground(x, y)
        if eye_z is None:
            eye_z = self.eye_height(x, y, height, start)
        ox, oy, oz, angle = self.offset()
        # Matrix3D(Vector3(0, 0, 1), angle) * offset, scaled to the eye height.
        k = (eye_z-ground)/oz
        dx = (ox*math.cos(angle) - oy*math.sin(angle))*k
        dy = (ox*math.sin(angle) + oy*math.cos(angle))*k
        return OrbitView(target=(float(x), float(y), ground), eye=(x+dx, y+dy, eye_z), fov=self.FOV, near=self.NEAR)


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
        top = float(terrain.heights.max())+2000
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
