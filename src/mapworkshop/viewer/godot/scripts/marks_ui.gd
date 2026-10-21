## The marking controls, as the studio viewer has them (docs/viewer.md, "Marking the map for an agent"): the palette at
## the top left (Navigate, Pin, Circle, Rectangle, Freehand; Undo, Delete, Clear all, Copy for agent), the marks panel
## at the right (what each mark covers, from the companion) and a status line at the bottom.
class_name MarksUI
extends CanvasLayer

## A tool armed: "pin", "circle", "rect", "freehand", or null (Navigate).
signal tool_chosen(tool)
## A command button: "undo", "delete", "clear" or "copy".
signal command(name: String)

const TOOLS := [["", "Navigate", "Navigate: the mouse moves the camera"], ["pin", "Pin", "Pin: click a point"],
	["circle", "Circle", "Circle: drag from the centre outwards"],
	["rect", "Rectangle", "Rectangle: drag from corner to corner, lined up with the screen"],
	["freehand", "Freehand", "Freehand: hold the button and draw; a path whose ends meet is an area"]]
const COMMANDS := [["undo", "Undo", "Undo the last mark change (Ctrl+Z)"], ["delete", "Delete", "Delete the selected mark (Del)"],
	["clear", "Clear all", "Remove every mark (Ctrl+Z brings them back)"],
	["copy", "Copy for agent", "Put the marks and what they cover on the clipboard, for an agent's prompt"]]
const STYLES := {"head": Color(1, 1, 1), "body": Color(0.86, 0.86, 0.86), "muted": Color(0.62, 0.62, 0.62)}

var _tool_buttons := {}
var _panel: VBoxContainer
var _panel_box: PanelContainer
var _status: Label
var _status_until := 0.0
var _hint := ""


func _ready() -> void:
	var frame := PanelContainer.new()
	frame.position = Vector2(12, 40)
	var palette := HBoxContainer.new()
	frame.add_child(palette)
	var group := ButtonGroup.new()
	for t in TOOLS:
		var b := Button.new()
		b.text = t[1]
		b.tooltip_text = t[2]
		b.toggle_mode = true
		b.button_group = group
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func() -> void: tool_chosen.emit(null if t[0] == "" else t[0]))
		palette.add_child(b)
		_tool_buttons[t[0]] = b
	_tool_buttons[""].button_pressed = true
	palette.add_child(VSeparator.new())
	for c in COMMANDS:
		var b := Button.new()
		b.text = c[1]
		b.tooltip_text = c[2]
		b.focus_mode = Control.FOCUS_NONE
		b.pressed.connect(func() -> void: command.emit(c[0]))
		palette.add_child(b)
	add_child(frame)
	_panel_box = PanelContainer.new()
	_panel_box.anchor_left = 1.0
	_panel_box.anchor_right = 1.0
	_panel_box.offset_left = -380
	_panel_box.offset_right = -12
	_panel_box.offset_top = 52
	_panel_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel = VBoxContainer.new()
	_panel_box.add_child(_panel)
	_panel_box.visible = false
	add_child(_panel_box)
	_status = Label.new()
	_status.anchor_top = 1.0
	_status.anchor_bottom = 1.0
	_status.offset_left = 12
	_status.offset_top = -30
	_status.add_theme_color_override("font_outline_color", Color.BLACK)
	_status.add_theme_constant_override("outline_size", 4)
	add_child(_status)


func _process(_delta: float) -> void:
	_status.text = _hint if Time.get_ticks_msec() / 1000.0 > _status_until else _status.text


## The palette's armed tool, as the companion's marks message has it.
func show_tool(tool) -> void:
	var key := "" if tool == null else String(tool)
	if _tool_buttons.has(key):
		_tool_buttons[key].button_pressed = true


func set_hint(hint) -> void:
	_hint = "" if hint == null else String(hint)


func set_status(text: String, seconds: float) -> void:
	_status.text = text
	_status_until = Time.get_ticks_msec() / 1000.0 + seconds


## The panel with the marks or without them (M).
func show_panel(shown: bool) -> void:
	_panel_box.visible = shown and _panel.get_child_count() > 0


## The marks panel: [text, style] lines (marking.summary_lines); empty hides it.
func set_panel(lines: Array, shown: bool) -> void:
	for child in _panel.get_children():
		child.queue_free()
	for line in lines:
		var label := Label.new()
		label.text = line[0]
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.custom_minimum_size = Vector2(350, 0)
		label.max_lines_visible = 3          # a long list of objects ends in an ellipsis; Copy for agent has it all
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		label.add_theme_color_override("font_color", STYLES.get(line[1], STYLES.body))
		_panel.add_child(label)
	_panel_box.visible = shown and not lines.is_empty()
