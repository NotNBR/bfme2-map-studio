## The map overlays of the View menu, drawn on the ground (mw render --walkable, --grid, --flow): the grid, the border's fade, the
## walkability estimate (one mesh draped on the surface, ground_overlay.gdshader) and the river flow arrows (each river
## strip's mesh, river_flow.gdshader). Python works out the walkability and the strips (godot_link); this draws them.
class_name Overlays
extends Node3D

const LIFT := 1.5             # map units over the surface (the shaders also pull it towards the camera)
const MAX_SAMPLES := 640      # the draped mesh's samples along its longer side, at most
const GROUND_SHADER := preload("res://shaders/ground_overlay.gdshader")
const FLOW_SHADER := preload("res://shaders/river_flow.gdshader")

var _ground: MeshInstance3D
var _ground_material := ShaderMaterial.new()
var _flow: Node3D
var _starts: Node3D
var _playable := Vector2.ONE
var _time := 0.0              # the flow arrows' clock: View > Animate stops it


func _init() -> void:
	name = "Overlays"
	_ground_material.shader = GROUND_SHADER
	_ground_material.render_priority = 5


## The draped mesh for a map: its surface's samples (every step-th along each side), lifted a little. The previous
## map's walkability goes (the new map's comes from the companion).
func build(surface: Surface, playable: Vector2, border: int) -> void:
	_playable = playable
	set_walkable("", Vector2.ONE)
	if _ground != null:
		_ground.queue_free()
	var step := maxi(1, ceili(float(maxi(surface.columns, surface.rows)) / MAX_SAMPLES))
	var xs := range(0, surface.columns, step)
	var ys := range(0, surface.rows, step)
	if xs[-1] != surface.columns - 1:
		xs.append(surface.columns - 1)
	if ys[-1] != surface.rows - 1:
		ys.append(surface.rows - 1)
	var vertices := PackedVector3Array()
	for j in ys:
		for i in xs:
			var x: float = (i - surface.border) * surface.cell
			var y: float = (j - surface.border) * surface.cell
			vertices.append(Surface.to_godot(Vector3(x, y, surface.heights[j * surface.columns + i] + LIFT)))
	var indices := PackedInt32Array()
	var w := xs.size()
	for r in ys.size() - 1:
		for c in w - 1:
			var a := r * w + c
			indices.append_array(PackedInt32Array([a, a + 1, a + w, a + 1, a + w + 1, a + w]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_INDEX] = indices
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	_ground = MeshInstance3D.new()
	_ground.mesh = mesh
	_ground.material_override = _ground_material
	_ground.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(_ground)
	_ground_material.set_shader_parameter("playable", playable)
	_ground_material.set_shader_parameter("border_fade", border * surface.cell)


func advance(delta: float) -> void:
	_time += delta
	if _flow != null:
		for strip in _flow.get_children():
			(strip as MeshInstance3D).material_override.set_shader_parameter("time", _time)


func set_grid(on: bool) -> void:
	_ground_material.set_shader_parameter("grid", on)


func set_border(shown: bool) -> void:
	_ground_material.set_shader_parameter("show_border", shown)
	if _flow != null:
		for strip in _flow.get_children():
			(strip as MeshInstance3D).material_override.set_shader_parameter("show_border", shown)


## The walkability estimate: an image with one pixel per cell from the playable area's corner (row 0 the south), or
## an empty path to hide it.
func set_walkable(path: String, size: Vector2) -> void:
	if path.is_empty():
		_ground_material.set_shader_parameter("walk", false)
		return
	var image := Image.load_from_file(path)
	_ground_material.set_shader_parameter("walk_tex", ImageTexture.create_from_image(image))
	_ground_material.set_shader_parameter("walk_size", size)
	_ground_material.set_shader_parameter("walk", true)


## Numbered skirmish starts: rings follow the terrain rather than sitting on a flat plane.
func set_starts(starts: Array, surface: Surface) -> void:
	if _starts != null:
		_starts.queue_free()
	_starts = Node3D.new()
	_starts.name = "StartingPositions"
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	material.cull_mode = BaseMaterial3D.CULL_DISABLED
	material.albedo_color = Color(1.0, 0.78, 0.24, 0.9)
	for start in starts:
		var x := float(start.x)
		var y := float(start.y)
		var vertices := PackedVector3Array()
		var indices := PackedInt32Array()
		var segments := 48
		for i in segments:
			var angle := TAU * i / segments
			for radius in [42.0, 52.0]:
				var px: float = x + cos(angle) * radius
				var py: float = y + sin(angle) * radius
				vertices.append(Surface.to_godot(Vector3(px, py, surface.height_at(px, py) + 3.0)))
			var a := i * 2
			var b := ((i + 1) % segments) * 2
			indices.append_array(PackedInt32Array([a, b, a + 1, a + 1, b, b + 1]))
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = vertices
		arrays[Mesh.ARRAY_INDEX] = indices
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var ring := MeshInstance3D.new()
		ring.mesh = mesh
		ring.material_override = material
		ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_starts.add_child(ring)
		var label := Label3D.new()
		label.text = str(start.number)
		label.font_size = 48
		label.pixel_size = 0.5
		label.outline_size = 8
		label.modulate = Color(1.0, 0.92, 0.7)
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.position = Surface.to_godot(Vector3(x, y, surface.height_at(x, y) + 23.0))
		_starts.add_child(label)
	add_child(_starts)


func show_starts(on: bool) -> void:
	if _starts != null:
		_starts.visible = on


## The river strips' flow arrows: [{vertices: [x, y, z, u, v] * n, triangles: [i, j, k] * m, length}], or [] to hide.
func set_flow(strips: Array, show_border: bool) -> void:
	if _flow != null:
		_flow.queue_free()
		_flow = null
	if strips.is_empty():
		return
	_flow = Node3D.new()
	for strip in strips:
		var flat: Array = strip.vertices
		var positions := PackedVector3Array()
		var uvs := PackedVector2Array()
		for k in range(0, flat.size(), 5):
			positions.append(Surface.to_godot(Vector3(flat[k], flat[k + 1], flat[k + 2] + LIFT)))
			uvs.append(Vector2(flat[k + 3], flat[k + 4]))
		var arrays := []
		arrays.resize(Mesh.ARRAY_MAX)
		arrays[Mesh.ARRAY_VERTEX] = positions
		arrays[Mesh.ARRAY_TEX_UV] = uvs
		arrays[Mesh.ARRAY_INDEX] = PackedInt32Array(strip.triangles)
		var mesh := ArrayMesh.new()
		mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
		var material := ShaderMaterial.new()
		material.shader = FLOW_SHADER
		material.render_priority = 6
		material.set_shader_parameter("strip_length", float(strip.length))
		material.set_shader_parameter("playable", _playable)
		material.set_shader_parameter("show_border", show_border)
		material.set_shader_parameter("time", _time)
		var instance := MeshInstance3D.new()
		instance.mesh = mesh
		instance.material_override = material
		instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		_flow.add_child(instance)
	add_child(_flow)
