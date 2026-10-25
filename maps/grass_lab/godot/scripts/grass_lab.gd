## Standalone visual test map. Uses the production grass and terrain shaders; no retail files needed.
extends Node3D

const ORIGIN := Vector2(-40, -340)
const GRID := 41
const TITLES := ["01   SPARSE / 25%", "02   MEDIUM / 50%", "03   DENSE / 100%",
	"04   GRASS > EARTH", "05   GRASS > STONE", "06   WINDING PATH",
	"07   SHORT / 0.55x", "08   TALL + LEAF LITTER", "09   SLOPE / 16 degrees"]
var camera: Camera3D
var focus := Vector3(132, 0, 132)
var distance := 400.0
var yaw := 0.0
var pitch := 0.88
var patches: Array[MultiMeshInstance3D] = []
var materials: Array[ShaderMaterial] = []
var terrain_materials: Array[ShaderMaterial] = []
var presets: Array[float] = []
var heights: Array[float] = []
var density_scale := 1.0
var height_scale := 1.0
var wind := 0.20
var grass_visible := true
var detail := true
var noise := FastNoiseLite.new()
var status: Label
var capture_dir := ""
var smoke := false
var wind_slider: HSlider

func _ready() -> void:
	get_window().size = Vector2i(1600, 1000)
	get_viewport().msaa_3d = Viewport.MSAA_8X
	noise.seed = 4701
	noise.frequency = 0.16
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--lab-captures="): capture_dir = arg.trim_prefix("--lab-captures=")
		if arg == "--lab-smoke": smoke = true
	var environment := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("171e25")
	environment.environment = env
	add_child(environment)
	camera = Camera3D.new()
	camera.far = 3000
	camera.fov = 48
	add_child(camera)
	camera.current = true
	_camera_update()
	_build()
	_ui()
	_apply()
	if smoke: _smoke_run()

func _height(x: float, z: float) -> float:
	return maxf(0.0, x - 200.0) * 0.28 if z >= 190.0 else 0.0

func _sample(plot: int, x: float, z: float) -> Color:
	var n := noise.get_noise_2d(x, z + 39) * 0.5 + 0.5
	var grain := noise.get_noise_2d(x * 5.0, z * 5.0) * 0.5 + 0.5
	var grass := Color(0.20, 0.29, 0.12) * lerpf(0.74, 1.15, n)
	var soil := Color(0.34, 0.245, 0.16) * lerpf(0.70, 1.20, grain)
	var stone := Color(0.34, 0.36, 0.37) * lerpf(0.70, 1.18, n)
	var coverage := 1.0
	var other := soil
	if plot == 3: coverage = 1.0 - smoothstep(16.0, 49.0, x + (n - 0.5) * 9.0)
	if plot == 4:
		coverage = 1.0 - smoothstep(30.0, 33.0, x)
		other = stone
	if plot == 5:
		var path := absf(x - 32.0 - sin(z * 0.09) * 11.0)
		coverage = smoothstep(5.0, 10.0, path + (n - 0.5) * 2.0)
	var color := other.lerp(grass, coverage)
	color.a = coverage
	return color

func _blade() -> ArrayMesh:
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = PackedVector3Array([Vector3(-0.5,0,0),Vector3(0.5,0,0),Vector3(-0.3,0.55,0.15),Vector3(0.3,0.55,0.15),Vector3(0,1,0.45)])
	arrays[Mesh.ARRAY_NORMAL] = PackedVector3Array([Vector3.UP,Vector3.UP,Vector3.UP,Vector3.UP,Vector3.UP])
	arrays[Mesh.ARRAY_TEX_UV] = PackedVector2Array([Vector2.ZERO,Vector2.ZERO,Vector2(0,0.55),Vector2(0,0.55),Vector2(0,1)])
	arrays[Mesh.ARRAY_INDEX] = PackedInt32Array([0,1,2,1,3,2,2,3,4])
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	return mesh

func _build() -> void:
	var height_image := Image.create(GRID, GRID, false, Image.FORMAT_RF)
	var flip_image := Image.create(GRID, GRID, false, Image.FORMAT_R8)
	flip_image.fill(Color.BLACK)
	for y in GRID:
		for x in GRID:
			height_image.set_pixel(x, y, Color(_height(ORIGIN.x+x*10, -(ORIGIN.y+y*10)),0,0))
	var guide := Image.create(410, 410, false, Image.FORMAT_RGBA8)
	guide.fill(Color(0,0,0,0))
	for y in 410:
		for x in 410:
			var wx := ORIGIN.x + x + 0.5
			var wz := -(ORIGIN.y + y + 0.5)
			var col := floori(wx / 100.0)
			var row := floori(wz / 100.0)
			var lx := wx - col*100
			var lz := wz - row*100
			if col >= 0 and col < 3 and row >= 0 and row < 3 and lx >= 0 and lx < 64 and lz >= 0 and lz < 64:
				guide.set_pixel(x,y,_sample(row*3+col,lx,lz))
	guide.generate_mipmaps()
	var habitat := Image.create(410,410,false,Image.FORMAT_RGBA8)
	for y in 410:
		for x in 410:
			var wx := ORIGIN.x+x+0.5
			var wz := -(ORIGIN.y+y+0.5)
			var leaf_fall := maxf(0.0,1.0-Vector2(wx-132,wz-232).length()/35.0)
			habitat.set_pixel(x,y,Color(leaf_fall,1.0 if guide.get_pixel(x,y).a>0.01 else 0.0,0))
	habitat.generate_mipmaps()
	var habitat_tex := ImageTexture.create_from_image(habitat)
	var guide_tex := ImageTexture.create_from_image(guide)
	var height_tex := ImageTexture.create_from_image(height_image)
	var flip_tex := ImageTexture.create_from_image(flip_image)
	var blade := _blade()
	var builder = ClassDB.instantiate("MapTerrainBuilder")
	var neutral := Image.create(4,4,false,Image.FORMAT_RGBA8)
	neutral.fill(Color(0.5,0.5,0))
	for plot in 9:
		var x := float(plot % 3) * 100.0
		var z := floorf(float(plot) / 3.0) * 100.0
		var atlas := Image.create(256,256,false,Image.FORMAT_RGBA8)
		var mask := Image.create(256,256,false,Image.FORMAT_R8)
		for py in 256:
			for px in 256:
				var sample := _sample(plot,(px+0.5)/4.0,(py+0.5)/4.0)
				mask.set_pixel(px,py,Color(sample.a,0,0))
				sample.a = 1.0
				atlas.set_pixel(px,py,sample)
		atlas.generate_mipmaps()
		var ground = builder.build_test_patch({"base_atlas":atlas,"uv0":PackedVector2Array([Vector2(0,1),Vector2(1,1),Vector2(1,0),Vector2(0,0)]),"layers":[]})
		ground.position = Vector3(x,0,z+64)
		ground.scale = Vector3(6.4,6.4,6.4)
		if plot == 8:
			var arrays: Array = ground.mesh.surface_get_arrays(0)
			var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			for v in vertices.size():
				vertices[v].y = vertices[v].x * 0.28
				normals[v] = Vector3(-0.28,1,0).normalized()
			arrays[Mesh.ARRAY_VERTEX] = vertices
			arrays[Mesh.ARRAY_NORMAL] = normals
			var old_material = ground.mesh.surface_get_material(0)
			var slope := ArrayMesh.new()
			slope.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays,[],{},ground.mesh.surface_get_format(0))
			slope.surface_set_material(0,old_material)
			ground.mesh = slope
		add_child(ground)
		var terrain: ShaderMaterial = ground.mesh.surface_get_material(0)
		# Preserve engine-built blend records while selecting the namespaced lab shader.
		var inherited := {}
		for key in ["base_atlas", "records", "atlas_size"]:
			inherited[key] = terrain.get_shader_parameter(key)
		terrain.shader = load("res://labs/grass/shaders/terrain.gdshader")
		for key in inherited: terrain.set_shader_parameter(key,inherited[key])
		terrain.set_shader_parameter("normal_atlas",ImageTexture.create_from_image(neutral))
		terrain.set_shader_parameter("meadow_mask",ImageTexture.create_from_image(mask))
		terrain.set_shader_parameter("turf_detail",load("res://labs/grass/assets/turf_detail.png"))
		terrain.set_shader_parameter("natural_ground_enabled",true)
		terrain.set_shader_parameter("sun_dir_sage",Vector3(0.4,0.3,0.85).normalized())
		terrain.set_shader_parameter("sun_color",Vector3(0.22,0.22,0.22))
		terrain.set_shader_parameter("overbright",false)
		terrain.set_shader_parameter("debug_mode",0)
		terrain.set_shader_parameter("terrain_guide",guide_tex)
		terrain.set_shader_parameter("world_origin",ORIGIN)
		terrain.set_shader_parameter("grid_size",Vector2(GRID,GRID))
		terrain.set_shader_parameter("grass_surface_enabled",true)
		terrain_materials.append(terrain)
		var mat := ShaderMaterial.new()
		mat.shader = load("res://labs/grass/shaders/ground_cover.gdshader")
		mat.set_shader_parameter("terrain_guide",guide_tex)
		mat.set_shader_parameter("habitat_guide",habitat_tex)
		mat.set_shader_parameter("habitat_enabled",true)
		mat.set_shader_parameter("height_map",height_tex)
		mat.set_shader_parameter("flip_map",flip_tex)
		mat.set_shader_parameter("grid_size",Vector2(GRID,GRID))
		mat.set_shader_parameter("world_origin",ORIGIN)
		mat.set_shader_parameter("ambient_color",Vector3.ONE)
		mat.set_shader_parameter("sun_color",Vector3(0.22,0.22,0.22))
		mat.set_shader_parameter("sun_dir_sage",Vector3(0.4,0.3,0.85).normalized())
		mat.set_shader_parameter("overbright",false)
		materials.append(mat)
		heights.append(0.55 if plot == 6 else (1.65 if plot == 7 else 1.0))
		for pz in 2:
			for px in 2:
				var mm := MultiMesh.new()
				mm.transform_format = MultiMesh.TRANSFORM_3D
				mm.mesh = blade
				mm.instance_count = 4096
				for i in 4096: mm.set_instance_transform(i,Transform3D.IDENTITY)
				mm.custom_aabb = AABB(Vector3(-5,-1,-5),Vector3(42,40,42))
				var patch := MultiMeshInstance3D.new()
				patch.multimesh = mm
				patch.material_override = mat
				patch.position = Vector3(x+px*32,0,z+pz*32)
				patch.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				add_child(patch)
				patches.append(patch)
				presets.append(0.25 if plot == 0 else (0.5 if plot == 1 else 1.0))
		var label := Label3D.new()
		label.text = TITLES[plot]
		label.font_size = 40
		label.pixel_size = 0.16
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.no_depth_test = true
		label.position = Vector3(x+32,3,z+73)
		add_child(label)

func _ui() -> void:
	var canvas := CanvasLayer.new()
	add_child(canvas)
	var panel := PanelContainer.new()
	panel.position = Vector2(18,18)
	panel.custom_minimum_size = Vector2(350,0)
	canvas.add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left","right","top","bottom"]: margin.add_theme_constant_override("margin_"+side,14)
	panel.add_child(margin)
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation",9)
	margin.add_child(box)
	var title := Label.new()
	title.text = "GRASS LAB  /  Visual test map"
	title.add_theme_font_size_override("font_size",22)
	box.add_child(title)
	var help := Label.new()
	help.text = "1 Overview  /  2 Density  /  3 Transitions  /  4 Height
WASD: move   RMB drag: orbit   Wheel: zoom
G: grass   T: ground detail   Space: wind"
	help.add_theme_font_size_override("font_size",14)
	box.add_child(help)
	_slider(box,"Density multiplier",0,1,1,func(v: float): density_scale=v; _apply())
	_slider(box,"Blade height",0.25,2,1,func(v: float): height_scale=v; _apply())
	_slider(box,"Wind strength",0,0.6,0.2,func(v: float): wind=v; _apply())
	var buttons := HBoxContainer.new()
	box.add_child(buttons)
	for i in 4:
		var button := Button.new()
		button.text = ["Overview","Density","Transitions","Height"][i]
		button.pressed.connect(_view.bind(i))
		buttons.add_child(button)
	status = Label.new()
	status.add_theme_font_size_override("font_size",13)
	box.add_child(status)
	var note := Label.new()
	note.text = "25 / 50 / 100% = 1 / 2 / 4 candidate blades per square unit.
Procedural test textures; production rendering shaders.
No units, AI or retail assets required."
	note.add_theme_font_size_override("font_size",13)
	box.add_child(note)

func _slider(box: VBoxContainer, caption: String, low: float, high: float, value: float, callback: Callable) -> void:
	var label := Label.new()
	label.text = "%s: %.2f" % [caption,value]
	box.add_child(label)
	var slider := HSlider.new()
	slider.min_value=low; slider.max_value=high; slider.step=0.01; slider.value=value
	box.add_child(slider)
	if caption == "Wind strength": wind_slider = slider
	slider.value_changed.connect(func(v: float): label.text="%s: %.2f" % [caption,v]; callback.call(v))

func _apply() -> void:
	for i in patches.size():
		var d := presets[i]*density_scale
		patches[i].visible = grass_visible
		patches[i].multimesh.visible_instance_count = ceili(4096*d)
		patches[i].set_instance_shader_parameter("patch_density",d)
	for i in materials.size():
		materials[i].set_shader_parameter("blade_height_scale",heights[i]*height_scale)
		materials[i].set_shader_parameter("wind_strength",wind)
	for mat in terrain_materials:
		mat.set_shader_parameter("natural_ground_enabled",detail)
		mat.set_shader_parameter("grass_surface_enabled",grass_visible)

func _view(index: int) -> void:
	yaw=0; pitch=0.88
	focus=Vector3(132,0,132) if index == 0 else Vector3(132,0,(index-1)*100+32)
	distance=400 if index == 0 else 310
	_camera_update()

func _camera_update() -> void:
	camera.position=focus+Vector3(sin(yaw)*cos(pitch),sin(pitch),cos(yaw)*cos(pitch))*distance
	camera.look_at(focus)
	camera.h_offset = -distance * 0.15

func _process(delta: float) -> void:
	var move := Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_W): move.z-=1
	if Input.is_physical_key_pressed(KEY_S): move.z+=1
	if Input.is_physical_key_pressed(KEY_A): move.x-=1
	if Input.is_physical_key_pressed(KEY_D): move.x+=1
	if move != Vector3.ZERO:
		focus += move.rotated(Vector3.UP,yaw)*delta*distance*0.45
		_camera_update()
	if status:
		status.text="%d FPS   |   Grass %s   |   Detail %s" % [Engine.get_frames_per_second(),"ON" if grass_visible else "OFF","ON" if detail else "OFF"]

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
		yaw-=event.relative.x*0.006
		pitch=clampf(pitch+event.relative.y*0.005,0.18,1.48)
		_camera_update()
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP: distance=maxf(30,distance*0.90)
		if event.button_index == MOUSE_BUTTON_WHEEL_DOWN: distance=minf(1000,distance*1.10)
		_camera_update()
	if event is InputEventKey and event.pressed and not event.echo:
		if event.keycode >= KEY_1 and event.keycode <= KEY_4: _view(event.keycode-KEY_1)
		if event.keycode == KEY_G: grass_visible=not grass_visible
		if event.keycode == KEY_T: detail=not detail
		if event.keycode == KEY_SPACE: wind_slider.value=0.0 if wind>0 else 0.2
		_apply()

func _smoke_run() -> void:
	var failures := 0
	if patches.size()!=36 or materials.size()!=9: failures+=1
	if _sample(4,60,32).a != 0 or _sample(4,4,32).a != 1: failures+=1
	if _sample(3,4,32).a <= _sample(3,60,32).a: failures+=1
	if _height(250,220) <= _height(210,220): failures+=1
	density_scale=0; _apply()
	for patch in patches:
		if patch.multimesh.visible_instance_count != 0: failures+=1
	density_scale=1; _apply()
	if patches[0].multimesh.visible_instance_count != 1024 or patches[4].multimesh.visible_instance_count != 2048 or patches[8].multimesh.visible_instance_count != 4096: failures+=1
	if not capture_dir.is_empty(): DirAccess.make_dir_recursive_absolute(capture_dir)
	for view in 4:
		_view(view)
		for frame in 35: await get_tree().process_frame
		await RenderingServer.frame_post_draw
		if not capture_dir.is_empty():
			if get_viewport().get_texture().get_image().save_png(capture_dir.path_join("lab-%d.png" % view)) != OK: failures+=1
	print("GRASS LAB ","PASS" if failures==0 else "FAIL", " / 9 plots, 36 batches; density 0/25/50/100 verified")
	get_tree().quit(0 if failures==0 else 1)
