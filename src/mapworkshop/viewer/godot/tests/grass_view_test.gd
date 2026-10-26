## Integration check: actual map View switches, lazy creation, reuse and rebuild persistence.
extends SceneTree
var failures := 0
func _initialize() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	print("GRASS VIEW ", "PASS " if ok else "FAIL ", label)
	if not ok: failures += 1
func run() -> void:
	var viewer = load("res://scenes/viewer.tscn").instantiate()
	root.add_child(viewer)
	await process_frame
	check(viewer._root != null, "map loaded")
	if viewer._root == null:
		quit(1)
		return
	check(viewer._root.get_node_or_null("GroundCover") == null, "off by default")
	var previous_aa := root.msaa_3d
	viewer._switch_view("grass", true)
	check(root.msaa_3d == Viewport.MSAA_8X, "grass edges use MSAA 8x")
	for i in 20: await process_frame
	var cover = viewer._root.get_node_or_null("GroundCover")
	check(cover != null and cover.visible, "View Grass builds and shows the map blades")
	check(cover.terrain_material.get_shader_parameter("grass_surface_enabled"), "Grass enables distant terrain canopy")
	viewer._switch_view("grass", false)
	check(not cover.terrain_material.get_shader_parameter("grass_surface_enabled"), "Grass off removes distant canopy")
	check(root.msaa_3d == previous_aa, "grass off restores previous AA")
	check(cover != null and not cover.visible and not cover.is_processing(), "off hides grass and stops updates")
	viewer._switch_view("grass", true)
	check(viewer._root.get_node_or_null("GroundCover") == cover and cover.visible, "on reuses existing grass")
	viewer._switch_view("fog", not viewer._views.get("fog", true))
	check(viewer._root.get_node_or_null("GroundCover") != null, "grass survives terrain rebuild")
	for i in 20: await process_frame
	await RenderingServer.frame_post_draw
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--grass-shot="):
			get_root().get_texture().get_image().save_png(arg.trim_prefix("--grass-shot="))
	print("GRASS VIEW RESULT ", failures)
	viewer.free()
	quit(0 if failures == 0 else 1)
