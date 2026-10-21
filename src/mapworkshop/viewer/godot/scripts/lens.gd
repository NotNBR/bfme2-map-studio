## Photo mode's lens, as render/photo.py works it out (its docstring has the reasoning): a full-frame camera, 36 x 24
## mm; a frame of aspect 3:2 or wider is 36 mm wide on it, a narrower one 24 mm tall, and a focal length frames it
## with a horizontal field of view of 2 atan(w / 2f). Depth of field is the thin lens, with UNITS_PER_METRE map units
## to the metre. The presets and the frames are viewer/camerabar.py's. Phase 4 of docs/godot-viewer/plan.md removes
## the Python viewer; this is then the presets' only home (render/photo.py keeps the lens for mw render).
class_name Lens
extends RefCounted

const SENSOR := Vector2(36.0, 24.0)       # mm, full frame
const UNITS_PER_METRE := 10.0
const FOCAL_RANGE := Vector2(10.0, 600.0)
const MAX_BLUR := 0.06                    # the largest blur circle's diameter, as a share of the image width
const SHARP := 1.0 / 1500.0               # the blur counted as sharp, as a share of the frame's diagonal
const FOCAL_STEP := 1.12                  # focal length factor per wheel notch (viewer/camera.py)
const FOCUS_STEP := 1.15                  # focus distance factor per wheel notch

## [value, label, width / height (0: the whole window)]
const FRAMES := [["free", "Free", 0.0], ["16:9", "16:9", 16.0 / 9.0], ["21:9", "21:9", 21.0 / 9.0],
	["3:2", "3:2", 1.5], ["4:3", "4:3", 4.0 / 3.0], ["1:1", "1:1", 1.0]]
const FOCALS := [14, 18, 24, 28, 35, 50, 85, 135, 200, 400]
const APERTURES := [0.0, 0.5, 0.7, 0.95, 1.2, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0]   # 0: everything sharp
const FOCUS_DISTANCES := [50, 100, 200, 500, 1000, 2000, 5000]
const EXPOSURES := [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]


## The largest frame of `aspect` on the sensor, in mm.
static func sensor(aspect: float) -> Vector2:
	return Vector2(SENSOR.x, SENSOR.x / aspect) if aspect >= SENSOR.x / SENSOR.y else Vector2(SENSOR.y * aspect, SENSOR.y)


## An image of `aspect` holding a centred frame of aspect `frame` (0: the image is the frame), in mm on the sensor's
## scale.
static func image_size(aspect: float, frame: float) -> Vector2:
	if frame <= 0.0:
		return sensor(aspect)
	var f := sensor(frame)
	return Vector2(f.x, f.x / aspect) if aspect <= frame else Vector2(f.y * aspect, f.y)


static func fov_from_focal(focal: float, width: float = SENSOR.x) -> float:
	return 2.0 * rad_to_deg(atan(width / 2.0 / focal))


static func focal_from_fov(fov: float, width: float = SENSOR.x) -> float:
	return width / 2.0 / tan(deg_to_rad(fov) / 2.0)


## (near, far) map units between which the blur stays under SHARP of a frame of `aspect`'s diagonal; far is INF at and
## beyond the hyperfocal distance.
static func sharp_range(focus: float, focal: float, aperture: float, aspect: float) -> Vector2:
	var c := sensor(aspect).length() * SHARP
	var s := maxf(focus / UNITS_PER_METRE * 1000.0, focal * 1.001)
	var hyperfocal := focal * focal / (aperture * c) + focal
	var near := s * (hyperfocal - focal) / (hyperfocal + s - 2.0 * focal)
	var far := s * (hyperfocal - focal) / (hyperfocal - s) if s < hyperfocal else INF
	return Vector2(near, far) / 1000.0 * UNITS_PER_METRE


static func frame_ratio(frame: String) -> float:
	for f in FRAMES:
		if f[0] == frame:
			return f[2]
	return 0.0


## The frame of aspect `ratio` centred in a window `size` (the whole window for 0), in pixels.
static func frame_rect(size: Vector2i, ratio: float) -> Rect2i:
	if ratio <= 0.0:
		return Rect2i(Vector2i.ZERO, size)
	if float(size.x) / size.y > ratio:
		var fw := roundi(size.y * ratio)
		return Rect2i((size.x - fw) / 2, 0, fw, size.y)
	var fh := roundi(size.x / ratio)
	return Rect2i(0, (size.y - fh) / 2, size.x, fh)


static func aperture_text(aperture: float) -> String:
	return "f/–" if aperture <= 0.0 else "f/%s" % number(aperture)


static func ev_text(ev: float) -> String:
	return "EV %+.1f" % ev if absf(ev) > 1e-6 else "EV 0"


static func sharp_text(r: Vector2) -> String:
	return "sharp %s – %s" % [thousands(r.x), "∞" if is_inf(r.y) else thousands(r.y)]


## A number as Python's :g shows it (2, 2.8, 0.95).
static func number(v: float) -> String:
	return String.num(v, 3).trim_suffix(".0")


## A whole number with thousands separators, as Python's :,.0f shows it (-1,234).
static func thousands(v: float) -> String:
	var digits := str(absi(roundi(v)))
	var out := ""
	while digits.length() > 3:
		out = "," + digits.right(3) + out
		digits = digits.left(digits.length() - 3)
	return ("-" if roundi(v) < 0 else "") + digits + out
