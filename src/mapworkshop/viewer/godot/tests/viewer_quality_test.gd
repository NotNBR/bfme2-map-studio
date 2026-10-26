## Exercise the real viewer's selector, viewport, persistence, grass and reload.
extends SceneTree

var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, label: String) -> void:
	print("VIEWER QUALITY ", "PASS " if ok else "FAIL ", label)
	if not ok: failures += 1

func run() -> void:
	var had_config := FileAccess.file_exists(ViewerQuality.FILE)
	var previous := FileAccess.get_file_as_bytes(ViewerQuality.FILE) if had_config else PackedByteArray()
	var viewer = load("res://scenes/viewer.tscn").instantiate()
	root.add_child(viewer)
	await process_frame
	check(viewer._root != null, "map loaded")
	if viewer._root == null:
		quit(1)
		return
	# The offline scene gives the test a map without a socket companion. Use the real frame and signal connection.
	viewer._frame = Frame.new()
	viewer.add_child(viewer._frame)
	var toolbar: Toolbar = viewer._frame.toolbar
	toolbar.quality_chosen.connect(viewer._choose_quality)
	var map_root = viewer._root
	var camera_transform: Transform3D = viewer._camera.transform
	var layers: Dictionary = viewer._views.duplicate()
	for index in ViewerQuality.NAMES.size():
		var choice: String = ViewerQuality.NAMES[index]
		toolbar._quality.select(index)
		toolbar._quality.item_selected.emit(index)
		var preset: Array = ViewerQuality.PRESETS[choice]
		check(is_equal_approx(root.scaling_3d_scale, preset[0]) and root.msaa_3d == preset[1]
			and root.screen_space_aa == preset[2] and root.anisotropic_filtering_level == preset[3], choice + " applies to viewport")
		check(ViewerQuality.read_choice() == choice, choice + " persists for reopening")
		check(viewer._root == map_root and viewer._camera.transform == camera_transform and viewer._views == layers,
			choice + " preserves map, camera and layers")
	viewer._choose_quality("Medium")
	viewer._switch_view("grass", true)
	check(root.msaa_3d == Viewport.MSAA_2X, "grass respects selected quality")
	viewer._reload(viewer._scene_path, false)
	check(viewer._quality == "Medium" and root.msaa_3d == Viewport.MSAA_2X, "quality survives map reload")
	viewer._set_mode("photo")
	check(is_equal_approx(root.scaling_3d_scale, 0.8), "Photo mode retains quality")
	viewer._set_mode("edit")
	toolbar._show_test_settings()
	check(toolbar._test_controls.has("quality"), "game launch quality is separate")
	toolbar._test_dialog.hide()
	viewer._choose_quality("High")
	for i in 24: await process_frame
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--quality-shot="):
			await RenderingServer.frame_post_draw
			root.get_texture().get_image().save_png(arg.trim_prefix("--quality-shot="))
	if had_config:
		var file := FileAccess.open(ViewerQuality.FILE, FileAccess.WRITE)
		file.store_buffer(previous)
		file.close()
	else:
		DirAccess.remove_absolute(ViewerQuality.FILE)
	viewer.free()
	print("VIEWER QUALITY RESULT ", failures)
	quit(0 if failures == 0 else 1)
