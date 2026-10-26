## The base of a film (mw film; docs/guide/rendering.md, "Films"): a map in the viewer, filmed frame by frame through
## OpenBFME's pro camera (the engine's scripts/pro_camera.gd and docs/PRO_CAMERA.md). A film extends this script and
## overrides prepare() (turn on what it shows, set `length`; false stops the film) and shot(t) (place `cam`, and
## anything else, `t` seconds in). The map's clock follows the film's. It films at Ultra High quality with object
## shadows; prepare() may change that through `viewer` (set_quality, set_shadows). With --music=<file> (MP3, Ogg or WAV)
## the film plays it from --music-start=<seconds> as it starts, fading it out over its last MUSIC_FADE; the movie
## writer records it with the picture.
extends SceneTree

const ProCamera := preload("res://scripts/pro_camera.gd")
const MUSIC_FADE := 1.5                   # seconds

var viewer: Node
var cam := ProCamera.new()                # the pose and lens; shot() sets it, the film applies it to `camera`
var camera := Camera3D.new()
var length := 10.0                        # seconds
var fps := 30.0                           # mw film passes --fps (and Godot's --fixed-fps) to match


func prepare() -> bool:
	return true


func shot(_t: float) -> void:
	pass


## A map point or offset (x east, y north, z up) in the viewer's coordinates.
static func sage(point: Vector3) -> Vector3:
	return ProCamera.sage(point)


func _initialize() -> void:
	call_deferred("_film")


func _film() -> void:
	var stills := ""
	var at := PackedFloat64Array()
	var music := ""
	var music_start := 0.0
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--fps="):
			fps = float(arg.trim_prefix("--fps="))
		elif arg.begins_with("--music="):
			music = arg.trim_prefix("--music=")
		elif arg.begins_with("--music-start="):
			music_start = float(arg.trim_prefix("--music-start="))
		elif arg.begins_with("--stills="):
			stills = arg.trim_prefix("--stills=")
		elif arg.begins_with("--at="):
			for t in arg.trim_prefix("--at=").split(",", false):
				at.append(float(t))
	viewer = load("res://scenes/viewer.tscn").instantiate()
	root.add_child(viewer)
	await process_frame
	viewer.clean_picture()
	viewer.set_quality("Ultra High")
	viewer.set_shadows(true)
	viewer.add_child(camera)
	camera.make_current()
	cam.taps = 256                            # a still's blur samples, as mw render's
	if not prepare():
		print("FILM stopped by prepare()")
		quit(1)
		return
	var player: AudioStreamPlayer = null
	if not music.is_empty():
		player = AudioStreamPlayer.new()
		player.stream = _audio(music)
		if player.stream == null:
			print("FILM no music in ", music)
			quit(1)
			return
		viewer.add_child(player)
	var frames := int(ceil(length * fps))
	print("FILM %s: %.2f s, %d frames at %s fps, shadows %s" % [get_script().resource_path.get_file(), length, frames,
		fps, viewer.shadows_drawn()])
	var base: float = viewer.get_clock()
	var next := 0
	for frame in frames:
		var t := frame / fps
		if not stills.is_empty() and next >= at.size():
			break
		viewer.set_clock(base + t)
		shot(t)
		cam.apply(camera)
		if player != null:
			if frame == 0:
				player.play(music_start)
			player.volume_db = linear_to_db(maxf(clampf((length - t) / MUSIC_FADE, 0.0, 1.0), 0.0001))
		await process_frame
		if not stills.is_empty() and t + 0.5 / fps >= at[next]:
			await RenderingServer.frame_post_draw
			DirAccess.make_dir_recursive_absolute(stills)
			var path := stills.path_join("%06.2f.png" % t)
			root.get_texture().get_image().save_png(path)
			print("FILM still ", path)
			next += 1
	print("FILM done")
	quit(0)


static func _audio(path: String) -> AudioStream:
	match path.get_extension().to_lower():
		"mp3": return AudioStreamMP3.load_from_file(path)
		"ogg": return AudioStreamOggVorbis.load_from_file(path)
		"wav": return AudioStreamWAV.load_from_file(path)
	return null
