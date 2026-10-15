"""The viewer's orbit camera: smooth motion towards a goal, picking the
terrain under the cursor, and the moves the mouse and keyboard make.

Navigation is in map units (x east, y north); heading and elevation are in
degrees. Every move changes the goal and update() eases the camera towards
it, except pan(), which keeps the grabbed point exactly under the cursor.
"""

import math

import numpy as np

from mapworkshop.render.camera import look_at, perspective

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
        near = max(2.0, s['distance']*0.01)
        proj = perspective(fov_y, aspect, near, s['distance']*20+30000)
        return dict(view_projection=proj @ look_at(eye, target), eye=eye, target=target)

    def ray(self, cursor, size):
        """World-space ray through a window position (pixels, origin top-left)."""
        cam = self.matrices(size[0]/size[1])
        inv = np.linalg.inv(cam['view_projection'])
        nx = 2*cursor[0]/size[0]-1
        ny = 1-2*cursor[1]/size[1]
        near = inv @ np.array([nx, ny, -1, 1.0]); near = near[:3]/near[3]
        far = inv @ np.array([nx, ny, 1, 1.0]); far = far[:3]/far[3]
        return near, (far-near)/np.linalg.norm(far-near)

    def pick(self, cursor, size):
        """Terrain point under the cursor (ray march + bisection), or None."""
        origin, direction = self.ray(cursor, size)
        reach = self.cur['distance']*6+20000
        t = np.linspace(0, reach, 1500)
        points = origin+np.outer(t, direction)
        below = points[:, 2] <= self.surface(points[:, 0], points[:, 1])
        hits = np.nonzero(below)[0]
        if not len(hits):
            return None
        i = hits[0]
        lo, hi = t[max(i-1, 0)], t[i]
        for _ in range(20):
            mid = (lo+hi)/2
            p = origin+direction*mid
            if p[2] <= self.surface(p[0], p[1]):
                hi = mid
            else:
                lo = mid
        return origin+direction*hi

    def plane_hit(self, cursor, size, z):
        origin, direction = self.ray(cursor, size)
        if abs(direction[2]) < 1e-6:
            return None
        t = (z-origin[2])/direction[2]
        return origin+direction*t if t > 0 else None
