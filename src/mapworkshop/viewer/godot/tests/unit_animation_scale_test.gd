## Real large-map regression: the number of pose samplers must not grow with the army.
extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var viewer = load("res://scenes/viewer.tscn").instantiate()
	root.add_child(viewer)
	await process_frame
	var started := Time.get_ticks_usec()
	viewer._experiments.configure("pike_stomp", true)
	var enable_ms := (Time.get_ticks_usec() - started) / 1000.0
	var animation = viewer._experiments.controllers.pike_stomp
	var frames: Array[float] = []
	for i in 6:
		started = Time.get_ticks_usec()
		animation.sample(i / 30.0)
		frames.append((Time.get_ticks_usec() - started) / 1000.0)
	var counts := {"units": animation.unit_count, "samplers": animation.rigs.size(), "enable_ms": enable_ms, "sample_ms": frames}
	var expected := 0
	var instancers := 0
	for target in viewer._objects_node.find_children("*", "", true, false):
		if target.has_method("find_model_instances"):
			var ids: PackedInt64Array = target.find_model_instances("IUPikeman_SKN")
			expected += ids.size()
			if not ids.is_empty(): instancers += 1
	var ok: bool = animation.error.is_empty() and expected > 15 and animation.unit_count == expected and animation.rigs.size() <= 16 * instancers
	started = Time.get_ticks_usec()
	viewer._experiments.configure("pike_stomp", false)
	counts["disable_ms"] = (Time.get_ticks_usec() - started) / 1000.0
	ok = ok and animation.unit_count == 0 and animation.rigs.is_empty()
	print("ARMY ANIMATION ", JSON.stringify(counts))
	print("ARMY ANIMATION RESULT ", "PASS" if ok else "FAIL")
	viewer.free()
	quit(0 if ok else 1)
