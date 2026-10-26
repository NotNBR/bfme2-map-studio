## Optional preview features discovered from manifests; controllers own their runtime work.
extends Node

signal view_requested(key: String, enabled: bool)
signal packs_changed()

var definitions: Array[Dictionary] = []
var states := {}
var controllers := {}
var objects: Node3D
var suspended := false
var dialog: ConfirmationDialog
var _fields := {}
var pack_paths := PackedStringArray()

func _init() -> void:
	for file in DirAccess.get_files_at("res://scripts/experiments"):
		if not file.ends_with(".json"): continue
		var spec = JSON.parse_string(FileAccess.get_file_as_string("res://scripts/experiments/" + file))
		if not spec is Dictionary or not spec.has_all(["id", "title", "description", "controls"]): continue
		if not spec.has("controller") and not spec.has("view") and not spec.has("pack_prefix"): continue
		if states.has(spec.id): continue
		definitions.append(spec)
		var values := {}
		for field in spec.controls: values[field.id] = field.default
		states[spec.id] = {"enabled": spec.get("default_enabled", false), "values": values}

func matching_packs(spec: Dictionary) -> PackedStringArray:
	var matches := PackedStringArray()
	for path in pack_paths:
		var name := path.replace("\\", "/").trim_suffix("/").get_file().to_lower()
		if name == spec.pack_prefix or name.begins_with(spec.pack_prefix + "-"):
			matches.append(path)
	return matches

func selected_packs() -> PackedStringArray:
	var selected := pack_paths.duplicate()
	for spec in definitions:
		if spec.has("pack_prefix") and not states[spec.id].enabled:
			for path in matching_packs(spec): selected.erase(path)
	return selected

func clear() -> void:
	for controller in controllers.values(): controller.clear()
	objects = null

func bind_map(target: Node3D, paused: bool = false) -> void:
	clear()
	objects = target
	suspended = paused
	for spec in definitions: _apply(spec)

func configure(id: String, enabled: bool, values: Dictionary = {}) -> void:
	for spec in definitions:
		if spec.id != id: continue
		var changed: bool = states[id].enabled != enabled
		states[id].enabled = enabled
		for field in spec.controls:
			var value = values.get(field.id, states[id].values[field.id])
			match field.type:
				"slider", "number": value = clampf(float(value), field.min, field.max)
				"bool": value = bool(value)
				"choice":
					if not value in field.options: value = field.default
			states[id].values[field.id] = value
		_apply(spec)
		if changed and spec.has("pack_prefix"): packs_changed.emit()

func _apply(spec: Dictionary) -> void:
	if spec.has("pack_prefix"): return
	if spec.has("view"):
		view_requested.emit(spec.view, states[spec.id].enabled)
		return
	if controllers.has(spec.id): controllers[spec.id].clear()
	if not states[spec.id].enabled or objects == null or suspended: return
	if not controllers.has(spec.id):
		var controller = load(spec.controller).new()
		add_child(controller)
		controllers[spec.id] = controller
	controllers[spec.id].enable(objects, states[spec.id].values)
	if not controllers[spec.id].error.is_empty(): states[spec.id].enabled = false

func sample(time: float) -> void:
	if suspended: return
	for id in controllers:
		if states[id].enabled: controllers[id].sample(time)

func open() -> void:
	if dialog != null: dialog.free()
	_fields.clear()
	dialog = ConfirmationDialog.new()
	dialog.title = "Experimental"
	dialog.ok_button_text = "Apply"
	add_child(dialog)
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(520, 350)
	dialog.add_child(scroll)
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 12)
	scroll.add_child(list)
	for spec in definitions:
		var enabled := CheckBox.new()
		enabled.text = spec.title
		enabled.button_pressed = states[spec.id].enabled
		var missing_pack: bool = spec.has("pack_prefix") and matching_packs(spec).is_empty()
		if missing_pack:
			enabled.button_pressed = false
			enabled.disabled = true
		list.add_child(enabled)
		var description := Label.new()
		description.text = spec.description
		if missing_pack: description.text += "\nNo BFME2 HD pack is configured. Add its folder to asset_packs in local/config.toml."
		description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		list.add_child(description)
		if controllers.has(spec.id) and not controllers[spec.id].error.is_empty():
			var error_label := Label.new()
			error_label.text = controllers[spec.id].error
			list.add_child(error_label)
		var fields := {}
		var settings := VBoxContainer.new()
		settings.visible = enabled.button_pressed
		list.add_child(settings)
		enabled.toggled.connect(func(on: bool) -> void: settings.visible = on)
		for field in spec.controls:
			var row := HBoxContainer.new()
			settings.add_child(row)
			var label := Label.new()
			label.text = field.label
			label.custom_minimum_size.x = 220
			row.add_child(label)
			var input: Control
			var value = states[spec.id].values[field.id]
			match field.type:
				"slider", "number":
					var number := SpinBox.new()
					number.min_value = field.min
					number.max_value = field.max
					number.step = field.step
					number.value = value
					input = number
					if field.type == "slider":
						var slider := HSlider.new()
						slider.custom_minimum_size.x = 130
						number.share(slider)
						row.add_child(slider)
				"bool":
					input = CheckBox.new()
					input.button_pressed = value
				"choice":
					input = OptionButton.new()
					for option in field.options: input.add_item(str(option))
					input.select(field.options.find(value))
				_: continue
			row.add_child(input)
			fields[field.id] = input
		_fields[spec.id] = {"enabled": enabled, "fields": fields, "settings": settings}
		list.add_child(HSeparator.new())
	dialog.confirmed.connect(_commit_form)
	dialog.popup_centered()

func _commit_form() -> void:
	for spec in definitions:
		var values := {}
		for field in spec.controls:
			var input = _fields[spec.id].fields[field.id]
			match field.type:
				"slider", "number": values[field.id] = input.value
				"bool": values[field.id] = input.button_pressed
				"choice": values[field.id] = field.options[input.selected]
		configure(spec.id, _fields[spec.id].enabled.button_pressed, values)
	# Keep failures visible instead of silently closing after an unsupported runtime.
	for controller in controllers.values():
		if not controller.error.is_empty(): call_deferred("open")
