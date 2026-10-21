## Photo mode's exposure and depth of field over the finished frame: a compositor effect running shaders/photo.glsl
## (a port of render/photo.py's Post) after the transparent pass, once OpenBFME's gamma composite has turned the colour
## buffer back to linear light; it has to stay the camera's last effect (keep_last). It also reads the distance at a
## pixel for focusing on what is there (ask_distance, then `distance` once `answered` reaches the request), ground or
## object. The lens is set from the main thread; the passes run on the render thread.
class_name PhotoEffect
extends CompositorEffect

const TILE := 16              # photo.glsl's

var taps := 128               # the blur's samples per pixel; 256 for a screenshot, as mw render
var focal := Lens.focal_from_fov(50.0)
var aperture := 0.0           # an f-number; 0: everything sharp
var focus := 1500.0
var ev := 0.0
var sensor_width := Lens.SENSOR.x     # the image's width in mm on the sensor's scale (FlyCamera.sensor_width)
var distance := -1.0          # along the view axis at the asked pixel; < 0: nothing drawn there
var answered := 0             # the distance request answered last

var _asked := 0
var _ask_at := Vector2i.ZERO
var _rd: RenderingDevice
var _shader: RID
var _pipeline: RID
var _sampler: RID
var _params: RID
var _probe: RID
var _copy: RID
var _tiles: RID
var _reach: RID
var _size := Vector2i.ZERO


func _init() -> void:
	effect_callback_type = EFFECT_CALLBACK_TYPE_POST_TRANSPARENT
	access_resolved_color = true
	access_resolved_depth = true
	RenderingServer.call_on_render_thread(_setup)


func _notification(what: int) -> void:
	if what == NOTIFICATION_PREDELETE and _rd != null:
		for rid in [_copy, _tiles, _reach, _params, _probe, _sampler, _pipeline, _shader]:
			if rid.is_valid():
				_rd.free_rid(rid)


## Whether the lens changes the picture (an aperture, an exposure).
func active() -> bool:
	return aperture > 0.0 or absf(ev) > 1e-6


## Read the distance at `pixel` with the next frame; returns the request's number.
func ask_distance(pixel: Vector2i) -> int:
	_ask_at = pixel
	_asked += 1
	return _asked


## `effect` the last of `camera`'s compositor effects, where it sees the linear colour (OpenBFME adds its pair).
static func keep_last(camera: Camera3D, effect: CompositorEffect) -> void:
	if camera.compositor == null:
		camera.compositor = Compositor.new()
	var effects := camera.compositor.compositor_effects
	if not effects.is_empty() and effects[-1] == effect:
		return
	effects.erase(effect)
	effects.append(effect)
	camera.compositor.compositor_effects = effects


func _setup() -> void:
	_rd = RenderingServer.get_rendering_device()
	if _rd == null:
		return
	var file: RDShaderFile = load("res://shaders/photo.glsl")
	var spirv := file.get_spirv()
	if not spirv.compile_error_compute.is_empty():
		print("VIEWER Photo mode's shader did not compile: ", spirv.compile_error_compute)
		return
	_shader = _rd.shader_create_from_spirv(spirv)
	_pipeline = _rd.compute_pipeline_create(_shader)
	var state := RDSamplerState.new()
	state.min_filter = RenderingDevice.SAMPLER_FILTER_NEAREST
	state.mag_filter = RenderingDevice.SAMPLER_FILTER_NEAREST
	state.repeat_u = RenderingDevice.SAMPLER_REPEAT_MODE_CLAMP_TO_EDGE
	state.repeat_v = RenderingDevice.SAMPLER_REPEAT_MODE_CLAMP_TO_EDGE
	_sampler = _rd.sampler_create(state)
	_params = _rd.storage_buffer_create(128)
	_probe = _rd.storage_buffer_create(16)


func _render_callback(_type: int, render_data: RenderData) -> void:
	if _rd == null or not _pipeline.is_valid():
		return
	# the lens as it is now, for every pass (the main thread may change it meanwhile)
	var lens := {"focal": focal, "aperture": aperture, "focus": focus, "ev": ev, "width": sensor_width, "taps": taps,
		"at": _ask_at}
	var probing := answered < _asked
	var changes: bool = lens.aperture > 0.0 or absf(lens.ev) > 1e-6
	if not (changes or probing):
		return
	var buffers := render_data.get_render_scene_buffers() as RenderSceneBuffersRD
	if buffers == null:
		return
	var size := buffers.get_internal_size()
	if size.x <= 0 or size.y <= 0:
		return
	var color := buffers.get_color_layer(0)
	var depth := buffers.get_depth_layer(0)
	_targets(size, _rd.texture_get_format(color).format)
	var inverse := render_data.get_render_scene_data().get_view_projection(0).inverse()
	var uniforms := UniformSetCacheRD.get_cache(_shader, 0, [
		_uniform(RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER, 0, [_params]),
		_uniform(RenderingDevice.UNIFORM_TYPE_SAMPLER_WITH_TEXTURE, 1, [_sampler, depth]),
		_uniform(RenderingDevice.UNIFORM_TYPE_IMAGE, 3, [color]),
		_uniform(RenderingDevice.UNIFORM_TYPE_IMAGE, 4, [_tiles]),
		_uniform(RenderingDevice.UNIFORM_TYPE_IMAGE, 5, [_reach]),
		_uniform(RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER, 6, [_probe]),
		_uniform(RenderingDevice.UNIFORM_TYPE_IMAGE, 7, [_copy])])
	var tiles := Vector2i(ceili(float(size.x) / TILE), ceili(float(size.y) / TILE))
	if probing:
		var request := _asked
		_pass(uniforms, inverse, size, lens, 3, Vector2i.ONE)
		distance = _rd.buffer_get_data(_probe, 0, 4).to_float32_array()[0]
		answered = request
	if not changes:
		return
	var pixels := Vector2i(ceili(size.x / 8.0), ceili(size.y / 8.0))
	_pass(uniforms, inverse, size, lens, 4, pixels)         # the frame copied, to read while the blur writes it
	if lens.aperture > 0.0:
		_pass(uniforms, inverse, size, lens, 0, Vector2i(ceili(tiles.x / 8.0), ceili(tiles.y / 8.0)))
		_pass(uniforms, inverse, size, lens, 1, Vector2i(ceili(tiles.x / 8.0), ceili(tiles.y / 8.0)))
	_pass(uniforms, inverse, size, lens, 2, pixels)


func _pass(uniforms: RID, inverse: Projection, size: Vector2i, lens: Dictionary, index: int, groups: Vector2i) -> void:
	var values := PackedFloat32Array()
	for column in [inverse.x, inverse.y, inverse.z, inverse.w]:
		values.append_array([column.x, column.y, column.z, column.w])
	var mm_per_unit := 1000.0 / Lens.UNITS_PER_METRE
	var open: bool = lens.aperture > 0.0
	values.append_array([size.x, size.y, lens.at.x, lens.at.y, mm_per_unit, lens.focus * mm_per_unit, lens.focal,
		lens.focal / lens.aperture if open else lens.focal, size.x / lens.width, maxf(2.0, Lens.MAX_BLUR * size.x),
		pow(2.0, lens.ev), lens.taps, 1.0 if open else 0.0, index, 0.0, 0.0])
	_rd.buffer_update(_params, 0, values.size() * 4, values.to_byte_array())
	var list := _rd.compute_list_begin()
	_rd.compute_list_bind_compute_pipeline(list, _pipeline)
	_rd.compute_list_bind_uniform_set(list, uniforms, 0)
	_rd.compute_list_dispatch(list, groups.x, groups.y, 1)
	_rd.compute_list_end()


## The frame's copy and the tiles' images, made again when the size or the colour format changes.
func _targets(size: Vector2i, format: int) -> void:
	if size == _size and _copy.is_valid() and _rd.texture_get_format(_copy).format == format:
		return
	for rid in [_copy, _tiles, _reach]:
		if rid.is_valid():
			_rd.free_rid(rid)
	_size = size
	_copy = _texture(size, format, RenderingDevice.TEXTURE_USAGE_STORAGE_BIT)
	var tiles := Vector2i(ceili(float(size.x) / TILE), ceili(float(size.y) / TILE))
	_tiles = _texture(tiles, RenderingDevice.DATA_FORMAT_R32_SFLOAT, RenderingDevice.TEXTURE_USAGE_STORAGE_BIT)
	_reach = _texture(tiles, RenderingDevice.DATA_FORMAT_R32_SFLOAT, RenderingDevice.TEXTURE_USAGE_STORAGE_BIT)


func _texture(size: Vector2i, format: int, usage: int) -> RID:
	var f := RDTextureFormat.new()
	f.width = size.x
	f.height = size.y
	f.format = format
	f.usage_bits = usage
	return _rd.texture_create(f, RDTextureView.new())


static func _uniform(type: int, binding: int, ids: Array) -> RDUniform:
	var u := RDUniform.new()
	u.uniform_type = type
	u.binding = binding
	for id in ids:
		u.add_id(id)
	return u
