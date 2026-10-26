## The toolbar across the top (docs/viewer.md, "The toolbar"): Open Map (MapPicker), Map (Properties, the project
## folder, the placement plan), Build with its chip, Play in game and what it starts, then the view switches in three
## menus that stay open while their entries are switched: Layers (the map's own content), Overlays (helpers drawn over
## it) and Atmosphere (Preview's weather and sun, its button showing the choice, and the effects); at the right Top
## view, Reset view, Screenshot and the frame rate with its cap (a menu). The lists come from the companion's menu
## message.
class_name Toolbar
extends PanelContainer

## Another map: its .map file, as the menu lists it.
signal map_chosen(path: String)
## A command for the companion: "properties", "open_folder", "placement", "build", "test".
signal command(name: String)
## Play in game's choice changed.
signal test_game_chosen(choice: String)
signal test_settings_chosen(settings: Dictionary)
signal quality_chosen(choice: String)
signal experiments_requested()
## A Layers, Overlays or Atmosphere switch.
signal view_switched(key: String, on: bool)
## A Preview entry (Atmosphere) chosen: "weather" or "sun" and its value.
signal preview_chosen(option: String, value: String)
## Top view, Reset view or Screenshot.
signal action(name: String)

const TEST_GAMES := {"original": "Original game", "openbfme": "OpenBFME (Godot)"}
const FPS_LIMITS := ["30", "60", "90", "120", "144", "vsync", "unlimited"]    # godot_viewer.FPS_LIMITS; 60 at the start
## The view menus: [group, title, tooltip]; each switch names its group (viewer.gd VIEWS).
const MENUS := [["layers", "Layers", "The map's own content: objects, water, roads, ground"],
	["overlays", "Overlays", "Helpers drawn over the map; never in the game"],
	["atmosphere", "Atmosphere", "Weather, sun and effects, to look at the map another way without changing it"]]
const MAP_ITEMS := [["properties", "Properties…"], ["open_folder", "Open project folder"],
	["placement", "Export placement plan"]]
const PREVIEW_ID := 1000      # Atmosphere's Preview entries: PREVIEW_ID + their index in _previews

var _map: Button
var picker: MapPicker
var _map_menu: MenuButton
var _map_controls: Array[BaseButton] = []
var _build_chip: Label
var _test_game: OptionButton
var _test_settings := {}
var _test_dialog: ConfirmationDialog
var _test_controls := {}
var _menus := {}              # group -> its MenuButton
var _views := []              # [key, title, on, group, section] of the switches, by item id
var _preview := {}            # the companion's Preview choices and the current one
var _previews := []           # [option, value, title] of Atmosphere's Preview entries
var _fps: MenuButton
var _quality: OptionButton
var _fps_limit := "60"
var _build := {}              # the build chip's last message


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	add_child(row)
	_map = _add(row, "Open Map", "Choose a custom or original map", func() -> void: picker.open())
	picker = MapPicker.new()
	add_child(picker)
	picker.map_chosen.connect(func(path: String) -> void: map_chosen.emit(path))
	picker.command.connect(func(name: String) -> void: command.emit(name))
	_map_menu = MenuButton.new()
	_map_menu.text = "Map  ▾"
	_map_menu.flat = false
	_map_menu.tooltip_text = "The map shown: its map-wide settings, its project folder, its placement plan"
	var map_items := _map_menu.get_popup()
	for i in MAP_ITEMS.size():
		map_items.add_item(MAP_ITEMS[i][1], i)
	map_items.set_item_tooltip(0, "The map's map-wide settings: a project's to edit (Save builds it), a game map's to read")
	map_items.set_item_tooltip(2, "Starts, buildings, lairs and capture-flag footprints of the map shown")
	map_items.id_pressed.connect(func(id: int) -> void: command.emit(MAP_ITEMS[id][0]))
	row.add_child(_map_menu)
	_add(row, "Build", "Build the project again (it reloads when it is done)", func() -> void: command.emit("build"))
	_build_chip = Label.new()
	_build_chip.add_theme_color_override("font_color", UITheme.MUTED)
	row.add_child(_build_chip)
	row.add_child(VSeparator.new())
	_add(row, "Play in game", "Start a skirmish on the map in the game, as mw play does", func() -> void: command.emit("test"))
	_test_game = OptionButton.new()
	_test_game.tooltip_text = "What Play in game starts"
	_test_game.focus_mode = Control.FOCUS_NONE
	for key in TEST_GAMES:
		_test_game.add_item(TEST_GAMES[key])
		_test_game.set_item_metadata(_test_game.item_count - 1, key)
	_test_game.item_selected.connect(func(index: int) -> void: test_game_chosen.emit(_test_game.get_item_metadata(index)))
	row.add_child(_test_game)
	_add(row, "⚙", "Quick settings for Play in game", _show_test_settings)
	row.add_child(VSeparator.new())
	for spec in MENUS:
		var menu := MenuButton.new()
		menu.text = "%s  ▾" % spec[1]
		menu.flat = false
		menu.tooltip_text = spec[2]
		menu.get_popup().hide_on_checkable_item_selection = false
		menu.get_popup().id_pressed.connect(_on_menu.bind(String(spec[0])))
		row.add_child(menu)
		_menus[spec[0]] = menu
	_add(row, "Experimental","Choose optional preview features and adjust their settings", func() -> void: experiments_requested.emit())
	_quality = OptionButton.new()
	_quality.tooltip_text = "Viewer graphics quality: render resolution, anti-aliasing and texture filtering. Applies immediately; map layers stay as chosen."
	_quality.focus_mode = Control.FOCUS_NONE
	for quality in ViewerQuality.NAMES:
		_quality.add_item("Quality: " + quality)
	_quality.item_selected.connect(func(index: int) -> void: quality_chosen.emit(ViewerQuality.NAMES[index]))
	row.add_child(_quality)
	set_quality(ViewerQuality.DEFAULT)
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
	for control in row.get_children():
		if control is BaseButton and control not in [_map, _fps, _quality]:
			_map_controls.append(control)


func set_quality(choice: String) -> void:
	_quality.select(maxi(0, ViewerQuality.NAMES.find(choice)))


func set_map_loaded(loaded: bool) -> void:
	for control in _map_controls:
		control.disabled = not loaded


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
	_test_dialog.title = "Play in game settings"
	_test_dialog.ok_button_text = "Save"
	add_child(_test_dialog)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation",10)
	_test_dialog.add_child(box)
	var note := Label.new()
	note.text = "For OpenBFME (Godot) test rounds"
	box.add_child(note)
	for spec in [["resolution","Resolution",["saved","1280x720","1920x1080","2560x1440","3840x2160"]],
	             ["window_mode","Window mode",["saved","windowed","borderless"]],
	             ["quality","Graphics quality",["saved","VeryLow","Low","Medium","High","UltraHigh"]]]:
		var row := HBoxContainer.new()
		var label := Label.new()
		label.text = spec[1]
		label.custom_minimum_size.x = 130
		row.add_child(label)
		var choice := OptionButton.new()
		choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		for value in spec[2]:
			choice.add_item({"saved":"Saved game setting","windowed":"Windowed","borderless":"Borderless fullscreen",
				"VeryLow":"Very Low","UltraHigh":"Ultra High"}.get(value,value))
			choice.set_item_metadata(choice.item_count-1,value)
			if value == _test_settings.get(spec[0],"saved"): choice.select(choice.item_count-1)
		row.add_child(choice)
		box.add_child(row)
		_test_controls[spec[0]] = choice
		if spec[0] == "quality":
			choice.tooltip_text = "OpenBFME's graphics preset: texture quality, particle limits and health bars. Other detail controls are not implemented by the engine yet."
	for spec in [["grass","Grass",true],["fog","Fog of war",false]]:
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
	_test_dialog.popup_centered(Vector2i(440,360))


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


## The companion's catalog for Open Map, the Map menu and Play in game's choice.
func set_menu(menu: Dictionary) -> void:
	_test_settings = menu.get("test_settings",{})
	_map.tooltip_text = "Choose a map (current: %s)" % menu.title
	picker.set_catalog(menu)
	var map_items := _map_menu.get_popup()
	map_items.set_item_disabled(map_items.get_item_index(1), not menu.get("project", false))
	map_items.set_item_disabled(map_items.get_item_index(2), not menu.get("loaded", false))
	for index in _test_game.item_count:
		if _test_game.get_item_metadata(index) == menu.test_game:
			_test_game.select(index)
	_set_preview(menu.preview)


## Preview's entries ({weather: [[value, title]], sun: [...], current: {weather, sun}, label}), at the top of
## Atmosphere; its button names the choice when it is not the map's own.
func _set_preview(preview: Dictionary) -> void:
	_preview = preview
	_previews.clear()
	for option in ["weather", "sun"]:
		for entry in preview[option]:
			_previews.append([option, entry[0], entry[1]])
	var own: bool = preview.current.weather == "map" and preview.current.sun == "own"
	_menus.atmosphere.text = "Atmosphere  ▾" if own else "Atmosphere: %s  ▾" % preview.label
	_fill_menu("atmosphere")


## The switches: [key, title, on, group (MENUS), section (a titled separator above it; "" for none)] entries.
func set_views(entries: Array) -> void:
	_views = entries.duplicate(true)
	for group in _menus:
		_fill_menu(group)


## A view menu's entries: Atmosphere's Preview entries first, then the group's switches under their sections.
func _fill_menu(group: String) -> void:
	var popup := (_menus[group] as MenuButton).get_popup()
	popup.clear()
	if group == "atmosphere" and not _previews.is_empty():
		popup.add_separator("Preview only: the map does not change")
		var option := ""
		for i in _previews.size():
			var p: Array = _previews[i]
			if p[0] != option:
				option = p[0]
				popup.add_separator({"weather": "Weather", "sun": "Sun"}[option])
			popup.add_radio_check_item(p[2], PREVIEW_ID + i)
			popup.set_item_checked(popup.item_count - 1, _preview.current[p[0]] == p[1])
	var section := ""
	for i in _views.size():
		var v: Array = _views[i]
		if v[3] != group:
			continue
		if v[4] != section:
			section = v[4]
			popup.add_separator(section)
		popup.add_check_item(v[1], i)
		popup.set_item_checked(popup.item_count - 1, v[2])


func set_view(key: String, on: bool) -> void:
	for i in _views.size():
		if _views[i][0] == key:
			_views[i][2] = on
			var popup := (_menus[_views[i][3]] as MenuButton).get_popup()
			var index := popup.get_item_index(i)
			if index >= 0:
				popup.set_item_checked(index, on)


func _on_menu(id: int, group: String) -> void:
	var popup := (_menus[group] as MenuButton).get_popup()
	if id >= PREVIEW_ID:
		var chosen: Array = _previews[id - PREVIEW_ID]
		for i in popup.item_count:                 # the chosen one checked at once among its option's entries
			var other := popup.get_item_id(i)
			if not popup.is_item_separator(i) and other >= PREVIEW_ID and _previews[other - PREVIEW_ID][0] == chosen[0]:
				popup.set_item_checked(i, other == id)
		preview_chosen.emit(chosen[0], chosen[1])
		return
	var index := popup.get_item_index(id)
	var on := not popup.is_item_checked(index)
	popup.set_item_checked(index, on)
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
