## Exercise the real blank viewer, modal, failed selection and first map load.
extends SceneTree

var viewer: Node3D
var failures := 0
var capture := ""


func _initialize() -> void:
	call_deferred("_run")


func check(ok: bool, message: String) -> void:
	if not ok:
		failures += 1
		print("PICKER FAIL: ", message)


func until(predicate: Callable) -> bool:
	var deadline := Time.get_ticks_msec() + 60000
	while not predicate.call() and Time.get_ticks_msec() < deadline:
		await process_frame
	return predicate.call()


func shot(name: String) -> void:
	if capture.is_empty():
		return
	for i in 12:
		await process_frame
	await RenderingServer.frame_post_draw
	root.get_texture().get_image().save_png(capture.path_join(name + ".png"))


func _run() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--capture="):
			capture = arg.substr(10)
	viewer = load("res://scripts/viewer.gd").new()
	root.add_child(viewer)
	var picker: MapPicker = viewer._frame.toolbar.picker
	check(await until(func() -> bool: return not picker._catalog.is_empty()), "catalog received")
	check(viewer._orbit == null and viewer._root == null, "startup has no map or camera controller")
	check(not viewer._frame.bar._edit.visible and not viewer._frame.marks.visible, "map controls hidden")
	check(viewer._frame.bar.visible and viewer._frame.bar._status.visible, "status line shown without a map")
	check(picker.visible, "modal opens at startup")
	check(picker._columns.get_child_count() == 2, "two map columns")
	await shot("empty-modal")
	var original_size := picker.size
	var original_position := picker.position
	# Hold the loading state without sending a request, so layout has time to settle.
	picker.set_block_signals(true)
	picker._choose({"title": "A long custom map name while building", "map": "layout-test.map", "ready": false})
	for i in 12:
		await process_frame
	check(picker.size == original_size and picker.position == original_position, "loading preserves modal bounds")
	await shot("loading-modal")
	picker.failed("A map could not be built. ".repeat(30))
	for i in 12:
		await process_frame
	check(picker.size == original_size and picker.position == original_position, "long error preserves modal bounds")
	await shot("error-modal")
	picker.set_block_signals(false)
	picker.loaded()
	picker.open()
	picker.hide()
	check(viewer._orbit == null, "closing leaves Studio empty")
	await shot("empty-studio")
	viewer._frame.toolbar._map.pressed.emit()
	check(picker.visible, "Open Map reopens modal")
	picker._choose({"title": "Missing map", "map": "missing-picker-test.map"})
	check(await until(func() -> bool: return not picker._busy), "failed selection recovers")
	check(picker.visible and not picker._status.text.is_empty(), "error stays in modal")
	check(viewer._orbit == null, "failed selection leaves Studio empty")
	picker._search.text = "Blend Lab"
	picker._search.text_changed.emit(picker._search.text)
	var row: VBoxContainer = picker._columns.get_child(0).get_child(1).get_child(0)
	check(row.get_child_count() == 1 and row.get_child(0) is Button, "search finds custom map")
	if row.get_child_count() != 1 or not row.get_child(0) is Button:
		quit(1)
		return
	row.get_child(0).pressed.emit()
	for i in 4:
		await process_frame
	check(viewer._orbit == null and not picker._busy, "selecting does not open or build")
	check(not picker.get_ok_button().disabled, "selection enables Open Map")
	await shot("selected-map")
	picker.get_ok_button().pressed.emit()
	check(await until(func() -> bool: return viewer._orbit != null), "first map loads")
	check(not picker.visible, "successful load closes modal")
	check(viewer._frame.bar._edit.visible and viewer._frame.marks.visible, "map controls enabled")
	check(viewer._scene.map == "map mp blend lab", "chosen map is shown")
	await shot("loaded-map")
	viewer._frame.toolbar._map.pressed.emit()
	picker._search.text = "Evendim"
	picker._search.text_changed.emit(picker._search.text)
	var originals: VBoxContainer = picker._columns.get_child(1).get_child(1).get_child(0)
	check(originals.get_child_count() == 1 and originals.get_child(0) is Button, "search finds original map in right column")
	if originals.get_child_count() == 1 and originals.get_child(0) is Button:
		originals.get_child(0).pressed.emit()
		check(viewer._scene.map == "map mp blend lab", "selecting original keeps current map")
		picker.get_ok_button().pressed.emit()
		check(await until(func() -> bool: return not picker.visible), "original map loads and closes modal")
		check(String(viewer._scene.map_path).ends_with("map mp evendim.map"), "original map replaces custom map")
	print("PICKER RESULT: %s (%d failed)" % ["PASS" if failures == 0 else "FAIL", failures])
	quit(0 if failures == 0 else 1)
