// Camera-local opaque blades: three triangles, stable world-space scatter, no alpha overdraw.
shader_type spatial;
render_mode unshaded, cull_disabled;
uniform sampler2D terrain_guide : filter_linear, repeat_disable;
uniform sampler2D height_map : filter_nearest, repeat_disable;
uniform sampler2D flip_map : filter_nearest, repeat_disable;
uniform vec2 world_origin;
uniform vec2 grid_size;
uniform vec3 sun_dir_sage = vec3(0, 0, 1);
uniform vec3 sun_color = vec3(1);
uniform bool overbright = true;
uniform float fog_enabled = 0.0;
uniform vec3 fog_color = vec3(0.5);
uniform float fog_range_start = 0.0;
uniform float fog_range_end = 10000.0;
global uniform float w3d_fog_shift;
uniform sampler2D shroud_tex : filter_linear, repeat_disable, hint_default_white;
uniform vec2 shroud_origin = vec2(0);
uniform vec2 shroud_extent = vec2(1);
uniform vec3 shroud_color = vec3(1);
uniform bool shroud_enabled = false;
instance uniform float patch_density = 1.0;
instance uniform float patch_span = 32.0;
uniform bool field_fade_enabled = false;
uniform vec2 field_center = vec2(0);
uniform float field_zoom = 1.0;
uniform float wind_strength = 0.20;
uniform float blade_height_scale : hint_range(0.2, 3.0) = 1.0;
uniform vec3 ambient_color = vec3(0.5);

varying vec2 ground_xy;
varying vec3 leaf_color;
varying float plant_fog;
varying float plant_alive;
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
float height_at(vec2 cell) {
 ivec2 i=clamp(ivec2(floor(cell)),ivec2(0),ivec2(grid_size)-ivec2(2)); vec2 f=fract(cell);
 float a=texelFetch(height_map,i,0).r, b=texelFetch(height_map,i+ivec2(1,0),0).r;
 float c=texelFetch(height_map,i+ivec2(1,1),0).r, d=texelFetch(height_map,i+ivec2(0,1),0).r;
 if(texelFetch(flip_map,i,0).r<0.5) {
  return f.y<=f.x ? a+f.x*(b-a)+f.y*(c-b) : a+f.y*(d-a)+f.x*(c-d);
 }
 return f.x+f.y<=1.0 ? a+f.x*(b-a)+f.y*(d-a) : c+(1.0-f.y)*(b-c)+(1.0-f.x)*(d-c);
}
vec3 decode_srgb(vec3 c) { return mix(c/12.92,pow((c+0.055)/1.055,vec3(2.4)),step(vec3(0.04045),c)); }
void vertex() {
 // Odd modular permutation gives evenly scattered prefixes when LOD removes instances.
 int index=(INSTANCE_ID*2653+173)%4096;
 vec2 tile=vec2(float(index%64),float(index/64));
 vec3 patch=(MODEL_MATRIX*vec4(0,0,0,1)).xyz;
 vec2 seed=patch.xz*2.0+tile*(patch_span/32.0);
 // Four nearby stems share an irregular root cluster; randomise cluster centres
 // as well as individual offsets, instead of planting one stem in every grid cell.
 vec2 group=floor(tile*0.5)*2.0;
 vec2 group_seed=patch.xz*2.0+group*(patch_span/32.0);
 vec2 center=group+vec2(hash21(group_seed+11.2),hash21(group_seed+39.1))*2.0;
 float root_angle=hash21(seed+17.3)*6.283185;
 float root_radius=sqrt(hash21(seed+7.4))*0.65;
 vec2 local=(center+vec2(cos(root_angle),sin(root_angle))*root_radius)*0.5*(patch_span/32.0);
 vec2 world=patch.xz+local;
 ground_xy=vec2(world.x,-world.y);
 vec2 cell=(ground_xy-world_origin)/10.0;
 vec2 guv=cell/grid_size;
 vec4 guide=textureLod(terrain_guide,guv,0.0);
 float r=hash21(seed+42.7), r2=hash21(seed+91.1);
 float meadow=noise(ground_xy*0.025);
 float colony=noise(ground_xy*0.019+vec2(18.7,4.2))*0.55+noise(ground_xy*0.13+vec2(9.1,7.6))*0.45;
 float dry=noise(ground_xy*0.012+vec2(3.4,81.2));
 float density=smoothstep(0.25,0.90,guide.a)*mix(0.08,0.92,smoothstep(0.38,0.66,colony));
 float alive=step(0.001,density)*step(r,density)*step(0.0,guv.x)*step(0.0,guv.y)*step(guv.x,1.0)*step(guv.y,1.0);
 float rank=float(INSTANCE_ID)/4096.0;
 float fade=1.0;
 if(field_fade_enabled) {
  float distance_to_focus=length(world-field_center);
  float outer_weight=smoothstep(140.0,220.0,distance_to_focus);
  fade=(patch_span>64.0 ? outer_weight*(1.0-smoothstep(640.0,880.0,distance_to_focus)) : 1.0-outer_weight)*field_zoom;
 }
 float visibility=smoothstep(rank,rank+0.045,patch_density)*alive*fade;
 float tip=UV.y;
 // Independent per-stem heights: short ground cover plus scattered taller growth,
 // rather than letting the density noise sculpt identical rounded bushes.
 float species=hash21(seed+vec2(72.1,16.8));
 float tall=step(0.88,species);
 float height=mix(mix(0.9,2.2,r2),mix(2.3,4.3,r2),tall);
 height*=mix(0.85,1.15,noise(ground_xy*0.031+vec2(53.0)))*blade_height_scale;
 float width=mix(0.18,0.32,hash21(seed+8.6))*mix(1.0,0.65,tall);
 float angle=hash21(seed+3.4)*6.283185;
 vec2 across=vec2(cos(angle),sin(angle)), bend=vec2(-across.y,across.x);
 float lean=mix(0.25,1.9,hash21(seed+vec2(31.3,7.8)));
 vec2 shape=across*VERTEX.x*width+bend*VERTEX.z*height*lean;
 // A little sideways twist keeps all blades from sharing one straight silhouette.
 shape+=across*sin(tip*2.1)*height*0.12*(hash21(seed+6.1)-0.5);
 float phase=dot(ground_xy,vec2(0.035,0.021))-TIME*1.35;
 float gust=sin(phase)+sin(phase*0.47+meadow*3.0)*0.45;
 shape+=vec2(1.0,0.45)*gust*wind_strength*height*tip*tip;
 VERTEX=vec3(local.x,height_at(cell)-0.08,local.y)+vec3(shape.x,tip*height,shape.y)*alive;
 // Keep local brightness, but avoid printing orange soil texels onto green leaves.
 vec3 regional=guide.rgb;
 vec2 offset_uv=vec2(1.0)/grid_size;
 regional+=textureLod(terrain_guide,guv+vec2(offset_uv.x,0),0.0).rgb;
 regional+=textureLod(terrain_guide,guv-vec2(offset_uv.x,0),0.0).rgb;
 regional+=textureLod(terrain_guide,guv+vec2(0,offset_uv.y),0.0).rgb;
 regional+=textureLod(terrain_guide,guv-vec2(0,offset_uv.y),0.0).rgb;
 regional*=0.2;
 float luminance=dot(regional,vec3(0.299,0.587,0.114));
 vec3 sage=vec3(0.80,1.04,0.62)*luminance;
 vec3 straw=vec3(1.12,1.00,0.71)*luminance;
 vec3 base=mix(regional,mix(sage,straw,dry*0.35),0.85);
 vec3 sun=overbright ? sun_color*0.5 : sun_color;
 vec3 blade_normal=normalize(vec3(bend.x*0.55,bend.y*0.55,0.85));
 float diffuse=0.35*max(normalize(sun_dir_sage).z,0.15)+0.65*abs(dot(normalize(sun_dir_sage),blade_normal));
 vec3 lighting=(ambient_color+sun*diffuse)*(overbright ? 2.0 : 1.0);
 leaf_color=base*lighting*mix(0.70,1.05,smoothstep(0.0,0.85,tip))*mix(0.87,1.08,hash21(seed+25.3));
 float dist=length(CAMERA_POSITION_WORLD-(MODEL_MATRIX*vec4(VERTEX,1)).xyz)-w3d_fog_shift;
 plant_fog=1.0-fog_enabled*clamp((dist-fog_range_start)/max(fog_range_end-fog_range_start,0.001),0.0,1.0);
 plant_alive=visibility;
}
void fragment() {
 // Fade coverage, not blade height: shrinking blades left a carpet of artificial stubble.
 if(plant_alive<0.001 || hash21(FRAGCOORD.xy)>plant_alive) discard;
 vec3 color=mix(fog_color,leaf_color,plant_fog);
 if(shroud_enabled) color*=shroud_color*texture(shroud_tex,(ground_xy-shroud_origin)/shroud_extent).r;
 ALBEDO=decode_srgb(max(color,vec3(0)));
}
