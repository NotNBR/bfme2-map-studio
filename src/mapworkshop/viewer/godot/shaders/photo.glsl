#[compute]
#version 450
// Photo mode's exposure and depth of field over the finished frame (scripts/photo_effect.gd), as render/photo.py's
// docstring lays out the method: each pixel's blur circle from its depth by the thin lens; the largest blur in each
// TILE x TILE tile (pass 0), then the largest of the tiles it can reach (pass 1); the blur itself, Dennis Gustafsson's
// single pass over a disc as large as that reach, in linear colour, then the exposure (pass 2). Pass 3 reads the
// distance at one pixel, to focus on it; pass 4 copies the frame for pass 2 to read. The colour buffer is already
// linear here (after OpenBFME's gamma composite); it is read clamped to 1, as mw render reads its 8-bit frame.

layout(local_size_x = 8, local_size_y = 8, local_size_z = 1) in;

layout(set = 0, binding = 0, std430) restrict readonly buffer Params {
	mat4 inv_projection;
	vec2 size;              // pixels
	vec2 probe;             // pass 3's pixel
	float mm_per_unit;
	float focus_mm;
	float focal_mm;
	float aperture_mm;      // the aperture's diameter: focal / f-number
	float px_per_mm;
	float max_blur;         // pixels, the largest circle's diameter
	float exposure;         // 2^ev
	float taps;
	float use_dof;
	float pass_index;
} p;
layout(set = 0, binding = 1) uniform sampler2D depth_tex;
layout(rgba16f, set = 0, binding = 3) uniform restrict image2D color_img;      // the frame
layout(r32f, set = 0, binding = 4) uniform restrict image2D tile_img;
layout(r32f, set = 0, binding = 5) uniform restrict image2D reach_img;
layout(set = 0, binding = 6, std430) restrict writeonly buffer Probe {
	float distance;
} probe_out;
layout(rgba16f, set = 0, binding = 7) uniform restrict image2D copy_img;      // the frame's copy (pass 4), read by pass 2

const int TILE = 16;

// The copy's colour at uv, the nearest pixel, as mw render's sampler reads it.
vec4 frame_at(vec2 uv) {
	ivec2 at = clamp(ivec2(uv * p.size), ivec2(0), ivec2(p.size) - 1);
	vec4 c = imageLoad(copy_img, at);
	return vec4(min(c.rgb, vec3(1.0)), c.a);
}

// The distance along the view axis (map units) of a depth buffer value.
float view_z(float depth) {
	vec4 q = p.inv_projection * vec4(0.0, 0.0, depth, 1.0);
	return -q.z / q.w;
}

// The blur circle's radius in pixels of a point `units` map units away.
float radius(float units) {
	float d = max(units * p.mm_per_unit, 1e-3);
	float s = max(p.focus_mm, p.focal_mm * 1.001);
	return min(p.aperture_mm * p.focal_mm / (s - p.focal_mm) * abs(d - s) / d * p.px_per_mm, p.max_blur) * 0.5;
}

void tile_pass(ivec2 t) {
	ivec2 base = t * TILE;
	ivec2 last = ivec2(p.size) - 1;
	float m = 0.0;
	for (int y = 0; y < TILE; y++) {
		for (int x = 0; x < TILE; x++) {
			m = max(m, radius(view_z(texelFetch(depth_tex, min(base + ivec2(x, y), last), 0).r)));
		}
	}
	imageStore(tile_img, t, vec4(m));
}

void spread_pass(ivec2 t) {
	int spread = int(ceil(p.max_blur / 2.0 / float(TILE)));
	ivec2 last = imageSize(tile_img) - 1;
	float m = 0.0;
	for (int y = -spread; y <= spread; y++) {
		for (int x = -spread; x <= spread; x++) {
			m = max(m, imageLoad(tile_img, clamp(t + ivec2(x, y), ivec2(0), last)).r);
		}
	}
	imageStore(reach_img, t, vec4(m));
}

void blur_pass(ivec2 pixel) {
	vec2 uv = (vec2(pixel) + 0.5) / p.size;
	vec4 own = frame_at(uv);
	vec3 c = own.rgb;
	float reach = p.use_dof > 0.5 ? imageLoad(reach_img, pixel / TILE).r : 0.0;
	if (reach >= 0.5) {
		float z0 = view_z(texture(depth_tex, uv).r);
		float s0 = radius(z0);
		float golden = 2.39996323;
		// interleaved gradient noise: the pattern's turn for this pixel
		float turn = 6.2831853 * fract(52.9829189 * fract(dot(vec2(pixel) + 0.5, vec2(0.06711056, 0.00583715))));
		float total = 1.0;
		int taps = int(p.taps);
		for (int i = 0; i < taps; i++) {
			float r = sqrt((float(i) + 0.5) / float(taps)) * reach;
			float a = float(i) * golden + turn;
			vec2 suv = uv + vec2(cos(a), sin(a)) * r / p.size;
			float z = view_z(texture(depth_tex, suv).r);
			float s = radius(z);
			if (z > z0) {
				s = min(s, s0 * 2.0);            // behind the pixel: it cannot spread over a sharper pixel
			}
			float m = smoothstep(r - 0.5, r + 0.5, s);   // does its circle reach this pixel?
			c += mix(c / total, frame_at(suv).rgb, m);
			total += 1.0;
		}
		c /= total;
	}
	imageStore(color_img, pixel, vec4(c * p.exposure, own.a));
}

void main() {
	ivec2 id = ivec2(gl_GlobalInvocationID.xy);
	int pass_index = int(p.pass_index);
	if (pass_index == 0 || pass_index == 1) {
		if (any(greaterThanEqual(id, imageSize(tile_img)))) {
			return;
		}
		if (pass_index == 0) {
			tile_pass(id);
		} else {
			spread_pass(id);
		}
	} else if (pass_index == 2 || pass_index == 4) {
		if (any(greaterThanEqual(id, ivec2(p.size)))) {
			return;
		}
		if (pass_index == 2) {
			blur_pass(id);
		} else {
			imageStore(copy_img, id, imageLoad(color_img, id));
		}
	} else if (id == ivec2(0)) {
		probe_out.distance = view_z(texelFetch(depth_tex, ivec2(p.probe), 0).r);
	}
}
