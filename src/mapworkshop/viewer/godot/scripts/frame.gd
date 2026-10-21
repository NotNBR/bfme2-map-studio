## The viewer's frame around the map: the toolbar along the top, the marks rail at the left and the marks panel at
## the right, the camera bar along the bottom, the toasts under the toolbar (a build or a reload: what it is doing,
## how it ended), and the controls (F1) over the middle. `chrome` hides all of it for a picture or Photo mode.
class_name Frame
extends CanvasLayer

const HELP := """Edit camera
  Left drag  orbit around the focus point        Right or middle drag  grab and pan the ground
  Wheel  zoom towards the cursor                 Double-click  fly to the clicked point
  W A S D / arrows  move (Shift faster, Ctrl slower)
  Q / E  rotate     R / F  tilt     Z / X  zoom     Space or Home  the whole map     T  top-down

Marks (the rail at the left)
  Click a mark to select it, drag it to move it, drag its handles to resize or rotate it (Shift snaps to 15 degrees)
  Del  delete the selected mark     Ctrl+Z  undo     Esc  step back: drawing, selection, tool

  1  objects     2  water     M  marks     P  screenshot     F1  these controls"""

var toolbar: Toolbar
var marks: MarksUI
var bar: CameraBar
var _root: Control
var _toast: PanelContainer
var _toast_title: Label
var _toast_detail: Label
var _toast_until := 0.0
var _help: PanelContainer


func _ready() -> void:
	_root = Control.new()
	_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_root.theme = UITheme.make()
	add_child(_root)
	marks = MarksUI.new()
	_root.add_child(marks)
	toolbar = Toolbar.new()
	_root.add_child(toolbar)
	bar = CameraBar.new()
	_root.add_child(bar)
	_toast = PanelContainer.new()
	_toast.add_theme_stylebox_override("panel", UITheme.box(UITheme.RAISED, 6, 10))
	_toast.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var lines := VBoxContainer.new()
	_toast_title = Label.new()
	_toast_detail = Label.new()
	_toast_detail.add_theme_color_override("font_color", UITheme.MUTED)
	lines.add_child(_toast_title)
	lines.add_child(_toast_detail)
	_toast.add_child(lines)
	_toast.visible = false
	_root.add_child(_toast)
	_help = PanelContainer.new()
	_help.add_theme_stylebox_override("panel", UITheme.box(UITheme.BAR, 8, 18))
	var text := Label.new()
	text.text = HELP
	_help.add_child(text)
	_help.visible = false
	_help.set_anchors_preset(Control.PRESET_CENTER)
	_root.add_child(_help)


func _process(_delta: float) -> void:
	marks.place(toolbar.size.y, bar.size.y)
	_toast.position = Vector2(150, toolbar.size.y + 8)
	if _toast.visible and Time.get_ticks_msec() / 1000.0 > _toast_until:
		_toast.visible = false
	_help.position = (_root.size - _help.size) / 2.0


## A toast: "done" (green), "failed" (red) or "busy", with a title and a detail line, for `seconds`.
func toast(kind: String, title: String, detail: String, seconds: float) -> void:
	_toast_title.text = title
	_toast_title.add_theme_color_override("font_color", {"done": UITheme.GOOD, "failed": UITheme.BAD}.get(kind, UITheme.TEXT))
	_toast_detail.text = detail
	_toast_detail.visible = not detail.is_empty()
	_toast.reset_size()
	_toast.visible = true
	_toast_until = Time.get_ticks_msec() / 1000.0 + seconds


func toggle_help() -> void:
	_help.visible = not _help.visible


## The frame shown or hidden: hidden for a picture and in Photo mode.
var chrome := true:
	set(on):
		chrome = on
		if _root != null:
			_root.visible = on
