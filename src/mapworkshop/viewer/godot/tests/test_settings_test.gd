## Quick-settings UI round trip: saved values populate controls and Save emits the selected settings.
extends SceneTree
var saved := {}
func _initialize() -> void:
 call_deferred("run")
func run() -> void:
 var toolbar = load("res://scripts/toolbar.gd").new()
 root.add_child(toolbar)
 toolbar._test_settings={"resolution":"2560x1440","window_mode":"windowed","grass":true,"ground_detail":true,"fog":false}
 toolbar.test_settings_chosen.connect(func(value: Dictionary): saved=value)
 toolbar._show_test_settings()
 await process_frame
 var controls: Dictionary = toolbar._test_controls
 var ok: bool = controls.resolution.get_item_metadata(controls.resolution.selected)=="2560x1440"
 controls.resolution.select(2)
 controls.grass.button_pressed=false
 controls.fog.button_pressed=true
 for i in 4: await process_frame
 await RenderingServer.frame_post_draw
 for arg in OS.get_cmdline_user_args():
  if arg.begins_with("--panel-shot="):
   toolbar._test_dialog.get_texture().get_image().save_png(arg.trim_prefix("--panel-shot="))
 toolbar._test_dialog.confirmed.emit()
 ok = ok and saved.get("resolution")=="1920x1080" and saved.get("grass")==false and saved.get("fog")==true
 toolbar._test_dialog.hide()
 toolbar._show_test_settings()
 ok = ok and toolbar._test_controls.resolution.get_item_metadata(toolbar._test_controls.resolution.selected)=="1920x1080"
 print("TEST SETTINGS PANEL ","PASS" if ok else "FAIL")
 toolbar.queue_free()
 quit(0 if ok else 1)
