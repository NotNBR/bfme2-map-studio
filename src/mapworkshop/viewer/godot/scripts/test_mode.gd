## Test mode: the map run as a game on OpenBFME's GameWorld (the retail logic, with its own drawables in place of the
## viewer's still objects), its units selected and ordered as in the game. The companion packs the map shown when the
## viewer starts (native.openbfme.pack_for_test: GameWorld finds maps in archives only) and gives the line-up, every
## slot human (no skirmish AI moves an army). An order goes out as the owner of the units selected, so either army
## takes orders; a selection holds one owner's units.
##
## Left click a unit: select it (Shift adds); left drag: select the units in the box. Right click the ground: move
## there (Shift: a waypoint after the last); right click a unit of another owner: attack it. X stops, Esc lets go.
## The camera stays the Edit camera; its left drag is the box here, so the middle drag orbits.
##
## Paths (the panel): the path each unit's AI follows, live (GameWorld.get_object_path, its AIMover's): from the unit
## through the nodes still ahead to the last, the nodes behind it faint, its goal a cross; orange while it waits for the
## pathfinder, red while it is blocked. A unit or battalion standing on its own is drawn thick, a battalion's members thin.
class_name TestMode
extends Node

const PICK_PIXELS := 18.0     # how near the cursor a unit's foot has to be, in pixels (a battalion: twice that)
const RING := Color(0.45, 0.95, 0.45)
const BOX := Color(0.85, 0.95, 0.85)
const PATH := Color(1.0, 0.85, 0.25)        # a path's nodes still ahead
const PATH_DONE := Color(1.0, 0.85, 0.25, 0.3)
const WAITING := Color(1.0, 0.55, 0.15)     # waiting for the pathfinder
const BLOCKED := Color(0.95, 0.3, 0.25)
const LIFT := 3.0                           # map units over the ground, so the lines are not under it
const PATHS := ["Off", "Selected", "All"]   # whose paths are drawn
const KEYS := "Left click / drag  select (Shift adds)     Right click  move, or attack a unit (Shift: waypoint)     X  stop     Esc  let go     Middle drag  orbit"

var world: Node                # the GameWorld
var selected: Array = []      # object ids, one owner's
var paused := false
var speed := 1.0
var _camera: Camera3D
var _box_from := Vector2.INF   # where a left drag started
var _box_to := Vector2.INF
var _layer: CanvasLayer
var _draw: Control
var _info: Label
var _panel: PanelContainer
var _pause_button: Button
var _speed_button: OptionButton
var paths := "Selected"       # PATHS


## The game on `map` (the archive's maps\<map>\) with these slots, over the viewer's file system `fs`. An empty string
## when it runs, else why not.
func start(fs: RefCounted, map: String, slots: Array, camera: Camera3D) -> String:
	_camera = camera
	world = ClassDB.instantiate("GameWorld")
	var setup: Dictionary = world.setup(fs)
	if not setup.ok:
		return "the game's object world did not load: %s" % [setup.get("errors", [])]
	var profile: Dictionary = world.set_simulation_profile("uber")
	if not profile.ok:
		return "Uber mode did not start: %s" % [profile.get("error", "unknown error")]
	var rep: Dictionary = world.load_map(map, {"slots": slots})
	if not rep.ok:
		return "the game did not start: %s" % [", ".join(PackedStringArray(rep.get("errors", []).slice(0, 3)))]
	add_child(world)
	world.set_shroud_drawn(false)                 # everything shows, as in the viewer
	_build_ui()
	return ""


## The game on by `delta` seconds of the viewer's time, at the speed chosen; the rings follow the units.
func advance(delta: float) -> void:
	if world != null and not paused:
		world.advance(delta * speed)
	_draw.queue_redraw()
	_show_info()


func _build_ui() -> void:
	_layer = CanvasLayer.new()
	add_child(_layer)
	_draw = Control.new()
	_draw.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_draw.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_draw.draw.connect(_draw_marks)
	_layer.add_child(_draw)
	var panel := PanelContainer.new()
	panel.theme = UITheme.make()
	panel.add_theme_stylebox_override("panel", UITheme.box(UITheme.BAR, 6, 8))
	panel.position = Vector2(8, 44)
	var column := VBoxContainer.new()
	var row := HBoxContainer.new()
	var title := Label.new()
	title.text = "Test mode"
	row.add_child(title)
	_pause_button = Button.new()
	_pause_button.text = "Pause"
	_pause_button.focus_mode = Control.FOCUS_NONE
	_pause_button.pressed.connect(func() -> void: set_paused(not paused))
	row.add_child(_pause_button)
	_speed_button = OptionButton.new()
	_speed_button.focus_mode = Control.FOCUS_NONE
	for s in [0.5, 1.0, 2.0, 4.0]:
		_speed_button.add_item("%sx" % [s], int(s * 10))
	_speed_button.select(1)
	_speed_button.item_selected.connect(func(index: int) -> void: speed = _speed_button.get_item_id(index) / 10.0)
	row.add_child(_speed_button)
	var paths_label := Label.new()
	paths_label.text = "   Paths"
	row.add_child(paths_label)
	var paths_button := OptionButton.new()
	paths_button.focus_mode = Control.FOCUS_NONE
	paths_button.tooltip_text = "The path each unit's AI follows: the selected units' (and their members'), or every unit's"
	for p in PATHS:
		paths_button.add_item(p)
	paths_button.select(PATHS.find(paths))
	paths_button.item_selected.connect(func(index: int) -> void: paths = PATHS[index])
	row.add_child(paths_button)
	column.add_child(row)
	_info = Label.new()
	_info.add_theme_color_override("font_color", UITheme.MUTED)
	column.add_child(_info)
	var keys := Label.new()
	keys.text = KEYS
	keys.add_theme_color_override("font_color", UITheme.MUTED)
	column.add_child(keys)
	panel.add_child(column)
	_layer.add_child(panel)
	_panel = panel


## The panel shown or hidden (hidden for a picture: a screenshot, a view's thumbnail).
func show_panel(on: bool) -> void:
	if _panel != null:
		_panel.visible = on


func set_paused(on: bool) -> void:
	paused = on
	_pause_button.text = "Resume" if on else "Pause"


func _show_info() -> void:
	selected = selected.filter(func(id) -> bool: return _alive(world.get_object(id)))
	if selected.is_empty():
		_info.text = "Nothing selected" + ("   (paused)" if paused else "")
		return
	var first: Dictionary = world.get_object(selected[0])
	var names := {}
	for id in selected:
		var t := String(world.get_object(id).template)
		names[t] = names.get(t, 0) + 1
	var parts := PackedStringArray()
	for t in names:
		parts.append(t if names[t] == 1 else "%s x %d" % [t, names[t]])
	_info.text = "%s: %s%s" % [first.owner, ", ".join(parts), "   (paused)" if paused else ""]


# The units --------------------------------------------------------------------------------------------------------

static func _alive(o: Dictionary) -> bool:
	return o.get("ok", false) and not o.get("destroyed", false)


## Whether a player may select it: a unit or a battalion standing on its own (not a member, not a building).
static func _selectable(o: Dictionary) -> bool:
	return _alive(o) and o.get("has_ai", false) and int(o.get("contained_by", 0)) == 0 and not o.get("structure", false) \
		and o.get("selectable", true)


func _screen(o: Dictionary) -> Variant:
	var at := Surface.to_godot(Vector3(o.x, o.y, o.z))
	if _camera.is_position_behind(at):
		return null
	return _camera.unproject_position(at)


static func _radius(o: Dictionary) -> float:
	return 45.0 if not (o.get("members", []) as Array).is_empty() else 14.0     # map units around its foot


## The unit under the cursor, or 0.
func unit_at(pos: Vector2) -> int:
	var best := 0
	var best_d := INF
	for id in world.get_object_ids():
		var o: Dictionary = world.get_object(id)
		if not _selectable(o):
			continue
		var p: Variant = _screen(o)
		if p == null:
			continue
		var reach := PICK_PIXELS * (2.0 if _radius(o) > 20.0 else 1.0)
		var d := (p as Vector2).distance_to(pos)
		if d < reach and d < best_d:
			best = id
			best_d = d
	return best


func _owner(id: int) -> String:
	return String(world.get_object(id).get("owner", ""))


## A left click: that unit selected (Shift: added, when it has the selection's owner), else nothing.
func click(pos: Vector2, shift: bool) -> void:
	var id := unit_at(pos)
	if id == 0:
		if not shift:
			selected.clear()
		return
	if not shift or selected.is_empty() or _owner(selected[0]) != _owner(id):
		selected.clear()
	if selected.has(id):
		selected.erase(id)
	else:
		selected.append(id)


func box_start(pos: Vector2) -> void:
	_box_from = pos
	_box_to = pos


func box_move(pos: Vector2) -> void:
	_box_to = pos


## The left drag ended: the units in the box, of one owner (the selection's when it has some there, else the first
## found's).
func box_end(shift: bool) -> void:
	var rect := Rect2(_box_from, Vector2.ZERO).expand(_box_to)
	_box_from = Vector2.INF
	var found := []
	for id in world.get_object_ids():
		var o: Dictionary = world.get_object(id)
		if not _selectable(o):
			continue
		var p: Variant = _screen(o)
		if p != null and rect.has_point(p):
			found.append(id)
	if found.is_empty():
		return
	var side := _owner(selected[0]) if shift and not selected.is_empty() else _owner(found[0])
	if not shift:
		selected.clear()
	for id in found:
		if _owner(id) == side and not selected.has(id):
			selected.append(id)


func dragging() -> bool:
	return _box_from != Vector2.INF


## The left button up: a click where it went down, else the box.
func left_up(pos: Vector2, shift: bool) -> void:
	if pos.distance_to(_box_from) < 4.0:
		_box_from = Vector2.INF
		click(pos, shift)
	else:
		_box_to = pos
		box_end(shift)


## A right click: attack the unit there if it is another owner's, else move to `ground` (map coordinates; INF:
## nothing under the cursor). Shift adds a waypoint.
func order(pos: Vector2, ground: Vector3, shift: bool) -> String:
	if selected.is_empty():
		return ""
	var target := unit_at(pos)
	var r: Dictionary
	if target != 0 and _owner(target) != _owner(selected[0]):
		r = world.order_attack(selected, target)
		return "attack %s: %s" % [world.get_object(target).template, "ok" if r.get("ok", false) else r.get("error", "?")]
	if ground == Vector3.INF:
		return ""
	r = world.order_move(selected, ground.x, ground.y, {"type": "waypoint" if shift else "move"})
	return "move to (%.0f, %.0f): %s" % [ground.x, ground.y, "ok" if r.get("ok", false) else r.get("error", "?")]


func stop() -> void:
	if not selected.is_empty():
		world.order_stop(selected)


# The marks over the view ------------------------------------------------------------------------------------------

## The units whose paths are drawn, each with whether it stands on its own (drawn thick; a battalion's member: thin): the
## selected ones and their members, or every unit standing on its own and every battalion's members.
func _path_units() -> Dictionary:
	var out := {}
	var ids: Array = selected if paths == "Selected" else (world.get_object_ids() if paths == "All" else [])
	for id in ids:
		var o: Dictionary = world.get_object(id)
		if not _selectable(o):
			continue
		out[id] = true
		for m in o.get("members", []):
			out[m] = false
	return out


func _draw_paths() -> void:
	var units := _path_units()
	for id in units:
		var r: Dictionary = world.get_object_path(id)
		if not r.get("ok", false):
			continue
		var o: Dictionary = world.get_object(id)
		var width := 3.0 if units[id] else 1.5
		var colour := BLOCKED if r.blocked else (WAITING if r.waiting else PATH)
		var points: Array = r.points
		var current: int = r.current
		var here := Vector3(o.x, o.y, o.z)
		if points.is_empty():
			if r.waiting:                              # no path yet: where it wants to go
				_line(here, r.goal, WAITING, width)
			continue
		for i in range(1, points.size()):
			_line(points[i - 1], points[i], PATH_DONE if current >= 0 and i <= current else colour, width)
		if r.moving and current >= 0 and current + 1 < points.size():
			_line(here, points[current + 1], colour, width)    # from the unit to the node it walks to
		_cross(points[-1], colour, 5.0 if units[id] else 3.0)


## A line between two map points over the ground, unless it runs behind the camera.
func _line(a: Vector3, b: Vector3, colour: Color, width: float) -> void:
	var pa := Surface.to_godot(a + Vector3(0, 0, LIFT))
	var pb := Surface.to_godot(b + Vector3(0, 0, LIFT))
	if _camera.is_position_behind(pa) or _camera.is_position_behind(pb):
		return
	_draw.draw_line(_camera.unproject_position(pa), _camera.unproject_position(pb), colour, width, true)


func _cross(at: Vector3, colour: Color, size: float) -> void:
	var p := Surface.to_godot(at + Vector3(0, 0, LIFT))
	if _camera.is_position_behind(p):
		return
	var c := _camera.unproject_position(p)
	_draw.draw_line(c - Vector2(size, size), c + Vector2(size, size), colour, 2.0, true)
	_draw.draw_line(c - Vector2(size, -size), c + Vector2(size, -size), colour, 2.0, true)


func _draw_marks() -> void:
	if paths != "Off" and world.has_method("get_object_path"):
		_draw_paths()
	for id in selected:
		var o: Dictionary = world.get_object(id)
		if not _alive(o):
			continue
		var r := _radius(o)
		var points := PackedVector2Array()
		for i in 25:
			var a := TAU * i / 24.0
			var at := Surface.to_godot(Vector3(o.x + r * cos(a), o.y + r * sin(a), o.z))
			if _camera.is_position_behind(at):
				points.clear()
				break
			points.append(_camera.unproject_position(at))
		if points.size() > 1:
			_draw.draw_polyline(points, RING, 2.0, true)
		var health := float(o.get("health", 0.0))
		var most := float(o.get("max_health", 0.0))
		var top: Variant = _screen({"x": o.x, "y": o.y, "z": o.z + 30.0})
		if most > 0.0 and top != null:
			var bar := Rect2((top as Vector2) - Vector2(16, 3), Vector2(32, 4))
			_draw.draw_rect(bar, Color(0, 0, 0, 0.7))
			_draw.draw_rect(Rect2(bar.position, Vector2(bar.size.x * clampf(health / most, 0.0, 1.0), bar.size.y)), RING)
	if _box_from != Vector2.INF and _box_from.distance_to(_box_to) > 3.0:
		var rect := Rect2(_box_from, Vector2.ZERO).expand(_box_to)
		_draw.draw_rect(rect, Color(BOX, 0.12))
		_draw.draw_rect(rect, BOX, false, 1.0)
