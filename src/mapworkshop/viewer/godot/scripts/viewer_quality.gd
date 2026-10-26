## Studio viewport presets. They change rendering only; map content and game launch settings stay separate.
class_name ViewerQuality
extends RefCounted

const FILE := "user://studio-graphics.cfg"
const DEFAULT := "High"
const NAMES := ["Very Low", "Low", "Medium", "High", "Ultra High"]
## Render scale, MSAA, screen-space AA, anisotropic filtering. UI always renders at native resolution.
const PRESETS := {
	"Very Low": [0.5, Viewport.MSAA_DISABLED, Viewport.SCREEN_SPACE_AA_DISABLED, Viewport.ANISOTROPY_DISABLED],
	"Low": [0.65, Viewport.MSAA_DISABLED, Viewport.SCREEN_SPACE_AA_FXAA, Viewport.ANISOTROPY_2X],
	"Medium": [0.8, Viewport.MSAA_2X, Viewport.SCREEN_SPACE_AA_DISABLED, Viewport.ANISOTROPY_4X],
	"High": [1.0, Viewport.MSAA_4X, Viewport.SCREEN_SPACE_AA_DISABLED, Viewport.ANISOTROPY_8X],
	"Ultra High": [1.0, Viewport.MSAA_8X, Viewport.SCREEN_SPACE_AA_DISABLED, Viewport.ANISOTROPY_16X]}

static func read_choice(path: String = FILE) -> String:
	var config := ConfigFile.new()
	if config.load(path) != OK:
		return DEFAULT
	var choice: Variant = config.get_value("graphics", "quality", DEFAULT)
	return choice if choice is String and PRESETS.has(choice) else DEFAULT

static func save_choice(choice: String, path: String = FILE) -> Error:
	if not PRESETS.has(choice):
		return ERR_INVALID_PARAMETER
	var config := ConfigFile.new()
	config.set_value("graphics", "quality", choice)
	return config.save(path)

static func apply(viewport: Viewport, choice: String) -> void:
	var preset: Array = PRESETS.get(choice, PRESETS[DEFAULT])
	viewport.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
	viewport.scaling_3d_scale = preset[0]
	viewport.msaa_3d = preset[1]
	viewport.screen_space_aa = preset[2]
	viewport.use_taa = false
	viewport.anisotropic_filtering_level = preset[3]
