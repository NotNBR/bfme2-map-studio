## The bar along the bottom, as the studio viewer's camera bar and status bar have them (docs/viewer.md, "Photo mode and
## the camera bar"): at the left the camera, Edit or Photo, and in Photo mode the lens (focal length, aperture, focus,
## exposure: the wheel or a sideways drag over a field changes it, a click opens its presets) and the framing aids
## (Thirds, the frame's aspect); then the status line (the latest message for its time, else what the mouse does now);
## at the right the camera's readout. The viewer keeps the camera and the lens; this shows them (set_photo) and says
## what was asked for.
class_name CameraBar
extends PanelContainer

signal mode_chosen(mode: String)
## A lens field's preset ("focal", "aperture", "focus" with "centre" or a distance, "ev") or the frame ("frame").
signal lens_pick(field: String, value: Variant)
## The wheel or a drag over a lens field, in notches.
signal lens_step(field: String, notches: int)
signal thirds_toggled(on: bool)

const FIELDS := ["focal", "aperture", "focus", "ev"]
const SCRUB_PIXELS := 6.0     # a sideways drag of this many pixels is a notch (viewer/app.py)

var _status: Label
var _readout: Label
var _until := 0.0
var _hint := ""
var _edit: Button
var _photo: Button
var _lens_row: HBoxContainer      # the lens and the framing aids, in Photo mode
var _fields := {}              # field -> Button
var _presets := {}             # field -> PopupMenu
var _choices := {}             # field -> the values of its PopupMenu's items, by id
var _thirds: Button
var _frame: MenuButton
var _state := {}               # the lens as last shown (set_photo)
var _scrub := {}               # a press on a field: {field, x, moved}


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	grow_vertical = Control.GROW_DIRECTION_BEGIN
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	add_child(row)
	var group := ButtonGroup.new()
	_edit = _toggle(row, "Edit", "The Edit camera: orbit the map, mark it (V)", group)
	_edit.button_pressed = true
	_edit.pressed.connect(func() -> void: mode_chosen.emit("edit"))
	_photo = _toggle(row, "Photo", "The free camera with a lens, for pictures (V)", group)
	_photo.pressed.connect(func() -> void: mode_chosen.emit("photo"))
	_lens_row = HBoxContainer.new()
	_lens_row.add_theme_constant_override("separation", 4)
	_lens_row.visible = false
	row.add_child(_lens_row)
	_lens_row.add_child(VSeparator.new())
	var tips := {"focal": "Focal length (mm, full frame): wheel or drag to change, click for presets",
		"aperture": "Aperture: depth of field (f/– is everything sharp)", "focus": "Focus distance along the view",
		"ev": "Exposure compensation"}
	for field in FIELDS:
		var b := Button.new()
		b.tooltip_text = tips[field]
		b.focus_mode = Control.FOCUS_NONE
		b.gui_input.connect(_field_input.bind(field))
		_lens_row.add_child(b)
		_fields[field] = b
		var menu := PopupMenu.new()
		menu.id_pressed.connect(func(id: int) -> void: lens_pick.emit(field, _choices[field][id]))
		b.add_child(menu)
		_presets[field] = menu
	_lens_row.add_child(VSeparator.new())
	_thirds = _toggle(_lens_row, "Thirds", "Thirds lines over the frame", null)
	_thirds.toggled.connect(func(on: bool) -> void: thirds_toggled.emit(on))
	_frame = MenuButton.new()
	_frame.tooltip_text = "The frame's aspect: screenshots crop to it"
	_frame.flat = false
	var frames := _frame.get_popup()
	frames.add_separator("Frame (screenshots crop to it)")
	for i in Lens.FRAMES.size():
		frames.add_radio_check_item(Lens.FRAMES[i][1], i)
	frames.id_pressed.connect(func(id: int) -> void: lens_pick.emit("frame", Lens.FRAMES[id][0]))
	_lens_row.add_child(_frame)
	row.add_child(VSeparator.new())
	_status = Label.new()
	_status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_status.clip_text = true
	_status.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	row.add_child(_status)
	_readout = Label.new()
	_readout.add_theme_color_override("font_color", UITheme.MUTED)
	row.add_child(_readout)


func _toggle(row: Container, text: String, tip: String, group: ButtonGroup) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tip
	b.toggle_mode = true
	b.button_group = group
	b.focus_mode = Control.FOCUS_NONE
	row.add_child(b)
	return b


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


func set_readout(text: String) -> void:
	_readout.text = text


## The Edit camera's readout, as the studio's: its target, distance, heading and tilt.
func set_orbit(orbit: OrbitCamera) -> void:
	var c: Dictionary = orbit.cur
	_readout.text = "target %.0f, %.0f   distance %.0f   heading %.0f°   tilt %.0f°" % [
		c.x, c.y, c.distance, fposmod(c.heading, 360.0), c.elevation]


func set_mode(mode: String) -> void:
	_edit.set_pressed_no_signal(mode == "edit")
	_photo.set_pressed_no_signal(mode == "photo")
	_lens_row.visible = mode == "photo"


## The lens and the framing as they are: {focal, aperture, focus, ev, thirds, frame, width (the frame's mm, for the
## focal presets' fields of view)}.
func set_photo(state: Dictionary) -> void:
	if state == _state:
		return
	_state = state.duplicate()
	_fields.focal.text = "%.0f mm" % state.focal
	_fields.aperture.text = Lens.aperture_text(state.aperture)
	_fields.focus.text = "focus %s" % Lens.thousands(state.focus)
	_fields.ev.text = Lens.ev_text(state.ev)
	_thirds.set_pressed_no_signal(state.thirds)
	for i in Lens.FRAMES.size():
		if Lens.FRAMES[i][0] == state.frame:
			_frame.text = "%s  ▾" % Lens.FRAMES[i][1]
		_frame.get_popup().set_item_checked(_frame.get_popup().get_item_index(i), Lens.FRAMES[i][0] == state.frame)


## A lens field's presets, checked where the lens is.
func _fill(field: String) -> void:
	var menu: PopupMenu = _presets[field]
	menu.clear()
	var values := []
	var add := func(text: String, value: Variant, checked: bool) -> void:
		menu.add_radio_check_item(text, values.size())
		menu.set_item_checked(menu.item_count - 1, checked)
		values.append(value)
	match field:
		"focal":
			menu.add_separator("Focal length (full frame)")
			for v in Lens.FOCALS:
				add.call("%d mm   %.0f° wide" % [v, Lens.fov_from_focal(v, _state.width)], float(v),
					absf(_state.focal - v) < 0.5)
		"aperture":
			menu.add_separator("Aperture: depth of field")
			for v in Lens.APERTURES:
				add.call("Off: all sharp" if v == 0.0 else Lens.aperture_text(v), v, _state.aperture == v)
		"focus":
			menu.add_separator("Focus distance")
			add.call("On the centre of the view   (middle click)", "centre", false)
			for v in Lens.FOCUS_DISTANCES:
				add.call("%s units   %s m" % [Lens.thousands(v), Lens.number(v / 10.0)], float(v),
					absf(_state.focus - v) < 0.5)
		"ev":
			menu.add_separator("Exposure")
			for v in Lens.EXPOSURES:
				add.call(Lens.ev_text(v), v, absf(_state.ev - v) < 1e-6)
	_choices[field] = values


func _field_input(event: InputEvent, field: String) -> void:
	if event is InputEventMouseButton:
		var b := event as InputEventMouseButton
		if b.pressed and (b.button_index == MOUSE_BUTTON_WHEEL_UP or b.button_index == MOUSE_BUTTON_WHEEL_DOWN):
			lens_step.emit(field, 1 if b.button_index == MOUSE_BUTTON_WHEEL_UP else -1)
			accept_event()
		elif b.button_index == MOUSE_BUTTON_LEFT:
			if b.pressed:
				_scrub = {"field": field, "x": b.position.x, "moved": false}
			elif not _scrub.is_empty():
				if not _scrub.moved:               # a click opens its presets, a drag scrubs
					_fill(field)
					var button: Button = _fields[field]
					var menu: PopupMenu = _presets[field]
					menu.reset_size()
					menu.popup(Rect2i(Vector2i(button.get_screen_position()) - Vector2i(0, menu.size.y + 6), menu.size))
				_scrub = {}
			accept_event()
	elif event is InputEventMouseMotion and not _scrub.is_empty():
		var notches := int((event.position.x - _scrub.x) / SCRUB_PIXELS)
		if notches != 0:
			lens_step.emit(field, notches)
			_scrub.x += notches * SCRUB_PIXELS
			_scrub.moved = true
		accept_event()
