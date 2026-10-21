// Over the ground: the walkability estimate
// (mapkit.walkable's colours per cell, blocked cells striped), the 100-unit grid, and outside the playable area the
// border faded to black over the border's width (shown when show_border). A mesh draped on the surface
// (scripts/overlays.gd) carries it; map coordinates are (x, -z) of Godot's.
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled;

uniform vec2 playable;
uniform float border_fade;          // the border's width in map units
uniform bool show_border = false;
uniform bool grid = false;
uniform bool walk = false;
uniform sampler2D walk_tex : filter_nearest, repeat_disable;     // as stored: OpenBFME composes in gamma space, as the game
uniform vec2 walk_size;             // the walkability image's extent from the playable area's corner

// Drawn a little nearer the camera than the surface it is draped on (a fraction of the distance), so that it stays
// over the terrain where the terrain cuts its cells on the other diagonal (cliffs).
const float PULL = 0.002;

varying vec2 world;

void vertex() {
	world = vec2(VERTEX.x, -VERTEX.z);
	vec4 view = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	POSITION = PROJECTION_MATRIX * vec4(view.xyz * (1.0 - PULL), 1.0);
}

vec4 over(vec4 below, vec4 c) {
	float a = c.a + below.a * (1.0 - c.a);
	vec3 rgb = (c.rgb * c.a + below.rgb * below.a * (1.0 - c.a)) / max(a, 1e-4);
	return vec4(rgb, a);
}

void fragment() {
	vec4 out_c = vec4(0.0);
	if (walk && all(greaterThanEqual(world, vec2(0.0))) && all(lessThan(world, walk_size))) {
		vec4 w = texture(walk_tex, world / walk_size);
		float a = w.a > 0.74 && fract((world.x + world.y) / 40.0) >= 0.5 ? w.a * 0.4 : w.a;
		out_c = over(out_c, vec4(w.rgb, a));
	}
	if (grid) {
		vec2 f = fract(world / 100.0);
		if (min(min(f.x, 1.0 - f.x), min(f.y, 1.0 - f.y)) < 0.012) {
			out_c = over(out_c, vec4(1.0, 1.0, 0.0, 0.35));
		}
	}
	if (!show_border && (any(lessThan(world, vec2(0.0))) || any(greaterThan(world, playable)))) {
		vec2 o = max(max(-world, world - playable), vec2(0.0));
		float fade = border_fade > 0.0 ? 1.0 - smoothstep(0.0, border_fade, length(o)) : 0.0;
		out_c = over(out_c, vec4(0.0, 0.0, 0.0, 1.0 - fade));
	}
	if (out_c.a <= 0.001) {
		discard;
	}
	ALBEDO = out_c.rgb;
	ALPHA = out_c.a;
}
