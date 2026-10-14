"""GLSL ports of the retail BFME2 effects used by the preview renderer.

Terrain: terrain.fx, technique by detail level (HeightMap 0x000E153A:
UseTerrainNormalMap ? Default : UseDistanceDependantTerrainTextures ?
Default_M : Default_L), RenderingMode 0. Each 16x16-cell tile draws one
CPU-composited texture (base, blend and three-way tiles mixed by the alpha
ramps only) and, at High, one composited normal texture. The vertex colour is
doTheLight (ambient + every global terrain light, clamped; the sun is left
out only with normal maps, where the light environment carries it to
Sas.DirectionalLight[0]; at Low/Medium that environment is empty).
- Default_L (Low): VS object 144, PSDefaultL_Array[overbright*5] (134/139):
  texture x vertex colour [x2]; no cloud or macro pass.
- Default_M (Medium): VSDefaultM0_Array[0] (105) with PSDefaultM0_Array
  [overbright*10] (110/120): texture x vertex colour [x2]; pass P1 (132/133)
  multiplies cloud x macro (x shroud).
- Default (High): VS 103, PSDefault_Array[5 x NumShadows] (83/88): normal
  from the normal texture's RG (z rebuilt), N.L and Blinn N.H^1200 x B x 0.9
  in the per-vertex tangent frame T=(Nz,0,-Nx), B=(0,Nz,-Ny); colour =
  (vertex + texture x sun x N.L + sun x specular) [x2] x cloud x macro.
Fog: lerp to the fog colour by the per-vertex linear distance factor, after
cloud and macro. Tiles beyond updateCenter's 2x distance use the 16 px/cell
texture (32 px/cell nearer, and only with distance-dependent textures).

Water: WaterShader.fx BumpSpecular (vs object 78, ps PSBumpSpecular_Array
76/77 by NumShadows) and BumpSpecular_M (vs 148, ps 149, the Medium water).
Two bump samples in frames rotated by WindAngle -/+ WaveAngle/2 give the
normal. BumpSpecular: env x 2 x Dimming x MaterialDiffuse x N.L plus Blinn
specular, x light colour, lerped to the (black) reflection by
ReflectionStrength. BumpSpecular_M: env x 2 x Dimming x MaterialDiffuse x
light colour x (N.L + N.H^exp). Both add the wave product; alpha from water
depth: clamp(depth / (DWA^2 x MaxAlphaDepth)) x DWA. PCA_L (vs 140, ps 141,
the Low water): env offset by one bump sample (texbem) x Dimming x
MaterialDiffuse, plus 0.1 x one wave sample; unlit, same alpha.

Objects (OBJECT_VS/OBJECT_FS, `technique` uniform). The light environment
is the object ambient plus the object lights LightEnvironmentClass::Add_Light
keeps (diffuse >= 0.05 in some channel, sorted by squared length), scaled at
ShaderLOD Low/Medium by GlobalLighting's last three values.
- 0 fixed function (classic W3D materials): per-vertex D3D lighting,
  emissive + ambient source x ambient + diffuse source x sum max(N.L, 0),
  saturated; sources from MeshMatDescClass::Post_Load_Process (DCG folded
  with the vertex material). Stage 0 texture x diffuse (MODULATE2X under
  overbright); ShaderClass blending, depth mask, alpha test >= 0x60 (>= 1
  for SrcAlpha/InvSrcAlpha), culling unless the mesh is two-sided.
- 1/2 vegetation.fx Default_L (Low/Medium) / Default (High) for the tree and
  shrub buffers: vs object 39/43 with model-space normals, |N.L| per light,
  (lights + ambient) x vertex colour x 0.5 saturated, SwayOffsets[type] x
  height above the tree's pivot; ps 41/42 tex x oD0 x 1.999 (no cloud), ps
  37/38 tex x oD0 x cloud x 2 with the shadowed main-light share (oT4)
  subtracted. Alpha test >= 96, back faces culled, trees alpha-blended
  (Vegetation.IsAlphaBlendEnabled), shrubs not. Sas colours x2 under
  overbright.
- 3 normalmapped.fx Default_M (vs 63, ps 65): DirectionalLight[0] and [2]
  per vertex x DiffuseColor + Ambient x AmbientColor; per pixel the bump
  diffuse of DirectionalLight[1] and the specular of light 0's half vector.
- 4 normalmapped.fx Default_L (vs 57, ps 59): three lights per vertex,
  halved and saturated, doubled in the pixel shader.
"""

TERRAIN_VS = """
#version 430
uniform mat4 view_projection;
uniform sampler2D heights;          // R32F world z, (width, height)
uniform usampler2D cells;           // RGBA32UI per cell
uniform ivec2 grid;                 // samples (width, height)
uniform int border;
uniform vec3 ambient;
uniform vec3 fill_dir[2];
uniform vec3 vs_sun_dir;            // towards the light
uniform vec3 vs_sun_color;
uniform int sun_in_vertex;          // 1 without terrain normal maps
uniform sampler2D depth_tint;       // RGB per sample; 1 outside standing water
uniform vec3 fill_color[2];
uniform vec3 sun_dir;               // normalized, towards the light (High VS preshader)
uniform vec3 eye;
uniform int technique;              // 0 Default_L, 1 Default_M, 2 Default
// map.ini Weather hardware fog: the VS fog factor 1 - clamp((d - start) / (end - start)).
uniform int fog_enabled;
uniform vec2 fog_range;             // HardwareFogStart, HardwareFogEnd
uniform vec3 fog_eye;
out vec3 v_world;
out vec3 v_normal;
out vec3 v_vertex_light;
out vec2 v_local;
out vec2 v_alpha;
out vec3 v_light_t;                 // Default VS oT5: light in the tangent frame
out vec3 v_half_t;                  // Default VS oT6: normalized half vector, tangent frame
out float v_fog;                    // 1 = no fog
flat out uvec4 v_cell;

const ivec2 CORNER[4] = ivec2[4](ivec2(0,0), ivec2(1,0), ivec2(1,1), ivec2(0,1));
const int PATTERN[6] = int[6](0, 2, 3, 0, 1, 2);

float h(ivec2 p) { return texelFetch(heights, clamp(p, ivec2(0), grid-1), 0).r; }

void main() {
    int cell_index = gl_VertexID / 6;
    int k = gl_VertexID % 6;
    ivec2 cell = ivec2(cell_index % (grid.x-1), cell_index / (grid.x-1));
    uvec4 data = texelFetch(cells, cell, 0);
    int corner = PATTERN[k];
    if (data.w != 0u) corner = (corner + 1) % 4;   // flipForBlend rotates the quad
    ivec2 p = cell + CORNER[corner];
    // HeightMapRenderObjClass::updateVB: central differences over two cells.
    vec3 l2r = vec3(20.0, 0.0, h(p+ivec2(1,0)) - h(p-ivec2(1,0)));
    vec3 n2f = vec3(0.0, 20.0, h(p+ivec2(0,1)) - h(p-ivec2(0,1)));
    vec3 n = normalize(cross(l2r, n2f));
    v_world = vec3((vec2(p) - float(border)) * 10.0, h(p));
    v_normal = n;
    vec3 light = ambient;
    // BaseHeightMapRenderObjClass::doTheLight (0x000694A3): ambient 0 plus
    // every global terrain light (ray = -GlobalLighting direction, not
    // normalized; colour x GlobalLighting v8 final values), clamped to
    // [0,1]; light 0 (the sun) is skipped only with UseTerrainNormalMap,
    // where the Default technique lights it per pixel instead.
    if (sun_in_vertex != 0) light += vs_sun_color * clamp(dot(vs_sun_dir, n), 0.0, 1.0);
    for (int i = 0; i < 2; i++) light += fill_color[i] * clamp(dot(fill_dir[i], n), 0.0, 1.0);
    v_vertex_light = clamp(light, 0.0, 1.0);
    // getStaticDiffuse: underwater terrain takes the water area's depth LUT.
    v_vertex_light *= texelFetch(depth_tint, p, 0).rgb;
    // Default VS (object 103): T = (Nz, 0, -Nx), B = (0, Nz, -Ny) from the
    // normalized normal, third axis the vertex normal; H = normalize(V) + L.
    vec3 t = vec3(n.z, 0.0, -n.x);
    vec3 b = vec3(0.0, n.z, -n.y);
    v_light_t = vec3(dot(sun_dir, t), dot(sun_dir, b), dot(sun_dir, n));
    vec3 h = normalize(eye - v_world) + sun_dir;
    v_half_t = normalize(vec3(dot(h, t), dot(h, b), dot(h, n)));
    float f = clamp((length(v_world - fog_eye) - fog_range.x) / max(fog_range.y - fog_range.x, 1.0), 0.0, 1.0);
    v_fog = fog_enabled != 0 ? 1.0 - f : 1.0;
    v_local = vec2(CORNER[corner]);
    v_alpha = vec2(float((data.y >> (20u + uint(corner))) & 1u), float((data.z >> (20u + uint(corner))) & 1u));
    v_cell = data;
    gl_Position = view_projection * vec4(v_world, 1.0);
}
"""

TERRAIN_FS = """
#version 430
uniform sampler2DArray albedo;      // terrain textures, top row first
uniform sampler2DArray normals;     // matching _nrm maps (neutral when absent)
uniform float subtiles[256];        // subtiles across each texture (2 x cell size)
uniform float array_size;           // texels across each array layer
uniform int technique;              // 0 Default_L, 1 Default_M, 2 Default
uniform int allow_2x;               // UseDistanceDependantTerrainTextures
uniform float distance_2x;          // updateCenter's 2x texture distance
uniform sampler2D tile_z;           // RG zmin, zmax of each 16x16-cell tile
uniform int border_cells;
uniform sampler2D macro_tex;
uniform sampler2D cloud_tex;
uniform vec4 macro_xform;           // uv = world.xy * xy + zw
uniform vec4 cloud_xform;
uniform int use_macro;
uniform sampler2D decal_tex;         // baked multiplicative shadow decals
uniform vec4 decal_xform;           // uv = world.xy * xy + zw
uniform int use_decals;
uniform int use_cloud;
uniform vec3 sun_color;
uniform vec3 eye;
uniform int overbright;
uniform int grid_lines;
uniform vec2 playable;              // playable extent in world units
uniform int show_border;
uniform sampler2D walk_tex;         // the game's pathfinding grid as colours (mapkit.walkable)
uniform int use_walk;
uniform vec2 walk_size;             // its extent in world units
uniform float border_fade;          // > 0: the border fades out over this many units
uniform sampler2DShadow shadow_map;
uniform mat4 light_view_projection;
uniform vec2 shadow_texel;          // 1 / shadow map size
uniform float shadow_bias;          // depth units
uniform int use_shadows;           // 0 off, 1 shadow map (High), 2 volumes (Medium)
uniform vec3 shadow_color;          // GlobalLighting shadow colour (volume mode)
uniform sampler2D volume_count;     // stencil count of the shadow volumes per pixel
// High: Terrain.fx/vegetation.fx take four depth tests one texel apart and
// scale only the main light. Medium: the shadow volumes' stencil count, read
// per pixel; renderStencilShadows multiplies every pixel whose count is at
// least 1 by the shadow colour.
float lit_fraction(vec3 world) {
    if (use_shadows == 0) return 1.0;
    if (use_shadows == 2) return texelFetch(volume_count, ivec2(gl_FragCoord.xy), 0).r > 0.5 ? 0.0 : 1.0;
    vec4 p = light_view_projection * vec4(world, 1.0);
    vec3 q = p.xyz / p.w * 0.5 + 0.5;
    if (any(lessThan(q.xy, vec2(0.0))) || any(greaterThan(q.xy, vec2(1.0)))) return 1.0;
    float z = q.z - shadow_bias;
    float s = texture(shadow_map, vec3(q.xy, z));
    s += texture(shadow_map, vec3(q.xy + vec2(shadow_texel.x, 0.0), z));
    s += texture(shadow_map, vec3(q.xy + vec2(0.0, shadow_texel.y), z));
    s += texture(shadow_map, vec3(q.xy + shadow_texel, z));
    return s * 0.25;
}
in vec3 v_world;
in vec3 v_normal;
in vec3 v_vertex_light;
in vec2 v_local;
in vec2 v_alpha;
in vec3 v_light_t;
in vec3 v_half_t;
in float v_fog;
flat in uvec4 v_cell;
out vec4 frag;
uniform vec3 fog_color;

float g_min_lod = 0.0;              // texel-per-cell cap of this tile's texture

// W3DTerrainBackground::updateCenter (0x0011234C): a tile gets the 2x
// (32 px/cell) texture when its nearest box point (corners, edge and face
// centres of its bounds) is within distance_2x of the camera; otherwise the
// 1x texture at 16 px/cell (doTesselatedUpdate 0x001149EB).
float tile_px_per_cell() {
    if (allow_2x == 0) return 16.0;
    ivec2 n = textureSize(tile_z, 0);
    ivec2 tile = clamp(ivec2(floor((v_world.xy / 10.0 + float(border_cells)) / 16.0)), ivec2(0), n - 1);
    vec2 z = texelFetch(tile_z, tile, 0).rg;
    vec3 lo = vec3((vec2(tile) * 16.0 - float(border_cells)) * 10.0, z.x);
    vec3 hi = vec3(lo.xy + 160.0, z.y);
    vec3 center = (lo + hi) * 0.5, extent = (hi - lo) * 0.5;
    float best = 1e30;
    for (int i = -1; i <= 1; i++) for (int j = -1; j <= 1; j++) for (int k = -1; k <= 1; k++) {
        vec3 d = eye - (center + extent * vec3(i, j, k));
        best = min(best, dot(d, d));
    }
    return best < distance_2x * distance_2x ? 32.0 : 16.0;
}

// Sample a terrain texture layer no finer than the tile texture's resolution.
vec4 sample_layer(sampler2DArray s, uint word) {
    int tex = int(word & 1023u);
    float n = subtiles[tex];
    vec2 sub = vec2(float((word >> 10u) & 31u), float((word >> 15u) & 31u));
    vec2 from_bottom = (sub + clamp(v_local, 0.0, 1.0)) / n;
    vec2 uv = vec2(from_bottom.x, 1.0 - from_bottom.y);
    // Continuous world-space derivatives avoid seams at subtile changes.
    vec2 period = vec2(10.0 * n);
    vec2 dx = dFdx(v_world.xy) / period * vec2(1.0, -1.0);
    vec2 dy = dFdy(v_world.xy) / period * vec2(1.0, -1.0);
    float texels = array_size * max(length(dx), length(dy));
    float lod = log2(max(texels, 1e-8));
    float min_lod = max(log2(array_size / n) - g_min_lod, 0.0);
    if (lod < min_lod) { float k = exp2(min_lod - lod); dx *= k; dy *= k; }
    return textureGrad(s, vec3(uv, tex), dx, dy);
}

bool has_blend(uint word) { return (word & (1u << 24u)) != 0u; }

bool outside(vec2 p) { return any(lessThan(p, vec2(0.0))) || any(greaterThan(p, playable)); }

void main() {
    // The game hides the non-playable border. Top views draw it black;
    // perspective views fade it out towards the map's edge, onto the sky.
    float fade = 1.0;
    if (show_border == 0 && outside(v_world.xy)) {
        if (border_fade <= 0.0) { frag = vec4(0.0, 0.0, 0.0, 1.0); return; }
        vec2 o = max(max(-v_world.xy, v_world.xy - playable), vec2(0.0));
        fade = 1.0 - smoothstep(0.0, border_fade, length(o));
        if (fade < 0.004) discard;
    }
    float g_lit = lit_fraction(v_world);
    g_min_lod = log2(tile_px_per_cell());
    // The CPU-composited tile texture: base, then blend and three-way tiles
    // mixed by their alpha ramps (blendTile 0x000ADDCE); texture alpha unused.
    vec3 tex = sample_layer(albedo, v_cell.x).rgb;
    if (has_blend(v_cell.y)) tex = mix(tex, sample_layer(albedo, v_cell.y).rgb, v_alpha.x);
    if (has_blend(v_cell.z)) tex = mix(tex, sample_layer(albedo, v_cell.z).rgb, v_alpha.y);
    vec3 c;
    if (technique == 2) {
        // Default PS (objects 83/88), composited normal texture alike.
        vec4 nm = sample_layer(normals, v_cell.x);
        if (has_blend(v_cell.y)) nm = mix(nm, sample_layer(normals, v_cell.y), v_alpha.x);
        if (has_blend(v_cell.z)) nm = mix(nm, sample_layer(normals, v_cell.z), v_alpha.y);
        vec2 xy = nm.rg * 2.0 - 1.0;
        vec3 tn = normalize(vec3(xy, sqrt(abs(1.0 - dot(xy, xy)))));
        float ndh = dot(tn, normalize(v_half_t));
        float ndl = dot(tn, normalize(v_light_t));
        float spec = (ndl > 0.0 && ndh > 0.0) ? pow(ndh, 1200.0) * nm.b * 0.9 : 0.0;
        float diffuse = max(ndl, 0.0);
        if (use_shadows == 1) { diffuse *= g_lit; spec *= g_lit; }
        // Sas.DirectionalLight Color is doubled under overbright and halved
        // again by the preshader, so the sun keeps its GlobalLighting colour.
        c = v_vertex_light * tex + sun_color * (diffuse * tex + spec);
    } else {
        // Default_L / Default_M pass P0: texture x vertex colour.
        c = v_vertex_light * tex;
    }
    if (overbright != 0) c *= 2.0;
    // ps_1_1 pass P0 ends in the 8-bit frame buffer before P1 multiplies.
    if (technique != 2) c = min(c, vec3(1.0));
    // Default_M pass P1 and the Default PS multiply cloud and macro; Default_L has neither.
    if (technique != 0) {
        if (use_cloud != 0) c *= texture(cloud_tex, v_world.xy * cloud_xform.xy + cloud_xform.zw).rgb;
        if (use_macro != 0) c *= texture(macro_tex, v_world.xy * macro_xform.xy + macro_xform.zw).rgb;
    }
    c = mix(fog_color, c, v_fog);
    // The stencil shadow pass runs after fog in game; the renderer fades it
    // with the fog too, so that far shadows (seen from low viewer angles the
    // game camera never takes) do not show as dark specks through it.
    if (use_shadows == 2) c *= mix(shadow_color, vec3(1.0), max(g_lit, 1.0 - v_fog));
    // Tree shadow decals multiply the fogged terrain; they fade with the fog
    // (towards white) so that distant blobs do not show through it.
    if (use_decals != 0) c *= mix(vec3(1.0), texture(decal_tex, v_world.xy * decal_xform.xy + decal_xform.zw).rgb, v_fog);
    if (use_walk != 0 && all(greaterThanEqual(v_world.xy, vec2(0.0))) && all(lessThan(v_world.xy, walk_size))) {
        vec4 w = texture(walk_tex, v_world.xy / walk_size);
        // Blocked cells (alpha over 0.74) are striped.
        float a = w.a > 0.74 && fract((v_world.x + v_world.y) / 40.0) >= 0.5 ? w.a * 0.4 : w.a;
        c = mix(c, w.rgb, a);
    }
    if (grid_lines != 0) {
        vec2 f = fract(v_world.xy / 100.0);
        if (min(min(f.x, 1.0-f.x), min(f.y, 1.0-f.y)) < 0.012) c = mix(c, vec3(1.0, 1.0, 0.0), 0.35);
    }
    frag = vec4(c, fade);
}
"""

WATER_VS = """
#version 430
uniform mat4 view_projection;
uniform float transparent_depth;    // MaxAlphaDepth <- WaterDraw.TransparentWaterDepth
uniform float min_opacity;          // DeepWaterAlpha <- WaterDraw.MinWaterOpacity
uniform float material_alpha;       // MaterialColorDiffuse.w
uniform int terrain_alpha;          // BlendUsingTerrainAlpha
uniform float wind_angle;
uniform float wave_angle;
uniform vec2 bump_scale_uv;
uniform vec2 env_scale_uv;
uniform vec2 wave_scale_uv;
uniform int technique;              // 0 BumpSpecular, 1 BumpSpecular_M, 2 PCA_L
uniform float time;                 // Sas Time, seconds
uniform float scroll_speed;         // WindSpeed + WaveSpeed
uniform float bump_speed;           // WindSpeed + BumpSpeed (PCA_L's bump frame)
in vec4 in_vertex;                 // x, y, water z, terrain height below
out vec3 v_world;
out float v_alpha;
out vec4 v_bump;                    // oT0: xy and the swizzled second sample
out vec2 v_env;                     // oT1
out vec4 v_wave;                    // oT4
void main() {
    v_world = in_vertex.xyz;
    // Preshader: 1 / (DeepWaterAlpha^2 x MaxAlphaDepth); oD0.w.
    float depth = in_vertex.z - in_vertex.w;
    float a = clamp(depth / (min_opacity * min_opacity * transparent_depth), 0.0, 1.0) * min_opacity;
    v_alpha = terrain_alpha != 0 ? a : material_alpha;
    // Two scroll frames at WindAngle -/+ WaveAngle/2 (Time 0 for stills).
    vec2 p = in_vertex.xy * 0.00166666671;
    float ca = cos(wind_angle - 0.5*wave_angle), sa = sin(wind_angle - 0.5*wave_angle);
    float cb = cos(wind_angle + 0.5*wave_angle), sb = sin(wind_angle + 0.5*wave_angle);
    // Preshader: each frame scrolls by Time x (WindSpeed + WaveSpeed) along its
    // own angle before the rotation.
    vec2 pa = p + time * scroll_speed * vec2(ca, sa);
    vec2 pb = p + time * scroll_speed * vec2(cb, sb);
    vec2 ra = vec2(pa.x*ca + pa.y*sa, pa.y*ca - pa.x*sa);
    vec2 rb = vec2(pb.x*cb + pb.y*sb, pb.y*cb - pb.x*sb);
    if (technique == 2) {
        // PCA_L (vs object 140): one frame, at WindAngle - WaveAngle/2. The
        // bump scrolls by Time x (WindSpeed + BumpSpeed) and the wave by
        // Time x (WindSpeed + WaveSpeed), both before the rotation.
        vec2 pc = p + time * bump_speed * vec2(ca, sa);
        v_bump = vec4(vec2(pc.x*ca + pc.y*sa, pc.y*ca - pc.x*sa) * bump_scale_uv, 0.0, 0.0);
        v_wave = vec4(ra * wave_scale_uv, 0.0, 0.0);
    } else {
        // BumpSpecular stores the second frame swizzled (oT0.zw = rb.yx x scale.xy,
        // read back as .wz); BumpSpecular_M passes it straight (oT1, oT5).
        v_bump = technique == 1 ? vec4(ra * bump_scale_uv, (rb * bump_scale_uv).yx)
                                : vec4(ra * bump_scale_uv, rb.y * bump_scale_uv.x, rb.x * bump_scale_uv.y);
        v_wave = technique == 1 ? vec4(ra * wave_scale_uv, (rb * wave_scale_uv).yx)
                                : vec4(ra * wave_scale_uv, rb.y * wave_scale_uv.x, rb.x * wave_scale_uv.y);
    }
    // PCA_L adds the World z axis' xy (0 for level water) before the scale.
    v_env = p * env_scale_uv;
    gl_Position = view_projection * vec4(v_world, 1.0);
}
"""

WATER_FS = """
#version 430
uniform sampler2D bump_tex;
uniform sampler2D env_tex;
uniform sampler2D wave_tex;
uniform int technique;              // 0 BumpSpecular, 1 BumpSpecular_M, 2 PCA_L
uniform vec3 diffuse;               // 2 x DimmingFactor x MaterialColorDiffuse (PCA_L: 1 x)
uniform vec3 eye;                   // ViewI translation
uniform vec3 light0_dir;            // DirectionalLight[0].Direction, towards the light
uniform vec3 light0_color;          // DirectionalLight[0].Color (x2 when overbright)
uniform vec3 specular_dir;          // oD1: DirectionalLight[1].Direction or MySpecularDirection
uniform vec3 specular_color;
uniform float specular_exponent;
uniform float bump_scale;
uniform float reflection_strength;
uniform float reflection_perturbation;
uniform float shadow_lightness;
uniform int has_wave;
uniform vec2 playable;
uniform int show_border;
uniform sampler2DShadow shadow_map;
uniform mat4 light_view_projection;
uniform vec2 shadow_texel;          // 1 / shadow map size
uniform float shadow_bias;          // depth units
uniform int use_shadows;           // 0 off, 1 shadow map (High), 2 volumes (Medium)
uniform vec3 shadow_color;          // GlobalLighting shadow colour (volume mode)
uniform sampler2D volume_count;     // stencil count of the shadow volumes per pixel
// High: Terrain.fx/vegetation.fx take four depth tests one texel apart and
// scale only the main light. Medium: the shadow volumes' stencil count, read
// per pixel; renderStencilShadows multiplies every pixel whose count is at
// least 1 by the shadow colour.
float lit_fraction(vec3 world) {
    if (use_shadows == 0) return 1.0;
    if (use_shadows == 2) return texelFetch(volume_count, ivec2(gl_FragCoord.xy), 0).r > 0.5 ? 0.0 : 1.0;
    vec4 p = light_view_projection * vec4(world, 1.0);
    vec3 q = p.xyz / p.w * 0.5 + 0.5;
    if (any(lessThan(q.xy, vec2(0.0))) || any(greaterThan(q.xy, vec2(1.0)))) return 1.0;
    float z = q.z - shadow_bias;
    float s = texture(shadow_map, vec3(q.xy, z));
    s += texture(shadow_map, vec3(q.xy + vec2(shadow_texel.x, 0.0), z));
    s += texture(shadow_map, vec3(q.xy + vec2(0.0, shadow_texel.y), z));
    s += texture(shadow_map, vec3(q.xy + shadow_texel, z));
    return s * 0.25;
}
in vec3 v_world;
in float v_alpha;
in vec4 v_bump;
in vec2 v_env;
in vec4 v_wave;
out vec4 frag;
// map.ini Weather hardware fog, as the effects apply it: by distance from the
// camera, lerp(fog colour, colour, 1 - clamp((d - start) / (end - start))).
uniform int fog_enabled;
uniform vec3 fog_color;
uniform vec2 fog_range;             // HardwareFogStart, HardwareFogEnd
uniform vec3 fog_eye;
vec3 apply_fog(vec3 c, vec3 world) {
    if (fog_enabled == 0) return c;
    float f = clamp((length(world - fog_eye) - fog_range.x) / max(fog_range.y - fog_range.x, 1.0), 0.0, 1.0);
    return mix(c, fog_color, f);
}
uniform sampler2D walk_tex;         // the pathfinding overlay, as on the terrain
uniform int use_walk;
uniform vec2 walk_size;
vec4 walk_tint(vec4 c) {
    if (use_walk == 0 || any(lessThan(v_world.xy, vec2(0.0))) || any(greaterThanEqual(v_world.xy, walk_size))) return c;
    vec4 w = texture(walk_tex, v_world.xy / walk_size);
    float a = w.a > 0.74 && fract((v_world.x + v_world.y) / 40.0) >= 0.5 ? w.a * 0.4 : w.a;
    return vec4(mix(c.rgb, w.rgb, a), max(c.a, a));
}

void main() {
    if (show_border == 0 && (any(lessThan(v_world.xy, vec2(0.0))) || any(greaterThan(v_world.xy, playable)))) discard;
    if (technique == 2) {
        // PCA_L (ps object 141, ps_1_1): texbem moves the env lookup by
        // BUMPENVMAT (0.05 on the diagonal) x the bump texel's red and green,
        // unsigned as the texture stores them; colour = env x oD0 + 0.1 x one
        // wave sample. oD0 is DimmingFactor x MaterialColorDiffuse (times the
        // World z axis' z^4, 1 for level water). No lights, no reflection and
        // no fog: the pass sets FogEnable false and the shader has none.
        vec2 du = texture(bump_tex, v_bump.xy).rg * 0.05;
        vec3 cp = texture(env_tex, v_env + du).rgb * clamp(diffuse, 0.0, 1.0);
        if (has_wave != 0)
            cp += 0.1 * texture(wave_tex, v_wave.xy).rgb;
        if (use_shadows == 2) cp *= mix(shadow_color, vec3(1.0), lit_fraction(v_world));
        frag = walk_tint(vec4(clamp(cp, 0.0, 1.0), v_alpha));
        return;
    }
    vec3 b = texture(bump_tex, v_bump.wz).rgb + texture(bump_tex, v_bump.xy).rgb;
    vec3 n = 2.0*b + vec3(0.0, 0.0, 1.0) - 2.0;     // + oT7, the world up axis
    n.xy *= bump_scale;
    n *= inversesqrt(dot(n, n) + 1e-10);
    if (technique == 1) {
        // BumpSpecular_M (vs object 148, ps 149): per-vertex half vector from
        // DirectionalLight[1] (unclamped), env x oD0 x (sat N.L + sat N.H^exp)
        // + wave product; oD0 already carries the light colour.
        vec3 hm = normalize(normalize(eye - v_world) + specular_dir);
        float lm = clamp(dot(n, light0_dir), 0.0, 1.0)
                 + pow(clamp(dot(n, hm), 0.0, 1.0), specular_exponent);
        vec3 cm = texture(env_tex, v_env).rgb * clamp(diffuse * light0_color, 0.0, 1.0) * lm;
        if (has_wave != 0)
            cm += texture(wave_tex, v_wave.xy).rgb * texture(wave_tex, v_wave.wz).rgb;
        cm = apply_fog(cm, v_world);
        if (use_shadows == 2) cm *= mix(shadow_color, vec3(1.0), lit_fraction(v_world));
        frag = walk_tint(vec4(clamp(cm, 0.0, 1.0), v_alpha));
        return;
    }
    // BumpSpecular: PSBumpSpecular_Array[NumShadows] (objects 76/77).
    vec3 h = normalize(normalize(eye - v_world) + clamp(specular_dir, 0.0, 1.0));
    float nh = dot(n, h);
    float nl = dot(n, light0_dir);
    float lit = nl > 0.0 ? 1.0 : 0.0;
    float spec = (nh > 0.0 ? 1.0 : 0.0) * lit * pow(max(nh, 0.0), specular_exponent);
    float diff = nl * lit;
    if (use_shadows == 1) {
        // Shadowed pixels keep min(lit/4 + ShadowLightness, 0.999).
        float s = lit_fraction(v_world);
        float k = s >= 1.0 ? 1.0 : min(s + shadow_lightness, 0.999);
        diff *= k; spec *= k;
    }
    vec3 env = texture(env_tex, v_env + reflection_perturbation * n.xy).rgb * clamp(diffuse, 0.0, 1.0);
    vec3 surface = env * diff + spec * specular_color;
    // The reflection texture is black unless map reflections are on.
    vec3 c = mix(light0_color * surface, vec3(0.0), reflection_strength);
    if (has_wave != 0)
        c += texture(wave_tex, v_wave.xy).rgb * texture(wave_tex, v_wave.wz).rgb;
    c = apply_fog(c, v_world);
    // Water writes depth (ZWriteEnable in every WaterShader pass) and is drawn
    // before the stencil shadows, which darken its surface (native captures).
    if (use_shadows == 2) c *= mix(shadow_color, vec3(1.0), lit_fraction(v_world));
    frag = walk_tint(vec4(clamp(c, 0.0, 1.0), v_alpha));
}
"""

OBJECT_VS = """
#version 430
// Vertex stage of the object techniques (see the module docstring):
// 0 fixed function, 1 vegetation.fx Default_L, 2 vegetation.fx Default,
// 3 normalmapped.fx Default_M, 4 normalmapped.fx Default_L.
uniform mat4 view_projection;
uniform int technique;
uniform vec3 ambient;               // light environment ambient
uniform vec3 light_dir[3];          // towards the light
uniform vec3 light_color[3];
uniform float sas_scale;            // Sas colours: 2 under ShaderOverbrightEnabled
uniform vec3 eye;                   // ViewI translation
uniform vec3 mat_ambient;           // fixed function: vertex material
uniform vec3 mat_diffuse;
uniform vec3 mat_emissive;
uniform float mat_opacity;
uniform int ambient_from_vertex;    // D3DMCS_COLOR1 sources (Post_Load_Process)
uniform int diffuse_from_vertex;
uniform int lighting;
uniform vec3 sway[11];              // Vegetation.SwayOffsets
uniform vec4 cloud_xform;           // Terrain.Cloud: uv = world.xy * xy + zw
uniform vec3 fx_ambient_color;      // normalmapped AmbientColor
uniform vec4 fx_diffuse;            // normalmapped DiffuseColor
uniform float fx_opacity;           // OpacityOverride
uniform int camera_mode;            // 0 normal, 1 camera-aligned, 2 camera-oriented mesh
uniform vec3 pivot;                 // aligned/oriented: the mesh's bone position, model space
uniform vec3 camera_back;           // the camera's z axis (pointing back, towards the viewer)
uniform vec3 uv_grid;               // Grid mapper: frames per row, frames per second, frames (0: none)
uniform float time;
in vec3 in_position;
in vec3 in_normal;
in vec2 in_uv;
in vec4 in_color;                   // diffuse colour array (DCG after Post_Load_Process)
in vec3 in_tangent;
in vec3 in_binormal;
in vec4 in_place;                   // x, y, z, angle
in float in_scale;
in float in_sway;                   // sway type (vegetation)
in vec2 in_uv2;                     // texture stage 1 (detail)
out vec3 v_world;
out vec2 v_uv;
out vec2 v_uv2;
out vec4 v_color;                   // oD0 (or oT4 for normalmapped Default_M)
out vec3 v_main;                    // main-light share of v_color (shadow mapping)
out vec2 v_cloud;
out vec3 v_light_t;                 // normalmapped: DirectionalLight[1] in tangent space
out vec3 v_half_t;                  // normalmapped: half vector of DirectionalLight[0]
void main() {
    float c = cos(in_place.w), s = sin(in_place.w);
    vec3 p = in_position * in_scale;
    v_world = vec3(c*p.x - s*p.y, s*p.x + c*p.y, p.z) + in_place.xyz;
    vec3 n = vec3(c*in_normal.x - s*in_normal.y, s*in_normal.x + c*in_normal.y, in_normal.z);
    if (camera_mode != 0) {
        // DX8 mesh renderer: Obj_Look_At(position, camera position) for
        // oriented meshes, (position, position + camera z) for aligned ones:
        // local x points along that direction, y stays level.
        vec3 q = pivot * in_scale;
        vec3 origin = vec3(c*q.x - s*q.y, s*q.x + c*q.y, q.z) + in_place.xyz;
        vec3 d = camera_mode == 2 ? eye - origin : camera_back;
        float len1 = length(d), len2 = length(d.xy);
        float sinp = len1 > 0.0 ? d.z / len1 : 0.0, cosp = len1 > 0.0 ? len2 / len1 : 1.0;
        float siny = len2 > 0.0 ? d.y / len2 : 0.0, cosy = len2 > 0.0 ? d.x / len2 : 1.0;
        mat3 look = mat3(vec3(cosy*cosp, siny*cosp, sinp), vec3(-siny, cosy, 0.0), vec3(-cosy*sinp, -siny*sinp, cosp));
        v_world = origin + look * p;
        n = look * in_normal;
    }
    v_uv = in_uv;
    v_uv2 = in_uv2;
    if (uv_grid.x > 0.0) {
        // GridTextureMapperClass: step through the frames row by row. The
        // offset applies to the loaded (V-flipped) coordinates, so it lowers
        // the stored V.
        float frame = mod(floor(time * uv_grid.y), uv_grid.z);
        v_uv += vec2(mod(frame, uv_grid.x), -floor(frame / uv_grid.x)) / uv_grid.x;
    }
    v_main = vec3(0.0);
    v_cloud = vec2(0.0);
    v_light_t = vec3(0.0);
    v_half_t = vec3(0.0);
    if (technique == 1 || technique == 2) {
        // vegetation.fx vs (object 39/43): the buffers copy model-space
        // normals (W3DShrubBuffer vertex fill 0x000E7DF3), so lighting ignores
        // the tree's rotation; |N.L| for each directional light, the sum plus
        // ambient times the vertex colour, halved and saturated into oD0.
        n = normalize(in_normal);
        int k = clamp(int(in_sway + 0.5), 0, 10);
        v_world += (v_world.z - in_place.z) * sway[k];
        vec3 sun = sas_scale * light_color[0] * abs(dot(n, light_dir[0]));
        vec3 sum = sun + sas_scale * (light_color[1] * abs(dot(n, light_dir[1]))
                                    + light_color[2] * abs(dot(n, light_dir[2])));
        v_main = sun * in_color.rgb * 0.5;
        v_color = vec4(clamp((sum + sas_scale * ambient) * in_color.rgb * 0.5, 0.0, 1.0), in_color.a);
        v_cloud = v_world.xy * cloud_xform.xy + cloud_xform.zw;
    } else if (technique == 3) {
        // normalmapped.fx Default_M vs (object 63): DirectionalLight[0] and
        // [2] per vertex into oT4 with DiffuseColor and Ambient x AmbientColor;
        // DirectionalLight[1] and the half vector of light 0 in tangent space
        // (x along -binormal, y along -tangent) for the pixel shader.
        vec3 N = normalize(n);
        vec3 T = normalize(vec3(c*in_tangent.x - s*in_tangent.y, s*in_tangent.x + c*in_tangent.y, in_tangent.z));
        vec3 B = normalize(vec3(c*in_binormal.x - s*in_binormal.y, s*in_binormal.x + c*in_binormal.y, in_binormal.z));
        v_light_t = vec3(dot(light_dir[1], -B), dot(light_dir[1], -T), dot(light_dir[1], N));
        vec3 h = normalize(eye - v_world) + light_dir[0];
        v_half_t = normalize(vec3(dot(h, -B), dot(h, -T), dot(h, N)));
        vec3 sun = sas_scale * light_color[0] * max(dot(N, light_dir[0]), 0.0);
        vec3 l = sun + sas_scale * light_color[2] * max(dot(N, light_dir[2]), 0.0);
        v_main = sun * fx_diffuse.rgb;
        v_color = vec4(l * fx_diffuse.rgb + sas_scale * ambient * fx_ambient_color, 1.0);
    } else if (technique == 4) {
        // normalmapped.fx Default_L vs (object 57): three lights per vertex,
        // halved and saturated into oD0; the pixel shader doubles.
        vec3 N = normalize(n);
        vec3 sum = vec3(0.0);
        for (int i = 0; i < 3; i++) sum += sas_scale * light_color[i] * max(dot(N, light_dir[i]), 0.0);
        v_main = sas_scale * light_color[0] * max(dot(N, light_dir[0]), 0.0) * fx_diffuse.rgb * 0.5;
        v_color = vec4(clamp((sum * fx_diffuse.rgb + sas_scale * ambient * fx_ambient_color) * 0.5, 0.0, 1.0), fx_opacity);
    } else {
        // Fixed function (DX8Wrapper::Set_Light_Environment, D3D lighting):
        // emissive + ambient source x D3DRS_AMBIENT + diffuse source x
        // sum(light diffuse x max(N.L, 0)), saturated per vertex.
        vec3 N = normalize(n);
        vec4 dif = diffuse_from_vertex != 0 ? in_color : vec4(mat_diffuse, mat_opacity);
        vec3 amb = ambient_from_vertex != 0 ? in_color.rgb : mat_ambient;
        vec3 sum = vec3(0.0);
        for (int i = 0; i < 3; i++) {
            vec3 d = light_color[i] * max(dot(N, light_dir[i]), 0.0);
            sum += d;
            if (i == 0) v_main = d * dif.rgb;
        }
        v_color = lighting != 0 ? vec4(clamp(mat_emissive + amb * ambient + dif.rgb * sum, 0.0, 1.0), dif.a)
                                : in_color;
    }
    gl_Position = view_projection * vec4(v_world, 1.0);
}
"""

OBJECT_FS = """
#version 430
uniform sampler2D tex;
uniform sampler2D normal_tex;
uniform sampler2D cloud_tex;
uniform int has_texture;            // 0: texture missing (drawn grey)
uniform int texturing;              // ShaderClass texturing; 0 draws the diffuse colour only
uniform int technique;
uniform int gradient;               // fixed function primary gradient: 0 disable, 1 modulate, 2 add
uniform int modulate2x;             // D3DTOP_MODULATE2X under ShaderOverbrightEnabled
uniform float alpha_ref;            // alpha test reference (>=), negative when off
uniform int use_cloud;
uniform vec3 light_color[3];
uniform float sas_scale;
uniform vec4 fx_diffuse;
uniform vec3 fx_specular;           // normalmapped SpecularColor
uniform float fx_exponent;          // SpecularExponent
uniform float fx_bump;              // BumpScale
uniform float fx_opacity;
uniform vec3 fx_emissive;           // simple.fx ColorEmissive
uniform int fx_fog;                 // simple.fx FogEnable
uniform vec2 fx_uv_scale;           // simple.fx TexCoordTransform_0.xy
uniform vec3 sky_horizon;           // sky domes: rim colour (also the background below)
uniform vec2 sky_rim;               // sky domes: rim world z, height of the fade (0: none)
uniform int depth_only;
uniform sampler2DShadow shadow_map;
uniform mat4 light_view_projection;
uniform vec2 shadow_texel;          // 1 / shadow map size
uniform float shadow_bias;          // depth units
uniform int use_shadows;           // 0 off, 1 shadow map (High), 2 volumes (Medium)
uniform vec3 shadow_color;          // GlobalLighting shadow colour (volume mode)
uniform sampler2D volume_count;     // stencil count of the shadow volumes per pixel
// High: Terrain.fx/vegetation.fx take four depth tests one texel apart and
// scale only the main light. Medium: the shadow volumes' stencil count, read
// per pixel; renderStencilShadows multiplies every pixel whose count is at
// least 1 by the shadow colour.
float lit_fraction(vec3 world) {
    if (use_shadows == 0) return 1.0;
    if (use_shadows == 2) return texelFetch(volume_count, ivec2(gl_FragCoord.xy), 0).r > 0.5 ? 0.0 : 1.0;
    vec4 p = light_view_projection * vec4(world, 1.0);
    vec3 q = p.xyz / p.w * 0.5 + 0.5;
    if (any(lessThan(q.xy, vec2(0.0))) || any(greaterThan(q.xy, vec2(1.0)))) return 1.0;
    float z = q.z - shadow_bias;
    float s = texture(shadow_map, vec3(q.xy, z));
    s += texture(shadow_map, vec3(q.xy + vec2(shadow_texel.x, 0.0), z));
    s += texture(shadow_map, vec3(q.xy + vec2(0.0, shadow_texel.y), z));
    s += texture(shadow_map, vec3(q.xy + shadow_texel, z));
    return s * 0.25;
}
in vec3 v_world;
in vec2 v_uv;
in vec2 v_uv2;
uniform int detail_func;            // W3D DetailColorFunc of texture stage 1
uniform sampler2D detail_tex;
in vec4 v_color;
in vec3 v_main;
in vec2 v_cloud;
in vec3 v_light_t;
in vec3 v_half_t;
out vec4 frag;
// map.ini Weather hardware fog, as the effects apply it: by distance from the
// camera, lerp(fog colour, colour, 1 - clamp((d - start) / (end - start))).
uniform int fog_enabled;
uniform vec3 fog_color;
uniform vec2 fog_range;             // HardwareFogStart, HardwareFogEnd
uniform vec3 fog_eye;
vec3 apply_fog(vec3 c, vec3 world) {
    if (fog_enabled == 0) return c;
    float f = clamp((length(world - fog_eye) - fog_range.x) / max(fog_range.y - fog_range.x, 1.0), 0.0, 1.0);
    return mix(c, fog_color, f);
}
void main() {
    // W3D stores V from the bottom (verified against native trees and bridges);
    // textures are uploaded top row first, so V is flipped here.
    vec2 uv = vec2(v_uv.x, 1.0 - v_uv.y);
    vec4 base = texturing == 0 ? vec4(1.0) : has_texture != 0 ? texture(tex, uv) : vec4(0.6, 0.6, 0.6, 1.0);
    if (depth_only != 0) {
        if (alpha_ref >= 0.0 && base.a < alpha_ref) discard;
        frag = vec4(1.0);
        return;
    }
    float lit = lit_fraction(v_world);
    vec4 c;
    if (technique == 1) {
        // PS_L_Array (objects 41/42, ps_1_1): tex x oD0 x 1.999, no cloud.
        c = base * v_color;
        c.rgb *= 1.999;
    } else if (technique == 2) {
        // PS_Array (objects 37/38, ps_2_0): shadow mapping subtracts the
        // shadowed share of the main light (oT4), then tex x oD0 x cloud x 2.
        vec3 d = v_color.rgb;
        if (use_shadows == 1) d -= v_main * (1.0 - lit);
        c = base * vec4(d, v_color.a);
        if (use_cloud != 0) c.rgb *= texture(cloud_tex, v_cloud).rgb;
        c.rgb *= 2.0;
    } else if (technique == 3) {
        // PS_M_Array (object 65, ps_2_0): oT4 x tex + DirectionalLight[1]
        // bump diffuse + DirectionalLight[0] specular gated by N.L1 > 0.
        vec3 nm = texture(normal_tex, uv).rgb * 2.0 - 1.0;
        nm.xy *= fx_bump;
        nm = normalize(nm);
        float ndh = dot(nm, v_half_t);
        float ndl = dot(nm, v_light_t);
        float gate = ndl > 0.0 ? 1.0 : 0.0;
        vec3 diffuse = base.rgb * sas_scale * light_color[1] * fx_diffuse.rgb * (ndl * gate);
        float spec = ndh > 0.0 ? pow(ndh, fx_exponent) * gate : 0.0;
        vec3 lightv = v_color.rgb;
        if (use_shadows == 1) lightv -= v_main * (1.0 - lit);
        c = vec4(lightv * base.rgb + diffuse + sas_scale * light_color[0] * fx_specular * spec, base.a * fx_opacity);
    } else if (technique == 4) {
        // PS_L_Array (object 59, ps_1_1): mul_x2 tex x oD0.
        c = vec4(base.rgb * v_color.rgb * 2.0, base.a * v_color.a);
    } else if (technique == 5) {
        // simple.fx Default (sky domes, ps_1_1): tex x ColorEmissive, no
        // lighting and no shadows; fog only with FogEnable.
        vec4 t = has_texture != 0 ? texture(tex, vec2(v_uv.x * fx_uv_scale.x, 1.0 - v_uv.y * fx_uv_scale.y)) : base;
        vec3 sky = t.rgb * fx_emissive;
        // The dome's lowest band fades into its rim colour, which the
        // background below the dome also takes: no edge at the horizon.
        if (sky_rim.y > 0.0) sky = mix(sky_horizon, sky, smoothstep(sky_rim.x, sky_rim.x + sky_rim.y, v_world.z));
        frag = vec4(clamp(fx_fog != 0 ? apply_fog(sky, v_world) : sky, 0.0, 1.0), t.a);
        return;
    } else {
        // Fixed function stage 0 (ShaderClass::Apply primary gradient).
        vec4 d = v_color;
        if (use_shadows == 1) d.rgb = max(d.rgb - v_main * (1.0 - lit), 0.0);
        if (gradient == 0) c = base;
        else if (gradient == 2) c = vec4(base.rgb + d.rgb, base.a * d.a);
        else c = vec4(base.rgb * d.rgb * (modulate2x != 0 ? 2.0 : 1.0), base.a * d.a);
        // Stage 1 (ShaderClass::Apply detail colour): DETAIL, SCALE, ADD,
        // ADDSIGNED, ADDSIGNED2X and SCALE2X.
        if (detail_func != 0) {
            vec3 dt = texture(detail_tex, vec2(v_uv2.x, 1.0 - v_uv2.y)).rgb;
            if (detail_func == 1) c.rgb = dt;
            else if (detail_func == 2) c.rgb *= dt;
            else if (detail_func == 4) c.rgb += dt;
            else if (detail_func == 9) c.rgb += dt - 0.5;
            else if (detail_func == 10) c.rgb = 2.0 * (c.rgb + dt - 0.5);
            else if (detail_func == 11) c.rgb *= 2.0 * dt;
        }
    }
    if (alpha_ref >= 0.0 && c.a < alpha_ref) discard;
    vec3 color = apply_fog(c.rgb, v_world);
    if (use_shadows == 2) color *= mix(shadow_color, vec3(1.0), lit);
    frag = vec4(clamp(color, 0.0, 1.0), clamp(c.a, 0.0, 1.0));
}
"""

DECAL_VS = """
#version 430
uniform vec4 world_to_clip;         // clip = world.xy * xy + zw
in vec2 in_corner;                  // -0.5 .. 0.5
in vec3 in_decal;                   // x, y, size
out vec2 v_uv;
void main() {
    vec2 world = in_decal.xy + in_corner * in_decal.z;
    v_uv = in_corner + 0.5;
    gl_Position = vec4(world * world_to_clip.xy + world_to_clip.zw, 0.0, 1.0);
}
"""

DECAL_FS = """
#version 430
uniform sampler2D tex;
in vec2 v_uv;
out vec4 frag;
void main() { frag = vec4(texture(tex, v_uv).rgb, 1.0); }
"""

PARTICLE_VS = """
#version 430
uniform mat4 view_projection;
uniform vec3 right;                 // camera right vector, world units
uniform float size;                 // SnowQuadSize
uniform float box;                  // SnowBoxHeight
uniform float travelled;            // time x SnowSpeed
uniform float amplitude;            // SnowAmplitude
uniform vec2 frequency;             // SnowFrequencyScaleX/Y
uniform vec2 drift;                 // time x SnowXYSpeed
uniform vec2 drift_per_cycle;       // SnowXYSpeed x SnowBoxHeight / SnowSpeed
in vec2 in_corner;
in vec3 in_emitter;                 // x, y, starting height
out vec2 v_uv;
out vec3 v_world;
void main() {
    // renderAsQuads (0x00093CC3): h = box - fmod(start + travelled, box),
    // wobble amplitude x sin(h x frequency + x), drift minus whole fall cycles.
    float fall = in_emitter.z + travelled;
    float cycles = floor(fall / box);
    float h = box - (fall - box * cycles);
    vec3 center = vec3(in_emitter.x + amplitude * sin(h * frequency.x + in_emitter.x) + drift.x - cycles * drift_per_cycle.x,
                       in_emitter.y + amplitude * sin(h * frequency.y + in_emitter.y) + drift.y - cycles * drift_per_cycle.y, h);
    v_world = center;
    v_uv = in_corner * 0.5 + 0.5;
    // Corners +-right +-world Z, scaled by 0.707 x SnowQuadSize.
    vec3 corner = center + (in_corner.x * right + in_corner.y * vec3(0.0, 0.0, 1.0)) * (0.707 * size);
    gl_Position = view_projection * vec4(corner, 1.0);
}
"""

PARTICLE_FS = """
#version 430
uniform sampler2D tex;
uniform vec2 playable;
in vec2 v_uv;
in vec3 v_world;
out vec4 frag;
void main() {
    if (any(lessThan(v_world.xy, vec2(0.0))) || any(greaterThan(v_world.xy, playable))) discard;
    // Shader 0x198B3 leaves fog off; the vertex colour is white.
    frag = texture(tex, vec2(v_uv.x, 1.0 - v_uv.y));
}
"""

# Object effects (render.effects): one quad or triangle per particle, its
# corners in camera space (x right, y up) as PointGroupClass builds them,
# turned by the particle's angle and scaled by its size. Ground-aligned
# systems pass world x and y as right and up. Texture x vertex colour
# (the point group's MODULATE gradient), alpha tested if the shader does.
EFFECT_VS = """
#version 430
uniform mat4 view_projection;
uniform vec3 right;
uniform vec3 up;
in vec4 in_corner;                  // offset x, y; u, v within the frame
in vec3 in_center;
in float in_size;
in vec4 in_color;
in float in_angle;
in vec3 in_frame;                   // frame origin u, v and frame size
out vec2 v_uv;
out vec4 v_color;
out vec3 v_world;
void main() {
    float c = cos(in_angle), s = sin(in_angle);
    vec2 o = vec2(in_corner.x * c - in_corner.y * s, in_corner.x * s + in_corner.y * c) * in_size;
    v_world = in_center + right * o.x + up * o.y;
    v_uv = in_frame.xy + in_corner.zw * in_frame.z;
    v_color = in_color;
    gl_Position = view_projection * vec4(v_world, 1.0);
}
"""

EFFECT_FS = """
#version 430
uniform sampler2D tex;
uniform float alpha_ref;            // < 0: no alpha test
uniform int fog_enabled;
uniform vec3 fog_color;
uniform vec2 fog_range;
uniform vec3 fog_eye;
uniform int fog_mode;               // 0 fog colour, 1 black (additive), 2 white (multiply)
in vec2 v_uv;
in vec4 v_color;
in vec3 v_world;
out vec4 frag;
void main() {
    vec4 c = texture(tex, v_uv) * v_color;
    if (alpha_ref >= 0.0 && c.a < alpha_ref) discard;
    if (fog_enabled != 0) {
        float f = clamp((length(v_world - fog_eye) - fog_range.x) / max(fog_range.y - fog_range.x, 1.0), 0.0, 1.0);
        vec3 target = fog_mode == 1 ? vec3(0.0) : fog_mode == 2 ? vec3(1.0) : fog_color;
        c.rgb = mix(c.rgb, target, f);
    }
    frag = c;
}
"""

# Stencil shadow volumes (Medium: UseShadowVolumes). The silhouette quads are
# built on the CPU (render.shadows.silhouette_quads), as the game builds them
# per object: each polygon's facing is decided once, so the quads of
# neighbouring edges always pair up. Faces in front of the scene depth add +1
# when they face the camera and -1 otherwise, as the INCR/DECR stencil passes
# do.
VOLUME_VS = """
#version 430
uniform mat4 view_projection;
in vec3 in_position;                // world space
void main() { gl_Position = view_projection * vec4(in_position, 1.0); }
"""

# RiverWater.fx (shaders/compiled/riverwater.fxo), technique Default_M; its
# Default_L pass 0 is the same arithmetic in ps_1_1 and pass 1 only multiplies
# in the shroud, which is not drawn. Per vertex: the river and sparkle
# textures at (u1, v), the alpha edge at (u2, v), the noise in world space at
# 1/16 scale scrolling by Time x UVScrollPerSecond (the river's UV speed on
# both axes). v scrolls and wobbles as drawRiverWater sets it (render.rivers).
# The pass draws with depth test, no depth writes, no culling and no fog
# (FOGENABLE 0), blending SRCALPHA with DESTBLEND 6 - 4 x IsAdditiveBlended:
# ONE for additive rivers, INVSRCALPHA for the others.
RIVER_VS = """
#version 430
uniform mat4 view_projection;
uniform float time;                 // seconds; VOrigin = time x the river's UV speed
uniform float uv_speed;
in vec3 in_position;                // x, y, the river's water height
in vec2 in_uv;                      // u1 (river, sparkle), u2 (alpha edge)
in float in_v;                      // v before the scroll and wobble
out vec3 v_world;
out vec2 v_tex0;                    // oT0 = oT1
out vec2 v_tex2;                    // oT2: the noise
out vec2 v_tex3;                    // oT3: the alpha edge
out vec2 v_strip;                   // u2 and the unscrolled v, for the flow overlay
void main() {
    float origin = time * uv_speed;
    float v = in_v + sin(6.28318531 * in_v - 3.0 * origin) / 22.0 - origin;
    v_world = in_position;
    v_tex0 = vec2(in_uv.x, v);
    v_tex3 = vec2(in_uv.y, v);
    v_tex2 = in_position.xy * 0.0625 + time * vec2(uv_speed);
    v_strip = vec2(in_uv.y, in_v);
    gl_Position = view_projection * vec4(in_position, 1.0);
}
"""

RIVER_FS = """
#version 430
uniform sampler2D river_tex;        // s0 RiverSampler
uniform sampler2D sparkle_tex;      // s1 SparklesSampler
uniform sampler2D noise_tex;        // s2 NoiseSampler
uniform sampler2D edge_tex;         // s3 OpacitySampler (the alpha edge)
uniform vec4 diffuse;               // oD0: the river's vertex colour (render.rivers.vertex_colour)
uniform float opacity;              // Opacity.w: the river's alpha
uniform vec2 playable;
uniform int show_border;
in vec3 v_world;
in vec2 v_tex0;
in vec2 v_tex2;
in vec2 v_tex3;
in vec2 v_strip;
out vec4 frag;
void main() {
    if (show_border == 0 && (any(lessThan(v_world.xy, vec2(0.0))) || any(greaterThan(v_world.xy, playable)))) discard;
    vec4 river = texture(river_tex, v_tex0);
    vec4 sparkle = texture(sparkle_tex, v_tex0);
    vec4 noise = texture(noise_tex, v_tex2);
    vec4 edge = texture(edge_tex, v_tex3);
    vec3 c = sparkle.rgb * noise.rgb + diffuse.rgb * river.rgb + edge.rgb;
    float a = edge.a * river.a * diffuse.a * opacity;
    frag = clamp(vec4(c, a), 0.0, 1.0);
}
"""

# The flow overlay over a river strip (mw render --flow, the viewer's River
# flow): chevrons pointing downstream, one per v repeat and drifting
# downstream with time; the strip's banks as thin lines, its first cross-section
# green and its last red. At least a pixel or two wide at any distance.
RIVER_FLOW_FS = """
#version 430
uniform float time;
uniform float strip_length;         // the strip's length in v
uniform vec2 playable;
uniform int show_border;
in vec3 v_world;
in vec2 v_strip;
out vec4 frag;
void main() {
    if (show_border == 0 && (any(lessThan(v_world.xy, vec2(0.0))) || any(greaterThan(v_world.xy, playable)))) discard;
    vec2 px = fwidth(v_strip) * 1.5;
    float across = abs(v_strip.x - 0.5);
    // The middle of each chevron leads: v + 0.8|u - 0.5| is constant along it.
    float f = fract(v_strip.y + 0.8 * across - time * 0.25);
    vec4 c = vec4(0.0);
    if (v_strip.x < max(0.02, px.x) || v_strip.x > 1.0 - max(0.02, px.x)) c = vec4(0.25, 0.85, 1.0, 0.85);
    if (across < 0.34 && f < max(0.12, px.y)) c = vec4(1.0, 0.82, 0.12, 0.95);
    if (v_strip.y < max(0.06, px.y)) c = vec4(0.2, 1.0, 0.3, 0.95);
    if (v_strip.y > strip_length - max(0.06, px.y)) c = vec4(1.0, 0.25, 0.2, 0.95);
    if (c.a == 0.0) discard;
    frag = c;
}
"""

WATER_DEPTH_VS = """
#version 430
uniform mat4 view_projection;
in vec4 in_vertex;                  // x, y, water z, terrain height below
void main() { gl_Position = view_projection * vec4(in_vertex.xyz, 1.0); }
"""

DEPTH_FS = """
#version 430
out vec4 frag;
void main() { frag = vec4(1.0); }
"""

VOLUME_FS = """
#version 430
out vec4 frag;
void main() { frag = vec4(gl_FrontFacing ? 1.0 : -1.0, 0.0, 0.0, 0.0); }
"""
