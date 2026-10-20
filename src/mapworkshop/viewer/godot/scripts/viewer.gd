## The studio's map viewer on OpenBFME's library (docs/godot-viewer/plan.md). mw view MAP --godot starts it
## (viewer/godot_viewer.py) with --scene=<scene.json>: the map to open (a user map by name, or a stock map from the
## archives), the surface heights it picks and drapes on, the marks, and the camera. It opens the map through the
## library (RetailFileSystem, MapTerrainBuilder, MapObjectBuilder) and shows it with the studio's Edit camera.
##
## The scene can also ask for a fixed view (mw render's, resolved in Python), points to project through it (probes:
## each printed with where Python puts it), a screenshot to save, or a check (headless: open the map, print the
## result, quit). Without --scene it only checks that the assembly brought what it needs, prints "VIEWER ready" or
## what is missing, and when headless quits with 0 or 1.
extends Node3D

const CLASSES := ["RetailFileSystem", "MapTerrainBuilder", "MapObjectBuilder", "PathfindView"]
const SHADERS := ["terrain", "water_standing", "road", "river"]
const WARMUP_FRAMES := 24     # frames before a screenshot: the objects' first poses and the streamed textures
const HELP := ("Left drag orbit, right/middle drag pan, wheel zoom, double-click fly to, WASD move, Q/E R/F Z/X turn tilt zoom,\n"
	+ "Space or Home reset, T top, 1 objects, 2 water, M marks, P screenshot, F1 help")

var _scene := {}
var _scene_dir := ""
var _surface: Surface
var _fs: RefCounted
var _terrain: RefCounted
var _objects: RefCounted
var _root: Node3D
var _marks: Node3D
var _camera: Camera3D
var _world_env: WorldEnvironment
var _sun: DirectionalLight3D
var _orbit: OrbitCamera
var _fixed := false           # a view from the scene: the camera stays where Python resolved it
var _label: Label
var _frames := 0
var _drag := ""               # "orbit" or "pan" while a mouse button is held
var _anchor := Vector3.INF    # the grabbed ground point while panning


func _ready() -> void:
	var scene_path := ""
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--scene="):
			scene_path = arg.substr(8)
	var missing := _missing()
	if scene_path.is_empty():
		print("VIEWER ready" if missing.is_empty() else "VIEWER missing: " + ", ".join(missing))
		if _headless():
			get_tree().quit(0 if missing.is_empty() else 1)
		return
	if not missing.is_empty():
		_fail("the assembly lacks " + ", ".join(missing))
		return
	_scene = JSON.parse_string(FileAccess.get_file_as_string(scene_path))
	if not (_scene is Dictionary):
		_fail("cannot read the scene %s" % scene_path)
		return
	_scene_dir = scene_path.get_base_dir()
	_surface = Surface.load_from(_scene_dir.path_join(_scene.surface.file), _scene.surface)
	if _surface == null:
		_fail("cannot read the surface heights")
		return
	# the picture's size in every mode, so the camera has the aspect Python resolved the view for
	get_window().size = Vector2i(int(_scene.size[0]), int(_scene.size[1]))
	get_window().title = "%s - Godot viewer" % _scene.title
	_build_stage()
	_open_map()


func _missing() -> PackedStringArray:
	var missing := PackedStringArray()
	for library_class in CLASSES:
		if not ClassDB.class_exists(library_class):
			missing.append(library_class)
	for shader in SHADERS:
		var path := "res://shaders/%s.gdshader" % shader
		if not ResourceLoader.exists(path) or load(path) == null:
			missing.append(path)
	return missing


func _headless() -> bool:
	return DisplayServer.get_name() == "headless"


func _fail(message: String) -> void:
	push_error(message)
	print("VIEWER failed: ", message)
	if _label != null:
		_label.text = "ERROR: " + message
		_label.modulate = Color(1, 0.4, 0.4)
	if _headless() or not String(_scene.get("screenshot", "")).is_empty() or _scene.get("check", false):
		get_tree().quit(1)


## The world as OpenBFME's own map viewer sets it up for a map: black around it, no ambient light until the map's
## object lighting is known, linear tone mapping.
func _build_stage() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0, 0, 0)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_DISABLED
	env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
	_world_env = WorldEnvironment.new()
	_world_env.environment = env
	add_child(_world_env)
	_camera = Camera3D.new()
	add_child(_camera)
	var ui := CanvasLayer.new()
	_label = Label.new()
	_label.position = Vector2(12, 8)
	_label.add_theme_color_override("font_outline_color", Color.BLACK)
	_label.add_theme_constant_override("outline_size", 4)
	ui.add_child(_label)
	add_child(ui)


func _open_map() -> void:
	var started := Time.get_ticks_msec()
	_fs = ClassDB.instantiate("RetailFileSystem")
	var mount: Dictionary = _fs.mount_retail()
	if not mount.ok:
		_fail("mounting the game's files failed: " + "; ".join(mount.errors))
		return
	var user_map: bool = _scene.user_map
	if user_map and not _same_folder(String(mount.get("user_map_folder", "")), String(_scene.user_map_folder)):
		_fail("OpenBFME's user maps folder is %s, the studio installed the map in %s" % [
			mount.get("user_map_folder", ""), _scene.user_map_folder])
		return
	var mounted := Time.get_ticks_msec()
	_terrain = ClassDB.instantiate("MapTerrainBuilder")
	_root = _terrain.build_map(_fs, _scene.map, {"user_map": user_map, "fog": false, "markers": false})
	var report: Dictionary = _terrain.get_report()
	if _root == null:
		_fail("the terrain did not build: %s" % [report.errors])
		return
	add_child(_root)
	var built_terrain := Time.get_ticks_msec()
	_objects = ClassDB.instantiate("MapObjectBuilder")
	var setup: Dictionary = _objects.setup(_fs)
	if not setup.ok:
		_fail("the object world did not load: %s" % [setup.errors])
		return
	var objects: Node3D = _objects.build_objects(_fs, _scene.map, {"user_map": user_map})
	var object_report: Dictionary = _objects.get_report()
	if objects == null:
		_fail("the objects did not build: %s" % [object_report.errors])
		return
	_root.add_child(objects)
	_apply_lighting(object_report)
	var width := maxf(4.0, maxf(_scene.playable[0], _scene.playable[1]) / 400.0)
	_marks = MarksLayer.build(_scene.marks, _surface, width)
	add_child(_marks)
	var done := Time.get_ticks_msec()
	print("VIEWER opened %s in %d ms: mount %d, terrain %d, objects %d (%d objects, %d errors), %d marks" % [
		_scene.map, done - started, mounted - started, built_terrain - mounted, done - built_terrain,
		int(object_report.objects.total), report.errors.size() + object_report.errors.size(), _scene.marks.size()])
	_orbit = OrbitCamera.new(_surface, Vector2(_scene.playable[0], _scene.playable[1]), float(_scene.fov))   # at its reset()
	if _scene.has("view"):
		# exactly where Python resolved the view, until a move hands it to the Edit camera, which orbits the view's
		# target from the view's eye (Python worked the orbit out)
		_fixed = true
		var v: Dictionary = _scene.view
		OrbitCamera.place(_camera, _vec(v.eye), _vec(v.target), v.fov, v.roll, v.near, v.far)
		var o: Dictionary = v.orbit
		_orbit.fov = v.fov
		_orbit.set_goal(o.x, o.y, o.distance, o.heading, o.elevation)
		_orbit.snap()
	else:
		_orbit.apply(_camera)
	var shot := String(_scene.get("screenshot", ""))
	var actual := Vector2i(get_viewport().get_visible_rect().size)
	if (_scene.has("probes") or not shot.is_empty()) and actual != Vector2i(int(_scene.size[0]), int(_scene.size[1])):
		_fail("the window is %dx%d, not the %dx%d asked for: the picture would not match mw render's" % [
			actual.x, actual.y, int(_scene.size[0]), int(_scene.size[1])])
		return
	_probe()
	_label.text = "%s\n%s" % [_scene.title, HELP]
	_label.visible = shot.is_empty()     # a picture without the help
	if _scene.get("check", false) and shot.is_empty():
		var layers := PackedStringArray()
		for layer in ["MapObjects", "StandingWater", "Rivers"]:
			if _root.has_node(layer):
				layers.append(layer)
		print("VIEWER layers: ", ", ".join(layers))
		print("VIEWER check ok")
		get_tree().quit(0)


static func _vec(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])


static func _same_folder(a: String, b: String) -> bool:
	return a.replace("\\", "/").trim_suffix("/").to_lower() == b.replace("\\", "/").trim_suffix("/").to_lower()


## Each probe point through the camera, with where Python's projection (mw render's) puts it in a picture this size.
func _probe() -> void:
	for probe in _scene.get("probes", []):
		var at := _camera.unproject_position(Surface.to_godot(_vec(probe.point)))
		var want := Vector2(probe.pixel[0], probe.pixel[1])
		print("VIEWER probe %s: Godot %.2f, %.2f, mw render %.2f, %.2f, %.3f px apart" % [
			probe.point, at.x, at.y, want.x, want.y, at.distance_to(want)])


## The map's object lighting, as OpenBFME's map viewer applies it: ambient and one sun.
func _apply_lighting(rep: Dictionary) -> void:
	var env := _world_env.environment
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	if not rep.has("lighting"):
		env.ambient_light_color = Color(0.6, 0.6, 0.6)
		return
	var lit: Dictionary = rep.lighting
	env.ambient_light_color = lit.ambient
	env.ambient_light_energy = 1.0
	_sun = DirectionalLight3D.new()
	_sun.light_color = lit.diffuse
	_sun.shadow_enabled = false
	var dir: Vector3 = lit.direction
	if dir.length() > 0.0001:
		var up := Vector3.UP if absf(dir.normalized().y) < 0.99 else Vector3.RIGHT
		_sun.transform = Transform3D(Basis.looking_at(dir.normalized(), up), Vector3.ZERO)
	add_child(_sun)


func _process(delta: float) -> void:
	if _objects != null:
		_objects.advance(delta)
	if _orbit != null:
		var forward := _axis(KEY_W, KEY_UP) - _axis(KEY_S, KEY_DOWN)
		var right := _axis(KEY_D, KEY_RIGHT) - _axis(KEY_A, KEY_LEFT)
		var turn := _axis(KEY_E) - _axis(KEY_Q)
		var tilt := _axis(KEY_R) - _axis(KEY_F)
		var zoom := _axis(KEY_X) - _axis(KEY_Z)
		if forward != 0.0 or right != 0.0 or turn != 0.0 or tilt != 0.0 or zoom != 0.0:
			_free()
		if not _fixed:
			# the studio viewer's speeds: Shift three times, Ctrl 0.3 times
			var speed := (3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0) * (0.3 if Input.is_key_pressed(KEY_CTRL) else 1.0)
			_orbit.drive(delta, forward, right, turn, tilt, zoom, speed)
			_orbit.update(delta)
			_orbit.apply(_camera)
	_frames += 1
	var shot := String(_scene.get("screenshot", ""))
	if not shot.is_empty() and _frames == WARMUP_FRAMES and _root != null:
		var code := _save(shot)
		get_tree().quit(0 if code == OK else 1)


func _axis(a: Key, b: Key = KEY_NONE) -> float:
	return 1.0 if Input.is_key_pressed(a) or (b != KEY_NONE and Input.is_key_pressed(b)) else 0.0


func _save(path: String) -> Error:
	var image := get_viewport().get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var code := image.save_png(path)
	print("VIEWER screenshot %s: %s (%dx%d)" % [path, error_string(code), image.get_width(), image.get_height()])
	return code


func _unhandled_input(event: InputEvent) -> void:
	if _orbit == null:
		return
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_LEFT:
			if b.pressed and b.double_click:
				var hit := _orbit.pick(_camera, b.position)
				if hit != Vector3.INF:
					_free()
					_orbit.fly_to(hit)
				_drag = ""
			else:
				_drag = "orbit" if b.pressed else ""
		elif b.button_index == MOUSE_BUTTON_RIGHT or b.button_index == MOUSE_BUTTON_MIDDLE:
			_anchor = Vector3.INF
			if b.pressed:
				# the ground under the cursor, else where the cursor's ray meets the focus point's height
				_anchor = _orbit.pick(_camera, b.position)
				if _anchor == Vector3.INF:
					_anchor = _orbit.plane_hit(_camera, b.position, _orbit.cur.z)
			_drag = "pan" if _anchor != Vector3.INF else ""
		elif b.pressed and (b.button_index == MOUSE_BUTTON_WHEEL_UP or b.button_index == MOUSE_BUTTON_WHEEL_DOWN):
			_free()
			_orbit.zoom(1.0 if b.button_index == MOUSE_BUTTON_WHEEL_UP else -1.0, _orbit.pick(_camera, b.position))
	elif event is InputEventMouseMotion and not _drag.is_empty():
		var m := event as InputEventMouseMotion
		_free()
		if _drag == "orbit":
			_orbit.orbit(m.relative.x, m.relative.y)   # dragging down raises the camera, as in the studio viewer
		else:
			# the grabbed point stays under the cursor: where the cursor's ray meets the grabbed point's height
			var hit := _orbit.plane_hit(_camera, m.position, _anchor.z)
			if hit != Vector3.INF:
				_orbit.pan(_anchor, hit)
	elif event is InputEventKey and event.pressed and not event.echo:
		match (event as InputEventKey).keycode:
			KEY_SPACE, KEY_HOME:
				_free()
				_orbit.reset()
			KEY_T:
				_free()
				_orbit.toggle_top()
			KEY_1: _toggle(_root.get_node_or_null("MapObjects"))
			KEY_2:
				_toggle(_root.get_node_or_null("StandingWater"))
				_toggle(_root.get_node_or_null("Rivers"))
			KEY_M: _toggle(_marks)
			KEY_P:
				var stamp := Time.get_datetime_string_from_system().replace(":", "-")
				_save(String(_scene.screenshots).path_join("%s %s.png" % [_scene.map, stamp]))
			KEY_F1: _label.visible = not _label.visible


## A move ends a fixed view: the Edit camera takes over from where it was.
func _free() -> void:
	_fixed = false


func _toggle(node: Node3D) -> void:
	if node != null:
		node.visible = not node.visible
