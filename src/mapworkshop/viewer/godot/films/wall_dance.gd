## Aragorn and Gandalf's dance on the Deeping Wall (Experimental > Dance on the Deeping Wall, scripts/wall_dance.gd),
## filmed in nine shots with two follow spots and lightning on the last pose:
##     mw film helms-deep-battle wall_dance
extends "res://scripts/film.gd"

const WallDance := preload("res://scripts/wall_dance.gd")
const PREROLL := 2.0                      # seconds before the first beat
const END_BEAT := 47.5

# [from beat, to beat, eye from, eye to, look from, look to, focal from, focal to, aperture]; eye and look are offsets
# from the dancers' middle in map axes (x east, y north, z up), so the camera follows their travels.
const SHOTS := [
	[-4.0, 2.6, Vector3(0, -420, 190), Vector3(0, -80, 30), Vector3(0, 0, 10), Vector3(0, 0, 12), 28.0, 50.0, 0.0],
	[2.6, 12.3, Vector3(0, 82, 17), Vector3(0, 66, 14), Vector3(0, 0, 11), Vector3(0, 0, 11), 45.0, 50.0, 2.0],
	[12.3, 19.4, Vector3(-10, 62, 8), Vector3(10, 58, 8), Vector3(0, 0, 7), Vector3(0, 0, 7), 40.0, 40.0, 2.8],
	[19.4, 21.5, Vector3(0, 44, 3), Vector3(0, 40, 3), Vector3(0, 0, 12), Vector3(0, 0, 12), 28.0, 28.0, 2.0],
	[21.5, 25.5, Vector3(84, 58, 12), Vector3(76, 52, 11), Vector3(-4, 0, 9), Vector3(-4, 0, 9), 45.0, 50.0, 2.8],
	[25.5, 34.5, Vector3(0, 108, 45), Vector3(0, 84, 32), Vector3(0, -5, 8), Vector3(0, -5, 8), 32.0, 36.0, 0.0],
	[34.5, 41.0, Vector3(-40, 52, 24), Vector3(-25, 48, 20), Vector3(0, 0, 8), Vector3(0, 0, 8), 40.0, 45.0, 2.8],
	[41.0, 42.5, Vector3(0, 42, 4), Vector3(0, 42, 4), Vector3(0, 0, 15), Vector3(0, 0, 15), 24.0, 24.0, 2.0],
	[42.5, END_BEAT, Vector3(0, 42, 4), Vector3(0, 150, 95), Vector3(0, 0, 15), Vector3(0, -60, 0), 24.0, 30.0, 2.0],
]
const FLASHES := [42.0, 43.4, 45.1]       # lightning on the final pose

var dance: Node
var flash := DirectionalLight3D.new()
var spots: Array[SpotLight3D] = []


func prepare() -> bool:
	dance = viewer.experiment("wall_dance", true)
	if dance == null or not dance.error.is_empty():
		push_error("wall dance: %s" % (dance.error if dance else "no controller"))
		return false
	length = PREROLL + END_BEAT * 60.0 / WallDance.BPM
	cam.ev = 0.6
	for side in [-1.0, 1.0]:                  # warm follow spots from the Deep side, as on a stage
		var spot := SpotLight3D.new()
		spot.light_color = Color(1.0, 0.86, 0.68)
		spot.light_energy = 6.0
		spot.spot_range = 260.0
		spot.spot_angle = 11.0
		spot.spot_attenuation = 0.4
		spot.shadow_enabled = true
		spot.set_meta("side", side)
		viewer.add_child(spot)
		spots.append(spot)
	flash.light_color = Color(0.75, 0.82, 1.0)
	flash.light_energy = 0.0
	viewer.add_child(flash)
	flash.look_at_from_position(Vector3.ZERO, Vector3(0.3, -1.0, -0.5))
	return true


func shot(t: float) -> void:
	var beat := (t - PREROLL) * WallDance.BPM / 60.0
	var at := maxf(beat, 0.0) * 60.0 / WallDance.BPM
	dance.sample(at)                          # the dance starts after the preroll, not with the map's clock
	var middle: Vector3 = dance.middle(at)
	var s: Array = SHOTS[-1]
	for candidate in SHOTS:
		if beat < candidate[1]:
			s = candidate
			break
	var u := smoothstep(s[0], s[1], beat)
	cam.look_at(middle + sage((s[2] as Vector3).lerp(s[3], u)), middle + sage((s[4] as Vector3).lerp(s[5], u)))
	cam.focal = lerpf(s[6], s[7], u)
	cam.aperture = s[8]
	for spot in spots:
		var side: float = spot.get_meta("side")
		var on := middle + sage(Vector3(side * 15.0, 0, 10.0))
		spot.look_at_from_position(on + sage(Vector3(side * 25.0, 120.0, 110.0)), on)
	var strike := 0.0
	for b in FLASHES:
		var since: float = (beat - b) * 60.0 / WallDance.BPM
		if since >= 0.0 and since < 0.35:
			strike = maxf(strike, (1.0 - since / 0.35) * (1.0 if fmod(since, 0.12) < 0.07 else 0.4))
	flash.light_energy = 3.5 * strike
