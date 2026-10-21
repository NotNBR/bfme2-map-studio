## The marks over the map, as the studio viewer draws them (viewer/overlay.py, MarkOverlay): each outline draped on the
## surface (Python sends the draped points: godot_link.marks_state), projected with the camera every frame and drawn
## on top as a thick line, a translucent fill for areas, discs for pins and a numbered tag per mark. Red marks; the one
## under the cursor lighter, the selected one yellow with square handles to resize it and, for a rectangle, a round
## handle on a stem to rotate it.
##
## It also answers what is under a window position, with overlay.py's rules and distances, for the companion's
## MarkEditor: handle_at, grab_at, mark_at, handle_direction.
class_name MarkOverlay
extends Control

const RED := Color(0.92, 0.12, 0.10)
const HOVER := Color(1.0, 0.42, 0.30)
const YELLOW := Color(1.0, 0.85, 0.15)
const WHITE := Color(1.0, 1.0, 1.0)

var camera: Camera3D
var state := {}                 # the companion's marks message
var _screen := {}               # mark id -> [visible pixels, closed and wholly visible]
var _tags := {}                 # mark id -> its tag's rectangle
var _handles := []              # [pixel, handle index or "rotate"] of the selected mark
var _centre = null              # the selected mark's centre in pixels


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_preset(Control.PRESET_FULL_RECT)


func _process(_delta: float) -> void:
	queue_redraw()


## Pixel positions of map points and whether each is in front of the camera.
func _project(world: Array) -> Array:
	var pixels := PackedVector2Array()
	var ok := []
	for p in world:
		var g := Surface.to_godot(Vector3(p[0], p[1], p[2]))
		ok.append(not camera.is_position_behind(g))
		pixels.append(camera.unproject_position(g))
	return [pixels, ok]


func _draw() -> void:
	_screen.clear()
	_tags.clear()
	_handles.clear()
	_centre = null
	if camera == null or state.is_empty() or not state.get("visible", true):
		return
	var shown: Array = state.get("marks", [])
	var preview = state.get("preview")
	var tags := []
	for mark in shown + ([preview] if preview != null else []):
		var is_preview: bool = mark == preview
		var projected := _project(mark.world)
		var pix: PackedVector2Array = projected[0]
		var ok: Array = projected[1]
		var id = mark.get("id")
		var color := YELLOW if id != null and id == state.get("selected") else (HOVER if id != null and id == state.get("hovered") else RED)
		if mark.kind == "pin":
			if ok[0]:
				draw_circle(pix[0], 9.0, WHITE)
				draw_circle(pix[0], 6.5, color)
				tags.append([id, pix[0] + Vector2(9, -20), color])
			_screen[id] = [PackedVector2Array([pix[0]]) if ok[0] else PackedVector2Array(), false]
			continue
		var closed: bool = mark.closed
		var all_ok := not ok.has(false)
		if closed and all_ok and pix.size() > 2:
			_fill(pix, Color(color, 0.16))
		_polyline(pix, ok, closed, 3.0, Color(color, 0.95))
		if not is_preview:
			var visible := PackedVector2Array()
			for i in pix.size():
				if ok[i]:
					visible.append(pix[i])
			_screen[id] = [visible, closed and all_ok]
			if visible.size() > 0:
				var top := visible[0]
				for v in visible:
					if v.y < top.y:
						top = v
				tags.append([id, top + Vector2(6, -24), color])
			if id == state.get("selected") and state.get("handles") != null:
				_draw_handles(state.handles, color)
	for tag in tags:
		_tags[tag[0]] = _tag(str(int(tag[0])), tag[1], tag[2])      # ids come as JSON numbers: floats here


## A fan from the centroid, as overlay.py fills an area (any outline, even one that crosses itself).
func _fill(pix: PackedVector2Array, color: Color) -> void:
	var c := Vector2.ZERO
	for p in pix:
		c += p
	c /= pix.size()
	for i in pix.size():
		draw_colored_polygon(PackedVector2Array([c, pix[i], pix[(i + 1) % pix.size()]]), color)


func _polyline(pix: PackedVector2Array, ok: Array, closed: bool, width: float, color: Color) -> void:
	var n := pix.size()
	for i in n - 1 + (1 if closed and n > 2 else 0):
		var j := (i + 1) % n
		if ok[i] and ok[j]:
			draw_line(pix[i], pix[j], color, width, true)
			draw_circle(pix[j], width / 2.0, color)


func _draw_handles(h: Dictionary, color: Color) -> void:
	var spots: Array = h.spots
	var extra := [h.center] + ([h.rotate] if h.get("rotate") != null else [])
	var projected := _project(spots + extra)
	var pix: PackedVector2Array = projected[0]
	var ok: Array = projected[1]
	var n := spots.size()
	_centre = pix[n] if ok[n] else null
	if h.get("rotate") != null and ok[n] and ok[n + 1]:
		var side := pix[n + 1]
		var d := side - pix[n]
		var knob := side + (d.normalized() if d.length() > 1e-6 else Vector2(0, -1)) * 26.0
		draw_line(side, knob, color, 2.0, true)
		draw_circle(knob, 7.0, WHITE)
		draw_circle(knob, 4.5, color)
		_handles.append([knob, "rotate"])
	for i in n:
		if ok[i]:
			draw_rect(Rect2(pix[i] - Vector2(6, 6), Vector2(12, 12)), WHITE)
			draw_rect(Rect2(pix[i] - Vector2(4, 4), Vector2(8, 8)), color)
			_handles.append([pix[i], i])


## A mark's number on a rounded tag; its rectangle, for picking.
func _tag(text: String, at: Vector2, color: Color) -> Rect2:
	var font := get_theme_default_font()
	var size := 13
	var width := font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x + 12.0
	var rect := Rect2(at, Vector2(width, 20))
	var box := StyleBoxFlat.new()
	box.bg_color = Color(color, 0.92)
	box.border_color = Color(WHITE, 0.92)
	box.set_border_width_all(1)
	box.set_corner_radius_all(5)
	draw_style_box(box, rect)
	var ink := Color(0.16, 0.12, 0.0) if color == YELLOW else WHITE
	draw_string(font, at + Vector2(6, 15), text, HORIZONTAL_ALIGNMENT_LEFT, -1, size, ink)
	return rect


# Picking ---------------------------------------------------------------------------------------------------------------

## The selected mark's handle at a window position: its index, "rotate", or null.
func handle_at(pos: Vector2):
	var best = null
	var best_d := 9.0
	for h in _handles:
		var d: float = (h[0] as Vector2).distance_to(pos)
		if d <= best_d:
			best = h[1]
			best_d = d
	return best


## How a handle moves on screen: "rotate", or "ew", "nesw", "ns" or "nwse" from the mark's centre outwards.
func handle_direction(key) -> String:
	if typeof(key) == TYPE_STRING and key == "rotate":
		return "rotate"
	if _centre == null:
		return "ew"
	for h in _handles:
		if typeof(h[1]) == typeof(key) and h[1] == key:
			var d: Vector2 = h[0] - _centre
			var a := fposmod(rad_to_deg(atan2(-d.y, d.x)), 180.0)
			return ["ew", "nesw", "ns", "nwse"][int((a + 22.5) / 45.0) % 4]
	return "ew"


## [the mark whose tag, pin or outline is within 10 pixels, or null; [[screen area, id]] of the areas containing pos].
func _picks(pos: Vector2) -> Array:
	for id in _tags:
		if (_tags[id] as Rect2).has_point(pos):
			return [id, []]
	var best = null
	var best_d := 10.0
	var inside := []
	for id in _screen:
		var pix: PackedVector2Array = _screen[id][0]
		var closed: bool = _screen[id][1]
		if id == null or pix.is_empty():
			continue
		var d := INF
		if pix.size() == 1:
			d = pix[0].distance_to(pos)
		else:
			var path := pix.duplicate()
			if closed:
				path.append(pix[0])
			for i in path.size() - 1:
				d = minf(d, pos.distance_to(Geometry2D.get_closest_point_to_segment(pos, path[i], path[i + 1])))
			if closed and Geometry2D.is_point_in_polygon(pos, pix):
				inside.append([_area(pix), id])
		if d < best_d:
			best = id
			best_d = d
	return [best, inside]


static func _area(pix: PackedVector2Array) -> float:
	var twice := 0.0
	for i in pix.size():
		var a := pix[i]
		var b := pix[(i + 1) % pix.size()]
		twice += a.x * b.y - a.y * b.x
	return absf(twice)


## The mark a drag from pos would move: its tag, pin or outline is there, or it is the selected area and contains it.
func grab_at(pos: Vector2, selected):
	var picked := _picks(pos)
	if picked[0] == null and selected != null:
		for entry in picked[1]:
			if entry[1] == selected:
				return selected
	return picked[0]


## The mark under pos: tags, pins and outlines within a few pixels, then the smallest area that contains it.
func mark_at(pos: Vector2):
	var picked := _picks(pos)
	if picked[0] != null or picked[1].is_empty():
		return picked[0]
	var smallest = picked[1][0]
	for entry in picked[1]:
		if entry[0] < smallest[0]:
			smallest = entry
	return smallest[1]
