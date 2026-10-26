## Experimental: Aragorn and Gandalf the White dance on the Deeping Wall of Helm's Deep, in the style of Michael
## Jackson's routines (a turn to the crowd, hits, the toe stand, the moonwalk, a spin, the Smooth Criminal lean, the
## Thriller step-drag), at Billie Jean's 117 beats a minute. Aragorn is the map's own (GondorAragornMP over the
## culvert, maps/helms_deep_battle); Gandalf is added beside him on the walkway. Every bone's pose is computed here
## from the models' own skeletons (two-bone IK for the limbs) and handed to the engine's custom rig API
## (set_instance_rig_pose); nothing of the game's is copied. They dance unarmed: the weapons, skinned into the same
## mesh, are hidden by bone (set_instance_hidden_bones); their swords stay sheathed. Disabling hands Aragorn back to
## his idle.
extends Node3D

const BPM := 117.0
const BEATS := 48.0                        # one loop of the routine
const GANDALF_EAST := 30.0                 # Gandalf stands this far to Aragorn's left (east, as he faces the host)
const STEP := 4.0                          # a moonwalk step, map units
const SHUFFLE := 4.0                       # a Thriller step-drag, map units
const BALL := 2.0                          # the ball of the foot ahead of the ankle
const TOE_ANGLE := 55.0                    # degrees the foot tips at a full heel raise
const WEAPONS := ["B_SWORDBONE", "B_BOWBONE", "PLANE02", "STAFF", "STAFF_LIGHT"]   # drawn weapons and their parts
const MOON_EASE := 0.6                     # beats a moonwalk takes to reach its glide, and to stop
const SWAY_LAG := 0.25                     # beats the hems and low capes trail the body's turn

# Hands, relative to the shoulder in the body's rest frame (x forward, y up, z out to the hand's side); with them the
# way the elbow points.
const DOWN := Vector3(0.5, -7.2, 1.0)
const HIP := Vector3(-0.8, -5.0, 2.2)
const UP := Vector3(0.9, 7.3, 0.7)
const DIAG := Vector3(2.0, 5.6, 4.3)
const CLAW := Vector3(4.6, -1.0, 2.0)
const CLAW_HIGH := Vector3(4.8, 1.2, 1.6)
const CHEST := Vector3(3.0, -2.4, -2.4)
const BROW := Vector3(2.8, 3.8, -1.2)              # tipping a hat, above the eyes
const RAISE := Vector3(1.6, 6.9, 2.4)
const TUCK := Vector3(2.4, -3.4, -0.6)
const OUT := Vector3(1.0, -4.2, 5.6)
const BACK := Vector3(-1.2, -7.0, 1.4)
const SWING := Vector3(2.0, -6.8, 0.8)
const ELBOW_BACK := Vector3(-1, -0.3, 0.4)
const ELBOW_OUT := Vector3(-0.4, -0.3, 1)
const ELBOW_DOWN := Vector3(-0.2, -1, 0.6)

# The routine, in beats: per pose parameter, keys [beat, value]; a value may be {"a": .., "g": ..} per dancer (Aragorn,
# Gandalf). Values run between keys on a monotone cubic: smooth through every key, never past a held value. A key
# [beat, value, "hold"] jumps there instead.
# yaw: 0 faces the host, 180 the Deep behind the wall; Aragorn stands west of Gandalf, so facing the Deep his left hand
# is outward, and Gandalf mirrors him wherever `mirror` is 1.
const ROUTINE := {
	"yaw": [[0, 0.0], [2.0, 0.0], [3.0, 180.0], [12.0, 180.0], [12.5, 90.0], [18.5, 90.0],
		[19.5, 540.0], [34.0, 540.0], [35.0, 630.0], [41.0, 630.0], [42.0, 900.0], [46.0, 900.0],
		[47.5, 1080.0]],
	"mirror": [[0, 1.0], [41.9, 1.0], [42.0, 0.0, "hold"], [47.9, 0.0], [48.0, 1.0, "hold"]],
	"drop": [[0, 0.4], [2.0, 0.4], [2.5, 1.2], [3.0, 0.6], [10.0, 0.6], [10.5, 0.9], [12.0, 0.9], [12.5, 1.0],
		[18.5, 1.0], [19.0, 0.4], [21.0, 0.4], [21.5, 0.2], [25.0, 0.3], [26.0, 1.6], [34.0, 1.6], [35.0, 1.0],
		[41.0, 1.0], [42.0, 0.5], [48.0, 0.4]],
	"bounce": [[0, 0.0], [3.0, 0.0], [4.0, 0.35], [10.0, 0.35], [10.5, 0.0], [26.0, 0.0], [26.5, 0.3], [34.0, 0.3],
		[34.5, 0.0], [44.0, 0.0], [45.0, 0.15], [48.0, 0.0]],
	"hip": [[0, Vector3.ZERO], [3.0, Vector3(0, 0, -0.9)], [10.0, Vector3(0, 0, -0.9)], [10.5, Vector3.ZERO],
		[42.0, Vector3.ZERO], [42.2, Vector3(0, 0, 0.8)], [46.0, Vector3(0, 0, 0.8)], [48.0, Vector3.ZERO]],
	"lean": [[0, 0.0], [21.5, 0.0], [22.6, 40.0], [24.0, 40.0], [25.0, 0.0]],
	"chest": [[0, Vector3.ZERO], [3.0, Vector3(-8, 4, 6)], [6.0, Vector3(-8, 4, 6)],
		[6.35, Vector3(10, -4, 0)], [7.0, Vector3(10, -4, 0)], [7.35, Vector3(-10, -4, 0)],
		[8.0, Vector3(-10, -4, 0)], [8.35, Vector3(0, 10, 0)], [9.0, Vector3(0, 10, 0)],
		[9.35, Vector3(0, -6, 0)], [10.0, Vector3(0, -2, 0)], [10.5, Vector3(0, -6, -4)], [12.0, Vector3(0, -6, -4)],
		[12.5, Vector3(0, 6, 0)], [18.5, Vector3(0, 6, 0)], [19.5, Vector3(0, 0, 0)], [21.5, Vector3(0, -4, 0)],
		[25.0, Vector3(0, 0, 0)], [26.0, Vector3(0, 14, 0)], [34.0, Vector3(0, 14, 0)], [35.0, Vector3(0, 6, 0)],
		[41.0, Vector3(0, 6, 0)], [42.0, Vector3(0, 0, 0)], [42.2, Vector3(8, -10, -6)],
		[46.0, Vector3(8, -10, -6)], [48.0, Vector3.ZERO]],
	"head": [[0, Vector3.ZERO], [0.8, Vector3(30, 0, 0)], [1.6, Vector3(-25, 0, 0)], [2.0, Vector3.ZERO],
		[3.0, Vector3(25, 38, 8)], [6.0, Vector3(25, 38, 8)], [6.35, Vector3(-55, 0, 0)],
		[7.0, Vector3(-55, 0, 0)], [7.35, Vector3(55, 0, 0)], [8.0, Vector3(55, 0, 0)],
		[8.35, Vector3(0, -15, 0)], [9.0, Vector3(0, -15, 0)], [9.35, Vector3(0, 20, 0)],
		[10.0, Vector3(0, 0, 0)], [10.5, Vector3(-20, -18, -14)], [12.0, Vector3(-20, -18, -14)],
		[12.5, Vector3(0, 0, 0)], [18.5, Vector3.ZERO], [19.5, Vector3(0, 10, 0)], [21.0, Vector3(0, 10, 0)],
		[21.5, Vector3(0, -10, 0)], [24.0, Vector3(0, -10, 0)], [25.0, Vector3.ZERO], [26.0, Vector3(0, 12, -22)],
		[34.0, Vector3(0, 12, -22)], [35.0, Vector3.ZERO], [41.0, Vector3.ZERO],
		[42.2, {"a": Vector3(35, -32, 0), "g": Vector3(18, -14, 0)}],
		[46.0, {"a": Vector3(35, -32, 0), "g": Vector3(18, -14, 0)}], [48.0, Vector3.ZERO]],
	"shrug": [[0, Vector2.ZERO], [6.0, Vector2.ZERO], [6.35, Vector2(0, 1)], [7.0, Vector2(0, 1)],
		[7.35, Vector2(1, 0)], [8.0, Vector2(1, 0)], [8.35, Vector2(1, 1)], [9.0, Vector2(1, 1)],
		[9.35, Vector2.ZERO], [26.0, Vector2.ZERO], [26.5, Vector2(0.8, 0.8)], [34.0, Vector2(0.8, 0.8)],
		[34.5, Vector2.ZERO]],
	"hand_l": [[0, DOWN], [2.0, DOWN], [2.6, TUCK], [3.0, DIAG], [10.0, DIAG], [10.5, BROW],
		[12.0, BROW], [12.5, SWING], [18.5, SWING], [19.0, TUCK], [19.5, BROW], [21.0, BROW], [21.5, DOWN],
		[25.0, DOWN], [26.0, CLAW], [34.0, CLAW], [35.0, SWING], [41.0, SWING], [41.5, TUCK],
		[42.2, {"a": DIAG, "g": RAISE}], [46.0, {"a": DIAG, "g": RAISE}], [48.0, DOWN]],
	"hand_r": [[0, DOWN], [2.0, DOWN], [2.6, TUCK], [3.0, HIP], [10.0, HIP], [10.5, OUT],
		[12.0, OUT], [12.5, BACK], [18.5, BACK], [19.0, TUCK], [19.5, OUT], [21.0, OUT], [21.5, DOWN],
		[25.0, DOWN], [26.0, CLAW_HIGH], [34.0, CLAW_HIGH], [35.0, BACK], [41.0, BACK], [41.5, TUCK],
		[42.2, {"a": OUT, "g": HIP}], [46.0, {"a": OUT, "g": HIP}], [48.0, DOWN]],
	"pole_l": [[0, ELBOW_BACK], [2.6, ELBOW_BACK], [3.0, ELBOW_OUT], [12.0, ELBOW_OUT], [12.5, ELBOW_BACK],
		[18.5, ELBOW_BACK], [19.5, ELBOW_OUT], [21.5, ELBOW_BACK], [25.0, ELBOW_BACK], [26.0, ELBOW_DOWN],
		[34.0, ELBOW_DOWN], [35.0, ELBOW_BACK], [41.5, ELBOW_BACK], [42.2, ELBOW_OUT], [46.0, ELBOW_OUT],
		[48.0, ELBOW_BACK]],
	"pole_r": [[0, ELBOW_BACK], [2.6, ELBOW_BACK], [3.0, ELBOW_OUT], [12.0, ELBOW_OUT], [12.5, ELBOW_BACK],
		[18.5, ELBOW_BACK], [19.5, ELBOW_OUT], [21.5, ELBOW_BACK], [25.0, ELBOW_BACK], [26.0, ELBOW_DOWN],
		[34.0, ELBOW_DOWN], [35.0, ELBOW_BACK], [41.5, ELBOW_BACK], [42.2, ELBOW_OUT], [46.0, ELBOW_OUT],
		[48.0, ELBOW_BACK]],
	# feet: [forward, lift, out] from the rest stance, and how far the heel is raised (1: on the toes)
	"foot_l": [[0, Vector3.ZERO], [3.0, Vector3(0.6, 0, 0.8)], [10.0, Vector3(0.6, 0, 0.8)],
		[10.5, Vector3(0.3, 0, -0.8)], [12.0, Vector3(0.3, 0, -0.8)], [12.5, Vector3.ZERO], [18.5, Vector3.ZERO],
		[19.5, Vector3(0.3, 0, -0.8)], [21.0, Vector3(0.3, 0, -0.8)], [21.5, Vector3(0, 0, -0.5)],
		[25.0, Vector3(0, 0, -0.5)], [26.0, Vector3(0, 0, 1.0)], [34.0, Vector3(0, 0, 1.0)], [35.0, Vector3.ZERO],
		[41.5, Vector3.ZERO], [42.2, Vector3(-0.5, 0, 1.4)], [46.0, Vector3(-0.5, 0, 1.4)],
		[48.0, Vector3.ZERO]],
	"foot_r": [[0, Vector3.ZERO], [3.0, Vector3(-0.8, 0, 0.6)], [10.0, Vector3(-0.8, 0, 0.6)],
		[10.5, Vector3(0.3, 0, -0.8)], [12.0, Vector3(0.3, 0, -0.8)], [12.5, Vector3.ZERO], [18.5, Vector3.ZERO],
		[19.5, Vector3(0.3, 0, -0.8)], [21.0, Vector3(0.3, 0, -0.8)], [21.5, Vector3(0, 0, -0.5)],
		[25.0, Vector3(0, 0, -0.5)], [26.0, Vector3(0, 0, 1.0)], [34.0, Vector3(0, 0, 1.0)], [35.0, Vector3.ZERO],
		[41.5, Vector3.ZERO], [42.2, Vector3(0.9, 0, 0.6)], [46.0, Vector3(0.9, 0, 0.6)],
		[48.0, Vector3.ZERO]],
	"heel_l": [[0, 0.0], [2.2, 0.0], [2.5, 1.0], [3.0, 0.0], [10.0, 0.0], [10.5, 1.0], [12.0, 1.0],
		[12.5, 0.0], [18.5, 0.0], [18.8, 1.0], [21.0, 1.0], [21.5, 0.0], [41.0, 0.0], [41.3, 1.0], [42.0, 0.0]],
	"heel_r": [[0, 0.0], [2.2, 0.0], [2.5, 1.0], [3.0, 0.6], [10.0, 0.6], [10.5, 1.0], [12.0, 1.0],
		[12.5, 0.0], [18.5, 0.0], [18.8, 1.0], [21.0, 1.0], [21.5, 0.0], [41.0, 0.0], [41.3, 1.0], [42.0, 0.0],
		[42.2, 0.7], [46.0, 0.7], [48.0, 0.0]],
}

# Footwork that travels: [first beat, last beat, kind, direction]. Moonwalks glide backwards (a step a beat: the flat
# foot slides back past the one on its toes, then they swap); Thriller's step-drag goes to the body's right (+1) or
# left (-1), a step out and a drag in every two beats.
const TRAVEL := [[12.5, 18.5, "moon", 1], [26.0, 30.0, "thriller", 1], [30.0, 34.0, "thriller", -1],
	[35.0, 41.0, "moon", 1]]
const TRAVEL_BLEND := 0.4                  # beats the feet take into and out of travelling footwork

var error := ""
var unit_count := 0
var speed := 1.0
var duration := BEATS * 60.0 / BPM
var dancers: Array = []
var _target: Node
var _added := PackedInt64Array()


## A hero's skeleton and its parts, in its model space (Godot axes: x forward, y up, z to its right).
class Dancer:
	var instance := -1
	var key := "a"
	var parents := PackedInt32Array()
	var rest_local: Array[Transform3D] = []
	var rest: Array[Transform3D] = []
	var bones := {}
	var names := PackedStringArray()
	var late := {}                         # followers and their parts, placed after the bones they ride with
	var follow := {}                       # bone -> [the bone it rides with, its offset from it] (weapons, capes)
	var hem := PackedInt32Array()          # hems and low cape bones: carried level with the hips, tilted by a lean

	func setup(data: Array, who: String) -> String:
		key = who
		for i in data.size():
			parents.append(int(data[i].parent))
			rest_local.append(data[i].rest)
			rest.append(rest[parents[i]] * rest_local[i] if parents[i] >= 0 else rest_local[i])
			bones[String(data[i].name).to_upper()] = i
			names.append(String(data[i].name).to_upper())
		for name in ["ROOT DUMMY", "BAT_RIBS", "BAT_HEAD", "BAT_UARMR", "BAT_FARMR", "B_HANDR", "BAT_UARML",
				"BAT_FARML", "B_HANDL", "BAT_THIGHR", "BAT_CALFR", "B_TOER", "BAT_THIGHL", "BAT_CALFL", "B_TOEL"]:
			if not bones.has(name):
				return "%s has no bone %s" % [who, name]
		var pelvis: int = bones["ROOT DUMMY"]
		for i in data.size():
			if parents[i] != 0 or i == pelvis:
				continue
			var at := rest[i].origin
			var ride := -1
			for hand in ["B_HANDR", "B_HANDL"]:
				if at.distance_to(rest[bones[hand]].origin) < 2.5:
					ride = bones[hand]
			if ride < 0 and at.y > 13.0:
				ride = bones["BAT_RIBS"]
			elif ride < 0 and at.y > 4.0:
				ride = pelvis
			if ride >= 0:
				follow[i] = [ride, rest[ride].affine_inverse() * rest[i]]
			else:
				hem.append(i)
		for i in data.size():
			if follow.has(i) or (parents[i] >= 0 and late.has(parents[i])):
				late[i] = true
		return ""

	func at(name: String) -> Vector3:
		return rest[bones[name]].origin

	func weapons() -> PackedStringArray:
		return PackedStringArray(WEAPONS.filter(func(n): return bones.has(n)))


func clear() -> void:
	if is_instance_valid(_target):
		for d in dancers:
			if not d.instance in _added:
				_target.set_instance_rig_pose(d.instance, [])
				_target.set_instance_hidden_bones(d.instance, PackedStringArray())
		for id in _added:
			_target.remove_instance(id)
		_target.update_now()
	dancers.clear()
	_added = PackedInt64Array()
	_target = null
	unit_count = 0
	error = ""


func enable(objects: Node3D, settings: Dictionary = {}) -> int:
	clear()
	speed = clampf(float(settings.get("speed", 1.0)), 0.5, 1.5)
	duration = BEATS * 60.0 / BPM / speed
	for target in objects.find_children("*", "", true, false):
		if target.has_method("find_model_instances") and not target.find_model_instances("GUAragorn_SKN").is_empty():
			_target = target
			break
	if _target == null:
		error = "No Aragorn on this map: open Helm's Deep (helms-deep-battle), where he stands on the Deeping Wall"
		return 0
	if not _target.has_method("set_instance_hidden_bones"):
		error = "This engine runtime lacks the custom rig API's hidden bones and instance transforms"
		_target = null
		return 0
	var aragorn: int = _target.find_model_instances("GUAragorn_SKN")[0]
	var model: int = _target.add_model("GUGandalf_SKN")
	if model < 0:
		error = "Gandalf the White's model did not load"
		return 0
	# beside Aragorn, as the map placed him: his model's -z is his left
	var place: Transform3D = _target.get_instance_transform(aragorn) * Transform3D(Basis(), Vector3(0, 0, -GANDALF_EAST))
	var gandalf: int = _target.add_instance(model, place, "", 0.0, 1.0)
	_target.set_instance_cast_shadow(gandalf, true)
	_added.append(gandalf)
	_target.update_now()
	for pair in [[aragorn, "a"], [gandalf, "g"]]:
		var d := Dancer.new()
		d.instance = pair[0]
		var problem := d.setup(_target.get_instance_rig(pair[0]), "Aragorn" if pair[1] == "a" else "Gandalf")
		d.key = pair[1]
		if not problem.is_empty():
			clear()
			error = problem
			return 0
		_target.set_instance_hidden_bones(d.instance, d.weapons())
		dancers.append(d)
	unit_count = dancers.size()
	sample(0.0)
	return unit_count


func sample(time: float) -> void:
	if not is_instance_valid(_target):
		return
	var beat := fposmod(time * speed * BPM / 60.0, BEATS)
	for d in dancers:
		if not _target.set_instance_rig_pose(d.instance, solve(d, pose(beat, d.key))):
			push_warning("wall dance: pose rejected")
	_target.update_now()


## Between the two dancers at `time` (as sample() takes it), on the walkway, in world coordinates: what a film aims at.
func middle(time: float) -> Vector3:
	var beat := fposmod(time * speed * BPM / 60.0, BEATS)
	var sum := Vector3.ZERO
	for d in dancers:
		sum += _target.get_instance_transform(d.instance) * (pose(beat, d.key).pos as Vector3)
	return (_target as Node3D).global_transform * (sum / maxi(dancers.size(), 1))


# ---- the routine --------------------------------------------------------------------------------------------------

static func value_of(v: Variant, who: String) -> Variant:
	return v[who] if v is Dictionary else v


static func parts(v: Variant) -> PackedFloat64Array:
	if v is Vector3:
		return PackedFloat64Array([v.x, v.y, v.z])
	if v is Vector2:
		return PackedFloat64Array([v.x, v.y])
	return PackedFloat64Array([v])


static func joined(a: PackedFloat64Array, like: Variant) -> Variant:
	if like is Vector3:
		return Vector3(a[0], a[1], a[2])
	if like is Vector2:
		return Vector2(a[0], a[1])
	return a[0]


## The slope a monotone cubic takes at a key between slopes `before` and `after` (Fritsch-Butland): their harmonic
## mean, or level where the curve turns or holds.
static func slope(before: float, after: float) -> float:
	return 2.0 * before * after / (before + after) if before * after > 0.0 else 0.0


static func held(key: Array) -> bool:
	return key.size() > 2 and key[2] == "hold"


static func track(keys: Array, beat: float, who: String) -> Variant:
	if beat <= keys[0][0]:
		return value_of(keys[0][1], who)
	for i in keys.size() - 1:
		var b: Array = keys[i + 1]
		if beat > b[0]:
			continue
		var a: Array = keys[i]
		var from: Variant = value_of(a[1], who)
		if held(b):
			return from
		var span := maxf(b[0] - a[0], 1e-4)
		var u := clampf((beat - a[0]) / span, 0.0, 1.0)
		var p0 := parts(from)
		var p1 := parts(value_of(b[1], who))
		var first := i == 0 or held(a)
		var last := i + 2 >= keys.size() or held(keys[i + 2])
		var pp := p0 if first else parts(value_of(keys[i - 1][1], who))
		var pn := p1 if last else parts(value_of(keys[i + 2][1], who))
		var before := 1.0 if first else maxf(a[0] - keys[i - 1][0], 1e-4)
		var after := 1.0 if last else maxf(keys[i + 2][0] - b[0], 1e-4)
		var h00 := 2 * u * u * u - 3 * u * u + 1
		var h10 := u * u * u - 2 * u * u + u
		var h01 := -2 * u * u * u + 3 * u * u
		var h11 := u * u * u - u * u
		var out := PackedFloat64Array()
		for c in p0.size():
			var d := (p1[c] - p0[c]) / span
			var m0 := slope((p0[c] - pp[c]) / before, d)
			var m1 := slope(d, (pn[c] - p1[c]) / after)
			out.append(h00 * p0[c] + h10 * span * m0 + h01 * p1[c] + h11 * span * m1)
		return joined(out, from)
	return value_of(keys[-1][1], who)


## The pose parameters at `beat` for dancer `who` ("a" or "g").
static func pose(beat: float, who: String) -> Dictionary:
	var p := {}
	for name in ROUTINE:
		p[name] = track(ROUTINE[name], beat, who)
	p["drop"] += p.bounce * (1.0 - cos(TAU * beat)) * 0.5
	p["chest"] += Vector3(0, 1.5 * sin(TAU * beat / 4.0), 0)        # breathing
	p["pos"] = Vector3.ZERO
	p["yaw_lag"] = track(ROUTINE.yaw, beat - SWAY_LAG, who)
	for w in TRAVEL:
		travel(p, w, beat)
	if who == "g" and p.mirror > 0.5:
		p = mirrored(p)
	return p


## A travelling window's share of the body's way and, while inside it, its footwork.
static func travel(p: Dictionary, w: Array, beat: float) -> void:
	var length: float = w[1] - w[0]
	var s := clampf(beat - w[0], 0.0, length)
	var facing := Basis(Vector3.UP, deg_to_rad(track(ROUTINE.yaw, (w[0] + w[1]) * 0.5, "a")))
	var blend := clampf(minf(beat - w[0] + TRAVEL_BLEND, w[1] + TRAVEL_BLEND - beat) / TRAVEL_BLEND, 0.0, 1.0)
	blend = blend * blend * (3.0 - 2.0 * blend)
	if w[2] == "moon":
		p.pos += facing * Vector3(-STEP * glide(s, length), 0, 0)   # straight back, a step a beat once going
		if blend <= 0.0:
			return
		var n := int(floor(minf(s, length - 1e-4)))
		var u := clampf(s - n, 0.0, 1.0)
		var swap := smoothstep(0.75, 1.0, u)
		var toe := Vector3((u - 0.5) * STEP, 0, -0.6)           # standing on its toes, still on the walkway
		var flat := Vector3((0.5 - u) * STEP, 0, -0.6)          # sliding back past it
		var right_on_toe := n % 2 == 0
		_blend_foot(p, "r", toe if right_on_toe else flat, (1.0 - swap) if right_on_toe else swap, blend)
		_blend_foot(p, "l", flat if right_on_toe else toe, swap if right_on_toe else (1.0 - swap), blend)
	elif w[2] == "thriller":
		var dir: float = w[3]
		var cycles := s / 2.0
		var n := floorf(minf(cycles, length / 2.0 - 1e-4))
		var u := clampf(cycles - n, 0.0, 1.0)
		var hips := SHUFFLE * (n + smoothstep(0.0, 1.0, u))
		p.pos += facing * Vector3(0, 0, dir * hips)
		if blend <= 0.0:
			return
		var k1 := clampf(u * 2.0, 0.0, 1.0)
		var k2 := clampf(u * 2.0 - 1.0, 0.0, 1.0)
		var lead := SHUFFLE * (n + smoothstep(0.0, 1.0, k1)) - hips
		var trail := SHUFFLE * (n + k2) - hips
		var lead_side := "r" if dir > 0 else "l"
		var trail_side := "l" if dir > 0 else "r"
		# out is measured away from the body's middle on each side
		_blend_foot(p, lead_side, Vector3(0, 1.4 * sin(PI * k1), 1.0 + lead), 0.3 * sin(PI * k1), blend)
		_blend_foot(p, trail_side, Vector3(0, 0, 1.0 - trail), 0.0, blend)
		p.chest += Vector3(dir * 10.0 * sin(PI * k1), 0, 0) * blend
		p.hip += Vector3(0, 0, dir * 0.6 * (k1 - k2)) * blend


## The beats of glide a moonwalk `length` long has covered after `s`: speeding up over MOON_EASE, slowing down over
## the last.
static func glide(s: float, length: float) -> float:
	var a := MOON_EASE
	if s < a:
		return s * s / (2.0 * a)
	if s > length - a:
		return length - a - (length - s) * (length - s) / (2.0 * a)
	return s - a / 2.0


static func _blend_foot(p: Dictionary, side: String, foot: Vector3, heel: float, w: float) -> void:
	p["foot_" + side] = (p["foot_" + side] as Vector3).lerp(foot, w)
	p["heel_" + side] = lerpf(p["heel_" + side], heel, w)


## The pose seen in a mirror across the body's middle: left and right swap, turns and tilts reverse.
static func mirrored(p: Dictionary) -> Dictionary:
	var m := p.duplicate()
	for pair in [["hand_l", "hand_r"], ["pole_l", "pole_r"], ["foot_l", "foot_r"], ["heel_l", "heel_r"]]:
		m[pair[0]] = p[pair[1]]
		m[pair[1]] = p[pair[0]]
	m["shrug"] = Vector2(p.shrug.y, p.shrug.x)
	m["chest"] = Vector3(-p.chest.x, p.chest.y, -p.chest.z)
	m["head"] = Vector3(-p.head.x, p.head.y, -p.head.z)
	m["hip"] = Vector3(p.hip.x, p.hip.y, -p.hip.z)
	return m


# ---- the pose solver ----------------------------------------------------------------------------------------------

## Euler turns in the body's frame, degrees: about up (to the left), then about right (pitch: forward) and forward
## (roll: to the right).
static func turn(v: Vector3) -> Basis:
	return Basis(Vector3.UP, deg_to_rad(v.x)) * Basis(Vector3(0, 0, 1), deg_to_rad(-v.y)) * Basis(Vector3(1, 0, 0), deg_to_rad(v.z))


static func frame(d: Vector3, h: Vector3) -> Basis:
	var x := d.normalized()
	var y := (h - x * h.dot(x)).normalized()
	return Basis(x, y, x.cross(y))


## Every bone's model-space transform for pose `p`.
static func solve(d: Dancer, p: Dictionary) -> Array[Transform3D]:
	var g: Array[Transform3D] = []
	g.resize(d.rest.size())
	var done := {}
	var body := Transform3D(Basis(Vector3.UP, deg_to_rad(p.yaw)), p.pos)
	var pelvis: int = d.bones["ROOT DUMMY"]
	# feet first: the lean pivots about them
	var feet := {}
	for side in ["r", "l"]:
		var s := 1.0 if side == "r" else -1.0
		var off: Vector3 = p["foot_" + side]
		var ankle := d.at("B_TOE" + side.to_upper())
		var base := Vector3(ankle.x + off.x, 0.0, ankle.z + s * off.z)
		var tip := deg_to_rad(TOE_ANGLE * clampf(p["heel_" + side], 0.0, 1.0))
		var ball := base + Vector3(BALL, 0, 0)
		var pitch := Basis(Vector3(0, 0, 1), -tip)
		var at := ball + pitch * Vector3(-BALL, ankle.y, 0) + Vector3(0, off.y, 0)
		feet[side] = [at, pitch]
	var pivot: Vector3 = (feet.r[0] + feet.l[0]) * 0.5
	pivot.y = 0.0
	var lean := Basis(Vector3(0, 0, 1), deg_to_rad(-p.lean))
	var hips := lean
	var hip_at: Vector3 = d.at("ROOT DUMMY") + p.hip + Vector3(0, -p.drop, 0)
	hip_at = pivot + lean * (hip_at - pivot)
	g[0] = body * d.rest[0]
	g[pelvis] = Transform3D(body.basis * hips * d.rest[pelvis].basis, body * hip_at)
	done[0] = true
	done[pelvis] = true
	var hips_frame := body.basis * hips
	var chest_turn := turn(p.chest)
	var spine := ["B_WAIST", "BAT_RIBS"].filter(func(n): return d.bones.has(n))
	var share := Basis(Quaternion.IDENTITY.slerp(chest_turn.get_rotation_quaternion(), 1.0 / spine.size()))
	var chest_frame := hips_frame * chest_turn
	for i in d.rest.size():
		if done.has(i):
			continue
		var parent := d.parents[i]
		if d.late.has(i):
			continue                                              # after the bone it rides with
		if d.hem.has(i):
			var trail := Transform3D(Basis(Vector3.UP, deg_to_rad(p.yaw_lag)), p.pos)   # swinging after the turn
			g[i] = Transform3D(trail.basis * lean * d.rest[i].basis,
				trail * (pivot + lean * (d.rest[i].origin + Vector3(p.hip.x, -p.drop * 0.3, p.hip.z) - pivot)))
			done[i] = true
			continue
		g[i] = g[parent] * d.rest_local[i]
		var name := d.names[i]
		if name in spine:
			var frame_now := hips_frame
			g[i].basis = (frame_now * share * frame_now.inverse()) * g[i].basis
			hips_frame = hips_frame * share
		elif name == "BAT_HEAD":
			g[i].basis = (chest_frame * turn(p.head) * chest_frame.inverse()) * g[i].basis
		elif name == "BAT_UARMR" or name == "BAT_UARML":
			var side := name.right(1).to_lower()
			_arm(d, g, i, side, p, chest_frame)
			done[d.bones["BAT_FARM" + side.to_upper()]] = true
			done[d.bones["B_HAND" + side.to_upper()]] = true
		elif name == "BAT_THIGHR" or name == "BAT_THIGHL":
			var side := name.right(1).to_lower()
			_leg(d, g, i, side, body, feet[side])
			done[d.bones["BAT_CALF" + side.to_upper()]] = true
			done[d.bones["B_TOE" + side.to_upper()]] = true
		elif name.begins_with("B_CLAV"):
			var child_side := _clavicle_side(d, i)
			var amount: float = p.shrug.x if child_side == "l" else p.shrug.y
			var lift := Basis(Vector3(1, 0, 0), deg_to_rad(16.0 * amount * (1.0 if child_side == "l" else -1.0)))
			g[i].basis = (chest_frame * lift * chest_frame.inverse()) * g[i].basis
		done[i] = true
	for i in d.rest.size():                                       # weapons and capes, then their own parts
		if d.follow.has(i):
			g[i] = g[d.follow[i][0]] * d.follow[i][1]
		elif d.late.has(i):
			g[i] = g[d.parents[i]] * d.rest_local[i]
	for i in d.rest.size():
		g[i] = g[i].orthonormalized()
	return g


## Which side a clavicle carries, by its upper arm (the models name some clavicles for the other side).
static func _clavicle_side(d: Dancer, i: int) -> String:
	return "r" if d.parents[d.bones["BAT_UARMR"]] == i else "l"


static func _arm(d: Dancer, g: Array[Transform3D], i: int, side: String, p: Dictionary, chest_frame: Basis) -> void:
	var s := 1.0 if side == "r" else -1.0
	var hand: Vector3 = p["hand_" + side]
	var pole: Vector3 = p["pole_" + side]
	var ribs: int = d.bones["BAT_RIBS"]
	var carried := g[ribs] * d.rest[ribs].affine_inverse()        # rest model space -> where the chest is now
	var target := carried * (d.rest[i].origin + Vector3(hand.x, hand.y, s * hand.z))
	var bend := carried.basis * Vector3(pole.x, pole.y, s * pole.z)
	_two_bone(d, g, i, d.bones["BAT_FARM" + side.to_upper()], d.bones["B_HAND" + side.to_upper()], target, bend,
		Vector3(-1, 0, 0), null)


static func _leg(d: Dancer, g: Array[Transform3D], i: int, side: String, body: Transform3D, foot: Array) -> void:
	var s := 1.0 if side == "r" else -1.0
	var toe: int = d.bones["B_TOE" + side.to_upper()]
	var knee := body.basis * Vector3(1, 0, 0.15 * s)
	_two_bone(d, g, i, d.bones["BAT_CALF" + side.to_upper()], toe, body * (foot[0] as Vector3), knee, Vector3(1, 0, 0),
		body.basis * (foot[1] as Basis))


## Turn a limb (upper, lower, end) so its end reaches `target`, the middle joint bending towards `pole`. The bones
## turn from their rest pose (bent towards `rest_pole`) by the turn that carries each bone's direction and the limb's
## hinge axis to the new ones, so they keep their twist. `end_turn` (a Basis) sets the end bone's turn from rest;
## null keeps it on the lower bone.
static func _two_bone(d: Dancer, g: Array[Transform3D], a: int, b: int, c: int, target: Vector3, pole: Vector3,
		rest_pole: Vector3, end_turn: Variant) -> void:
	var r0 := d.rest[a].origin
	var r1 := d.rest[b].origin
	var r2 := d.rest[c].origin
	var first := r0.distance_to(r1)
	var second := r1.distance_to(r2)
	var root := g[a].origin
	var span := target - root
	var dir := span.normalized()
	var reach := clampf(span.length(), absf(first - second) + 0.01, first + second - 0.01)
	var side := (pole - dir * pole.dot(dir)).normalized()
	if side.is_zero_approx():
		side = dir.cross(Vector3(0, 0, 1)).normalized()
	var along := (first * first - second * second + reach * reach) / (2.0 * reach)
	var joint := root + dir * along + side * sqrt(maxf(0.0, first * first - along * along))
	var tip := root + dir * reach
	var hinge := side.cross(dir).normalized()
	var rest_dir := (r2 - r0).normalized()
	var rest_hinge := (rest_pole - rest_dir * rest_pole.dot(rest_dir)).normalized().cross(rest_dir)
	var upper := frame(joint - root, hinge) * frame(r1 - r0, rest_hinge).transposed()
	var lower := frame(tip - joint, hinge) * frame(r2 - r1, rest_hinge).transposed()
	g[a] = Transform3D(upper * d.rest[a].basis, root)
	g[b] = Transform3D(lower * d.rest[b].basis, joint)
	if end_turn == null:
		g[c] = Transform3D(lower * d.rest[c].basis, tip)
	else:
		g[c] = Transform3D(end_turn * d.rest[c].basis, tip)
