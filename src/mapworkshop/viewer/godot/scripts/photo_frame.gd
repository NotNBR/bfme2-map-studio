## Photo mode's framing aids over the view, as the Python viewer drew them: bands darkening what is outside the
## frame's aspect (Lens.frame_rect, which screenshots crop to), thirds lines in it, and a focus mark at the centre
## while the lens blurs.
class_name PhotoFrame
extends Control

var ratio := 0.0:
	set(v):
		ratio = v
		queue_redraw()
var thirds := false:
	set(v):
		thirds = v
		queue_redraw()
var reticle := false:
	set(v):
		reticle = v
		queue_redraw()


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(queue_redraw)


func _draw() -> void:
	var w := size
	var r := Rect2(Lens.frame_rect(Vector2i(w), ratio))
	var band := Color(0, 0, 0, 150 / 255.0)
	if r.position.y > 0:
		draw_rect(Rect2(0, 0, w.x, r.position.y), band)
		draw_rect(Rect2(0, r.end.y, w.x, w.y - r.end.y), band)
	if r.position.x > 0:
		draw_rect(Rect2(0, 0, r.position.x, w.y), band)
		draw_rect(Rect2(r.end.x, 0, w.x - r.end.x, w.y), band)
	var line := Color(1, 1, 1, 90 / 255.0)
	if thirds:
		for k: int in [1, 2]:
			var x := r.position.x + r.size.x * k / 3.0
			var y := r.position.y + r.size.y * k / 3.0
			draw_line(Vector2(x, r.position.y), Vector2(x, r.end.y), line)
			draw_line(Vector2(r.position.x, y), Vector2(r.end.x, y), line)
	if reticle:
		var c := w / 2.0
		draw_arc(c, maxf(6.0, w.y / 90.0), 0.0, TAU, 32, Color(1, 1, 1, 170 / 255.0), 1.0)
		draw_rect(Rect2(c, Vector2.ONE), Color(1, 1, 1, 220 / 255.0))
