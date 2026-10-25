// Frustum-covered grass: three triangles, stable world-space scatter, MSAA sample coverage.
shader_type spatial;
render_mode unshaded, cull_disabled, alpha_to_coverage_and_one, depth_draw_always;
uniform sampler2D terrain_guide : filter_linear_mipmap, repeat_disable;
uniform sampler2D habitat_guide : filter_linear_mipmap, repeat_disable;
uniform bool habitat_enabled = false;
uniform bool ground_litter_enabled = true;
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
uniform float output_gamma = 2.2;
uniform float wind_strength = 0.20;
uniform float blade_height_scale : hint_range(0.2, 3.0) = 1.0;
uniform vec3 ambient_color = vec3(0.5);

varying vec2 ground_xy;
varying vec3 leaf_color;
varying float plant_fog;
varying float plant_alive;
varying vec2 litter_uv;
varying float leaf_detail;
#include "res://labs/grass/shaders/grass_field.gdshaderinc"
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
 float root_radius=pow(hash21(seed+7.4),1.2)*mix(0.22,0.85,hash21(group_seed+6.7));
 vec2 local=(center+vec2(cos(root_angle),sin(root_angle))*root_radius)*0.5*(patch_span/32.0);
 vec2 world=patch.xz+local;
 ground_xy=vec2(world.x,-world.y);
 vec2 cell=(ground_xy-world_origin)/10.0;
 vec2 guv=cell/grid_size;
 vec4 guide=textureLod(terrain_guide,guv,0.0);
 float r=hash21(seed+42.7), r2=hash21(seed+91.1);
 float meadow=noise(ground_xy*0.025);
 vec3 regional=textureLod(terrain_guide,guv,1.0).rgb;
 float density=grass_density(ground_xy,guide.a,regional);
 vec4 habitat=habitat_enabled ? textureLod(habitat_guide,guv,0.0) : vec4(0.0,1.0,0.0,0.0);
 float kind=hash21(seed+vec2(411.7,91.2));
 // Reuse a few near-pool candidates for actual low geometry, not extra sprite batches.
 float leaf=step(1.0-habitat.r*0.025,kind);
 float dead=step(0.976,kind)*(1.0-leaf);
 float stone=(1.0-step(0.003,kind))*(1.0-leaf);
 float litter=max(leaf,max(dead,stone))*float(patch_span<64.0 && ground_litter_enabled);
 float litter_allowed=step(0.7,habitat.g)*step(0.025,guide.a+habitat.r);

 float alive=step(0.001,density)*step(r,density)*step(0.0,guv.x)*step(0.0,guv.y)*step(guv.x,1.0)*step(guv.y,1.0);
 alive=mix(alive,litter_allowed,litter);
 float ground_height=height_at(cell)-0.08;
 vec3 root_world=vec3(world.x,ground_height,world.y);
 float depth=-(VIEW_MATRIX*vec4(root_world,1)).z;
 float rank=float(INSTANCE_ID)/4096.0;
 float fade=1.0;
 float population=patch_density;
 if(field_fade_enabled) {
  fade=(patch_span>64.0 ? grass_far(world,depth) : grass_near(world,depth))*field_zoom;
  population*=mix(0.35,1.0,smoothstep(3.0,9.0,grass_pixels(depth)));
 }
 float visibility=smoothstep(rank,rank+0.045,population)*alive*fade;
 float tip=UV.y;
 litter_uv=vec2(0.0,tip);
 leaf_detail=leaf*litter;
 // Height has its own distribution, independent of curl and blade colour.
 // Local growth patches favour taller tufts, while each stem keeps its own height.
 float species=hash21(seed+vec2(72.1,16.8));
 float stature=hash21(seed+vec2(213.7,54.2));
 float tuft=smoothstep(0.38,0.70,noise(ground_xy*0.12+vec2(83.1,17.6)));
 float tall=step(mix(0.98,0.72,tuft),stature);
 float low=1.0-step(0.36,stature);
 float curled=step(0.62,species)*(1.0-step(0.86,species))*(1.0-tall);
 float droop=step(0.86,species)*(1.0-tall);
 float verge=grass_verge(ground_xy,guide.a);
 float height=mix(0.95,2.10,r2);
 height=mix(height,mix(0.30,0.85,r2),low);
 height=mix(height,mix(2.60,4.60,r2),tall);
 float growth=mix(0.72,1.18,noise(ground_xy*0.045+vec2(32.8,91.4)));
 float root_variation=mix(0.88,1.12,hash21(group_seed+61.3));
 height*=growth*root_variation*mix(0.28,1.0,verge)*blade_height_scale;
 float width=mix(0.10,0.23,hash21(seed+8.6))*(1.0+curled*0.35);
 if(field_fade_enabled) width*=mix(1.65,1.0,smoothstep(3.0,9.0,grass_pixels(depth)));
 float angle=hash21(seed+3.4)*6.283185;
 vec2 across=vec2(cos(angle),sin(angle)), bend=vec2(-across.y,across.x);
 if(field_fade_enabled) {
  float projected_width=length((VIEW_MATRIX*vec4(across.x,0.0,across.y,0.0)).xy)*width*grass_pixels(depth)/1.8;
  // Avoid needle-thin rasterization at medium range; retain the actual blade height.
  width*=clamp(0.70/max(projected_width,0.001),1.0,3.0);
 }
 float lean=mix(0.10,0.48,hash21(seed+vec2(31.3,7.8)))+curled*0.75+droop*1.2+(1.0-verge)*1.4;
 vec2 shape=across*VERTEX.x*width+bend*pow(tip,1.5+curled)*height*lean;
 shape+=across*sin(tip*3.3)*height*0.10*(hash21(seed+6.1)-0.5)*curled;
 float vertical=tip*height*(1.0-droop*0.72*tip);
 float phase=dot(ground_xy,vec2(0.035,0.021))-TIME*1.35;
 float gust=sin(phase)+sin(phase*0.47+meadow*3.0)*0.45;
 float wind_lod=field_fade_enabled ? mix(0.15,1.0,smoothstep(1.5,6.0,grass_pixels(depth))) : 1.0;
 shape+=vec2(1.0,0.45)*gust*wind_strength*height*tip*tip*wind_lod;
 VERTEX=vec3(local.x,ground_height,local.y)+vec3(shape.x,vertical,shape.y)*alive;
 if(litter>0.5) {
  float length=mix(0.45,1.1,r2);
  float breadth=mix(0.12,0.30,hash21(seed+33.1));
  breadth=mix(breadth,0.06,dead);
  float cross_section=tip<0.9 ? (VERTEX_ID==0 || VERTEX_ID==2 ? -1.0 : 1.0) : 0.0;
  litter_uv.x=cross_section*(tip<0.1 ? 0.12 : 1.0);
  vec2 offset=across*cross_section*breadth*(tip<0.1 ? mix(0.45,0.12,leaf) : 1.0)+bend*(tip-0.5)*length;
  float arch=(1.0-abs(tip*2.0-1.0))*mix(0.05,0.32,stone);
  vec2 surface_cell=(vec2(world.x+offset.x,-world.y-offset.y)-world_origin)/10.0;
  VERTEX=vec3(local.x+offset.x,height_at(surface_cell)+0.035+arch,local.y+offset.y);
 }
 // Keep local brightness, but avoid printing orange soil texels onto green leaves.
 vec3 base=grass_palette(regional,ground_xy);
 if(litter>0.5) {
  float luma=dot(regional,vec3(0.299,0.587,0.114));
  vec3 litter_color=mix(vec3(1.04,0.80,0.48),vec3(0.84,0.84,0.78),stone)*luma;
  base=mix(regional,litter_color,0.65)*mix(0.68,0.96,hash21(seed+2.3));
 }
 vec3 sun=overbright ? sun_color*0.5 : sun_color;
 vec3 blade_normal=normalize(vec3(bend.x*0.55,bend.y*0.55,0.85));
 float diffuse=0.70*max(normalize(sun_dir_sage).z,0.15)+0.30*abs(dot(normalize(sun_dir_sage),blade_normal));
 vec3 lighting=(ambient_color+sun*diffuse)*(overbright ? 2.0 : 1.0);
 float root_shade=mix(mix(0.57,0.75,1.0-density),1.0,smoothstep(0.0,0.70,tip));
 leaf_color=base*lighting*mix(root_shade,0.88,litter)*mix(0.96,1.02,hash21(seed+25.3));
 float dist=length(CAMERA_POSITION_WORLD-(MODEL_MATRIX*vec4(VERTEX,1)).xyz)-w3d_fog_shift;
 plant_fog=1.0-fog_enabled*clamp((dist-fog_range_start)/max(fog_range_end-fog_range_start,0.001),0.0,1.0);
 plant_alive=visibility;
}
void fragment() {
 // Continuous alpha replaces screen-space noise, which sparkled during pans.
 if(plant_alive<0.001) discard;
 ALPHA=plant_alive;
 vec3 surface_color=leaf_color;
 if(leaf_detail>0.5) {
  float vein=1.0-smoothstep(0.0,0.12,abs(litter_uv.x));
  float edge=smoothstep(0.6,1.0,abs(litter_uv.x));
  surface_color*=0.94+vein*0.10-edge*0.14;
 }
 vec3 color=mix(fog_color,surface_color,plant_fog);
 if(shroud_enabled) color*=shroud_color*texture(shroud_tex,(ground_xy-shroud_origin)/shroud_extent).r;
 // Real maps blend transparent draws in their gamma compositor; the standalone lab uses linear output.
 ALBEDO=output_gamma == 1.0 ? max(color,vec3(0)) : decode_srgb(max(color,vec3(0)));
}
