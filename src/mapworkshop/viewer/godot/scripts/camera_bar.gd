## The bar along the bottom: the status line at the left (the latest message for its time, else what the mouse does
## now) and the camera's readout at the right, as the studio viewer's camera bar and status bar have them.
class_name CameraBar
extends PanelContainer

var _status: Label
var _readout: Label
var _until := 0.0
var _hint := ""


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	grow_vertical = Control.GROW_DIRECTION_BEGIN
	var row := HBoxContainer.new()
	add_child(row)
	_status = Label.new()
	_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_status.clip_text = true
	_status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	row.add_child(_status)
	_readout = Label.new()
	_readout.add_theme_color_override("font_color", UITheme.MUTED)
	row.add_child(_readout)


func _process(_delta: float) -> void:
	if Time.get_ticks_msec() / 1000.0 > _until:
		_status.text = _hint
		_status.add_theme_color_override("font_color", UITheme.MUTED)


func set_status(text: String, seconds: float) -> void:
	_status.text = text
	_status.add_theme_color_override("font_color", UITheme.TEXT)
	_until = Time.get_ticks_msec() / 1000.0 + seconds


## What the mouse does now, between messages.
func set_hint(hint) -> void:
	_hint = "" if hint == null else String(hint)


## The Edit camera's readout, as the studio's: its target, distance, heading and tilt.
func set_orbit(orbit: OrbitCamera) -> void:
	var c: Dictionary = orbit.cur
	_readout.text = "target %.0f, %.0f   distance %.0f   heading %.0f°   tilt %.0f°" % [
		c.x, c.y, c.distance, fposmod(c.heading, 360.0), c.elevation]
