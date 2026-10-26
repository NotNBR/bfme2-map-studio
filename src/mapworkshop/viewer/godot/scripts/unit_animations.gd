## Army preview: sixteen shared phases, with one renderer update per instancer.
extends Node3D
const STOMP := "res://scripts/animation/uruk_pike_stomp.gd"
const MAX_PHASES := 16
var rigs: Array[Skeleton3D] = []
var players: Array[AnimationPlayer] = []
var offsets: Array[float] = []
var duration := 1.4
var speed := 1.0
var error := ""
var unit_count := 0
var _groups: Array[Dictionary] = []
var _targets: Array[Node] = []

func clear() -> void:
	for group in _groups:
		if is_instance_valid(group.target): group.target.set_instances_rig_pose(group.ids, [])
	for target in _targets:
		if is_instance_valid(target): target.update_now()
	for child in get_children(): child.free()
	rigs.clear()
	players.clear()
	offsets.clear()
	_groups.clear()
	_targets.clear()
	unit_count = 0
	error = ""

func enable(objects: Node3D, settings: Dictionary = {}) -> int:
	clear()
	speed = clampf(float(settings.get("speed", 1.0)), 0.25, 2.0)
	if not ResourceLoader.exists(STOMP):
		error = "This engine runtime does not include custom unit animations"
		return 0
	var matches: Array[Dictionary] = []
	for target in objects.find_children("*", "", true, false):
		if not target.has_method("find_model_instances"): continue
		if not target.has_method("set_instances_rig_pose"):
			error = "This engine runtime needs the batched custom animation update"
			return 0
		var ids: PackedInt64Array = target.find_model_instances("IUPikeman_SKN")
		if not ids.is_empty(): matches.append({"target": target, "ids": ids})
	var author = load(STOMP)
	var clip: Animation
	for entry in matches:
		var target: Node = entry.target
		var ids: PackedInt64Array = entry.ids
		target.set_instance_pose(ids[0], "IUPIKEMAN_SKL.IUPikeman_IDLA", 0.0, "", 0.0, 0.0)
		target.update_now()
		var data: Array = target.get_instance_rig(ids[0])
		_targets.append(target)
		var phases := mini(MAX_PHASES, ids.size())
		for phase in phases:
			var members := PackedInt64Array()
			for i in ids.size():
				if (i * 37) % phases == phase: members.append(ids[i])
			var actor := Node3D.new()
			add_child(actor)
			var rig := Skeleton3D.new()
			rig.name = "Rig"
			actor.add_child(rig)
			for bone in data: rig.add_bone(bone.name)
			for i in data.size():
				rig.set_bone_parent(i, data[i].parent)
				rig.set_bone_rest(i, data[i].rest)
				var local: Transform3D = data[i].pose
				if data[i].parent >= 0: local = (data[data[i].parent].pose as Transform3D).affine_inverse() * local
				rig.set_bone_pose(i, local)
			if clip == null: clip = author.create(rig, settings)
			if clip == null:
				clear()
				error = "The unit rig cannot play the pike-stomp example"
				return 0
			var library := AnimationLibrary.new()
			library.add_animation("stomp", clip)
			var player := AnimationPlayer.new()
			actor.add_child(player)
			player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
			player.add_animation_library("custom", library)
			player.play("custom/stomp")
			duration = clip.length
			offsets.append(float(phase) / maxi(1, phases - 1) * clampf(float(settings.get("phase_spread", author.PHASE_SPREAD)), 0.0, 0.35))
			rigs.append(rig)
			players.append(player)
			_groups.append({"target": target, "ids": members})
		unit_count += ids.size()
	sample(0.0)
	return unit_count

func sample(time: float) -> void:
	for i in players.size():
		players[i].seek(fposmod(time * speed + offsets[i], duration), true)
		var pose: Array[Transform3D] = []
		for bone in rigs[i].get_bone_count(): pose.append(rigs[i].get_bone_global_pose(bone))
		_groups[i].target.set_instances_rig_pose(_groups[i].ids, pose)
	for target in _targets: target.update_now()
