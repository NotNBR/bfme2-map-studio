## In-studio map chooser: custom maps on the left, originals on the right, backed by the companion's map catalog.
class_name MapPicker
extends AcceptDialog

signal map_chosen(path: String)
signal command(name: String)

var _catalog := {}
var _columns: HBoxContainer
var _search: LineEdit
var _status: Label
var _busy := false
var _selected := {}


func _ready() -> void:
	title = "Open Map"
	ok_button_text = "Open Map"
	dialog_hide_on_ok = false
	get_ok_button().disabled = true
	get_ok_button().add_theme_stylebox_override("normal", UITheme.box(UITheme.ON, 4, 12))
	get_ok_button().add_theme_stylebox_override("disabled", UITheme.box(UITheme.RAISED, 4, 12))
	confirmed.connect(func() -> void:
		if not _selected.is_empty():
			_choose(_selected))
	add_button("Cancel", true, "cancel")
	custom_action.connect(func(action: String) -> void:
		if action == "cancel": hide())
	exclusive = true
	theme = UITheme.make()
	theme.set_stylebox("panel", "AcceptDialog", UITheme.box(UITheme.BAR, 8, 12))
	theme.set_stylebox("embedded_border", "Window", UITheme.box(UITheme.RAISED, 8, 8))
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	add_child(box)
	_search = LineEdit.new()
	_search.placeholder_text = "Search maps…"
	_search.text_changed.connect(func(_text: String) -> void:
		_select({})
		_fill_columns())
	box.add_child(_search)
	_columns = HBoxContainer.new()
	_columns.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_columns.add_theme_constant_override("separation", 12)
	box.add_child(_columns)
	# Keep wrapped status text out of the dialog's minimum-size calculation.
	# Its transient width during layout could otherwise grow the window vertically.
	var status_slot := Control.new()
	status_slot.custom_minimum_size.y = 36
	status_slot.clip_contents = true
	box.add_child(status_slot)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.clip_text = true
	_status.visible = false
	status_slot.add_child(_status)
	_status.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var actions := HBoxContainer.new()
	box.add_child(actions)
	var browse := Button.new()
	browse.text = "Browse .map…"
	browse.tooltip_text = "Open a .map file: a downloaded or separately generated map"
	browse.pressed.connect(func() -> void: command.emit("browse"))
	actions.add_child(browse)
	set_catalog(_catalog)


func set_catalog(catalog: Dictionary) -> void:
	_catalog = catalog
	if _columns == null:
		return
	_fill_columns()


func open() -> void:
	var available: Vector2 = get_parent().get_viewport_rect().size
	popup_centered(Vector2i(mini(820, int(available.x) - 48), mini(520, int(available.y) - 80)))
	_search.grab_focus()


func failed(message: String) -> void:
	_busy = false
	_status.text = message
	_status.tooltip_text = message
	_status.visible = true
	_status.add_theme_color_override("font_color", UITheme.BAD)
	_set_busy(false)
	if not visible:
		open()


func loaded() -> void:
	_set_busy(false)
	_select({})
	_status.text = ""
	_status.tooltip_text = ""
	_status.visible = false
	hide()


func _choose(entry: Dictionary) -> void:
	if _busy:
		return
	_busy = true
	_status.visible = true
	_status.remove_theme_color_override("font_color")
	_status.text = "%s %s…" % ["Opening" if entry.get("ready", true) else "Building and opening", entry.title]
	_status.tooltip_text = _status.text
	_set_busy(true)
	map_chosen.emit(entry.map)


func _set_busy(busy: bool) -> void:
	_busy = busy
	get_ok_button().disabled = busy or _selected.is_empty()
	# Preserve the lists and their scroll positions while a selection loads.
	for column in _columns.get_children():
		for control in column.get_child(1).get_child(0).get_children():
			if control is Button:
				control.disabled = busy


func _select(entry: Dictionary) -> void:
	_selected = entry
	if not _busy:
		_status.text = ""
		_status.tooltip_text = ""
		_status.visible = false
	ok_button_text = "Build and Open" if not entry.is_empty() and not entry.get("ready", true) else "Open Map"
	get_ok_button().disabled = _busy or entry.is_empty()
	for column in _columns.get_children():
		for control in column.get_child(1).get_child(0).get_children():
			if control is Button:
				control.set_pressed_no_signal(control.get_meta("map") == entry.get("map", ""))


func _fill_columns() -> void:
	for child in _columns.get_children():
		_columns.remove_child(child)
		child.queue_free()
	for group in [["Custom maps", "projects"], ["Original maps", "stock"]]:
		var column := VBoxContainer.new()
		column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		column.add_theme_constant_override("separation", 6)
		_columns.add_child(column)
		var label := Label.new()
		label.text = group[0]
		label.add_theme_font_size_override("font_size", 16)
		column.add_child(label)
		var scroll := ScrollContainer.new()
		scroll.custom_minimum_size.y = 300
		scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
		scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
		scroll.follow_focus = true
		column.add_child(scroll)
		var row := VBoxContainer.new()
		row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_theme_constant_override("separation", 4)
		scroll.add_child(row)
		for entry in _catalog.get(group[1], []):
			if not _search.text.is_empty() and not String(entry.title).to_lower().contains(_search.text.to_lower()):
				continue
			var button := Button.new()
			button.custom_minimum_size = Vector2(210, 34)
			button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			button.disabled = _busy
			button.toggle_mode = true
			button.set_meta("map", entry.map)
			button.set_pressed_no_signal(entry.map == _selected.get("map", ""))
			button.add_theme_stylebox_override("normal", UITheme.box(UITheme.RAISED, 6, 10))
			button.add_theme_stylebox_override("disabled", UITheme.box(UITheme.RAISED.darkened(0.2), 6, 10))
			button.add_theme_stylebox_override("focus", UITheme.box(Color(0.3, 0.42, 0.62, 0.3), 6, 10))
			button.tooltip_text = entry.map
			button.pressed.connect(func() -> void: _select(entry))
			row.add_child(button)
			var contents := HBoxContainer.new()
			contents.mouse_filter = Control.MOUSE_FILTER_IGNORE
			button.add_child(contents)
			contents.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
			contents.offset_left = 10
			contents.offset_right = -10
			var text := Label.new()
			text.text = entry.title
			text.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
			text.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
			text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			text.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
			text.mouse_filter = Control.MOUSE_FILTER_IGNORE
			contents.add_child(text)
			var badge := Label.new()
			badge.text = "Open" if entry.get("current", false) else ("Build" if not entry.get("ready", true) else "")
			badge.add_theme_font_size_override("font_size", 12)
			badge.add_theme_color_override("font_color", UITheme.MUTED)
			badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
			contents.add_child(badge)
			button.tooltip_text = "%s\n%s\n%s" % [entry.title,
				"Open map" if entry.get("ready", true) else "Build and open", entry.map]
		if row.get_child_count() == 0:
			var empty := Label.new()
			empty.text = "Loading maps…" if _catalog.is_empty() else "No matching maps"
			empty.add_theme_color_override("font_color", UITheme.MUTED)
			row.add_child(empty)
