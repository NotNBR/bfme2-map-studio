## The studio's map viewer on OpenBFME's library (docs/godot-viewer/plan.md). mw view MAP --godot starts it
## (viewer/godot_viewer.py) with --scene=<scene.json>: the map to open (a user map by name, or a stock map from the
## archives), the surface heights it picks on, the marks, the camera and the companion's port. It opens the map through
## the library (RetailFileSystem, MapTerrainBuilder, MapObjectBuilder) and shows it with the studio's Edit camera.
##
## With the companion (viewer/godot_link.py, over Link) it edits marks: the palette arms a tool, and each left press,
## drag, release and hover goes to the companion with the cursor's ray and what the overlay finds under it; the
## companion's MarkEditor answers with the marks to draw, the panel and the status. A new build reloads in place.
##
## The scene's views ({key: on}) start the View switches other than they start by default (a screenshot of an overlay).
##
## The scene can also ask for a fixed view (mw render's, resolved in Python), points to project through it (probes:
## each printed with where Python puts it), a screenshot to save, or a check (headless: open the map, print the
## result, quit). Without --scene it only checks that the assembly brought what it needs, prints "VIEWER ready" or
## what is missing, and when headless quits with 0 or 1.
extends Node3D

const CLASSES := ["RetailFileSystem", "MapTerrainBuilder", "MapObjectBuilder", "PathfindView"]
const SHADERS := ["terrain", "water_standing", "road", "river"]
const WARMUP_FRAMES := 24     # frames before a screenshot: the objects' first poses and the streamed textures
const CLICK_PIXELS := 4.0     # a press and release closer than this is a click, not an orbit (viewer/marking.py)
## The View menu: [key, title, on at the start] (docs/viewer.md, "The toolbar"; the studio viewer's keys)
const VIEWS := [["objects", "Objects (1)", true], ["water", "Water (2)", true], ["roads", "Roads", true],
	["fog", "Fog (6)", true], ["animate", "Animate", true], ["grid", "Grid (G)", false], ["border", "Map border (B)", false],
	["walkable", "Walkable (7)", false], ["flow", "River flow arrows (8)", false], ["marks", "Marks (M)", true]]
const CURSORS := {"draw": Input.CURSOR_CROSS, "move": Input.CURSOR_MOVE, "rotate": Input.CURSOR_DRAG,
	"ew": Input.CURSOR_HSIZE, "ns": Input.CURSOR_VSIZE, "nesw": Input.CURSOR_BDIAGSIZE, "nwse": Input.CURSOR_FDIAGSIZE}

var _scene := {}
var _scene_path := ""
var _surface: Surface
var _fs: RefCounted
var _terrain: RefCounted
var _objects: RefCounted
var _root: Node3D
var _camera: Camera3D
var _world_env: WorldEnvironment
var _sun: DirectionalLight3D
var _orbit: OrbitCamera
var _overlay: MarkOverlay
var _frame: Frame             # the toolbar, the marks rail and panel, the camera bar: with the companion only
var _overlays: Overlays
var _objects_node: Node3D     # the object layer, beside the terrain so that the terrain alone can be built again
var _views := {}              # View key -> on
var _link: Link
var _fixed := false           # a view from the scene: the camera stays where Python resolved it
var _frames := 0
var _drag := ""               # while a button is held: "orbit", "pan", "marks" (the companion edits), "pending" (asked it)
var _anchor := Vector3.INF    # the grabbed ground point while panning
var _press_at := Vector2.ZERO
var _press_seq := 0           # the number of the last press sent; the companion's answer carries it
var _press_double := false    # that press was a double-click: unless the marks take it, the camera flies there
var _pending_orbit := Vector2.ZERO   # the mouse's motion while the answer is awaited, for the orbit it may become
var _hover := false           # the cursor moved: tell the companion what is under it, once a frame
var _drive := []              # the scene's scripted input, for tests: steps still to play
var _drive_wait := 0          # frames until the next step
var _drive_until := 0         # and the time (ms) it waits for
var _driving := false
var _drive_at := Vector2.ZERO # where the scripted cursor last was


func _ready() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--scene="):
			_scene_path = arg.substr(8)
	var missing := _missing()
	if _scene_path.is_empty():
		print("VIEWER ready" if missing.is_empty() else "VIEWER missing: " + ", ".join(missing))
		if _headless():
			get_tree().quit(0 if missing.is_empty() else 1)
		return
	if not missing.is_empty():
		_fail("the assembly lacks " + ", ".join(missing))
		return
	if not _read_scene():
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
	if _frame != null:
		_frame.toast("failed", "The map could not be shown", message, 30)
	if _headless() or not String(_scene.get("screenshot", "")).is_empty() or _scene.get("check", false):
		get_tree().quit(1)


## The scene and its surface, again on a reload. False (after saying why) when either cannot be read.
func _read_scene() -> bool:
	var scene = JSON.parse_string(FileAccess.get_file_as_string(_scene_path))
	if not (scene is Dictionary):
		_fail("cannot read the scene %s" % _scene_path)
		return false
	var surface := Surface.load_from(_scene_path.get_base_dir().path_join(scene.surface.file), scene.surface)
	if surface == null:
		_fail("cannot read the surface heights")
		return false
	_scene = scene
	_surface = surface
	return true


## The world as OpenBFME's own map viewer sets it up for a map: black around it, no ambient light until the map's
## object lighting is known, linear tone mapping. Over it the marks and, with the companion, the marking controls.
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
	var layer := CanvasLayer.new()
	for view in VIEWS:
		_views[view[0]] = view[2]
	for key in _scene.get("views", {}):           # the scene's own switches (screenshots of an overlay)
		_views[key] = bool(_scene.views[key])
	_overlays = Overlays.new()
	add_child(_overlays)
	_overlay = MarkOverlay.new()
	_overlay.camera = _camera
	_overlay.state = _scene.get("marks", {})
	layer.add_child(_overlay)
	add_child(layer)
	if _scene.get("port") != null:
		_frame = Frame.new()
		add_child(_frame)
		_frame.marks.tool_chosen.connect(func(tool) -> void: _send({"type": "tool", "tool": tool}))
		_frame.marks.command.connect(func(name: String) -> void: _send({"type": "command", "name": name}))
		_frame.toolbar.map_chosen.connect(func(path: String) -> void: _send({"type": "command", "name": "open_map", "map": path}))
		_frame.toolbar.command.connect(func(name: String) -> void: _send({"type": "command", "name": name}))
		_frame.toolbar.test_game_chosen.connect(
			func(choice: String) -> void: _send({"type": "command", "name": "test_game", "choice": choice}))
		_frame.toolbar.view_switched.connect(_switch_view)
		_frame.toolbar.preview_chosen.connect(_preview)
		_frame.toolbar.action.connect(_toolbar_action)
		var entries := []
		for view in VIEWS:
			entries.append([view[0], view[1], _views[view[0]]])
		_frame.toolbar.set_views(entries)
		_link = Link.new()
		var code := _link.open(int(_scene.port))
		if code != OK:
			_fail("cannot reach the companion on port %d: %s" % [int(_scene.port), error_string(code)])


func _open_map() -> void:
	var started := Time.get_ticks_msec()
	_fs = ClassDB.instantiate("RetailFileSystem")
	var mount: Dictionary = _fs.mount_retail()
	if not mount.ok:
		_fail("mounting the game's files failed: " + "; ".join(mount.errors))
		return
	if _scene.user_map and not _same_folder(String(mount.get("user_map_folder", "")), String(_scene.user_map_folder)):
		_fail("OpenBFME's user maps folder is %s, the studio installed the map in %s" % [
			mount.get("user_map_folder", ""), _scene.user_map_folder])
		return
	var mounted := Time.get_ticks_msec()
	var report := _build_map()
	if report.is_empty():
		return
	var done := Time.get_ticks_msec()
	print("VIEWER opened %s in %d ms: mount %d, terrain %d, objects %d (%d objects, %d errors), %d marks" % [
		_scene.map, done - started, mounted - started, report.terrain_ms, report.objects_ms, report.objects,
		report.errors, (_overlay.state.get("marks", []) as Array).size()])
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
	_send({"type": "ready", "ms": done - started})
	_drive = (_scene.get("drive", []) as Array).duplicate()
	_driving = not _drive.is_empty()
	_drive_wait = 10
	if _scene.get("check", false) and shot.is_empty():
		var layers := PackedStringArray()
		if _objects_node != null:
			layers.append(_objects_node.name)
		for layer in ["StandingWater", "Rivers", "Roads"]:
			if _root.has_node(layer):
				layers.append(layer)
		print("VIEWER layers: ", ", ".join(layers))
		print("VIEWER check ok")
		get_tree().quit(0)


## The map's terrain and objects through the library, in place of any built before: {terrain_ms, objects_ms, objects,
## errors}, or {} (after saying why) when they did not build. The terrain is built before the old map goes, so a map
## that does not build leaves the last good one; its objects then go with it (the object builder holds one map).
func _build_map() -> Dictionary:
	var started := Time.get_ticks_msec()
	var user_map: bool = _scene.user_map
	if not _build_terrain():
		return {}
	var report: Dictionary = _terrain.get_report()
	if _sun != null:
		_sun.queue_free()
		_sun = null
	if _objects_node != null:
		remove_child(_objects_node)
		_objects_node.queue_free()
		_objects_node = null
	var built_terrain := Time.get_ticks_msec()
	if _objects == null:
		_objects = ClassDB.instantiate("MapObjectBuilder")
		var setup: Dictionary = _objects.setup(_fs)
		if not setup.ok:
			_fail("the object world did not load: %s" % [setup.errors])
			return {}
	var objects: Node3D = _objects.build_objects(_fs, _scene.map, {"user_map": user_map})
	var object_report: Dictionary = _objects.get_report()
	if objects == null:
		_fail("the objects did not build: %s" % [object_report.errors])
		return {}
	_objects_node = objects
	add_child(objects)
	_apply_lighting(object_report)
	_overlays.build(_surface, Vector2(_scene.playable[0], _scene.playable[1]), int(_scene.surface.border))
	_apply_views()
	return {"terrain_ms": built_terrain - started, "objects_ms": Time.get_ticks_msec() - built_terrain,
		"objects": int(object_report.objects.total), "errors": report.errors.size() + object_report.errors.size()}


## The terrain (water, rivers, roads) in place of the one before, which stays when it does not build. False when
## it did not (after saying why).
func _build_terrain() -> bool:
	if _terrain == null:
		_terrain = ClassDB.instantiate("MapTerrainBuilder")
	var options := {"user_map": _scene.user_map, "fog": _views.get("fog", true), "markers": false}
	var built: Node3D = _terrain.build_map(_fs, _scene.map, options)
	if built == null:
		_fail("the terrain did not build: %s" % [_terrain.get_report().errors])
		return false
	if _root != null:
		remove_child(_root)
		_root.queue_free()
	_root = built
	add_child(_root)
	return true


## The View switches on what was just built (`keys`, else all): the layers shown, the overlays drawn and, from the
## companion, worked out.
func _apply_views(keys: Array = []) -> void:
	for key in (keys if not keys.is_empty() else _views.keys()):
		if key != "fog":
			_switch_view(key, _views[key])


## A new build, another map (`new_map`) or a preview (`what` names it): the scene and its surface read and the map
## built in place. The camera stays for a new build and a preview; another map starts at its whole map.
func _reload(path: String, new_map: bool, what: String = "") -> void:
	var started := Time.get_ticks_msec()
	var previous := _scene_path
	_scene_path = path
	if _frame != null:
		var loading := what if not what.is_empty() else "the new build" if not new_map else path.get_base_dir().get_file()
		_frame.toast("busy", "Loading %s" % loading, "", 30)
	if not _read_scene():
		_scene_path = previous
		_send({"type": "reload_failed", "error": "the scene could not be read"})
		return
	_orbit.surface = _surface
	_orbit.playable = Vector2(_scene.playable[0], _scene.playable[1])
	if new_map:
		_fixed = false
		_orbit.fov = float(_scene.fov)
		_orbit.reset()
		_orbit.snap()
		get_window().title = "%s - Godot viewer" % _scene.title
	if _build_map().is_empty():
		_send({"type": "reload_failed", "error": "the map did not build"})
		return
	if _frame != null:
		_frame.toast("done", "Loaded %s" % (what if not what.is_empty() else _scene.title), "in %.1f s" % ((Time.get_ticks_msec() - started) / 1000.0), 3)
	print("VIEWER reloaded %s in %d ms" % [_scene.map, Time.get_ticks_msec() - started])
	_send({"type": "reloaded", "ms": Time.get_ticks_msec() - started})


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
	if _views.get("animate", true):
		if _objects != null:
			_objects.advance(delta)
		if _overlays != null:
			_overlays.advance(delta)
	_serve_link()
	if _orbit != null:
		var forward := _axis(KEY_W, KEY_UP) - _axis(KEY_S, KEY_DOWN)
		var right := _axis(KEY_D, KEY_RIGHT) - _axis(KEY_A, KEY_LEFT)
		var turn := _axis(KEY_E) - _axis(KEY_Q)
		var tilt := _axis(KEY_R) - _axis(KEY_F)
		var zoom := _axis(KEY_X) - _axis(KEY_Z)
		if Input.is_key_pressed(KEY_CTRL):
			zoom = 0.0             # Ctrl+Z undoes
		if forward != 0.0 or right != 0.0 or turn != 0.0 or tilt != 0.0 or zoom != 0.0:
			_free()
		if not _fixed:
			# the studio viewer's speeds: Shift three times, Ctrl 0.3 times
			var speed := (3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0) * (0.3 if Input.is_key_pressed(KEY_CTRL) else 1.0)
			_orbit.drive(delta, forward, right, turn, tilt, zoom, speed)
			_orbit.update(delta)
			_orbit.apply(_camera)
		if _frame != null:
			_frame.bar.set_orbit(_orbit)
		if _hover and _drag.is_empty():
			_send(_event("hover", get_viewport().get_mouse_position()))
		_hover = false
	_play_drive()
	_frames += 1
	var shot := String(_scene.get("screenshot", ""))
	if not shot.is_empty() and _frames == WARMUP_FRAMES and _root != null:
		var code := _save(shot)
		get_tree().quit(0 if code == OK else 1)


## The scene's scripted input (tests): each step after its frames, a mouse button, motion or key as Input gets them
## from the hand, at a map point the camera projects; "tool" arms a palette tool, "command" sends one as its button
## does, "screenshot" saves the window as it is, controls and all; "wait" holds the next step back for its seconds.
## Done, the viewer closes.
func _play_drive() -> void:
	if not _driving or _orbit == null:
		return
	_drive_wait -= 1
	if _drive_wait > 0 or Time.get_ticks_msec() < _drive_until:
		return
	if _drive.is_empty():
		_driving = false
		print("VIEWER drive done")
		await get_tree().create_timer(1.0).timeout      # the companion's last answers
		get_tree().quit(0)
		return
	var step: Dictionary = _drive.pop_front()
	_drive_wait = int(step.get("frames", 3))
	_drive_until = Time.get_ticks_msec() + int(float(step.get("seconds", 0.0)) * 1000.0)   # "wait" steps
	var pos := Vector2.ZERO
	if step.has("at"):
		var x: float = step.at[0]
		var y: float = step.at[1]
		pos = _camera.unproject_position(Surface.to_godot(Vector3(x, y, _surface.height_at(x, y))))
	if step.has("at"):
		_drive_at = pos
	match String(step.do):
		"press", "release":
			var b := InputEventMouseButton.new()
			b.button_index = MOUSE_BUTTON_LEFT
			b.pressed = step.do == "press"
			b.position = pos
			b.global_position = pos
			Input.parse_input_event(b)
		"move":
			var m := InputEventMouseMotion.new()
			m.position = pos
			m.global_position = pos
			m.relative = pos - _drive_at
			Input.parse_input_event(m)
		"key":
			var k := InputEventKey.new()
			k.keycode = OS.find_keycode_from_string(String(step.key))
			k.ctrl_pressed = step.get("ctrl", false)
			k.pressed = true
			Input.parse_input_event(k)
		"tool":
			_send({"type": "tool", "tool": step.get("tool")})
		"command":
			var command := step.duplicate()       # its name and arguments, as the toolbar sends them
			command.erase("do")
			command.erase("frames")
			command["type"] = "command"
			_send(command)
		"screenshot":
			_save(String(step.path))


## The companion's messages since the last frame; its closing ends the viewer (the session is over).
func _serve_link() -> void:
	if _link == null:
		return
	for message in _link.poll():
		match String(message.get("type", "")):
			"marks":
				_overlay.state = message
				_frame.marks.show_tool(message.get("tool"))
				_frame.bar.set_hint(message.get("hint"))
				_frame.marks.show_panel(message.get("visible", true))      # M hides the panel with the marks
				_views["marks"] = bool(message.get("visible", true))
				_frame.toolbar.set_view("marks", _views["marks"])
				var cursor = message.get("cursor")
				Input.set_default_cursor_shape(CURSORS.get(cursor, Input.CURSOR_ARROW) if cursor != null else Input.CURSOR_ARROW)
			"press_result":
				if int(message.get("seq", -1)) == _press_seq:
					_answered(bool(message.handled))
			"panel":
				_frame.marks.set_panel(message.lines, _overlay.state.get("visible", true))
			"status":
				_frame.bar.set_status(message.text, float(message.get("seconds", 3)))
			"clipboard":
				DisplayServer.clipboard_set(message.text)
				_frame.bar.set_status("Copied the marks for an agent: paste them into its prompt", 4)
			"reload":
				_reload(String(message.get("scene", _scene_path)), bool(message.get("new_map", false)),
					String(message.get("what", "")))
			"menu":
				_frame.toolbar.set_menu(message)
			"walkable":
				if message.has("error"):
					_switch_view("walkable", false)
					_frame.bar.set_status("Walkability failed: %s" % message.error, 10)
				elif _views.get("walkable", false):          # still on: it may have been switched off meanwhile
					_overlays.set_walkable(String(message.image), Vector2(message.size[0], message.size[1]))
					_frame.bar.set_status("Walkability ready: %d cut-off areas" % int(message.cut_off), 5)
			"flow":
				if _views.get("flow", false):
					_overlays.set_flow(message.strips, _views.get("border", false))
			"build":
				_frame.toolbar.set_build(bool(message.running), message.get("line"), message.get("outcome"))
			"toast":
				_frame.toast(String(message.kind), String(message.title), String(message.get("detail", "")),
					float(message.get("seconds", 3)))
			"window":
				var mode := DisplayServer.WINDOW_MODE_MINIMIZED if message.minimized else DisplayServer.WINDOW_MODE_WINDOWED
				DisplayServer.window_set_mode(mode)
	if _link.closed():
		print("VIEWER the companion closed the link")
		get_tree().quit(0)


func _send(message: Dictionary) -> void:
	if _link != null:
		_link.send(message)


## The companion's answer to the last press: the marks took it, or the camera does (a double-click flies there; else
## the motion meanwhile starts the orbit). The button may be up already.
func _answered(handled: bool) -> void:
	var held := _drag == "pending"
	if handled:
		_drag = "marks" if held else _drag
	elif _press_double:
		var hit := _orbit.pick(_camera, _press_at)
		if hit != Vector3.INF:
			_free()
			_orbit.fly_to(hit)
		_drag = "" if held else _drag
	elif held:
		_drag = "orbit"
		if _pending_orbit != Vector2.ZERO:
			_free()
			_orbit.orbit(_pending_orbit.x, _pending_orbit.y)
	_pending_orbit = Vector2.ZERO


## A mouse event for the companion's MarkEditor: the cursor's ray in map coordinates, what the overlay finds under the
## cursor, Shift, and the Edit camera's focus.
func _event(kind: String, pos: Vector2) -> Dictionary:
	var handle = _overlay.handle_at(pos)
	return {"type": kind,
		"ray": [_list(Surface.to_map(_camera.project_ray_origin(pos))), _list(Surface.to_map(_camera.project_ray_normal(pos)))],
		"picks": {"handle": handle, "grab": _overlay.grab_at(pos, _overlay.state.get("selected")), "mark": _overlay.mark_at(pos),
			"direction": _overlay.handle_direction(handle) if handle != null else null},
		"shift": Input.is_key_pressed(KEY_SHIFT),
		"focus": {"z": _orbit.cur.z, "distance": _orbit.cur.distance, "angle": _orbit.screen_angle()}}


static func _list(v: Vector3) -> Array:
	return [v.x, v.y, v.z]


func _axis(a: Key, b: Key = KEY_NONE) -> float:
	return 1.0 if Input.is_key_pressed(a) or (b != KEY_NONE and Input.is_key_pressed(b)) else 0.0


func _save(path: String) -> Error:
	var image := get_viewport().get_texture().get_image()
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var code := image.save_png(path)
	print("VIEWER screenshot %s: %s (%dx%d)" % [path, error_string(code), image.get_width(), image.get_height()])
	return code


## P: the view without the controls, into the renders folder.
func _screenshot() -> void:
	if _frame != null:
		_frame.chrome = false
	await RenderingServer.frame_post_draw
	var stamp := Time.get_datetime_string_from_system().replace(":", "-")
	var path := String(_scene.screenshots).path_join("%s %s.png" % [_scene.map, stamp])
	var code := _save(path)
	if _frame != null:
		_frame.chrome = true
		_frame.bar.set_status("Screenshot saved: %s" % path if code == OK else "The screenshot was not saved: %s" % error_string(code), 4)


func _unhandled_input(event: InputEvent) -> void:
	if _orbit == null:
		return
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_LEFT:
			if b.pressed:
				_press_at = b.position
				_press_double = b.double_click and _overlay.state.get("tool") == null
				if _link != null:
					# the companion says whether the press acts on the marks (as the studio viewer offers every press
					# to its MarkEditor first); until then the drag waits, and its moves still go to the companion
					_drag = "pending"
					_pending_orbit = Vector2.ZERO
					_press_seq += 1
					var press := _event("press", b.position)
					press["seq"] = _press_seq
					_send(press)
				elif _press_double:
					_answered(false)
				else:
					_drag = "orbit"
			else:
				if _link != null:
					_send(_event("release", b.position))       # nothing when the press did not act on the marks
					if _drag != "marks" and b.position.distance_to(_press_at) < CLICK_PIXELS:
						_send(_event("click", b.position))
				_drag = ""
				_hover = true                                   # the cursor for what a press there does now
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
	elif event is InputEventMouseMotion:
		var m := event as InputEventMouseMotion
		match _drag:
			"":
				_hover = true
			"marks":
				_send(_event("move", m.position))
			"pending":
				_send(_event("move", m.position))
				_pending_orbit += m.relative
			"orbit":
				_free()
				_orbit.orbit(m.relative.x, m.relative.y)   # dragging down raises the camera, as in the studio viewer
			"pan":
				_free()
				# the grabbed point stays under the cursor: where the cursor's ray meets the grabbed point's height
				var hit := _orbit.plane_hit(_camera, m.position, _anchor.z)
				if hit != Vector3.INF:
					_orbit.pan(_anchor, hit)
	elif event is InputEventKey and event.pressed and not event.echo:
		var key := event as InputEventKey
		if key.keycode == KEY_Z and key.ctrl_pressed:
			_send({"type": "command", "name": "undo"})
			return
		match key.keycode:
			KEY_SPACE, KEY_HOME:
				_free()
				_orbit.reset()
			KEY_T:
				_free()
				_orbit.toggle_top()
			KEY_1: _switch_view("objects", not _shown("objects"))
			KEY_2: _switch_view("water", not _shown("water"))
			KEY_6: _switch_view("fog", not _shown("fog"))
			KEY_G: _switch_view("grid", not _shown("grid"))
			KEY_B: _switch_view("border", not _shown("border"))
			KEY_7: _switch_view("walkable", not _shown("walkable"))
			KEY_8: _switch_view("flow", not _shown("flow"))
			KEY_M:
				if _link != null:
					_send({"type": "command", "name": "toggle"})
				else:
					_overlay.visible = not _overlay.visible
			KEY_DELETE, KEY_BACKSPACE: _send({"type": "command", "name": "delete"})
			KEY_ESCAPE: _send({"type": "command", "name": "escape"})
			KEY_P: _screenshot()
			KEY_F1:
				if _frame != null:
					_frame.toggle_help()


## A Preview entry: the companion writes the map's preview copy and has the viewer build it in place.
func _preview(option: String, value: String) -> void:
	_send({"type": "command", "name": "preview", option: value})


## A View switch (the menu or its key): the layer shown or hidden, the overlay drawn, the terrain built again (fog).
func _switch_view(key: String, on: bool) -> void:
	var was: bool = _views.get(key, false)
	_views[key] = on
	match key:
		"objects":
			if _objects_node != null:
				_objects_node.visible = on
		"water":
			_show(["StandingWater", "Rivers"], on)
		"roads":
			_show(["Roads"], on)
		"fog":
			if on != was and _root != null:
				_build_terrain()
				_apply_views(["water", "roads"])               # the layers in the terrain; the rest stays as it is
		"grid":
			_overlays.set_grid(on)
		"border":
			_overlays.set_border(on)
		"walkable", "flow":
			if on:
				_send({"type": "command", "name": "overlay", "overlay": key})
			elif key == "walkable":
				_overlays.set_walkable("", Vector2.ONE)
			else:
				_overlays.set_flow([], false)
		"marks":
			if _link != null and bool(_overlay.state.get("visible", true)) != on:
				_send({"type": "command", "name": "toggle"})
	if _frame != null:
		_frame.toolbar.set_view(key, on)


func _shown(key: String) -> bool:
	return _views.get(key, false)


func _show(names: Array, on: bool) -> void:
	for n in names:
		var node: Node3D = _root.get_node_or_null(n) if _root != null else null
		if node != null:
			node.visible = on


func _toolbar_action(name: String) -> void:
	match name:
		"top":
			_free()
			_orbit.toggle_top()
		"reset":
			_free()
			_orbit.reset()
		"screenshot":
			_screenshot()


## A move ends a fixed view: the Edit camera takes over from where it was.
func _free() -> void:
	_fixed = false
