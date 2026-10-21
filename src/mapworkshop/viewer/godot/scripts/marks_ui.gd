## The marking controls (docs/viewer.md, "Marking the map for an agent"): a rail down the left edge with the tools
## (Navigate, Pin, Circle, Rectangle, Freehand) and the commands (Undo, Delete, Clear all, Copy for agent), and the
## marks panel at the right with what each mark covers, from the companion.
class_name MarksUI
extends Control

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
const STYLES := {"head": UITheme.TEXT, "body": Color(0.80, 0.81, 0.84), "muted": UITheme.MUTED}
const PANEL_WIDTH := 376.0

var _tool_buttons := {}
var _rail: PanelContainer
var _panel: VBoxContainer
var _panel_box: PanelContainer
var _top := 0.0
var _bottom := 0.0


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rail = PanelContainer.new()
	var column := VBoxContainer.new()
	_rail.add_child(column)
	var group := ButtonGroup.new()
	for t in TOOLS:
		var b := _button(column, t[1], t[2])
		b.toggle_mode = true
		b.button_group = group
		b.pressed.connect(func() -> void: tool_chosen.emit(null if t[0] == "" else t[0]))
		_tool_buttons[t[0]] = b
	_tool_buttons[""].button_pressed = true
	column.add_child(HSeparator.new())
	for c in COMMANDS:
		_button(column, c[1], c[2]).pressed.connect(func() -> void: command.emit(c[0]))
	add_child(_rail)
	_panel_box = PanelContainer.new()
	_panel_box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel = VBoxContainer.new()
	_panel_box.add_child(_panel)
	_panel_box.visible = false
	add_child(_panel_box)


func _button(column: VBoxContainer, text: String, tip: String) -> Button:
	var b := Button.new()
	b.text = text
	b.tooltip_text = tip
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	b.focus_mode = Control.FOCUS_NONE
	column.add_child(b)
	return b


## Between the bars: `top` and `bottom` are their heights.
func place(top: float, bottom: float) -> void:
	_top = top
	_bottom = bottom


func _process(_delta: float) -> void:
	_rail.position = Vector2(0, _top + 8)
	_panel_box.custom_minimum_size = Vector2(PANEL_WIDTH, 0)
	_panel_box.position = Vector2(size.x - PANEL_WIDTH - 8, _top + 8)


## The palette's armed tool, as the companion's marks message has it.
func show_tool(tool) -> void:
	var key := "" if tool == null else String(tool)
	if _tool_buttons.has(key):
		_tool_buttons[key].button_pressed = true


## The panel with the marks or without them (M).
func show_panel(shown: bool) -> void:
	_panel_box.visible = shown and _panel.get_child_count() > 0


## The marks panel: [text, style] lines (marking.summary_lines); empty hides it.
func set_panel(lines: Array, shown: bool) -> void:
	for child in _panel.get_children():
		_panel.remove_child(child)
		child.queue_free()
	for line in lines:
		var label := Label.new()
		label.text = line[0]
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.custom_minimum_size = Vector2(PANEL_WIDTH - 16, 0)
		label.max_lines_visible = 3          # a long list of objects ends in an ellipsis; Copy for agent has it all
		label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		label.add_theme_color_override("font_color", STYLES.get(line[1], STYLES.body))
		_panel.add_child(label)
	_panel_box.reset_size()
	_panel_box.visible = shown and not lines.is_empty()
