// OpenBFME. GPL-3.0. S-4640: terrain projection of RadiusCursor's retail texture,
// colour and client-clock opacity, following the selection decal compositor.
// Composite alongside selection decals so the preview also works on unshaded terrain.
global uniform sampler2D radius_cursor_texture : filter_linear, repeat_disable;
global uniform vec4 radius_cursor_transform; // SAGE centre x/y, diameter (0 = off), Godot Y rotation
global uniform vec4 radius_cursor_params; // opacity, alpha style (otherwise additive), reserved

vec4 radius_cursor_sample(vec2 world) {
	float size = radius_cursor_transform.z;
	if (size <= 0.0) {
		return vec4(0.0);
	}
	vec2 d = world - radius_cursor_transform.xy;
	float c = cos(radius_cursor_transform.w);
	float s = sin(radius_cursor_transform.w);
	// Inverse Godot Y rotation, with SAGE y mapped to -Godot z.
	vec2 uv = vec2(c * d.x + s * d.y, s * d.x - c * d.y) / size + 0.5;
	if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) {
		return vec4(0.0);
	}
	vec4 texel = texture(radius_cursor_texture, uv);
	return vec4(texel.rgb, texel.a * radius_cursor_params.x);
}
