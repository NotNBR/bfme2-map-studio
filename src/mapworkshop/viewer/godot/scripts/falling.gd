## The rain or snow the map's weather lets fall (View > Fog and weather): one quad per emitter of the game's lattice,
## which Python works out (render.godot.falling) with the weather's settings; falling.gdshader moves them on the
## viewer's clock, which View > Animate stops and mw render --time sets.
class_name Falling
extends MultiMeshInstance3D

const SHADER := preload("res://shaders/falling.gdshader")

var _material := ShaderMaterial.new()
var _speed := 0.0
var _xy_speed := Vector2.ZERO


func _init() -> void:
	name = "Falling"
	_material.shader = SHADER
	_material.render_priority = 4


## The emitters and settings of a scene's `falling` entry, its files in `folder`. False when they did not load.
func build(falling: Dictionary, folder: String, playable: Vector2) -> bool:
	var data := FileAccess.get_file_as_bytes(folder.path_join(String(falling.emitters))).to_float32_array()
	var image := Image.load_from_file(folder.path_join(String(falling.texture)))
	if data.size() != int(falling.count) * 3 or image == null:
		return false
	image.generate_mipmaps()
	_material.set_shader_parameter("tex", ImageTexture.create_from_image(image))
	for key in ["size", "box", "amplitude"]:
		_material.set_shader_parameter(key, float(falling[key]))
	_material.set_shader_parameter("frequency", Vector2(falling.frequency[0], falling.frequency[1]))
	_material.set_shader_parameter("drift_per_cycle", Vector2(falling.drift_per_cycle[0], falling.drift_per_cycle[1]))
	_material.set_shader_parameter("playable", playable)
	_speed = float(falling.speed)
	_xy_speed = Vector2(falling.xy_speed[0], falling.xy_speed[1])
	var quad := QuadMesh.new()
	quad.material = _material
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_custom_data = true
	mm.mesh = quad
	mm.instance_count = int(falling.count)
	for i in mm.instance_count:
		mm.set_instance_transform(i, Transform3D.IDENTITY)
		mm.set_instance_custom_data(i, Color(data[i * 3], data[i * 3 + 1], data[i * 3 + 2]))
	# the shader places every quad: the bounds are the whole box over the map
	mm.custom_aabb = AABB(Vector3(-1000, -100, -playable.y - 1000), Vector3(playable.x + 2000, float(falling.box) + 4000, playable.y + 2000))
	multimesh = mm
	set_time(0.0)
	return true


## The particles `time` seconds after the map was built.
func set_time(time: float) -> void:
	_material.set_shader_parameter("travelled", time * _speed)
	_material.set_shader_parameter("drift", time * _xy_speed)
