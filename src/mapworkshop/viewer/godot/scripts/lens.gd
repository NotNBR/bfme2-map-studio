## Photo mode's lens: the maths is OpenBFME's pro camera (Pro, the engine's scripts/pro_lens.gd, which the assembly
## brings from the pinned engine; its docs/PRO_CAMERA.md has the model), and this keeps what is Photo mode's own: the
## presets, the frames and the texts. render/photo.py repeats the maths for mw render's views in Python
## (test_photo checks it against Pro's constants).
class_name Lens
extends RefCounted

const Pro := preload("res://scripts/pro_lens.gd")
const SENSOR := Pro.SENSOR                # mm, full frame
const UNITS_PER_METRE := Pro.UNITS_PER_METRE
const FOCAL_RANGE := Vector2(10.0, 600.0)
const FOCAL_STEP := 1.12                  # focal length factor per wheel notch
const FOCUS_STEP := 1.15                  # focus distance factor per wheel notch

## [value, label, width / height (0: the whole window)]
const FRAMES := [["free", "Free", 0.0], ["16:9", "16:9", 16.0 / 9.0], ["21:9", "21:9", 21.0 / 9.0],
	["3:2", "3:2", 1.5], ["4:3", "4:3", 4.0 / 3.0], ["1:1", "1:1", 1.0]]
const FOCALS := [14, 18, 24, 28, 35, 50, 85, 135, 200, 400]
const APERTURES := [0.0, 0.5, 0.7, 0.95, 1.2, 1.4, 2.0, 2.8, 4.0, 5.6, 8.0, 11.0, 16.0, 22.0]   # 0: everything sharp
const FOCUS_DISTANCES := [50, 100, 200, 500, 1000, 2000, 5000]
const EXPOSURES := [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]


static func sensor(aspect: float) -> Vector2:
	return Pro.sensor(aspect)


static func image_size(aspect: float, frame: float) -> Vector2:
	return Pro.image_size(aspect, frame)


static func fov_from_focal(focal: float, width: float = SENSOR.x) -> float:
	return Pro.fov_from_focal(focal, width)


static func focal_from_fov(fov: float, width: float = SENSOR.x) -> float:
	return Pro.focal_from_fov(fov, width)


static func sharp_range(focus: float, focal: float, aperture: float, aspect: float) -> Vector2:
	return Pro.sharp_range(focus, focal, aperture, aspect)


static func frame_rect(size: Vector2i, ratio: float) -> Rect2i:
	return Pro.frame_rect(size, ratio)


static func frame_ratio(frame: String) -> float:
	for f in FRAMES:
		if f[0] == frame:
			return f[2]
	return 0.0


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
