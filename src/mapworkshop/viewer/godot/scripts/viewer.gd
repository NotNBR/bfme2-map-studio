## The studio's map viewer on OpenBFME's library (docs/viewer.md). mw view MAP starts it
## (viewer/godot_viewer.py) with --scene=<scene.json>: the map to open (a user map by name, or a stock map from the
## archives), the surface heights it picks on, the marks, the camera and the companion's port. It opens the map through
## the library (RetailFileSystem, MapTerrainBuilder, MapObjectBuilder) and shows it with the studio's Edit camera.
##
## With the companion (viewer/godot_link.py, over Link) it edits marks: the palette arms a tool, and each left press,
## drag, release and hover goes to the companion with the cursor's ray and what the overlay finds under it; the
## companion's MarkEditor answers with the marks to draw, the panel and the status. A new build reloads in place.
##
## Photo mode (V, or the camera bar) swaps the Edit camera for the free one (FlyCamera) with its lens: the exposure
## and the depth of field over the frame (PhotoEffect), the framing aids, screenshots cropped to the frame. A scene
## view with an aperture or an exposure starts in it, so a screenshot shows what mw render's picture of the view does.
##
## The scene's views ({key: on}) start the View switches other than they start by default (a screenshot of an overlay).
##
## Shots (mw render's pictures, mw item's, and --screenshot): [{path, size, view (resolved as for the start) or top
## {center, width, height, z}, background [r, g, b] (black), map (another user map of the same size, built for it)}],
## each saved in turn once it has settled, the viewer closing after the last; the overlays then
## come in the scene (walkable, flow), worked out in Python, as there is no companion.
##
## The scene can also ask for a fixed view (mw render's, resolved in Python), points to project through it (probes:
## each printed with where Python puts it), a screenshot to save, or a check (headless: open the map, print the
## result, quit). Without --scene it only checks that the assembly brought what it needs, prints "VIEWER ready" or
## what is missing, and when headless quits with 0 or 1.
extends Node3D

const WARMUP_FRAMES := 24     # frames before the first shot: the objects' first poses and the streamed textures
const SHOT_FRAMES := 12       # and before each further shot: the new view's textures and the window's new size
const CLICK_PIXELS := 4.0     # a press and release closer than this is a click, not an orbit (viewer/marking.py)
## The View menu: [key, title, on at the start] (docs/viewer.md, "The toolbar"; each title's key in brackets)
const VIEWS := [["objects", "Objects (1)", true], ["water", "Water (2)", true], ["roads", "Roads", true],
	["fog", "Fog, rain and snow (6)", true], ["clouds", "Cloud shadows", true], ["animate", "Animate", true],
	["grid", "Grid (G)", false], ["border", "Map border (B)", false], ["starts", "Starting positions (3)", false],
	["walkable", "Walkable (7)", false], ["flow", "River flow arrows (8)", false], ["marks", "Marks (M)", true],
	["grass", "Grass", false], ["ground_detail", "Ground detail", false],
	["units", "Units", true], ["limits", "The game's tree and shrub limits", false]]
const COPY_VIEWS := ["units", "limits"]       # the switches the map's copy carries (render.godot.preview_map)
const CURSORS := {"draw": Input.CURSOR_CROSS, "move": Input.CURSOR_MOVE, "rotate": Input.CURSOR_DRAG,
	"ew": Input.CURSOR_HSIZE, "ns": Input.CURSOR_VSIZE, "nesw": Input.CURSOR_BDIAGSIZE, "nwse": Input.CURSOR_FDIAGSIZE}

var _grass_previous_msaa := -1
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
var _mode := "edit"           # "edit": the orbit camera; "photo": the free camera with its lens; "test": the game runs
var _test: TestMode           # the game in Test mode
var _right_at := Vector2.INF  # where a right press was, in Test mode: a click there is an order
var _fly: FlyCamera
var _photo: PhotoEffect
var _captured := false        # Photo mode has the mouse: moving it looks around
var _sliding := false         # a right drag in Photo mode
var _thirds := false
var _frame_choice := "free"   # the frame's aspect (Lens.FRAMES)
var _focus_request := 0       # the PhotoEffect distance request being waited for (focus on the centre)
var _shots := []              # the scene's shots still to take
var _shot_wait := 0           # frames until the current shot is saved
var _shot_failed := false
var _fixed := false           # a view from the scene: the camera stays where Python resolved it
var _frames := 0
var _clock := 0.0             # seconds the objects and overlays have run since the map was built
var _falling: Falling         # the rain or snow, when the map's weather has it
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
	return EngineRuntime.missing()


func _headless() -> bool:
	return DisplayServer.get_name() == "headless"


func _fail(message: String) -> void:
	push_error(message)
	print("VIEWER failed: ", message)
	if _frame != null:
		_frame.toast("failed", "The map could not be shown", message, 30)
	if _headless() or not (_scene.get("shots", []) as Array).is_empty() or _scene.get("check", false):
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
	_photo = PhotoEffect.new()
	_photo.enabled = false
	var layer := CanvasLayer.new()
	for view in VIEWS:
		_views[view[0]] = view[2]
	_views["starts"] = _scene.get("port") != null  # shown while exploring; render outputs stay as requested
	for key in _scene.get("views", {}):           # the scene's own switches (screenshots of an overlay)
		_views[key] = bool(_scene.views[key])
	for key in COPY_VIEWS:                        # and those of the copy it opens
		_views[key] = bool(_scene.get("preview", {}).get(key, _views[key]))
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
		_frame.toolbar.test_settings_chosen.connect(
			func(settings: Dictionary) -> void: _send({"type": "command", "name": "test_settings", "settings": settings}))
		_frame.toolbar.view_switched.connect(_switch_view)
		_frame.toolbar.preview_chosen.connect(_preview)
		_frame.toolbar.action.connect(_toolbar_action)
		_frame.bar.mode_chosen.connect(_set_mode)
		_frame.bar.lens_pick.connect(_lens_pick)
		_frame.bar.lens_step.connect(_lens_step)
		_frame.bar.thirds_toggled.connect(func(on: bool) -> void: _thirds = on)
		_frame.bar.view_save.connect(_save_view)
		_frame.bar.view_go.connect(func(name: String) -> void: _send({"type": "command", "name": "apply_view",
			"view": name, "size": _size()}))
		_frame.bar.view_rename.connect(func(name: String, new: String) -> void: _send({"type": "command",
			"name": "rename_view", "view": name, "new": new}))
		_frame.bar.view_delete.connect(func(name: String) -> void: _send({"type": "command", "name": "delete_view",
			"view": name}))
		_frame.bar.view_copy.connect(_copy_view)
		var entries := []
		for view in VIEWS:
			entries.append([view[0], view[1], _views[view[0]]])
		_frame.toolbar.set_views(entries)
		_frame.toolbar.set_fps_limit(String(_scene.get("fps", "60")))    # mw view --fps
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
	_fly = FlyCamera.new(_surface)
	_shots = (_scene.get("shots", []) as Array).duplicate()
	if not _shots.is_empty():
		_photo.taps = 256                              # as mw render's
	_drive = (_scene.get("drive", []) as Array).duplicate()
	_driving = not _drive.is_empty()
	_drive_wait = 10
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
		if _lens_changes(v):
			_place_view_photo(v)                       # the lens changes the picture (render.photo.active)
			_set_mode("photo", false)
	else:
		_orbit.apply(_camera)
	var actual := Vector2i(get_viewport().get_visible_rect().size)
	if _scene.has("probes") and actual != Vector2i(int(_scene.size[0]), int(_scene.size[1])):
		_fail("the window is %dx%d, not the %dx%d asked for: the picture would not match mw render's" % [
			actual.x, actual.y, int(_scene.size[0]), int(_scene.size[1])])
		return
	_probe()
	_send({"type": "ready", "ms": done - started})
	if _scene.get("test_start", false) and _link != null:
		_set_mode("test")                              # started again for Test mode, on the new build
	if not _shots.is_empty():
		_next_shot(WARMUP_FRAMES)
	if _scene.get("check", false) and _shots.is_empty():
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
	_clock = 0.0
	var object_report: Dictionary = _objects.get_report()
	if objects == null:
		_fail("the objects did not build: %s" % [object_report.errors])
		return {}
	_objects_node = objects
	add_child(objects)
	_apply_lighting(object_report)
	_overlays.build(_surface, Vector2(_scene.playable[0], _scene.playable[1]), int(_scene.surface.border))
	_overlays.set_starts(_scene.get("starts", []), _surface)
	_build_falling()
	_apply_views()
	return {"terrain_ms": built_terrain - started, "objects_ms": Time.get_ticks_msec() - built_terrain,
		"objects": int(object_report.objects.total), "errors": report.errors.size() + object_report.errors.size()}


## The scene's rain or snow in place of the one before.
func _build_falling() -> void:
	if _falling != null:
		_falling.queue_free()
		_falling = null
	if _scene.get("falling") == null:
		return
	_falling = Falling.new()
	if not _falling.build(_scene.falling, _scene_path.get_base_dir(), Vector2(_scene.playable[0], _scene.playable[1])):
		print("VIEWER the rain or snow did not load")
		_falling.free()
		_falling = null
		return
	_falling.visible = _views.get("fog", true)
	add_child(_falling)


## The terrain (water, rivers, roads) in place of the one before, which stays when it does not build. False when
## it did not (after saying why).
func _build_terrain() -> bool:
	if _terrain == null:
		_terrain = ClassDB.instantiate("MapTerrainBuilder")
	var options := {"user_map": _scene.user_map, "fog": _views.get("fog", true), "markers": false,
		"ground_cover": _views.get("grass", false), "natural_ground": _views.get("ground_detail", false)}
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
	if _test != null:
		_leave_test()                                  # the game ran on the map as it was
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
	_fly.surface = _surface
	if new_map:
		_set_mode("edit")
		_fixed = false
		_orbit.fov = float(_scene.fov)
		_orbit.reset()
		_orbit.snap()
		get_window().title = "%s - Godot viewer" % _scene.title
	if _build_map().is_empty():
		_send({"type": "reload_failed", "error": "the map did not build"})
		return
	if _frame != null:
		var loaded: String = what if not what.is_empty() else _scene.title
		_frame.toast("done", "Loaded %s" % loaded, "in %.1f s" % ((Time.get_ticks_msec() - started) / 1000.0), 3)
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
	if _views.get("animate", true) and _shots.is_empty():     # shots stand at their own time (_next_shot)
		_advance(_clock + delta)
	_serve_link()
	if _test != null:
		_test.advance(delta)
	if _orbit != null and _mode == "photo":
		_process_photo(delta)
	elif _orbit != null:
		var forward := _axis(KEY_W, KEY_UP) - _axis(KEY_S, KEY_DOWN)
		var right := _axis(KEY_D, KEY_RIGHT) - _axis(KEY_A, KEY_LEFT)
		var turn := _axis(KEY_E) - _axis(KEY_Q)
		var tilt := _axis(KEY_R) - _axis(KEY_F)
		var zoom := _axis(KEY_X) - _axis(KEY_Z)
		if Input.is_key_pressed(KEY_CTRL) or _mode == "test":
			zoom = 0.0             # Ctrl+Z undoes; in Test mode X stops (the wheel zooms)
		if forward != 0.0 or right != 0.0 or turn != 0.0 or tilt != 0.0 or zoom != 0.0:
			_free()
		if not _fixed:
			# the speeds: Shift three times as fast, Ctrl 0.3 times
			var speed := (3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0) * (0.3 if Input.is_key_pressed(KEY_CTRL) else 1.0)
			_orbit.drive(delta, forward, right, turn, tilt, zoom, speed)
			_orbit.update(delta)
			_orbit.apply(_camera)
		if _frame != null:
			_frame.bar.set_orbit(_orbit)
		if _hover and _drag.is_empty() and _mode != "test":
			_send(_event("hover", get_viewport().get_mouse_position()))
		_hover = false
	_play_drive()
	_frames += 1
	_take_shot()


## The map's cloud shadows on the terrain (its CloudTexture, the cloud_tex of OpenBFME's terrain shader), or plain
## white in their place.
func _show_clouds(on: bool) -> void:
	EngineRuntime.show_clouds(_root, on)


## The objects' animations and the overlays run on to `time` seconds after the map was built.
func _advance(time: float) -> void:
	while time - _clock > 1e-6:                      # a shot's --time in steps, as frames would take it
		var step := minf(time - _clock, 0.1)
		if _objects != null and _test == null:     # Test's GameWorld owns the visible objects; keep the idle layer still
			_objects.advance(step)
		if _overlays != null:
			_overlays.advance(step)
		_clock += step
	if _falling != null:
		_falling.set_time(_clock)


## Whether a view's lens changes the picture (render.photo.active): an aperture or an exposure.
static func _lens_changes(v: Dictionary) -> bool:
	var lens: Dictionary = v.get("photo", {})
	return (lens.get("aperture") != null and float(lens.aperture) > 0.0) or absf(float(lens.get("ev", 0.0))) > 1e-6


## The next shot in place, saved after `frames` frames: the window at its size, the camera at its view (Photo mode
## when its lens changes the picture) or looking straight down on its top view's region, orthographic, north up.
func _next_shot(frames: int) -> void:
	var shot: Dictionary = _shots[0]
	if shot.has("map") and String(shot.map) != String(_scene.map):
		_scene.map = shot.map                          # mw item: each item on a map of its own
		_scene.user_map = true
		if _build_map().is_empty():
			_shot_failed = true
	get_window().size = Vector2i(int(shot.size[0]), int(shot.size[1]))
	var bg: Array = shot.get("background", [0.0, 0.0, 0.0])
	_world_env.environment.background_color = Color(bg[0], bg[1], bg[2])
	_fixed = true
	_advance(float(shot.get("time", 0.0)))           # mw render --time; an earlier time than the last shot's stays
	_camera.projection = Camera3D.PROJECTION_PERSPECTIVE
	if shot.has("top"):
		_set_mode("edit")
		_fixed = true                                  # after _set_mode, which frees the Edit camera
		var t: Dictionary = shot.top
		var from := Surface.to_godot(Vector3(t.center[0], t.center[1], t.z))
		_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
		_camera.keep_aspect = Camera3D.KEEP_WIDTH
		_camera.size = float(t.width)
		_camera.near = 1.0
		_camera.far = float(t.z) + 500.0
		_camera.look_at_from_position(from, from + Vector3.DOWN, Vector3(0, 0, -1))      # north up
	elif shot.has("view"):
		var v: Dictionary = shot.view
		if _lens_changes(v):
			_place_view_photo(v)
			_set_mode("photo", false)
		else:
			_set_mode("edit")
			_fixed = true
			OrbitCamera.place(_camera, _vec(v.eye), _vec(v.target), v.fov, v.roll, v.near, v.far)
	_shot_wait = frames


## The current shot saved once it has settled, then the next; the viewer closes after the last.
func _take_shot() -> void:
	if _shots.is_empty() or _root == null:
		return
	_shot_wait -= 1
	if _shot_wait > 0:
		return
	var shot: Dictionary = _shots.pop_front()
	var want := Vector2i(int(shot.size[0]), int(shot.size[1]))
	var actual := Vector2i(get_viewport().get_visible_rect().size)
	if actual != want:
		print("VIEWER failed: the window is %dx%d, not the %dx%d asked for" % [actual.x, actual.y, want.x, want.y])
		_shot_failed = true
	elif _save(String(shot.path)) != OK:
		_shot_failed = true
	if _shots.is_empty():
		get_tree().quit(1 if _shot_failed else 0)
	else:
		_next_shot(SHOT_FRAMES)


## A frame of Photo mode: the keys fly the camera, the lens goes to the effect, the bar and the framing aids show them.
func _process_photo(delta: float) -> void:
	delta = minf(delta, 0.1)                       # after a stall (a reload) the camera does not jump
	var aspect := _aspect()
	if not _driving:
		var speed := (3.0 if Input.is_key_pressed(KEY_SHIFT) else 1.0) * (0.3 if Input.is_key_pressed(KEY_CTRL) else 1.0)
		var down := 0.0 if Input.is_key_pressed(KEY_CTRL) else _axis(KEY_C)
		_fly.drive(delta, _axis(KEY_W, KEY_UP) - _axis(KEY_S, KEY_DOWN), _axis(KEY_D, KEY_RIGHT) - _axis(KEY_A, KEY_LEFT),
			_axis(KEY_SPACE) - down, _axis(KEY_E) - _axis(KEY_Q), speed)
	_fly.update(delta)
	_fly.apply(_camera, aspect)
	_photo.focal = _fly.focal
	_photo.aperture = _fly.aperture
	_photo.focus = _fly.focus
	_photo.ev = _fly.ev
	_photo.sensor_width = _fly.sensor_width(aspect)
	PhotoEffect.keep_last(_camera, _photo)
	if _focus_request > 0 and _photo.answered >= _focus_request:
		_focus_request = 0
		var d := _photo.distance
		if is_nan(d) or d <= 0.0 or d >= FlyCamera.FAR * 0.99:
			_status("Nothing at the centre of the view to focus on", 3)
		else:
			_fly.focus = d
			_status("Focus %s" % Lens.thousands(d), 2)
	if _frame != null:
		_frame.bar.set_readout(_fly.readout(aspect))
		_frame.bar.set_photo({"focal": snappedf(_fly.focal, 0.1), "aperture": _fly.aperture, "focus": roundf(_fly.focus),
			"ev": snappedf(_fly.ev, 0.01), "thirds": _thirds, "frame": _frame_choice,
			"width": Lens.sensor(_fly.frame_aspect(aspect)).x})
		var pf := _frame.photo_frame
		pf.ratio = _fly.frame
		pf.thirds = _thirds
		pf.reticle = _fly.aperture > 0.0 and _captured


func _aspect() -> float:
	var size := get_viewport().get_visible_rect().size
	return size.x / maxf(size.y, 1.0)


func _status(text: String, seconds: float) -> void:
	if _frame != null:
		_frame.bar.set_status(text, seconds)


## Edit or Photo, without moving the view: Photo starts where the orbit camera is (unless `place` is false: it is
## placed already), with its lens as it was left; Edit orbits the ground Photo looks at.
func _set_mode(mode: String, place := true) -> void:
	if mode == "test" and _mode != "test" and _orbit != null:
		_ask_test()
		return
	if _mode == "test" and mode != "test":
		_leave_test()
	if mode == _mode or _orbit == null:
		if _frame != null:
			_frame.bar.set_mode(_mode)
		return
	_mode = mode
	_focus_request = 0
	if mode == "photo":
		if place and _fixed:
			_place_view_photo(_scene.view)             # the scene's view as it is, its focal length and roll
		elif place:
			var et := _orbit.eye_target()
			var ahead: Vector3 = et[1] - et[0]
			_fly.place(et[0], ahead, ahead.length())
		_fixed = false
		_send({"type": "tool", "tool": null})
		_fly.apply(_camera, _aspect())
	else:
		_orbit.aim(_fly.eye, _fly.forward(), _fly.pick_ahead())
		_free()
	_photo.enabled = mode == "photo"
	_overlay.visible = mode == "edit" and _views.get("marks", true)
	_capture(mode == "photo")
	if _frame != null:
		_frame.set_photo_mode(mode == "photo")
	print("VIEWER mode ", mode)


## Test mode asked of the companion, which answers with the map to run and its line-up ("test_mode"), or starts the
## viewer again when the map shown is not the one packed for it.
func _ask_test() -> void:
	if _link == null:
		print("VIEWER Test mode runs with the companion: open the map with mw view")
		return
	_frame.bar.set_mode(_mode)                         # until the game runs
	_frame.toast("busy", "Starting Test mode", "the game on OpenBFME", 30)
	_send({"type": "command", "name": "test_mode", "camera": _camera_state(), "views": _views})


## The game started (TestMode.start: a few seconds, the first time) in place of the still objects, the marks and their
## tools put away.
func _enter_test(message: Dictionary) -> void:
	await get_tree().process_frame                     # the toast shows before the game loads
	await get_tree().process_frame
	if _mode == "photo":
		_set_mode("edit")
	var test := TestMode.new()
	add_child(test)
	var started := Time.get_ticks_msec()
	var error := test.start(_fs, String(message.map), message.slots, _camera)
	if not error.is_empty():
		test.queue_free()
		_frame.toast("failed", "Test mode did not start", error, 10)
		_frame.bar.set_mode(_mode)
		return
	_test = test
	_mode = "test"
	_drag = ""
	_send({"type": "tool", "tool": null})
	if _objects_node != null:
		_objects_node.visible = false
	_overlay.visible = false
	_overlays.show_starts(false)
	_frame.set_test_mode(true)
	_frame.toast("done", "Test mode", "the game runs (%.1f s to start): left button selects, right orders" % [
		(Time.get_ticks_msec() - started) / 1000.0], 5)
	print("VIEWER mode test")


## Back to Edit: the game goes, the still objects and the marks come back.
func _leave_test() -> void:
	_test.queue_free()
	_test = null
	_mode = "edit"
	_drag = ""
	if _objects_node != null:
		_objects_node.visible = _views.get("objects", true)
	_overlay.visible = _views.get("marks", true)
	_overlays.show_starts(_views.get("starts", false))
	_frame.set_test_mode(false)
	print("VIEWER mode edit")


## Test mode's mouse and keys: the left button selects (a click, or a box), a right click orders, the middle drag
## orbits; X stops, Esc lets go. The marks' keys do nothing. True when it was one of them.
func _test_input(event: InputEvent) -> bool:
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		match b.button_index:
			MOUSE_BUTTON_LEFT:
				if b.pressed:
					_test.box_start(b.position)
				elif _test.dragging():
					_test.left_up(b.position, b.shift_pressed)
				return true
			MOUSE_BUTTON_RIGHT:
				if b.pressed:
					_right_at = b.position
				elif b.position.distance_to(_right_at) < CLICK_PIXELS:
					var done := _test.order(b.position, _orbit.pick(_camera, b.position), b.shift_pressed)
					if not done.is_empty():
						_status(done, 3)
				return false                               # a right drag still pans
			MOUSE_BUTTON_MIDDLE:
				_drag = "orbit" if b.pressed else ""
				return true
	elif event is InputEventMouseMotion and _test.dragging():
		_test.box_move((event as InputEventMouseMotion).position)
		return true
	elif event is InputEventKey and event.pressed and not event.echo:
		var k := event as InputEventKey
		match k.keycode:
			KEY_X:
				_test.stop()
				return true
			KEY_ESCAPE:
				_test.selected.clear()
				return true
			KEY_DELETE, KEY_BACKSPACE, KEY_M:
				return true
			KEY_Z:
				return k.ctrl_pressed
	return false


## The free camera at the scene's view (Python resolved it): its eye towards its target, its roll and lens.
func _place_view_photo(v: Dictionary) -> void:
	var lens: Dictionary = v.get("photo", {})
	_fly.place(_vec(v.eye), _vec(v.target) - _vec(v.eye), float(lens.get("focus", 0.0)))
	_fly.roll = v.roll
	_fly.focal = float(lens.get("focal", _fly.focal))
	_fly.aperture = float(lens.aperture) if lens.get("aperture") != null else 0.0
	_fly.ev = float(lens.get("ev", 0.0))


## Photo mode takes the mouse (hidden, turning the view) or frees it; only in a window someone uses.
func _capture(on: bool) -> void:
	_captured = on and _frame != null and not _driving
	_sliding = false
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if _captured else Input.MOUSE_MODE_VISIBLE


## A lens field's preset, or the frame, from the camera bar.
func _lens_pick(field: String, value: Variant) -> void:
	match field:
		"focal": _fly.focal = float(value)
		"aperture": _fly.aperture = float(value)
		"focus":
			if value is String:
				_focus_centre()
			else:
				_fly.focus = float(value)
		"ev": _fly.ev = float(value)
		"frame":
			_frame_choice = String(value)
			_fly.frame = Lens.frame_ratio(_frame_choice)


## The wheel or a drag over a lens field: steps that field `notches` steps (negative: the other way).
func _lens_step(field: String, notches: int) -> void:
	match field:
		"focal": _fly.zoom(notches)
		"aperture":
			var steps := Lens.APERTURES
			var i := steps.find(_fly.aperture)
			if i < 0:
				i = 1
				for k in range(1, steps.size()):
					if absf(steps[k] - _fly.aperture) < absf(steps[i] - _fly.aperture):
						i = k
			_fly.aperture = steps[clampi(i + signi(notches), 0, steps.size() - 1)]
		"focus": _fly.refocus(notches)
		"ev": _fly.ev = clampf(snappedf(_fly.ev + 0.1 * notches, 0.01), -3.0, 3.0)


## Focus on what is at the centre of the view, ground or object: the effect reads its distance with the next frame.
func _focus_centre() -> void:
	_focus_request = _photo.ask_distance(Vector2i(get_viewport().get_visible_rect().size / 2.0))


## The scene's scripted input (tests): each step after its frames, a mouse button, motion or key as Input gets them
## from the hand, at a map point the camera projects (a key with "ctrl" and "shift"); "tool" arms a palette tool, "command" sends one as its button
## does, "lens" picks a lens field's preset as the camera bar does, "screenshot" saves the window as it is, controls
## and all; "wait" holds the next step back for its seconds. Done, the viewer closes.
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
			b.button_index = {"left": MOUSE_BUTTON_LEFT, "right": MOUSE_BUTTON_RIGHT,
				"middle": MOUSE_BUTTON_MIDDLE}[String(step.get("button", "left"))]
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
			k.shift_pressed = step.get("shift", false)
			k.pressed = true
			Input.parse_input_event(k)
		"tool":
			_send({"type": "tool", "tool": step.get("tool")})
		"lens":
			_lens_pick(String(step.field), step.value)         # as the camera bar's preset
		"shot":                                            # Photo mode's camera and lens at once (videos): eye, target, lens
			if step.has("eye"):
				var at := _vec(step.eye)
				_fly.place(at, _vec(step.target) - at, float(step.get("focus", _fly.focus)))
				_fly.roll = float(step.get("roll", 0.0))
			for field in ["focal", "aperture", "focus", "ev"]:
				if step.has(field):
					_lens_pick(field, step[field])
		"view":
			_switch_view(String(step.key), bool(step.on))      # as the View menu
		"mode":
			_set_mode(String(step.mode))                     # as the camera bar
		"paths":
			if _test != null:
				_test.paths = String(step.paths)               # as Test mode's panel
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
				_status(message.text, float(message.get("seconds", 3)))
			"clipboard":
				DisplayServer.clipboard_set(message.text)
				if message.has("what"):
					_status("Copied %s" % message.what, 5)
				else:
					_status("Copied the marks for an agent: paste them into its prompt", 4)
			"views":
				_frame.bar.set_views(message.items, message.free)
			"view":
				_go_to_view(message)
			"reload":
				_reload(String(message.get("scene", _scene_path)), bool(message.get("new_map", false)),
					String(message.get("what", "")))
			"menu":
				_frame.toolbar.set_menu(message)
				for key in COPY_VIEWS:                # the copy shown, also after a preview that failed
					_views[key] = bool(message.preview.current.get(key, _views[key]))
					_frame.toolbar.set_view(key, _views[key])
			"walkable":
				if message.has("error"):
					_switch_view("walkable", false)
					_status("Walkability failed: %s" % message.error, 10)
				elif _views.get("walkable", false):          # still on: it may have been switched off meanwhile
					_overlays.set_walkable(String(message.image), Vector2(message.size[0], message.size[1]))
					_status("Walkability ready: %d cut-off areas" % int(message.cut_off), 5)
			"flow":
				if _views.get("flow", false):
					_overlays.set_flow(message.strips, _views.get("border", false))
			"build":
				_frame.toolbar.set_build(bool(message.running), message.get("line"), message.get("outcome"))
			"toast":
				_frame.toast(String(message.kind), String(message.title), String(message.get("detail", "")),
					float(message.get("seconds", 3)))
			"test_mode":
				_enter_test(message)
			"quit":                                    # the companion starts the viewer again (Test mode, a new build)
				get_tree().quit(0)
			"window":
				if message.minimized:
					_capture(false)                    # the game is up: the mouse is the game's
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


## The window's picture as a PNG, or only `crop` of it.
func _save(path: String, crop := Rect2i()) -> Error:
	var image := get_viewport().get_texture().get_image()
	if crop.has_area():
		image = image.get_region(crop)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var code := image.save_png(path)
	print("VIEWER screenshot %s: %s (%dx%d)" % [path, error_string(code), image.get_width(), image.get_height()])
	return code


## P: the view without the controls, into the renders folder.
func _screenshot() -> void:
	if _frame != null:
		_frame.chrome = false
	_photo.taps = 256                              # the blur's samples as mw render's
	await RenderingServer.frame_post_draw
	_photo.taps = 128
	var stamp := Time.get_datetime_string_from_system().replace(":", "-")
	var photo := _mode == "photo"
	var path := String(_scene.screenshots).path_join("%s%s %s.png" % [_scene.map, " photo" if photo else "", stamp])
	var crop := Lens.frame_rect(Vector2i(get_viewport().get_visible_rect().size), _fly.frame) if photo else Rect2i()
	var code := _save(path, crop)                  # Photo mode: the frame, with the lens
	if _frame != null:
		_frame.chrome = true
		_status("Screenshot saved: %s" % path if code == OK else "The screenshot was not saved: %s" % error_string(code), 4)


func _unhandled_input(event: InputEvent) -> void:
	if _orbit == null:
		return
	if event is InputEventKey and event.pressed and not event.echo and _view_key(event as InputEventKey):
		return
	if event is InputEventKey and event.pressed and not event.echo:
		var k := event as InputEventKey
		if k.keycode == KEY_F5:
			_send({"type": "command", "name": "reload"})        # read the map again
			return
		if k.keycode == KEY_B and k.ctrl_pressed:
			_send({"type": "command", "name": "build"})
			return
	if _mode == "photo" and _photo_input(event):
		return
	if _mode == "test" and _test_input(event):
		return
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.button_index == MOUSE_BUTTON_LEFT:
			if b.pressed:
				_press_at = b.position
				_press_double = b.double_click and _overlay.state.get("tool") == null
				if _link != null:
					# the companion says whether the press acts on the marks (every press goes to its MarkEditor
					# first); until then the drag waits, and its moves still go to the companion
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
				_orbit.orbit(m.relative.x, m.relative.y)   # dragging down raises the camera
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
			KEY_V: _set_mode("photo")
			KEY_1: _switch_view("objects", not _shown("objects"))
			KEY_2: _switch_view("water", not _shown("water"))
			KEY_3: _switch_view("starts", not _shown("starts"))
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


## The views' keys in either mode: Ctrl+1-9 goes to the view in that slot, Ctrl+Shift+1-9
## saves the current one there, Ctrl+C copies the view as a mw render command. True when it was one of them.
func _view_key(key: InputEventKey) -> bool:
	if not key.ctrl_pressed:
		return false
	var digit := key.physical_keycode if key.physical_keycode != KEY_NONE else key.keycode   # the digit row's place
	if digit >= KEY_1 and digit <= KEY_9:
		var slot := int(digit - KEY_0)
		if key.shift_pressed:
			_save_view(slot)
		else:
			_send({"type": "command", "name": "apply_view", "slot": slot, "size": _size()})
		return true
	if key.keycode == KEY_C:
		_copy_view()
		return true
	return false


func _size() -> Array:
	var size := get_viewport().get_visible_rect().size
	return [size.x, size.y]


## The camera as the companion turns it into a view (Companion.spec): the mode, the orbit camera's goal and field of
## view, the free camera where its eye is going and its lens.
func _camera_state() -> Dictionary:
	var g: Dictionary = _orbit.goal
	return {"mode": _mode,
		"orbit": {"x": g.x, "y": g.y, "distance": g.distance, "elevation": g.elevation, "heading": g.heading,
			"fov": _orbit.fov},
		"fly": {"goal": _list(_fly.goal), "forward": _list(_fly.forward()), "focal": _fly.focal, "roll": _fly.roll,
			"aperture": _fly.aperture, "focus": _fly.focus, "ev": _fly.ev}}


## Save the view (in `slot`, else the first free one) with a thumbnail of the next frame without the controls (Photo:
## the frame).
func _save_view(slot := 0) -> void:
	if _link == null:
		return
	var camera := _camera_state()
	var photo := _mode == "photo"
	var frame := _fly.frame
	_frame.chrome = false
	await RenderingServer.frame_post_draw
	var path := _scene_path.get_base_dir().path_join("view %d.png" % Time.get_ticks_msec())   # the companion takes it
	var size := Vector2i(get_viewport().get_visible_rect().size)
	var code := _save(path, Lens.frame_rect(size, frame) if photo else Rect2i())
	_frame.chrome = true
	_send({"type": "command", "name": "save_view", "camera": camera, "slot": slot if slot > 0 else null,
		"thumbnail": path if code == OK else ""})


## Copy view: the camera and what mw render can reproduce of the picture (the size, Photo's frame; the View switches).
func _copy_view() -> void:
	var size := Vector2i(get_viewport().get_visible_rect().size)
	if _mode == "photo":
		size = Lens.frame_rect(size, _fly.frame).size
	_send({"type": "command", "name": "copy_view", "camera": _camera_state(), "preview": {"size": [size.x, size.y],
		"objects": _shown("objects"), "water": _shown("water"), "fog": _shown("fog"), "clouds": _shown("clouds"),
		"grid": _shown("grid"),
		"border": _shown("border"), "walkable": _shown("walkable"), "flow": _shown("flow")}})


## A saved view the companion resolved: Photo at its eye with its lens, or the Edit camera orbiting its target.
func _go_to_view(v: Dictionary) -> void:
	_fixed = false
	if v.mode == "photo":
		_place_view_photo(v)
		_set_mode("photo", false)
	else:
		_set_mode("edit")
		var o: Dictionary = v.orbit
		var heading: float = _orbit.goal.heading + wrapf(float(o.heading) - _orbit.goal.heading, -180.0, 180.0)
		_orbit.set_goal(o.x, o.y, o.distance, heading, o.elevation)     # the short way round
		_orbit.top = null
	_status(String(v.name), 2)


## Photo mode's mouse and keys: with the mouse taken, it looks around, a right drag slides, the wheel
## dollies (Alt: focal length, Shift: focus), a middle click focuses on the centre; a click takes the mouse back.
## True when the event was Photo mode's; the View keys and P, F1 go on to the common handling.
func _photo_input(event: InputEvent) -> bool:
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if not _captured:
			if b.pressed and b.button_index == MOUSE_BUTTON_LEFT:
				_capture(true)
			return true
		match b.button_index:
			MOUSE_BUTTON_RIGHT:
				_sliding = b.pressed
			MOUSE_BUTTON_MIDDLE:
				if b.pressed:
					_focus_centre()
			MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN:
				if b.pressed:
					var notches := 1.0 if b.button_index == MOUSE_BUTTON_WHEEL_UP else -1.0
					if b.alt_pressed:
						_fly.zoom(notches)
					elif b.shift_pressed:
						_fly.refocus(notches)
					else:
						_fly.dolly(notches)
		return true
	if event is InputEventMouseMotion:
		if _captured:
			var m := event as InputEventMouseMotion
			if _sliding:
				_fly.slide(m.relative.x, m.relative.y)
			else:
				_fly.look(m.relative.x, m.relative.y)
		return true
	if event is InputEventKey and event.pressed and not event.echo:
		match (event as InputEventKey).keycode:
			KEY_V:
				_set_mode("edit")
			KEY_ESCAPE:
				if _captured:
					_capture(false)
				else:
					_set_mode("edit")              # the second Esc, as the studio's
			KEY_R:
				_fly.roll = 0.0
			KEY_SPACE, KEY_HOME, KEY_T, KEY_DELETE, KEY_BACKSPACE, KEY_Z:
				pass                       # flying keys, and the marks' and the Edit camera's: not in Photo mode
			_:
				return false
		return true
	return false


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
		"grass":
			if on and _grass_previous_msaa < 0:
				_grass_previous_msaa = get_viewport().msaa_3d
				if get_viewport().msaa_3d < Viewport.MSAA_8X:
					get_viewport().msaa_3d = Viewport.MSAA_8X
			elif not on and _grass_previous_msaa >= 0:
				get_viewport().msaa_3d = _grass_previous_msaa
				_grass_previous_msaa = -1
			if not EngineRuntime.show_grass(_root, on):
				if _build_terrain(): _apply_views(["water", "roads", "clouds"])
				if _root != null: _root.visible = _views.get("terrain", true)
		"ground_detail":
			EngineRuntime.show_ground_detail(_root, on)
		"terrain":                                      # the ground, water and roads (mw item's pictures leave them out)
			if _root != null:
				_root.visible = on
			_overlays.visible = on                         # and what lies on the ground
		"fog":
			if _falling != null:
				_falling.visible = on
			if on != was and _root != null:
				_build_terrain()
				_apply_views(["water", "roads", "clouds"])     # the layers in the terrain; the rest stays as it is
		"clouds":
			_show_clouds(on)
		"grid":
			_overlays.set_grid(on)
		"border":
			_overlays.set_border(on)
		"starts":
			_overlays.show_starts(on and _mode != "test")
		"walkable", "flow":
			if on and _link == null and _scene.has(key):
				# worked out in Python with the scene (mw render's pictures, no companion)
				if key == "walkable":
					var w: Dictionary = _scene.walkable
					_overlays.set_walkable(String(w.image), Vector2(w.size[0], w.size[1]))
				else:
					_overlays.set_flow(_scene.flow, _views.get("border", false))
			elif on:
				_send({"type": "command", "name": "overlay", "overlay": key})
			elif key == "walkable":
				_overlays.set_walkable("", Vector2.ONE)
			else:
				_overlays.set_flow([], false)
		"units", "limits":                             # a copy of the map without them, built in place
			if on != was and _link != null:
				_send({"type": "command", "name": "preview", key: on})
		"marks":
			if _link == null:
				_overlay.visible = on and _mode == "edit"    # no companion: mw render's pictures leave them out
			elif bool(_overlay.state.get("visible", true)) != on:
				_send({"type": "command", "name": "toggle"})
	if _frame != null:
		_frame.toolbar.set_view(key, on)


func _shown(key: String) -> bool:
	return _views.get(key, false)


func _show(names: Array, on: bool) -> void:
	EngineRuntime.show_layers(_root, names, on)


func _toolbar_action(name: String) -> void:
	if name != "screenshot":
		_set_mode("edit")
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
