## The viewer's look: dark bars over the map, light text, the selected and hovered controls lighter.
class_name UITheme
extends RefCounted

const BAR := Color(0.09, 0.10, 0.12, 0.94)
const RAISED := Color(0.18, 0.19, 0.23, 1.0)
const HOVER := Color(0.25, 0.27, 0.32, 1.0)
const ON := Color(0.30, 0.42, 0.62, 1.0)
const TEXT := Color(0.90, 0.91, 0.93)
const MUTED := Color(0.60, 0.62, 0.66)
const GOOD := Color(0.45, 0.78, 0.48)
const BAD := Color(0.93, 0.42, 0.38)


static func box(color: Color, radius := 4, margin := 6) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = color
	b.set_corner_radius_all(radius)
	b.content_margin_left = margin
	b.content_margin_right = margin
	b.content_margin_top = margin * 0.6
	b.content_margin_bottom = margin * 0.6
	return b


static func make() -> Theme:
	var t := Theme.new()
	t.default_font_size = 14
	t.set_stylebox("panel", "PanelContainer", box(BAR, 0, 6))
	for kind in ["Button", "MenuButton", "OptionButton", "CheckBox"]:
		t.set_stylebox("normal", kind, box(Color(0, 0, 0, 0)))
		t.set_stylebox("hover", kind, box(HOVER))
		t.set_stylebox("pressed", kind, box(ON))
		t.set_stylebox("hover_pressed", kind, box(ON.lightened(0.1)))
		t.set_stylebox("disabled", kind, box(Color(0, 0, 0, 0)))
		t.set_stylebox("focus", kind, StyleBoxEmpty.new())
		t.set_color("font_color", kind, TEXT)
		t.set_color("font_hover_color", kind, Color.WHITE)
		t.set_color("font_pressed_color", kind, Color.WHITE)
		t.set_color("font_disabled_color", kind, MUTED.darkened(0.3))
	t.set_stylebox("panel", "PopupMenu", box(RAISED, 4, 4))
	t.set_stylebox("hover", "PopupMenu", box(HOVER))
	t.set_color("font_color", "PopupMenu", TEXT)
	t.set_color("font_hover_color", "PopupMenu", Color.WHITE)
	t.set_color("font_disabled_color", "PopupMenu", MUTED)
	t.set_color("font_separator_color", "PopupMenu", MUTED)
	t.set_color("font_color", "Label", TEXT)
	t.set_stylebox("panel", "TooltipPanel", box(RAISED))
	t.set_color("font_color", "TooltipLabel", TEXT)
	return t
