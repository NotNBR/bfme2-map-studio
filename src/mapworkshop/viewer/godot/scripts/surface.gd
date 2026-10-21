## The visible surface Python sends (viewer/godot_viewer.py, Surface): heights in map units on the height map's samples,
## 10 map units apart, `border` samples around the playable area. Map coordinates are x east, y north from the playable
## area's south-west corner (the coordinates of map objects and of mw render); Godot's are (x, height, -y), as
## OpenBFME builds the map.
class_name Surface
extends RefCounted

var heights := PackedFloat32Array()
var columns := 0
var rows := 0
var border := 0
var cell := 10.0


static func load_from(path: String, info: Dictionary) -> Surface:
	var s := Surface.new()
	s.heights = FileAccess.get_file_as_bytes(path).to_float32_array()
	s.columns = int(info.columns)
	s.rows = int(info.rows)
	s.border = int(info.border)
	s.cell = float(info.cell)
	if s.heights.size() != s.columns * s.rows:
		push_error("surface %s holds %d heights, not %d x %d" % [path, s.heights.size(), s.columns, s.rows])
		return null
	return s


static func to_godot(p: Vector3) -> Vector3:
	return Vector3(p.x, p.z, -p.y)


static func to_map(p: Vector3) -> Vector3:
	return Vector3(p.x, -p.z, p.y)


## Bilinear height at map x, y, clamped to the grid (formats.terrain.height_at).
func height_at(x: float, y: float) -> float:
	var gx := clampf(x / cell + border, 0.0, columns - 1.001)
	var gy := clampf(y / cell + border, 0.0, rows - 1.001)
	var ix := int(gx)
	var iy := int(gy)
	var fx := gx - ix
	var fy := gy - iy
	var i := iy * columns + ix
	return ((1.0 - fy) * ((1.0 - fx) * heights[i] + fx * heights[i + 1])
		+ fy * ((1.0 - fx) * heights[i + columns] + fx * heights[i + columns + 1]))


## The first surface point along a ray in map coordinates within `reach`, or Vector3.INF (godot_link.march: 1500
## steps, then bisection).
func march(origin: Vector3, direction: Vector3, reach: float) -> Vector3:
	var steps := 1500
	var previous := 0.0
	for k in steps:
		var t := reach * k / (steps - 1)
		var p := origin + direction * t
		if p.z <= height_at(p.x, p.y):
			var lo := previous
			var hi := t
			for _i in 20:
				var mid := (lo + hi) * 0.5
				var q := origin + direction * mid
				if q.z <= height_at(q.x, q.y):
					hi = mid
				else:
					lo = mid
			return origin + direction * hi
		previous = t
	return Vector3.INF
