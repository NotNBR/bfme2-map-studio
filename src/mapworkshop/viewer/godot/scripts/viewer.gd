## The studio's map viewer on OpenBFME's library (docs/godot-viewer/plan.md), so far its skeleton: it checks that
## what the assembly brings (native/openbfme.py, assemble()) is there, OpenBFME's classes the viewer uses and the
## shaders the library loads by path, prints "VIEWER ready" or what is missing, and when headless quits with 0 or 1.
extends Node3D

const CLASSES := ["RetailFileSystem", "MapTerrainBuilder", "MapObjectBuilder", "PathfindView"]
const SHADERS := ["terrain", "water_standing", "road", "river"]


func _ready() -> void:
	var missing := PackedStringArray()
	for library_class in CLASSES:
		if not ClassDB.class_exists(library_class):
			missing.append(library_class)
	for shader in SHADERS:
		var path := "res://shaders/%s.gdshader" % shader
		if not ResourceLoader.exists(path) or load(path) == null:
			missing.append(path)
	print("VIEWER ready" if missing.is_empty() else "VIEWER missing: " + ", ".join(missing))
	if DisplayServer.get_name() == "headless":
		get_tree().quit(0 if missing.is_empty() else 1)
