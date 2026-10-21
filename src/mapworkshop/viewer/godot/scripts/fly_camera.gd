## Photo mode's free camera, a port of viewer/camera.py's FlyCamera: an eye anywhere (nothing holds it above the
## ground), turned by `heading` (0 north, 90 east), `pitch` (above the horizon) and `roll` (to the right), and a lens
## (Lens): `focal` mm, `aperture` (an f-number, 0 for everything sharp), `focus` (map units along the view) and `ev`.
## `frame` is the aspect of the picture within the window (0: the whole window); the focal length is on that frame's
## crop of the sensor, and the window shows more around it. Moves ease the eye towards its goal; turns follow the
## mouse at once. All in map coordinates.
class_name FlyCamera
extends RefCounted

const LOOK_DEGREES_PER_PIXEL := 0.08      # at a 50 degree field of view; narrower turns slower
const FAR := 80000.0

var surface: Surface
var eye := Vector3(0, 0, 1000)
var goal := Vector3(0, 0, 1000)
var heading := 0.0
var pitch := -30.0
var roll := 0.0
var focal := Lens.focal_from_fov(50.0)
var aperture := 0.0
var focus := 1500.0
var ev := 0.0
var frame := 0.0


func _init(s: Surface) -> void:
	surface = s


func frame_aspect(aspect: float) -> float:
	return frame if frame > 0.0 else aspect


## The picture's horizontal field of view (degrees) in a window of `aspect`.
func fov(aspect: float) -> float:
	return Lens.fov_from_focal(focal, Lens.sensor(frame_aspect(aspect)).x)


func forward() -> Vector3:
	var h := deg_to_rad(heading)
	var p := deg_to_rad(pitch)
	return Vector3(sin(h) * cos(p), cos(h) * cos(p), sin(p))


func right() -> Vector3:
	var h := deg_to_rad(heading)
	return Vector3(cos(h), -sin(h), 0.0)


## Height above the ground under the eye (negative below it).
func clearance() -> float:
	return eye.z - surface.height_at(eye.x, eye.y)


## Map units per second at speed 1: faster high up.
func speed() -> float:
	return maxf(60.0, absf(clearance()))


## The eye at `at` looking along `ahead` (roll 0), focused `at_focus` along it when given (> 0).
func place(at: Vector3, ahead: Vector3, at_focus := 0.0) -> void:
	var f := ahead.normalized()
	eye = at
	goal = at
	heading = rad_to_deg(atan2(f.x, f.y))
	pitch = rad_to_deg(asin(clampf(f.z, -1.0, 1.0)))
	roll = 0.0
	if at_focus > 0.0:
		focus = at_focus


func update(dt: float) -> void:
	eye += (goal - eye) * (1.0 - exp(-12.0 * dt))


## Turn by a mouse movement in pixels: right and down look right and down.
func look(dx: float, dy: float) -> void:
	var k := LOOK_DEGREES_PER_PIXEL * Lens.fov_from_focal(focal) / 50.0
	heading = fposmod(heading + dx * k, 360.0)
	pitch = clampf(pitch - dy * k, -89.9, 89.9)


## Keyboard movement for dt seconds: along the view, right and up; roll turns about the view.
func drive(dt: float, ahead: float, side: float, up: float, turn: float, rate: float) -> void:
	var step := speed() * rate * dt
	goal += (forward() * ahead + right() * side + Vector3(0, 0, 1) * up) * step
	roll = clampf(roll + turn * 45.0 * dt, -90.0, 90.0)


## Sideways and up by a mouse movement in pixels (a right drag).
func slide(dx: float, dy: float) -> void:
	var k := speed() * 0.003
	goal += right() * dx * k + Vector3(0, 0, 1) * (-dy) * k


## Along the view by wheel notches (positive: forward).
func dolly(notches: float) -> void:
	goal += forward() * notches * maxf(20.0, speed() * 0.25)


func zoom(notches: float) -> void:
	focal = clampf(focal * pow(Lens.FOCAL_STEP, notches), Lens.FOCAL_RANGE.x, Lens.FOCAL_RANGE.y)


func refocus(notches: float) -> void:
	focus = clampf(focus * pow(Lens.FOCUS_STEP, notches), 5.0, 100000.0)


## The image's width in mm on the sensor's scale in a window of `aspect`: what the blur scales its pixels by.
func sensor_width(aspect: float) -> float:
	return Lens.image_size(aspect, frame).x


## Place `camera` as this camera looks in a window of `aspect`.
func apply(camera: Camera3D, aspect: float) -> void:
	var w := sensor_width(aspect)
	var near := minf(40.0, maxf(1.0, absf(clearance()) * 0.02))
	OrbitCamera.place(camera, eye, eye + forward() * focus, Lens.fov_from_focal(focal, w), roll, near, FAR)


## The surface point at the centre of the view, or Vector3.INF.
func pick_ahead() -> Vector3:
	return surface.march(eye, forward(), 60000.0)


## The readout, as the studio's: the position, heading, tilt, roll, the frame's field of view and what stays sharp.
func readout(aspect: float) -> String:
	var text := "x %s  y %s  z %s   heading %.0f°   tilt %+.0f°" % [Lens.thousands(eye.x), Lens.thousands(eye.y),
		Lens.thousands(eye.z), fposmod(heading, 360.0), pitch]
	if absf(roll) >= 0.5:
		text += "   roll %+.0f°" % roll
	text += "   %.0f° wide" % fov(aspect)
	if aperture > 0.0:
		text += "   " + Lens.sharp_text(Lens.sharp_range(focus, focal, aperture, frame_aspect(aspect)))
	return text
