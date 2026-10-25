// OpenBFME. GPL-3.0. Optional artistic ground treatment; not retail shader maths.
// The atlas mask identifies eligible meadow classes, never inferred from pixel colour.
// All detail is world anchored and static. Derivatives fade sub-pixel relief at RTS distances.
uniform bool natural_ground_enabled = false;
uniform sampler2D meadow_mask : filter_linear_mipmap, repeat_disable, hint_default_black;
uniform sampler2D turf_detail : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float natural_ground_strength : hint_range(0.0, 1.0) = 1.0;
varying vec2 v_ground_xy;
varying float v_ground_flatness;

float ground_hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float ground_noise(vec2 p) {
	vec2 cell = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(ground_hash(cell), ground_hash(cell + vec2(1.0, 0.0)), f.x),
		mix(ground_hash(cell + vec2(0.0, 1.0)), ground_hash(cell + vec2(1.0)), f.x), f.y);
}

// x: broad dryness; y: broken soil patches; z: fine-detail visibility.
vec3 ground_pattern(vec2 p, float footprint) {
	float broad = ground_noise(p / 145.0);
	float islands = ground_noise(p / 27.0 + vec2(19.0, 43.0));
	float broken = ground_noise(p / 6.5 + vec2(73.0, 11.0));
	float soil = smoothstep(0.51, 0.78, islands * 0.72 + broken * 0.28);
	return vec3(broad, soil, 1.0 - smoothstep(0.18, 1.25, footprint));
}

void ground_surface(float mask, vec3 pattern, vec4 detail, inout vec3 albedo, inout vec3 normal, inout float gloss) {
	float amount = mask * natural_ground_strength * smoothstep(0.65, 0.94, v_ground_flatness);
	float dry = smoothstep(0.40, 0.83, pattern.x);
	float soil = pattern.y * 0.66;
	float luminance = dot(albedo, vec3(0.299, 0.587, 0.114));
	// Retain the map's palette while softening the coarse, baked texture underneath.
	vec3 living_turf = mix(albedo, luminance * vec3(0.91, 1.14, 0.64), 0.45);
	vec3 dry_turf = mix(living_turf, luminance * vec3(1.17, 1.05, 0.72), dry * 0.40);
	vec3 earth = luminance * vec3(0.80, 0.62, 0.42);
	vec3 surface = mix(dry_turf, earth, soil);
	surface *= mix(0.90, 1.06, pattern.x);
	surface *= 1.0 + (detail.b - 0.5) * 0.24 * pattern.z * (1.0 - soil);
	albedo = mix(albedo, surface, amount);
	vec2 micro = (detail.rg * 2.0 - 1.0) * 0.42 * pattern.z;
	normal = normalize(normal + vec3(micro, 0.0) * amount * (1.0 - soil * 0.65));
	// Dry turf and bare earth should not inherit the retail pin-point gloss.
	gloss *= 1.0 - amount * 0.90;
}

// Keep painted boundaries and their endpoints; break up only the transition interior.
// This uses procedural turf height, not an authored height map for the legacy materials.
float ground_blend(float alpha, float under_mask, float over_mask, vec3 pattern, vec4 detail) {
	float organic_edge = abs(over_mask - under_mask);
	float height_bias = (over_mask - under_mask) * ((detail.b - 0.5) * 1.5 - pattern.y * 0.65);
	float irregular = (ground_noise(v_ground_xy / 3.5) - 0.5) * 0.65;
	return clamp(alpha + alpha * (1.0 - alpha) * (height_bias + irregular * organic_edge)
		* natural_ground_strength * smoothstep(0.65, 0.94, v_ground_flatness), 0.0, 1.0);
}
