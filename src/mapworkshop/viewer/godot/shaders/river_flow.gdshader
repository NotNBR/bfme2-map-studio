// River flow (View > River flow arrows), as render/shaders.py's RIVER_FLOW_FS draws it: over each river strip, chevrons
// pointing downstream, one per v repeat and drifting downstream with time; the strip's banks as thin lines, its first
// cross-section green and its last red. UV is the strip's (across, along); map coordinates are (x, -z) of Godot's.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;

uniform float strip_length;         // the strip's length in v
uniform vec2 playable;
uniform bool show_border = false;
uniform float time;                 // the viewer's clock, which View > Animate stops

// Drawn a little nearer the camera than the surface it is draped on (a fraction of the distance), so that it stays
// over the terrain where the terrain cuts its cells on the other diagonal (cliffs).
const float PULL = 0.002;

varying vec2 world;

void vertex() {
	world = vec2(VERTEX.x, -VERTEX.z);
	vec4 view = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	POSITION = PROJECTION_MATRIX * vec4(view.xyz * (1.0 - PULL), 1.0);
}

void fragment() {
	if (!show_border && (any(lessThan(world, vec2(0.0))) || any(greaterThan(world, playable)))) {
		discard;
	}
	vec2 strip = UV;
	vec2 px = fwidth(strip) * 1.5;
	float across = abs(strip.x - 0.5);
	// the middle of each chevron leads: v + 0.8|u - 0.5| is constant along it
	float f = fract(strip.y + 0.8 * across - time * 0.25);
	vec4 c = vec4(0.0);
	if (strip.x < max(0.02, px.x) || strip.x > 1.0 - max(0.02, px.x)) c = vec4(0.25, 0.85, 1.0, 0.85);
	if (across < 0.34 && f < max(0.12, px.y)) c = vec4(1.0, 0.82, 0.12, 0.95);
	if (strip.y < max(0.06, px.y)) c = vec4(0.2, 1.0, 0.3, 0.95);
	if (strip.y > strip_length - max(0.06, px.y)) c = vec4(1.0, 0.25, 0.2, 0.95);
	if (c.a == 0.0) {
		discard;
	}
	ALBEDO = c.rgb;
	ALPHA = c.a;
}
