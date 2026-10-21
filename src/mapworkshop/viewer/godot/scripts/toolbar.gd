## The toolbar across the top, as the studio viewer has it (docs/viewer.md, "The toolbar"): Map (the map projects, the
## game's maps, Open project folder), Properties, Build with its chip, Test In-Game and what it starts, Preview, View
## (the layers and overlays, check marks that keep the menu open), and at the right Top view, Reset view, Screenshot
## and the frame rate. The lists come from the companion's menu message.
class_name Toolbar
extends PanelContainer

## Another map: its .map file, as the menu lists it.
signal map_chosen(path: String)
## A command for the companion: "open_folder", "build", "test".
signal command(name: String)
## Test In-Game's choice changed.
signal test_game_chosen(choice: String)
## A View entry switched.
signal view_switched(key: String, on: bool)
## Top view, Reset view or Screenshot.
signal action(name: String)

const TEST_GAMES := {"original": "Original game", "openbfme": "OpenBFME (Godot)"}

var _map: MenuButton
var _maps := []               # the Map menu's .map paths, by item id
var _build_chip: Label
var _test_game: OptionButton
var _view: MenuButton
var _views := []              # [key, title] of the View menu's entries, by item id
var _fps: Label
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
	_add(row, "Properties", "The map's map-wide settings: not in the Godot viewer yet", Callable()).disabled = true
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
	row.add_child(VSeparator.new())
	var preview := MenuButton.new()
	preview.text = "Preview"
	preview.tooltip_text = "Detail, weather and sun: not in the Godot viewer yet"
	preview.disabled = true
	row.add_child(preview)
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
	_fps = Label.new()
	_fps.add_theme_color_override("font_color", UITheme.MUTED)
	_fps.custom_minimum_size = Vector2(60, 0)
	_fps.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(_fps)


func _add(row: HBoxContainer, text: String, tip: String, pressed: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tip
	b.focus_mode = Control.FOCUS_NONE
	if pressed.is_valid():
		b.pressed.connect(pressed)
	row.add_child(b)
	return b


func _process(_delta: float) -> void:
	_fps.text = "%d fps" % Engine.get_frames_per_second()
	_show_build()


## The companion's menu message: the Map menu's entries and Test In-Game's choice.
func set_menu(menu: Dictionary) -> void:
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
	for index in _test_game.item_count:
		if _test_game.get_item_metadata(index) == menu.test_game:
			_test_game.select(index)


func _on_map(id: int) -> void:
	if id == -2:
		command.emit("open_folder")
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
