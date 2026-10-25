"""The lens of a view with `focal`: its field of view, for mw render to work
out the camera in Python before the Godot viewer draws it.

The model is OpenBFME's pro camera (the engine's godot/scripts/pro_lens.gd;
its docs/PRO_CAMERA.md has it): a full-frame 36 x 24 mm sensor, a picture of
aspect 3:2 or wider 36 mm wide on it and a narrower one 24 mm tall (sensor()),
and a focal length f giving a frame w mm wide a horizontal field of view of
2 atan(w / 2f): at 3:2 and wider, 39 mm is the preview cameras' 50 degrees.
The depth of field and exposure are drawn by the engine's effect alone
(pro_lens_effect.gd); this module keeps only what the camera needs.
"""

import math

SENSOR = 36.0, 24.0                 # mm, full frame
SENSOR_WIDTH = SENSOR[0]


def sensor(aspect):
    """(width, height) in mm of the largest frame of `aspect` (width / height)
    on the sensor: 36 mm wide at 3:2 and wider, 24 mm tall when narrower."""
    w, h = SENSOR
    return (w, w/aspect) if aspect >= w/h else (h*aspect, h)


def fov_from_focal(focal, width=SENSOR_WIDTH):
    """Horizontal field of view (degrees) of a focal length (mm) over an image
    `width` mm wide."""
    return 2*math.degrees(math.atan(width/2/focal))


def focal_from_fov(fov, width=SENSOR_WIDTH):
    """Focal length (mm) giving an image `width` mm wide a horizontal field of
    view (degrees)."""
    return width/2/math.tan(math.radians(fov)/2)
