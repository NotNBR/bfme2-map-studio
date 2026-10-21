## The Edit camera: the Python viewer's orbit camera, ported move for move. It orbits a
## ground point; heading, elevation and the field of view are in degrees, the field of view across the width.
## Every move changes the goal and update() eases the camera towards it, except pan(), which keeps the grabbed point
## exactly under the cursor.
class_name OrbitCamera
extends RefCounted

const ORBIT_DEGREES_PER_PIXEL := 0.25
const SMOOTHING := 16.0
const MIN_DISTANCE := 60.0
const MAX_DISTANCE := 40000.0
const ZOOM_STEP := 0.82
const FLY_DISTANCE := 1500.0

var surface: Surface
var playable := Vector2.ONE
var fov := 50.0
var goal := {}
var cur := {}
var top = null          # [elevation, heading] to return to from the top view


func _init(s: Surface, size: Vector2, field_of_view: float) -> void:
	surface = s
	playable = size
	fov = field_of_view
	reset()
	snap()


static func smooth(current: float, target: float, dt: float, rate := SMOOTHING) -> float:
	return current + (target - current) * (1.0 - exp(-rate * dt))


func reset() -> void:
	goal = {"x": playable.x / 2, "y": playable.y / 2, "distance": maxf(playable.x, playable.y) * 0.75, "heading": 0.0, "elevation": 55.0}


func set_goal(x: float, y: float, distance: float, heading: float, elevation: float) -> void:
	goal = {"x": x, "y": y, "distance": _clamp_distance(distance), "heading": heading, "elevation": _clamp_elevation(elevation)}


func snap() -> void:
	cur = goal.duplicate()
	cur["z"] = surface.height_at(cur.x, cur.y)


func update(dt: float) -> void:
	for key in ["x", "y", "heading", "elevation"]:
		cur[key] = smooth(cur[key], goal[key], dt)
	# zoom eases in log space, so it feels the same at every scale
	cur["distance"] = exp(smooth(log(cur.distance), log(goal.distance), dt))
	cur["z"] = smooth(cur.z, surface.height_at(cur.x, cur.y), dt, 8.0)


func toggle_top() -> void:
	if top == null:
		top = [goal.elevation, goal.heading]
		goal["elevation"] = 89.5
		goal["heading"] = roundf(goal.heading / 360.0) * 360.0
	else:
		goal["elevation"] = top[0]
		top = null


func orbit(dx: float, dy: float) -> void:
	goal["heading"] += dx * ORBIT_DEGREES_PER_PIXEL
	goal["elevation"] = _clamp_elevation(goal.elevation + dy * ORBIT_DEGREES_PER_PIXEL)


## Keep the grabbed ground point `anchor` under the cursor, now over `hit` (map coordinates; 1:1, unsmoothed).
func pan(anchor: Vector3, hit: Vector3) -> void:
	for pair in [["x", anchor.x - hit.x], ["y", anchor.y - hit.y]]:
		goal[pair[0]] += pair[1]
		cur[pair[0]] += pair[1]


## Zoom by wheel notches (positive: in), towards the map point `toward` (Vector3.INF: the focus point).
func zoom(notches: float, toward := Vector3.INF) -> void:
	var old: float = goal.distance
	var new := _clamp_distance(old * pow(ZOOM_STEP, notches))
	if toward != Vector3.INF:
		var k := 1.0 - new / old
		goal["x"] += (toward.x - goal.x) * k
		goal["y"] += (toward.y - goal.y) * k
	goal["distance"] = new


func fly_to(point: Vector3) -> void:
	goal["x"] = point.x
	goal["y"] = point.y
	goal["distance"] = maxf(MIN_DISTANCE, minf(goal.distance, FLY_DISTANCE))


## Keyboard movement for dt seconds: forward, right, turn, tilt and zoom are -1, 0 or 1; moving scales with the zoom
## level and `speed`, and keeps the focus point on the map.
func drive(dt: float, forward: float, right: float, turn: float, tilt: float, zoom_in: float, speed: float) -> void:
	var rate: float = goal.distance * 1.1 * speed
	if forward != 0.0 or right != 0.0:
		var h := deg_to_rad(goal.heading)
		goal["x"] += (sin(h) * forward + cos(h) * right) * rate * dt
		goal["y"] += (cos(h) * forward - sin(h) * right) * rate * dt
	goal["heading"] += turn * 90.0 * dt
	goal["elevation"] = _clamp_elevation(goal.elevation + tilt * 60.0 * dt)
	if zoom_in != 0.0:
		goal["distance"] = _clamp_distance(goal.distance * exp(zoom_in * 1.5 * dt))
	goal["x"] = clampf(goal.x, 0.0, playable.x)
	goal["y"] = clampf(goal.y, 0.0, playable.y)


## Orbit the ground the free camera at `eye` looks at along `ahead` (Camera.aim): `hit`, or where its heading meets the
## ground ahead when it looks above the horizon (`hit` INF). Snaps there; the tilt keeps within its limits.
func aim(eye: Vector3, ahead: Vector3, hit: Vector3) -> void:
	var heading := rad_to_deg(atan2(ahead.x, ahead.y))
	if hit == Vector3.INF:
		var flat := Vector2(ahead.x, ahead.y).normalized()
		var reach := maxf(300.0, absf(eye.z - surface.height_at(eye.x, eye.y)) * 1.5)
		var x := eye.x + flat.x * reach
		var y := eye.y + flat.y * reach
		hit = Vector3(x, y, surface.height_at(x, y))
	var offset := eye - hit
	var distance := offset.length()
	var elevation := rad_to_deg(asin(clampf(offset.z / maxf(distance, 1e-6), -1.0, 1.0)))
	set_goal(hit.x, hit.y, _clamp_distance(distance), heading, _clamp_elevation(elevation))
	top = null
	snap()


## The angle (radians, counter-clockwise) that lines a new rectangle up with the screen; 0 within 10 degrees of the
## map axes (Camera.screen_angle).
func screen_angle() -> float:
	var turn := -deg_to_rad(cur.heading)
	var a := turn - roundf(turn / (PI / 2.0)) * (PI / 2.0)     # math.remainder(turn, pi/2)
	return 0.0 if absf(a) < deg_to_rad(10.0) else a


## The eye and target in map coordinates (Camera.matrices): never inside the terrain.
func eye_target() -> Array:
	var e := deg_to_rad(cur.elevation)
	var h := deg_to_rad(cur.heading)
	var target := Vector3(cur.x, cur.y, cur.z)
	var eye: Vector3 = target + Vector3(-sin(h) * cos(e), -cos(h) * cos(e), sin(e)) * float(cur.distance)
	eye.z = maxf(eye.z, surface.height_at(eye.x, eye.y) + 15.0)
	return [eye, target]


## Place `camera` as this camera looks: eye, target, field of view across the width, near and far as the studio's.
func apply(camera: Camera3D) -> void:
	var et := eye_target()
	place(camera, et[0], et[1], fov, 0.0, maxf(2.0, cur.distance * 0.01), cur.distance * 20.0 + 30000.0)


## A camera at map points `eye` and `target` (render.camera.look_at, up north-up z), `roll` degrees about the view.
static func place(camera: Camera3D, eye: Vector3, target: Vector3, field_of_view: float, roll: float, near: float, far: float) -> void:
	camera.keep_aspect = Camera3D.KEEP_WIDTH
	camera.fov = field_of_view
	camera.near = near
	camera.far = far
	var from := Surface.to_godot(eye)
	var to := Surface.to_godot(target)
	var forward := (to - from).normalized()
	var up := Vector3.UP if absf(forward.dot(Vector3.UP)) <= 0.999 else Vector3.FORWARD
	camera.look_at_from_position(from, to, up)
	if roll != 0.0:
		# about the view direction (local -z): a positive angle turns the camera clockwise as seen from behind it,
		# render.camera.rolled's sense
		camera.rotate_object_local(Vector3.FORWARD, deg_to_rad(roll))


## The surface point under a window position, in map coordinates, or Vector3.INF.
func pick(camera: Camera3D, cursor: Vector2) -> Vector3:
	var origin := Surface.to_map(camera.project_ray_origin(cursor))
	var direction := Surface.to_map(camera.project_ray_normal(cursor))
	return surface.march(origin, direction, cur.distance * 6.0 + 20000.0)


## Where a window position's ray meets the plane at height z (map coordinates), or Vector3.INF.
func plane_hit(camera: Camera3D, cursor: Vector2, z: float) -> Vector3:
	var origin := Surface.to_map(camera.project_ray_origin(cursor))
	var direction := Surface.to_map(camera.project_ray_normal(cursor))
	if absf(direction.z) < 1e-6:
		return Vector3.INF
	var t := (z - origin.z) / direction.z
	return origin + direction * t if t > 0.0 else Vector3.INF


static func _clamp_distance(distance: float) -> float:
	return clampf(distance, MIN_DISTANCE, MAX_DISTANCE)


static func _clamp_elevation(elevation: float) -> float:
	return clampf(elevation, 5.0, 89.5)
