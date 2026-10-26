## Studio's runtime contract. Python verifies payload hashes before assembly;
## Godot checks the loaded extension's methods, rather than trusting a DLL name.
class_name EngineRuntime
extends RefCounted

static func missing() -> PackedStringArray:
	var problems := PackedStringArray()
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://studio_runtime.json"))
	if not parsed is Dictionary or parsed.get("adapter_api", 0) != 1:
		problems.append("a compatible Studio runtime manifest (run mw engine check)")
		return problems
	var methods: Dictionary = parsed.get("methods", {})
	for library_class in methods:
		if not ClassDB.class_exists(library_class):
			problems.append(library_class)
			continue
		for method in methods[library_class]:
			if not ClassDB.class_has_method(library_class, method):
				problems.append("%s.%s" % [library_class, method])
	var resources: Dictionary = parsed.get("groups", {}).get("viewer", {})
	for name in resources:
		if String(name).ends_with(".gdshader"):
			var path := "res://" + String(name)
			if not ResourceLoader.exists(path) or load(path) == null:
				problems.append(path)
	return problems


## The fork's internal scene/material layout is isolated here. Editor UI calls
## these operations; a future engine pin only needs its adapter updated.
static func show_layers(root: Node3D, names: Array, on: bool) -> void:
	for name in names:
		var node: Node3D = root.get_node_or_null(name) if root != null else null
		if node != null:
			node.visible = on


static func show_clouds(root: Node3D, on: bool) -> void:
	if root == null:
		return
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mesh_node := node as MeshInstance3D
		var materials := [mesh_node.material_override]
		if mesh_node.mesh != null:
			for i in mesh_node.mesh.get_surface_count():
				materials.append(mesh_node.mesh.surface_get_material(i))
		for material in materials:
			var shader_material := material as ShaderMaterial
			if shader_material == null:
				continue
			if not shader_material.has_meta("cloud_tex"):
				var clouds: Variant = shader_material.get_shader_parameter("cloud_tex")
				if clouds == null:
					continue
				shader_material.set_meta("cloud_tex", clouds)
			shader_material.set_shader_parameter("cloud_tex", shader_material.get_meta("cloud_tex") if on else null)


## False means enabling grass requires rebuilding terrain with ground_cover.
static func show_grass(root: Node3D, on: bool) -> bool:
	if root == null:
		return true
	var cover := root.get_node_or_null("GroundCover")
	if cover == null:
		return not on
	cover.set("enabled", on)
	return true
