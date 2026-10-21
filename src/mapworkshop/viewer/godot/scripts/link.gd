## The viewer's end of the companion's socket (viewer/godot_link.py): one JSON object per line, both ways, on
## 127.0.0.1. Messages sent before the connection stands wait for it; poll() returns the messages that arrived since
## the last call; closed() says the companion has gone.
class_name Link
extends RefCounted

var _peer := StreamPeerTCP.new()
var _buffer := PackedByteArray()
var _was_connected := false
var _queue := []


func open(port: int) -> Error:
	return _peer.connect_to_host("127.0.0.1", port)


func send(message: Dictionary) -> void:
	_queue.append(message)
	_flush()


func _flush() -> void:
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return
	for message in _queue:
		_peer.put_data((JSON.stringify(message) + "\n").to_utf8_buffer())
	_queue.clear()


func poll() -> Array:
	_peer.poll()
	var messages := []
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return messages
	_was_connected = true
	_flush()
	var available := _peer.get_available_bytes()
	if available > 0:
		var got: Array = _peer.get_data(available)
		if got[0] == OK:
			_buffer.append_array(got[1])
	while true:
		var end := _buffer.find(10)        # "\n"
		if end < 0:
			break
		var line := _buffer.slice(0, end).get_string_from_utf8()
		_buffer = _buffer.slice(end + 1)
		var message = JSON.parse_string(line)
		if message is Dictionary:
			messages.append(message)
	return messages


## The companion has gone, or could not be reached at all.
func closed() -> bool:
	var status := _peer.get_status()
	return status == StreamPeerTCP.STATUS_ERROR or (_was_connected and status == StreamPeerTCP.STATUS_NONE)
