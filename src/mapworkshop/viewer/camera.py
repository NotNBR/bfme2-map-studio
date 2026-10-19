"""The viewer's cameras: the orbit camera of Edit mode and the free camera
of Photo mode, the moves the mouse and keyboard make, and picking the
terrain under the cursor.

Navigation is in map units (x east, y north); heading, elevation, pitch and
roll are in degrees. Every move changes the goal and update() eases the
camera towards it, except pan(), which keeps the grabbed point exactly under
the cursor, and looking around in Photo mode, which follows the mouse 1:1.
Both cameras' matrices() give what the renderer draws with: view_projection,
eye, target, near and far.
"""

import math

import numpy as np

from mapworkshop.render.camera import look_at, perspective, rolled
from mapworkshop.render.photo import FOCAL_RANGE, focal_from_fov, fov_from_focal, image_size, sensor

ORBIT_DEGREES_PER_PIXEL = 0.25
SMOOTHING = 16.0          # 1/s; higher follows input faster
MIN_DISTANCE, MAX_DISTANCE = 60.0, 40000.0
ZOOM_STEP = 0.82          # distance factor per wheel notch
FLY_DISTANCE = 1500.0     # a double-click comes at least this close


def smooth(current, goal, dt, rate=SMOOTHING):
    return current + (goal-current)*(1-math.exp(-rate*dt))


def _clamp_distance(distance):
    return min(MAX_DISTANCE, max(MIN_DISTANCE, distance))


def _clamp_elevation(elevation):
    return min(89.5, max(5.0, elevation))


class Camera:
    """Orbit camera with separate goal and current state for smooth motion."""

    def __init__(self, surface, playable):
        self.surface = surface          # (x, y) -> visible height (terrain or water)
        self.playable = playable
        self.fov = 50.0
        self.top = None                 # (elevation, heading) to return to from the top view
        self.reset()
        self.snap()

    def reset(self):
        w, h = self.playable
        self.goal = dict(x=w/2, y=h/2, distance=max(w, h)*0.75, heading=0.0, elevation=55.0)

    def snap(self):
        self.cur = dict(self.goal)
        self.cur['z'] = self.ground(self.cur['x'], self.cur['y'])

    def ground(self, x, y):
        return float(self.surface(x, y))

    def update(self, dt):
        for key in ('x', 'y', 'heading', 'elevation'):
            self.cur[key] = smooth(self.cur[key], self.goal[key], dt)
        # Zoom is smoothed in log space so it feels uniform at every scale.
        self.cur['distance'] = math.exp(smooth(math.log(self.cur['distance']), math.log(self.goal['distance']), dt))
        self.cur['z'] = smooth(self.cur['z'], self.ground(self.cur['x'], self.cur['y']), dt, 8.0)

    # Moves -------------------------------------------------------------------
    def toggle_top(self):
        """Look straight down, north up; again to go back to the earlier tilt."""
        if self.top is None:
            self.top = (self.goal['elevation'], self.goal['heading'])
            self.goal['elevation'], self.goal['heading'] = 89.5, round(self.goal['heading']/360)*360
        else:
            self.goal['elevation'] = self.top[0]
            self.top = None

    def orbit(self, dx, dy):
        """Turn and tilt around the focus point by a mouse movement in pixels."""
        self.goal['heading'] += dx*ORBIT_DEGREES_PER_PIXEL
        self.goal['elevation'] = _clamp_elevation(self.goal['elevation']+dy*ORBIT_DEGREES_PER_PIXEL)

    def pan(self, anchor, hit):
        """Keep the grabbed ground point `anchor` under the cursor, now over
        `hit` (1:1, unsmoothed)."""
        for key, value in zip(('x', 'y'), anchor[:2]-hit[:2]):
            self.goal[key] += float(value)
            self.cur[key] += float(value)

    def zoom(self, notches, toward=None):
        """Zoom by wheel notches (positive: in), towards the map point `toward`."""
        old = self.goal['distance']
        new = _clamp_distance(old*ZOOM_STEP**notches)
        if toward is not None:
            k = 1-new/old
            self.goal['x'] += float((toward[0]-self.goal['x'])*k)
            self.goal['y'] += float((toward[1]-self.goal['y'])*k)
        self.goal['distance'] = new

    def fly_to(self, point):
        self.goal['x'], self.goal['y'] = float(point[0]), float(point[1])
        self.goal['distance'] = max(MIN_DISTANCE, min(self.goal['distance'], FLY_DISTANCE))

    def drive(self, dt, forward=0, right=0, turn=0, tilt=0, zoom=0, speed=1.0):
        """Keyboard movement for dt seconds: each of forward, right, turn,
        tilt and zoom is -1, 0 or 1; moving scales with the zoom level and
        `speed`. Keeps the focus point on the map."""
        rate = self.goal['distance']*1.1*speed
        if forward or right:
            h = math.radians(self.goal['heading'])
            self.goal['x'] += (math.sin(h)*forward+math.cos(h)*right)*rate*dt
            self.goal['y'] += (math.cos(h)*forward-math.sin(h)*right)*rate*dt
        self.goal['heading'] += turn*90*dt
        self.goal['elevation'] = _clamp_elevation(self.goal['elevation']+tilt*60*dt)
        if zoom:
            self.goal['distance'] = _clamp_distance(self.goal['distance']*math.exp(zoom*1.5*dt))
        w, h = self.playable
        self.goal['x'] = min(w, max(0.0, self.goal['x']))
        self.goal['y'] = min(h, max(0.0, self.goal['y']))

    def screen_angle(self):
        """The angle (radians, counter-clockwise) that lines a new rectangle up
        with the screen; 0 within 10 degrees of the map axes."""
        a = math.remainder(-math.radians(self.cur['heading']), math.pi/2)
        return 0.0 if abs(a) < math.radians(10) else a

    # Projection and picking --------------------------------------------------
    def matrices(self, aspect, state=None):
        s = state or self.cur
        e, h = math.radians(s['elevation']), math.radians(s['heading'])
        target = np.array([s['x'], s['y'], s['z']])
        eye = target + np.array([-math.sin(h)*math.cos(e), -math.cos(h)*math.cos(e), math.sin(e)])*s['distance']
        # Never look from inside the terrain.
        floor = self.ground(eye[0], eye[1])+15.0
        if eye[2] < floor:
            eye[2] = floor
        fov_y = 2*math.degrees(math.atan(math.tan(math.radians(self.fov)/2)/aspect))
        near, far = max(2.0, s['distance']*0.01), s['distance']*20+30000
        proj = perspective(fov_y, aspect, near, far)
        return dict(view_projection=proj @ look_at(eye, target), eye=eye, target=target, near=near, far=far)

    def ray(self, cursor, size):
        """World-space ray through a window position (pixels, origin top-left)."""
        return screen_ray(self.matrices(size[0]/size[1]), cursor, size)

    def pick(self, cursor, size):
        """Terrain point under the cursor (ray march + bisection), or None."""
        return march(*self.ray(cursor, size), self.surface, self.cur['distance']*6+20000)

    def plane_hit(self, cursor, size, z):
        origin, direction = self.ray(cursor, size)
        if abs(direction[2]) < 1e-6:
            return None
        t = (z-origin[2])/direction[2]
        return origin+direction*t if t > 0 else None

    # Edit and Photo ----------------------------------------------------------
    def aim(self, eye, forward, surface_hit=None):
        """Orbit the ground the free camera at `eye` looks at along `forward`:
        `surface_hit`, or where its heading meets the ground ahead when it looks
        above the horizon. Snaps there; the tilt keeps within its limits."""
        heading = math.degrees(math.atan2(forward[0], forward[1]))
        if surface_hit is None:
            ahead = np.array([forward[0], forward[1]])
            ahead = ahead/(np.linalg.norm(ahead) or 1.0)
            reach = max(300.0, abs(eye[2]-self.ground(eye[0], eye[1]))*1.5)
            x, y = eye[0]+ahead[0]*reach, eye[1]+ahead[1]*reach
            surface_hit = np.array([x, y, self.ground(x, y)])
        offset = np.asarray(eye, float)-surface_hit
        distance = float(np.linalg.norm(offset))
        elevation = math.degrees(math.asin(max(-1.0, min(1.0, offset[2]/(distance or 1.0)))))
        self.goal = dict(x=float(surface_hit[0]), y=float(surface_hit[1]), distance=_clamp_distance(distance),
                         heading=heading, elevation=_clamp_elevation(elevation))
        self.top = None
        self.snap()


def screen_ray(camera, cursor, size):
    """World-space ray (origin, unit direction) through a window position."""
    inv = np.linalg.inv(camera['view_projection'])
    nx = 2*cursor[0]/size[0]-1
    ny = 1-2*cursor[1]/size[1]
    near = inv @ np.array([nx, ny, -1, 1.0]); near = near[:3]/near[3]
    far = inv @ np.array([nx, ny, 1, 1.0]); far = far[:3]/far[3]
    return near, (far-near)/np.linalg.norm(far-near)


def march(origin, direction, surface, reach):
    """The first point along a ray at or below `surface` within `reach` (ray
    march + bisection), or None."""
    t = np.linspace(0, reach, 1500)
    points = origin+np.outer(t, direction)
    below = points[:, 2] <= surface(points[:, 0], points[:, 1])
    hits = np.nonzero(below)[0]
    if not len(hits):
        return None
    i = hits[0]
    lo, hi = t[max(i-1, 0)], t[i]
    for _ in range(20):
        mid = (lo+hi)/2
        p = origin+direction*mid
        if p[2] <= surface(p[0], p[1]):
            hi = mid
        else:
            lo = mid
    return origin+direction*hi


LOOK_DEGREES_PER_PIXEL = 0.08     # at a 50 degree field of view; narrower turns slower
FOCAL_STEP = 1.12                  # focal length factor per wheel notch
FOCUS_STEP = 1.15                  # focus distance factor per wheel notch


class FlyCamera:
    """Photo mode's free camera: an eye anywhere, turned by `heading` (0 north,
    90 east), `pitch` (above the horizon, -90 to 90) and `roll` (to the
    right), and a lens (render.photo): `focal` mm, `aperture` (an f-number,
    None for everything sharp), `focus` (map units along the view) and `ev`.
    `frame` is the aspect of the picture within the window (None: the whole
    window); the focal length is on that frame's crop of the sensor, and the
    window shows more around it.

    Moves ease the eye towards its goal; turns follow the mouse at once."""

    def __init__(self, surface):
        self.surface = surface
        self.eye = np.array([0.0, 0.0, 1000.0])
        self.goal = self.eye.copy()
        self.heading, self.pitch, self.roll = 0.0, -30.0, 0.0
        self.focal, self.aperture, self.focus, self.ev = focal_from_fov(50.0), None, 1500.0, 0.0
        self.frame = None

    def frame_aspect(self, aspect):
        """The picture's aspect in a window of `aspect`."""
        return self.frame or aspect

    def fov(self, aspect):
        """The picture's horizontal field of view (degrees) in a window of `aspect`."""
        return fov_from_focal(self.focal, sensor(self.frame_aspect(aspect))[0])

    def forward(self):
        h, p = math.radians(self.heading), math.radians(self.pitch)
        return np.array([math.sin(h)*math.cos(p), math.cos(h)*math.cos(p), math.sin(p)])

    def right(self):
        h = math.radians(self.heading)
        return np.array([math.cos(h), -math.sin(h), 0.0])

    def clearance(self):
        """Height above the ground under the eye (negative below it)."""
        return float(self.eye[2]-float(self.surface(self.eye[0], self.eye[1])))

    def speed(self):
        """Map units per second at speed 1: faster high up."""
        return max(60.0, abs(self.clearance()))

    def place(self, eye, forward, focus=None):
        """Put the eye at `eye` looking along `forward` (roll 0)."""
        f = np.asarray(forward, float)
        f = f/(np.linalg.norm(f) or 1.0)
        self.eye = np.asarray(eye, float).copy()
        self.goal = self.eye.copy()
        self.heading = math.degrees(math.atan2(f[0], f[1]))
        self.pitch = math.degrees(math.asin(max(-1.0, min(1.0, f[2]))))
        self.roll = 0.0
        if focus is not None:
            self.focus = float(focus)

    def update(self, dt):
        self.eye = self.eye + (self.goal-self.eye)*(1-math.exp(-12.0*dt))

    def look(self, dx, dy):
        """Turn by a mouse movement in pixels: right and down look right and down."""
        k = LOOK_DEGREES_PER_PIXEL*fov_from_focal(self.focal)/50.0
        self.heading = (self.heading + dx*k) % 360
        self.pitch = min(89.9, max(-89.9, self.pitch - dy*k))

    def drive(self, dt, forward=0, right=0, up=0, roll=0, speed=1.0):
        """Keyboard movement for dt seconds: forward along the view, right,
        and up; roll turns about the view direction."""
        step = self.speed()*speed*dt
        self.goal = self.goal + (self.forward()*forward + self.right()*right + np.array([0, 0, 1.0])*up)*step
        self.roll = max(-90.0, min(90.0, self.roll + roll*45*dt))

    def slide(self, dx, dy):
        """Move sideways and up by a mouse movement in pixels (a right drag)."""
        k = self.speed()*0.003
        self.goal = self.goal + self.right()*dx*k + np.array([0, 0, 1.0])*(-dy)*k

    def dolly(self, notches):
        """Move along the view by wheel notches (positive: forward)."""
        self.goal = self.goal + self.forward()*notches*max(20.0, self.speed()*0.25)

    def zoom(self, notches):
        """Longer focal length by wheel notches (positive: in)."""
        self.focal = min(FOCAL_RANGE[1], max(FOCAL_RANGE[0], self.focal*FOCAL_STEP**notches))

    def refocus(self, notches):
        """Focus further by wheel notches (positive: further)."""
        self.focus = min(100000.0, max(5.0, self.focus*FOCUS_STEP**notches))

    def matrices(self, aspect):
        """The camera for the renderer; its target is the point in focus ahead,
        `sensor` the window's width in mm at the sensor's scale."""
        eye = self.eye
        target = eye + self.forward()*self.focus
        width, height = image_size(aspect, self.frame)
        fov_y = 2*math.degrees(math.atan(height/2/self.focal))
        near = min(40.0, max(1.0, abs(self.clearance())*0.02))
        far = 80000.0
        proj = perspective(fov_y, aspect, near, far)
        view = rolled(look_at(eye, target), self.roll)
        return dict(view_projection=proj @ view, eye=eye.copy(), target=target, near=near, far=far, sensor=width,
                    photo=self.settings())

    def settings(self):
        return dict(focal=self.focal, aperture=self.aperture, focus=self.focus, ev=self.ev)

    def ray(self, cursor, size):
        return screen_ray(self.matrices(size[0]/size[1]), cursor, size)

    def pick_ahead(self, size):
        """The terrain point at the centre of the view, or None."""
        return march(*self.ray((size[0]/2, size[1]/2), size), self.surface, 60000.0)
