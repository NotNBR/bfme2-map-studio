// Falling rain or snow, as the game's W3DSnowManager draws it with renderAsQuads (render/weather.py has the
// addresses): every emitter (INSTANCE_CUSTOM: map x, y and its starting height) falls from the ceiling `box` by
// h = box - fmod(start + travelled, box), wobbles sideways by amplitude * sin(h * frequency + x) and drifts by the
// wind, less the drift of every whole fall. Its quad stands on the camera's horizontal right and the vertical,
// 0.707 * size either side of the centre, alpha blended without depth writes or fog, inside the playable area.
// Map coordinates (x, y, z) are Godot's (x, -z, y).
shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_disabled, shadows_disabled, fog_disabled,
	world_vertex_coords;

uniform sampler2D tex : filter_linear_mipmap, repeat_disable;   // gamma values, as the transparent pass composites
uniform float size;                 // SnowQuadSize
uniform float box;                  // SnowBoxHeight
uniform float travelled;            // the clock x SnowSpeed
uniform float amplitude;            // SnowAmplitude
uniform vec2 frequency;             // SnowFrequencyScaleX/Y
uniform vec2 drift;                 // the clock x SnowXYSpeed
uniform vec2 drift_per_cycle;       // SnowXYSpeed x SnowBoxHeight / SnowSpeed
uniform vec2 playable;

varying vec2 map_xy;

void vertex() {
	vec3 emitter = INSTANCE_CUSTOM.xyz;
	float fall = emitter.z + travelled;
	float cycles = floor(fall / box);
	float h = box - (fall - box * cycles);
	vec2 centre = emitter.xy + amplitude * sin(h * frequency + emitter.xy) + drift - cycles * drift_per_cycle;
	map_xy = centre;
	vec3 right = INV_VIEW_MATRIX[0].xyz;
	right = length(right.xz) > 1e-4 ? normalize(vec3(right.x, 0.0, right.z)) : vec3(1.0, 0.0, 0.0);
	// QuadMesh corners are +-0.5: twice that is the game's +-1
	VERTEX = vec3(centre.x, h, -centre.y) + (VERTEX.x * right + VERTEX.y * vec3(0.0, 1.0, 0.0)) * (2.0 * 0.707 * size);
}

void fragment() {
	if (any(lessThan(map_xy, vec2(0.0))) || any(greaterThan(map_xy, playable))) {
		discard;
	}
	vec4 colour = texture(tex, UV);             // UV's v is 0 at the top, as the game's quads
	ALBEDO = colour.rgb;
	ALPHA = colour.a;
}
