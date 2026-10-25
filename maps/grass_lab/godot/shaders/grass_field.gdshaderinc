// OpenBFME. GPL-3.0. Shared placement, palette and screen-size LOD for blades and distant turf.
uniform bool field_fade_enabled = false;
uniform vec2 field_center = vec2(0);
uniform float field_zoom = 1.0;
uniform float grass_projection_scale = 1000.0;
uniform bool grass_orthographic = false;
uniform float grass_wind_strength = 0.20;
float hash21(vec2 p) {
 uvec2 q=uvec2(ivec2(round(p*64.0)));
 uint h=q.x*1597334677u ^ q.y*3812015801u;
 h=(h ^ (h >> 16u))*2246822519u;
 h=(h ^ (h >> 13u))*3266489917u;
 h=h ^ (h >> 16u);
 return float(h >> 8u)*(1.0/16777216.0);
}
float noise(vec2 p) {
 vec2 i=floor(p), f=fract(p); f=f*f*(3.0-2.0*f);
 return mix(mix(hash21(i),hash21(i+vec2(1,0)),f.x),mix(hash21(i+vec2(0,1)),hash21(i+vec2(1)),f.x),f.y);
}

float grass_colony(vec2 p) {
 return noise(p*0.019+vec2(18.7,4.2))*0.55+noise(p*0.13+vec2(9.1,7.6))*0.45;
}
float grass_density(vec2 p, float mask) {
 return smoothstep(0.25,0.90,mask)*mix(0.08,0.92,smoothstep(0.38,0.66,grass_colony(p)));
}
vec3 grass_palette(vec3 regional, vec2 p) {
 float dry=noise(p*0.012+vec2(3.4,81.2));
 float luminance=dot(regional,vec3(0.299,0.587,0.114));
 vec3 sage=vec3(0.80,1.04,0.62)*luminance;
 vec3 straw=vec3(1.12,1.00,0.71)*luminance;
 return mix(regional,mix(sage,straw,dry*0.35),0.35);
}
float grass_pixels(float depth) {
 return 1.8*grass_projection_scale/(grass_orthographic ? 1.0 : max(depth,0.1));
}
float grass_resolved(float depth) {
 return field_fade_enabled ? smoothstep(0.325,1.5,grass_pixels(depth)) : 1.0;
}
// All visible tiles are covered; LOD has no focus-centred pool edge.
float grass_near(vec2 world_xz, float depth) {
 return smoothstep(3.0,7.0,grass_pixels(depth));
}
float grass_far(vec2 world_xz, float depth) {
 return grass_resolved(depth)*(1.0-grass_near(world_xz,depth));
}
float grass_surface_mix(vec2 world_xz, float depth) {
 if(!field_fade_enabled) return 0.0;
 return 1.0-(grass_near(world_xz,depth)+0.35*grass_far(world_xz,depth))*field_zoom;
}
