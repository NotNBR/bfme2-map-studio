## The viewer's frame around the map: the toolbar along the top, the marks rail at the left and the marks panel at
## the right, the camera bar along the bottom, the toasts under the toolbar (a build or a reload: what it is doing,
## how it ended), and the controls (F1) over the middle. In Photo mode the marks give way to the framing aids
## (photo_frame) and a short list of Photo mode's controls above the camera bar. `chrome` hides all of it for a
## picture.
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

View
  1  objects     2  water     6  fog     7  walkable     8  river flow arrows     G  grid     B  map border     M  marks

  V  Photo mode     P  screenshot     F5  read the map again     Ctrl+B  build     F1  these controls

Views
  Ctrl+1-9  go to the view saved there     Ctrl+Shift+1-9  save the view there
  Ctrl+C  copy the view as a mw render command"""

## Photo mode's controls, above the camera bar (viewer/camerabar.py's PHOTO_KEYS).
const PHOTO_KEYS := """Photo mode
  Mouse  look        Right drag  slide        W A S D  fly             Space / C  up / down
  Wheel  forward / back        Q / E, R  roll, level        Alt+wheel  focal length
  Shift+wheel  focus distance        Middle click  focus on the centre        Shift / Ctrl  faster / slower
  Esc  free the mouse        V  back to Edit"""

var toolbar: Toolbar
var marks: MarksUI
var bar: CameraBar
var photo_frame: PhotoFrame
var _photo_keys: PanelContainer
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
	photo_frame = PhotoFrame.new()
	photo_frame.visible = false
	_root.add_child(photo_frame)
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
	_photo_keys = PanelContainer.new()
	_photo_keys.add_theme_stylebox_override("panel", UITheme.box(UITheme.BAR, 8, 10))
	_photo_keys.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var keys := Label.new()
	keys.text = PHOTO_KEYS
	keys.add_theme_color_override("font_color", UITheme.MUTED)
	_photo_keys.add_child(keys)
	_photo_keys.visible = false
	_root.add_child(_photo_keys)


func _process(_delta: float) -> void:
	marks.place(toolbar.size.y, bar.size.y)
	_toast.position = Vector2(150, toolbar.size.y + 8)
	if _toast.visible and Time.get_ticks_msec() / 1000.0 > _toast_until:
		_toast.visible = false
	_help.position = (_root.size - _help.size) / 2.0
	_photo_keys.position = Vector2(8, _root.size.y - bar.size.y - _photo_keys.size.y - 8)


## A toast: "done" (green), "failed" (red) or "busy", with a title and a detail line, for `seconds`.
func toast(kind: String, title: String, detail: String, seconds: float) -> void:
	_toast_title.text = title
	_toast_title.add_theme_color_override("font_color", {"done": UITheme.GOOD, "failed": UITheme.BAD}.get(kind, UITheme.TEXT))
	_toast_detail.text = detail
	_toast_detail.visible = not detail.is_empty()
	_toast.reset_size()
	_toast.visible = true
	_toast_until = Time.get_ticks_msec() / 1000.0 + seconds


## Photo mode (`on`) or Edit: the framing aids and Photo's controls, or the marks.
func set_photo_mode(on: bool) -> void:
	photo_frame.visible = on
	_photo_keys.visible = on
	marks.visible = not on
	bar.set_mode("photo" if on else "edit")


func toggle_help() -> void:
	_help.visible = not _help.visible


## The frame shown or hidden: hidden for a picture and in Photo mode.
var chrome := true:
	set(on):
		chrome = on
		if _root != null:
			_root.visible = on
