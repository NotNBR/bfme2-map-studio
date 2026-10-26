## Exercise the real Studio toggle on Shadow Lab's fifteen Uruk pikemen.
extends SceneTree
var failures := 0

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, label: String) -> void:
	print("UNIT ANIMATION ", "PASS " if ok else "FAIL ", label)
	if not ok: failures += 1

func run() -> void:
	var viewer = load("res://scenes/viewer.tscn").instantiate()
	root.add_child(viewer)
	await process_frame
	viewer._experiments.open()
	check(not viewer._experiments._fields.pike_stomp.settings.visible, "disabled feature settings start hidden")
	viewer._experiments.dialog.hide()
	viewer._experiments.configure("pike_stomp", true)
	check(viewer._experiments.controllers.pike_stomp.error.is_empty(), "runtime supports animation")
	check(viewer._experiments.controllers.pike_stomp.unit_count == 15, "all fifteen placed Uruks attached")
	var offsets: Array = viewer._experiments.controllers.pike_stomp.offsets
	check(offsets.size() == 15 and offsets[0] != offsets[1], "near-synchronous timing offsets")
	check(viewer._experiments.controllers.pike_stomp.duration == 1.4, "shortened rest")
	viewer._experiments.open()
	var form = viewer._experiments._fields.pike_stomp
	check(form.settings.visible, "enabled feature settings shown")
	form.enabled.button_pressed = false
	check(not form.settings.visible, "unchecking collapses settings immediately")
	form.enabled.button_pressed = true
	check(form.settings.visible, "checking reveals settings immediately")
	check(viewer._experiments._fields.has("grass"), "terrain enhancements discovered in Experiments")
	form.fields.phase_spread.value = 0.2
	form.fields.knee_dip.value = 0.25
	form.fields.speed.value = 0.8
	viewer._experiments._commit_form()
	check(is_equal_approx(viewer._experiments.controllers.pike_stomp.offsets.back(), 0.2), "form applies timing slider")
	check(is_equal_approx(viewer._experiments.controllers.pike_stomp.speed, 0.8), "form applies numeric speed")
	viewer._experiments.dialog.hide()
	viewer._experiments.configure("grass", true)
	check(viewer._views.grass and viewer._root.get_node_or_null("GroundCover") != null, "grass experiment creates preview blades")
	viewer._experiments.configure("grass", false)
	check(not viewer._views.grass, "terrain experiments disable")
	viewer._advance(0.5)
	var first_rig = viewer._experiments.controllers.pike_stomp.rigs[0]
	viewer._set_mode("photo")
	viewer._advance(0.6)
	check(viewer._mode == "photo" and viewer._experiments.controllers.pike_stomp.rigs[0] == first_rig, "Photo mode keeps the animation attached")
	viewer._set_mode("edit")
	check(viewer._mode == "edit" and viewer._experiments.controllers.pike_stomp.rigs[0] == first_rig, "Edit mode keeps the animation attached")
	viewer._switch_view("animate", false)
	var paused: float = viewer._clock
	await process_frame
	await process_frame
	check(viewer._clock == paused, "Animate pauses the loop")
	viewer._experiments.configure("pike_stomp", false)
	check(viewer._experiments.controllers.pike_stomp.rigs.is_empty(), "disable releases every rig")
	viewer._experiments.configure("pike_stomp", true)
	viewer._reload(viewer._scene_path, false)
	check(viewer._experiments.states.pike_stomp.enabled and viewer._experiments.controllers.pike_stomp.rigs.size() == 15, "reload reattaches once")
	viewer.free()
	print("UNIT ANIMATION RESULT ", failures)
	quit(0 if failures == 0 else 1)
