## The map's marks (local/marks/, viewer/marks.py), drawn red as the studio viewer draws them: each outline a ribbon
## draped on the surface, a pin a post with its number's place on the ground. The outlines come from Python
## (godot_viewer.outlines: points in map x/y, closed or not); only the draping is done here.
class_name MarksLayer
extends Node3D

const COLOR := Color(1.0, 0.18, 0.15)
const LIFT := 1.5             # map units above the surface
const STEP := 10.0            # at most this far between draped points: one height sample apart


static func build(marks: Array, surface: Surface, width: float) -> MarksLayer:
	var layer := MarksLayer.new()
	layer.name = "Marks"
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.albedo_color = COLOR
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	# drawn over everything, as an annotation: a flat ribbon on a steep slope would dip into the cliff
	material.no_depth_test = true
	material.render_priority = 10
	for mark in marks:
		var points: Array = mark.points
		var instance := MeshInstance3D.new()
		instance.name = "Mark%d" % int(mark.id)
		if mark.kind == "pin" or points.size() < 2:
			var box := BoxMesh.new()          # a post `width` thick, ten times as high, standing on the surface
			box.size = Vector3(width, width * 10.0, width)
			instance.mesh = box
			var x: float = points[0][0]
			var y: float = points[0][1]
			instance.position = Surface.to_godot(Vector3(x, y, surface.height_at(x, y) + width * 5.0))
		else:
			instance.mesh = _ribbon(points, bool(mark.closed), surface, width)
		instance.material_override = material
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		layer.add_child(instance)
	return layer


## The outline densified to STEP and lifted onto the surface, as a flat ribbon `width` wide.
static func _ribbon(points: Array, closed: bool, surface: Surface, width: float) -> ArrayMesh:
	var path := PackedVector2Array()
	for p in points:
		path.append(Vector2(p[0], p[1]))
	if closed:
		path.append(path[0])
	var dense := PackedVector2Array([path[0]])
	for i in range(1, path.size()):
		var a := path[i - 1]
		var b := path[i]
		var n := maxi(1, ceili(a.distance_to(b) / STEP))
		for k in range(1, n + 1):
			dense.append(a.lerp(b, float(k) / n))
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in range(dense.size() - 1):
		var a := dense[i]
		var b := dense[i + 1]
		var side := (b - a).orthogonal().normalized() * width * 0.5
		var quad := [a - side, a + side, b + side, b - side]
		var lifted := []
		for q in quad:
			lifted.append(Surface.to_godot(Vector3(q.x, q.y, surface.height_at(q.x, q.y) + LIFT)))
		for k in [0, 1, 2, 0, 2, 3]:
			st.add_vertex(lifted[k])
	return st.commit()
