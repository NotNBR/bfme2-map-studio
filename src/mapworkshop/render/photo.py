"""Photo effects: a camera lens and exposure over a rendered view.

The game has neither; the viewer's Photo mode and `mw render` views with
`focal`, `aperture`, `focus` or `ev` use them for pictures.

The lens is a full-frame camera's: a 36 x 24 mm sensor. A picture of aspect
3:2 or wider is 36 mm wide on it, a narrower one 24 mm tall, as a camera's
crop modes take the largest frame of their aspect (sensor()). A focal length
f gives a frame w mm wide a horizontal field of view of 2 atan(w / 2f): at 3:2
and wider, 39 mm is the preview cameras' 50 degrees. Where the viewer shows a
frame inside a wider window, the window shows more around it at the frame's
scale (image_size()).

Depth of field follows the thin lens: a point at distance D, focused at S with
aperture f/N, blurs to a circle of (f / N) x f / (S - f) x |D - S| / D on the
sensor, scaled to pixels by the frame's pixels per mm. D and S are along the
view axis (the depth buffer's distance), so what is in focus is a plane, as
with a real lens. Distances need a scale: UNITS_PER_METRE map units to the
metre (a soldier is about 20 units tall), so wide apertures blur as a real lens
would at that size. Light mixes in linear colour, so a bright point spreads
into a bright disc. The aperture changes only the depth of field, as under
aperture-priority auto exposure; `ev` is the exposure compensation.

Exposure multiplies the linear colour by 2^ev, so it brightens or darkens; it
cannot bring back highlights that were white.

The viewer draws both effects over the finished frame
(viewer/godot/shaders/photo.glsl): each pixel's blur circle is worked out from
its depth. Two small passes find how far blur reaches around each pixel: the
largest blur in each TILE x TILE tile, then the largest of the tiles it can
reach (MAX_BLUR, 6% of the width, is the most). The blur is Dennis
Gustafsson's single pass ("Bokeh depth of field in a single pass", 2018):
over a disc as large as that reach, every sample
whose own circle reaches the pixel joins a running average with equal weight,
and one that does not adds the average so far. So a blurred foreground spreads
over a sharp background, its outline soft, while a sample behind the pixel
counts with at most twice the pixel's own circle, so a sharp foreground keeps
its edge. The disc's sample pattern turns per pixel, which trades the repeated
copies a fixed pattern gives in large blur for fine grain.
"""

import math

SENSOR = 36.0, 24.0                 # mm, full frame
SENSOR_WIDTH = SENSOR[0]
UNITS_PER_METRE = 10.0
FOCAL_RANGE = 10.0, 600.0           # mm
MAX_BLUR = 0.06                     # the largest blur circle's diameter, as a share of the image width
SHARP = 1/1500                      # the blur counted as sharp, as a share of the frame's diagonal (0.029 mm on full frame)


def sensor(aspect):
    """(width, height) in mm of the largest frame of `aspect` (width / height)
    on the sensor: 36 mm wide at 3:2 and wider, 24 mm tall when narrower."""
    w, h = SENSOR
    return (w, w/aspect) if aspect >= w/h else (h*aspect, h)


def image_size(aspect, frame=None):
    """(width, height) in mm on the sensor's scale of an image of `aspect`
    holding a centred frame of aspect `frame` (None: the image is the frame),
    as the viewer's Photo mode fits a frame in the window (lens.gd's frame_rect)."""
    if not frame:
        return sensor(aspect)
    fw, fh = sensor(frame)
    return (fw, fw/aspect) if aspect <= frame else (fh*aspect, fh)


def fov_from_focal(focal, width=SENSOR_WIDTH):
    """Horizontal field of view (degrees) of a focal length (mm) over an image
    `width` mm wide."""
    return 2*math.degrees(math.atan(width/2/focal))


def focal_from_fov(fov, width=SENSOR_WIDTH):
    """Focal length (mm) giving an image `width` mm wide a horizontal field of
    view (degrees)."""
    return width/2/math.tan(math.radians(fov)/2)


def _mm(units):
    return units/UNITS_PER_METRE*1000


def blur_pixels(distance, focus, focal, aperture, width, sensor_width=SENSOR_WIDTH):
    """Diameter in pixels of the blur circle of a point `distance` map units
    away, focused at `focus`, for a focal length (mm), an f-number and an
    image `width` pixels and `sensor_width` mm wide; not limited to MAX_BLUR."""
    d, s = _mm(distance), max(_mm(focus), focal*1.001)
    circle = (focal/aperture)*focal/(s-focal)*abs(d-s)/max(d, 1e-6)
    return circle/sensor_width*width


def sharp_range(focus, focal, aperture, aspect=1.5):
    """(near, far) map units between which the blur stays below SHARP of a
    frame of `aspect`'s diagonal; far is inf at and beyond the hyperfocal
    distance."""
    c = math.hypot(*sensor(aspect))*SHARP
    s = max(_mm(focus), focal*1.001)
    hyperfocal = focal*focal/(aperture*c) + focal
    near = s*(hyperfocal-focal)/(hyperfocal+s-2*focal)
    far = s*(hyperfocal-focal)/(hyperfocal-s) if s < hyperfocal else math.inf
    return near/1000*UNITS_PER_METRE, far/1000*UNITS_PER_METRE


def active(settings):
    """Whether photo `settings` (aperture, ev) change the image."""
    return bool(settings.get('aperture')) or abs(settings.get('ev') or 0.0) > 1e-6
