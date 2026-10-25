## The toolbar across the top (docs/viewer.md, "The toolbar"): Map (the map projects,
## the game's maps, Open project folder, Browse...), Properties, Build with its chip, Test In-Game and what it starts,
## Preview (the weather and the sun, its button showing the choice), View (the layers and overlays; both menus stay
## open while their entries are switched), and at the right Top view, Reset view, Screenshot and the frame rate with
## its cap (a menu). The lists come from the companion's menu message.
class_name Toolbar
extends PanelContainer

## Another map: its .map file, as the menu lists it.
signal map_chosen(path: String)
## A command for the companion: "open_folder", "build", "test".
signal command(name: String)
## Test In-Game's choice changed.
signal test_game_chosen(choice: String)
signal test_settings_chosen(settings: Dictionary)
## A View entry switched.
signal view_switched(key: String, on: bool)
## A Preview entry chosen: "weather" or "sun" and its value.
signal preview_chosen(option: String, value: String)
## Top view, Reset view or Screenshot.
signal action(name: String)

const TEST_GAMES := {"original": "Original game", "openbfme": "OpenBFME (Godot)"}
const FPS_LIMITS := ["30", "60", "90", "120", "144", "vsync", "unlimited"]    # godot_viewer.FPS_LIMITS; 60 at the start

var _map: MenuButton
var _maps := []               # the Map menu's .map paths, by item id
var _build_chip: Label
var _test_game: OptionButton
var _test_settings := {}
var _test_dialog: ConfirmationDialog
var _test_controls := {}
var _view: MenuButton
var _views := []              # [key, title] of the View menu's entries, by item id
var _preview: MenuButton
var _previews := []           # [option, value] of the Preview menu's entries, by item id
var _fps: MenuButton
var _fps_limit := "60"
var _build := {}              # the build chip's last message


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	add_child(row)
	_map = MenuButton.new()
	_map.text = "Map"
	_map.flat = false
	_map.get_popup().id_pressed.connect(_on_map)
	_map.get_popup().max_size = Vector2i(520, 700)
	row.add_child(_map)
	_add(row, "Properties", "The map's map-wide settings: a project's to edit (Save builds it), a game map's to read",
		func() -> void: command.emit("properties"))
	_add(row, "Build", "Build the project again (it reloads when it is done)", func() -> void: command.emit("build"))
	_build_chip = Label.new()
	_build_chip.add_theme_color_override("font_color", UITheme.MUTED)
	row.add_child(_build_chip)
	row.add_child(VSeparator.new())
	_add(row, "Test In-Game", "Start a skirmish on the map, as mw play does", func() -> void: command.emit("test"))
	_test_game = OptionButton.new()
	_test_game.tooltip_text = "What Test In-Game starts"
	_test_game.focus_mode = Control.FOCUS_NONE
	for key in TEST_GAMES:
		_test_game.add_item(TEST_GAMES[key])
		_test_game.set_item_metadata(_test_game.item_count - 1, key)
	_test_game.item_selected.connect(func(index: int) -> void: test_game_chosen.emit(_test_game.get_item_metadata(index)))
	row.add_child(_test_game)
	_add(row, "⚙", "Quick settings for Test In-Game", _show_test_settings)
	row.add_child(VSeparator.new())
	_preview = MenuButton.new()
	_preview.text = "Preview"
	_preview.tooltip_text = "Show the map with another weather or sun, without changing it"
	_preview.get_popup().hide_on_checkable_item_selection = false
	_preview.get_popup().id_pressed.connect(_on_preview)
	row.add_child(_preview)
	_view = MenuButton.new()
	_view.text = "View"
	_view.get_popup().hide_on_checkable_item_selection = false
	_view.get_popup().id_pressed.connect(_on_view)
	row.add_child(_view)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	_add(row, "Top view", "Look straight down, north up (T)", func() -> void: action.emit("top"))
	_add(row, "Reset view", "The whole map (Space)", func() -> void: action.emit("reset"))
	_add(row, "Screenshot", "Save the view into the renders folder (P)", func() -> void: action.emit("screenshot"))
	_fps = MenuButton.new()
	_fps.tooltip_text = "The frame rate and its cap: click to change the cap"
	_fps.add_theme_color_override("font_color", UITheme.MUTED)
	_fps.custom_minimum_size = Vector2(90, 0)
	var caps := _fps.get_popup()
	caps.add_separator("Frame rate cap")
	for i in FPS_LIMITS.size():
		var v: String = FPS_LIMITS[i]
		caps.add_radio_check_item({"vsync": "VSync (monitor rate)", "unlimited": "Unlimited"}.get(v, "%s fps" % v), i)
	caps.id_pressed.connect(func(id: int) -> void: set_fps_limit(FPS_LIMITS[id]))
	row.add_child(_fps)
	set_fps_limit("60")


func _add(row: HBoxContainer, text: String, tip: String, pressed: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tip
	b.focus_mode = Control.FOCUS_NONE
	if pressed.is_valid():
		b.pressed.connect(pressed)
	row.add_child(b)
	return b


func _show_test_settings() -> void:
	if _test_dialog != null:
		_test_dialog.queue_free()
	_test_controls.clear()
	_test_dialog = ConfirmationDialog.new()
	_test_dialog.title = "Test In-Game settings"
	_test_dialog.ok_button_text = "Save"
	add_child(_test_dialog)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation",10)
	_test_dialog.add_child(box)
	var note := Label.new()
	note.text = "For OpenBFME (Godot) test rounds"
	box.add_child(note)
	for spec in [["resolution","Resolution",["saved","1280x720","1920x1080","2560x1440","3840x2160"]],
	             ["window_mode","Window mode",["saved","windowed","borderless"]]]:
		var row := HBoxContainer.new()
		var label := Label.new()
		label.text = spec[1]
		label.custom_minimum_size.x = 130
		row.add_child(label)
		var choice := OptionButton.new()
		choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for value in spec[2]:
			choice.add_item({"saved":"Saved game setting","windowed":"Windowed","borderless":"Borderless fullscreen"}.get(value,value))
			choice.set_item_metadata(choice.item_count-1,value)
			if value == _test_settings.get(spec[0],"saved"): choice.select(choice.item_count-1)
		row.add_child(choice)
		box.add_child(row)
		_test_controls[spec[0]] = choice
	for spec in [["grass","Grass",true],["ground_detail","Ground detail",true],["fog","Fog of war",false]]:
		var check := CheckBox.new()
		check.text = spec[1]
		check.button_pressed = _test_settings.get(spec[0],spec[2])
		box.add_child(check)
		_test_controls[spec[0]] = check
	var hint := Label.new()
	hint.text = "Applies next launch. Fullscreen uses your monitor's resolution."
	hint.add_theme_font_size_override("font_size",12)
	box.add_child(hint)
	_test_dialog.confirmed.connect(_save_test_settings)
	_test_dialog.popup_centered(Vector2i(440,320))


func _save_test_settings() -> void:
	var settings := {}
	for key in _test_controls:
		var control = _test_controls[key]
		settings[key] = control.get_item_metadata(control.selected) if control is OptionButton else control.button_pressed
	_test_settings = settings
	test_settings_chosen.emit(settings)


func _process(_delta: float) -> void:
	var cap := "" if _fps_limit in ["vsync", "unlimited"] else " / %s" % _fps_limit
	_fps.text = "%d fps%s" % [Engine.get_frames_per_second(), cap]
	_show_build()


## The frame rate cap: a number of frames a second, "vsync" (the monitor's rate) or "unlimited".
func set_fps_limit(limit: String) -> void:
	_fps_limit = limit
	Engine.max_fps = int(limit) if limit.is_valid_int() else 0
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_ENABLED if limit == "vsync" else DisplayServer.VSYNC_DISABLED)
	for i in FPS_LIMITS.size():
		_fps.get_popup().set_item_checked(_fps.get_popup().get_item_index(i), FPS_LIMITS[i] == limit)


## The companion's menu message: the Map menu's entries and Test In-Game's choice.
func set_menu(menu: Dictionary) -> void:
	_test_settings = menu.get("test_settings",{})
	_map.text = "%s  ▾" % menu.title
	var popup := _map.get_popup()
	popup.clear()
	_maps.clear()
	for group in [["Your maps", menu.projects], ["The game's maps", menu.stock]]:
		if not (group[1] as Array).is_empty():
			popup.add_separator(group[0])
		for entry in group[1]:
			popup.add_radio_check_item(entry.title, _maps.size())
			popup.set_item_checked(popup.item_count - 1, entry.current)
			_maps.append(entry.map)
	popup.add_separator()
	popup.add_item("Open project folder", -2)
	popup.set_item_disabled(popup.item_count - 1, not menu.project)
	popup.add_item("Export placement plan", -4)
	popup.add_item("Browse...", -3)
	for index in _test_game.item_count:
		if _test_game.get_item_metadata(index) == menu.test_game:
			_test_game.select(index)
	_set_preview(menu.preview)


## Preview's entries ({weather: [[value, title]], sun: [...], current: {weather, sun}, label}) and the button's text.
func _set_preview(preview: Dictionary) -> void:
	var popup := _preview.get_popup()
	popup.clear()
	_previews.clear()
	popup.add_separator("Preview only: these do not change the map")
	for option in [["weather", "Weather"], ["sun", "Sun"]]:
		popup.add_separator(option[1])
		for entry in preview[option[0]]:
			popup.add_radio_check_item(entry[1], _previews.size())
			popup.set_item_checked(popup.item_count - 1, preview.current[option[0]] == entry[0])
			_previews.append([option[0], entry[0]])
	_preview.text = "%s  ▾" % preview.label


func _on_preview(id: int) -> void:
	var popup := _preview.get_popup()
	for i in popup.item_count:                     # the chosen one checked at once among its option's entries
		var other := popup.get_item_id(i)
		if popup.is_item_radio_checkable(i) and _previews[other][0] == _previews[id][0]:
			popup.set_item_checked(i, other == id)
	preview_chosen.emit(_previews[id][0], _previews[id][1])


func _on_map(id: int) -> void:
	if id == -2:
		command.emit("open_folder")
	elif id == -3:
		command.emit("browse")
	elif id == -4:
		command.emit("placement")
	elif id >= 0 and id < _maps.size():
		map_chosen.emit(_maps[id])


## The View menu: [key, title, on] entries.
func set_views(entries: Array) -> void:
	var popup := _view.get_popup()
	popup.clear()
	_views = entries.duplicate(true)
	for i in entries.size():
		popup.add_check_item(entries[i][1], i)
		popup.set_item_checked(i, entries[i][2])


func set_view(key: String, on: bool) -> void:
	for i in _views.size():
		if _views[i][0] == key:
			_views[i][2] = on
			_view.get_popup().set_item_checked(i, on)


func _on_view(id: int) -> void:
	var on := not _view.get_popup().is_item_checked(id)
	_view.get_popup().set_item_checked(id, on)
	_views[id][2] = on
	view_switched.emit(_views[id][0], on)


## The build chip: building with its latest line, or how long ago the last build ended and how long it took.
func set_build(running: bool, line, outcome) -> void:
	_build = {"running": running, "line": line, "outcome": outcome}


func _show_build() -> void:
	if _build.is_empty():
		return
	var outcome = _build.outcome
	if _build.running:
		_build_chip.text = "building: %s" % ("" if _build.line == null else String(_build.line).left(48))
		_build_chip.add_theme_color_override("font_color", UITheme.MUTED)
	elif outcome != null:
		var ago := int(Time.get_unix_time_from_system() - float(outcome.ended))
		var when := "%ds ago" % ago if ago < 120 else "%d min ago" % (ago / 60)
		_build_chip.text = "%s %s (%.0f s)" % ["built" if outcome.ok else "build failed", when, float(outcome.seconds)]
		_build_chip.add_theme_color_override("font_color", UITheme.GOOD if outcome.ok else UITheme.BAD)
	else:
		_build_chip.text = ""
