# Rendering maps

`mw render` draws a map offscreen on the GPU, without starting the game. It
reads terrain textures, models and INIs from the installed BFME2 archives and
the extracted game data, so previews use the same art as the game. The
[viewer](viewer.md) uses the same renderer. Use them for fast iteration, and
check what matters in the game itself (`mw play`).

```powershell
mw render --map greywater-marches --out local/renders/greywater `
  --view base5  target=5500,1090 distance=1800 elevation=40 `
  --view bridge target=11900,3850 distance=900 elevation=30 heading=300 `
  --view sw     region=0,0,4500,3000 `
  --top
```

`--map` takes a map project, a stock map name or a `.map` file. Each run
writes one PNG per view plus `render.json` (map hash, camera settings, missing
assets and texture-size errors). Rendering a set of views takes a few seconds.
`--weather PRESET` and `--sun NAME` apply the viewer's weather presets and
light rigs.

## Cameras

`--view` specs are plain preview cameras (the game's own camera is described
below). `near=` sets the near clip.
World units: X east, Y north, origin at the playable south-west corner,
10 units per terrain cell.

| Key | Default | Meaning |
| --- | --- | --- |
| `target=X,Y[,Z]` | required | Point to look at; Z defaults to the terrain height |
| `distance=` | 1500 | Camera distance from the target |
| `elevation=` | 45 | Degrees above the horizon; 90 looks straight down |
| `heading=` | 0 | Direction the camera faces: 0 N, 90 E, 180 S, 270 W |
| `fov=` | 50 | Horizontal field of view in degrees |
| `eye=X,Y,Z` | — | Explicit camera position instead of distance/elevation/heading |
| `region=X0,Y0,X1,Y1` | — | Orthographic top view of a rectangle, north up |

`--top` adds a top view of the whole map at `--top-scale` pixels per cell
(default 2). `--size` sets the size of orbit views (default 1600x1200).
Reusable view sets go in a JSON file passed with `--views`:

```json
{"views": {
  "river-shore": {"target": [6700, 6050], "distance": 1700, "elevation": 40},
  "southwest":   {"region": [0, 0, 4500, 3000]}
}}
```

The 30-cell border outside the playable area is drawn black, as the game
does; `--border` shows its terrain (generators often fill it by repeating the
edge, which looks streaked). Other options: `--no-objects`, `--normal-maps auto|on|off`, `--no-shadows`, `--no-clouds`
(the cloud texture is on, as in game, frozen at time zero), `--lod`, `--grid` (100-unit world grid overlay) and `--flow` (river flow arrows: yellow chevrons
pointing downstream along each river strip, its banks in blue, its first cross-section green and its last
red, so joins and overlaps between strips show).

## Single objects and collages

`mw item` renders one object template on its own; `mw items` puts any number
of them into one labelled collage. Each stands on a plain background (white,
`--background transparent` or `#rrggbb`) with a soft ground shadow (`--no-shadow`),
drawn by this renderer, so models, materials and textures are those of the map
renders.

```powershell
mw item GenericTreeBridge                              # three-quarter view, framed to the model
mw item GenericTreeBridge --heading 90 --elevation 20 --rotation 45
mw item ShireGeneric03 --top                           # straight down: the footprint
mw items "*bridge*"                                    # every template with "bridge" in its name
mw items ShireGeneric01 CBHobbitBldg01 --views 3q,side,top
mw items --from-map bramble-hollow --layer Hamlet      # what a map places, most used first
mw item FireCampfire --info                            # no image: what the game says about it
```

To find names to render, `mw find` searches the templates by type, region and
material ([making maps](making-maps.md#finding-objects-textures-and-effects));
`mw find ... --render` renders its results as a collage.

Patterns are template names or case-insensitive wildcards over the game's
templates that have a model. Views: `3q` (default), `front`, `back`, `left`,
`right`, `side`, `top`, or `HEADING/ELEVATION` such as `135/20`; several views
give one row per object. `--heading` and `--elevation` change the `3q` view,
`--rotation` turns the object itself. The named views are camera positions
around the object at rotation 0, not the model's own sides: `front` (heading 0)
shows its local -y side, `back` its +y side, `left` (heading 270) its +x side
and `right`/`side` its -x side. They look from 15 degrees up, which leaves the
side away from the sun dark; `0/40,90/40,180/40,270/40` shows all four sides
more clearly. Models don't agree on which side is their front, so look before
choosing a building's angle: on a map, angles are counter-clockwise and at
angle 0 a model's local +y points north. Each image is cropped to the object and
its shadow and fills its tile, so a scale bar in the corner gives the size
(map units at the object's centre; exact in top views). Each tile is labelled
with the template and its size in map units (width x depth x height of the
model as placed).
Images go to `local/renders/items/` (or `--out`), each with a JSON file listing
every object's model, scale and size, and the templates left out and why.
About 60 bridges take 11 seconds.

## The game camera

`render.camera.GameCamera` reproduces the game's camera from the matched W3DView
code. bfme-workshop uses it to render native screenshot runs from the same
camera, side by side (`render-compare`); this repository keeps the camera.

`lookAt` (0x0008D55D) keeps the focus with z = 0 and sets the ground level G
to the map's smoothed camera height at the focus (`SmoothCameraHeightField`
0x0030E961: the maximum of each 4 x 4 block of height samples, 40 units
apart, raised to every neighbour minus `cameraMapHeightSmoothnessScalar` x 24,
x 1.4 diagonally; sampled by 0x0030E67C). The offset (`getCameraOffset`
0x001018CD) points back at `cameraPitchAngle` (37.5) above the horizon with
offset.z = `cameraMaxHeight` (map WorldInfo, else GameData).
`W3DView::update` (0x0008C3AC) moves the zoom towards (height + G) / offset.z
by `CameraAdjustSpeed` per frame and stops once a step is below 0.0001, which
leaves the eye a few units off (up to 10 at Greywater's 30000
cameraMaxHeight), on the side it came from. The solver (as Zero Hour's
buildCameraTransform) puts the eye at z = zoom x offset.z and looks at
(focus x, focus y, G); near clip 10, 50-degree horizontal field of view.
`capture.json` records the eye height the game reached
(`camera.renderHeight`); it is used when present, otherwise the convergence
is replayed from the previous shot. On the Greywater captures this
reproduces every recorded eye height to float precision (the first shot of a
run to 0.1 units) and the native framing to within one pixel.

## What is reproduced

The renderer ports the retail effect files, the openbfme2/EA height-map source
and functions disassembled from `game.dat` 1.06. It imitates a game detail
level from `GameLOD.ini`: `--lod medium` (default), `high` or `low`. Medium has no terrain normal maps and uses stencil
volume shadows; High adds normal maps and uses shadow mapping. `--normal-maps`
switches the terrain between the High and Medium techniques, as
`UseTerrainNormalMap` does in game.

- Terrain technique: `terrain.fx` is set up in `HeightMap` 0x000E153A with
  shader LOD 2 when `UseTerrainNormalMap` is on, else 1 with
  `UseDistanceDependantTerrainTextures`, else 0 (GameLOD.ini offsets 0x14 and
  0x15, copied to GlobalData +0x49/+0x4A). `InitializeShader` turns that into
  `Default` (High), `Default_M` (Medium) or `Default_L` (Low). The array
  selectors (fx_2_0 preshaders) pick `min(RenderingMode,4)` plus
  5 x Taint (Medium) or 5 x NumShadows (High) plus 10 x IsRenderingOverbright
  (Medium) or 5 x it (Low); terrain draws with RenderingMode 0.
- Terrain texture: the game composites each 16x16-cell tile into one texture
  on the CPU (`getPointerToTileData` 0x000AED2E): base tile, then the blend
  and three-way tiles (`Use3WayTerrainBlends`) mixed by the 64x64 alpha ramps
  of `setupAlphaTiles`; the tiles' own alpha is not used, and cliff cells drop
  the primary blend. The renderer mixes the same layers per pixel with the
  per-corner ramps of `getAlphaUVData` (diagonal flips included), which give
  the same weights. Tiles beyond `updateCenter`'s distance
  (display width / 1024 clamped to 0.5..2.5, times 430, plus 25) use the 1x
  texture at 16 px per cell; nearer ones get 32 px per cell, and only with
  distance-dependent textures (so Low is 16 px per cell everywhere).
- Terrain lighting: vertex colour from `doTheLight` (ambient plus every global
  terrain light, rays as stored, colours times the GlobalLighting v8 final
  values, clamped). The sun stays in it unless normal maps are on: the terrain
  light environment (0x000E3150) holds the sun only then, so at Low and Medium
  `Sas.DirectionalLight[0]` is black. Low (`Default_L`): texture x vertex
  colour, x2 under overbright, no cloud or macro. Medium (`Default_M`): the
  same, then pass P1 multiplies cloud x macro (native captures confirm it,
  and the distance fog, although the effect's pass states would disable both).
  High (`Default`): normal from the composited normal texture's RG with z
  rebuilt, N.L and N.H^1200 x B x 0.9 in the per-vertex frame
  T = (Nz, 0, -Nx), B = (0, Nz, -Ny); colour = vertex x texture + sun x
  (N.L x texture + specular), x2 under overbright, x cloud x macro. Textures
  without `_nrm` maps get a flat normal without gloss (B = 0): in game their
  flat ground shows no sun glare, where B = 255 mirrored the sun over whole
  fields seen from afar ([Specular Lab](../maps/specular_lab/map.py), High
  screenshots facing the sun, 15 October 2026). Macro UV: stretched
  `(x + border, -(y + border)) / (samples x 10)`, else `(x, -y) / 660`.
  Cloud UV: world / CloudTextureSize plus Time x CloudOffsetPerSecond.
- Water: the mesh of `RenderableStandingWaterArea::AllocateAndFillBuffers`
  (0x0008304A): a grid of 20 units (40 while `WaterLOD` is High or lower),
  doubled until it fits the vertex budget, cells kept by centre-in-polygon,
  each vertex carrying the terrain height below it. Alpha per vertex as in
  `WaterShader.fx`: `clamp(depth / (MinOpacity^2 x TransparentWaterDepth)) x
  MinOpacity`, with both values from the `WaterTransparency` INI block
  (water.ini, then the map's map.ini), so shorelines fade across one grid cell.
- Water model and technique: `StandingWaterArea::loadFXShaderSetup`
  (0x00308C31) reads `WaterLOD` from GameLOD.ini (Low 0, Medium 1, High 2,
  UltraHigh 3; the Medium preset sets Medium), tries the area's shader name
  without `.W3D` plus `L`/`M`/none/none from that level upwards, and passes
  the same level as the shader LOD. The model's FX chunk stores a technique
  index (`FXShaderSetup::Load_W3D`); `InitializeShader` strips any `_L/_M/_U`
  suffix and takes the first technique the effect has from the LOD's suffix
  downwards, then upwards. Greywater at Medium: `wtr_Riv03M` with
  `BumpSpecular_M`; at High `wtr_Riv03` with `BumpSpecular`.
- Water shading: GLSL ports of the compiled `WaterShader.fx` shaders, read
  with `python -m mapworkshop.formats.fxo` (see below). Both take two bump samples in
  frames rotated by WindAngle -/+ WaveAngle/2. `BumpSpecular_M`: env texture x
  2 x Dimming x MaterialDiffuse x light colour x (N.L + N.H^exponent), plus
  the wave product. `BumpSpecular`: Blinn specular and N.L, lerped towards the
  reflection texture by ReflectionStrength; the env and reflection lookups
  move by ReflectionPerturbation x the bump normal before it is normalized
  (PSBumpSpecular's r0, about three times the unit normal's xy). Lights are `Sas.DirectionalLight[0..1]`: the object lights, towards
  the light, colours doubled under overbright. `PCA_L` (Low) is unlit and
  takes no reflection, despite its name: the env texture, its lookup moved by
  0.05 x one bump sample (texbem), x DimmingFactor x MaterialDiffuse, plus 0.1
  x one wave sample, in one frame at WindAngle - WaveAngle/2; the pass has
  fog off. Other techniques (`PCA_M`, `PCA`, `PCA_U`, which read the engine's
  `PCAWater` bases) are drawn with the BumpSpecular port and flagged
  `approximated` in the render report.
- Underwater terrain: as in `getStaticDiffuse` (0x0006B4CC), the terrain
  vertex colour under a standing-water area is multiplied by the area's depth
  LUT (24-bit TGA, e.g. `LUTDepthTint.tga`) sampled at
  `(waterZ - groundZ) / max(waterZ, 1)`.
- Weather: the map.ini Weather block over weather.ini's. Hardware fog
  (HardwareFogEnable/Color/Start/End) reaches the effects as the WW3D `Fog`
  parameters (IsEnabled, Color, RangeStart, RangeEnd): the scene fog is set
  from TheWeatherSetting (near 0x00071F88) and bound by 0x0018BFCE. The
  effects switch fixed-function fog off and blend towards the fog colour by
  1 - clamp((|world - eye| - start) / (end - start)), per vertex; the
  renderer evaluates the same expression per pixel. Terrain, objects and
  water are fogged before the stencil shadows darken the frame; rain and
  snow are not fogged (their shader, bits 0x198B3, has fog off).
  With IsSnowing, falling rain or snow follows W3DSnowManager and
  renderAsQuads (0x00093CC3, read from game.dat): emitters every SnowSpacing
  units over the first of NumberTiles x NumberTiles sub-boxes of the map,
  repeated over the tiles; heights from a 64x64 table of rand() %
  SnowBoxHeight, falling from SnowBoxHeight (world height); SnowAmplitude
  wobble; drift time x SnowXYSpeed less SnowXYSpeed x box / SnowSpeed per
  completed fall. Each drop is a quad spanned by the camera's right vector
  and world Z, 0.707 x SnowQuadSize either side of its centre, alpha blended
  without depth writes, with no distance cull (only the near clip).
  `--no-weather` and viewer key 6 turn it off.
- Shadows, Medium: stencil shadow volumes as the game builds them
  (`src/mapworkshop/render/shadows.py`). W3DShadowManager::addShadow (0x0009A8D3) sends
  `SHADOW_VOLUME` and `SHADOW_VOLUME_NON_SELF_*` to W3DVolumetricShadowManager
  and `SHADOW_VOLUME_NEW` to the V2 manager; `*_OR_DECAL` become volumes only
  while UseShadowVolumes is on. Geometry is the top LOD's meshes with the W3D
  CAST_SHADOW attribute (0x8000), hidden ones included (V2 skips hidden meshes
  without SHADOW in the name), so objects without such a mesh (crates, fire
  pits, giant skulls, rubble) cast nothing. `KindOf OPTIMIZED_PROP` map
  objects go to the prop buffer (W3DTerrainVisual::addProp 0x0009257A) and
  cast nothing either. The light is terrain light 0, reversed and placed
  10,000,000 units away (W3DShadowManager::setTimeOfDay 0x0009A64D). With the
  camera outside a volume both managers draw only quads over silhouette
  edges (edges of light-facing triangles whose neighbour faces away or that
  have none: buildSilhouette; V2 0x00106D56 and 0x00107A50), extruded per
  instance. Like the game, the renderer builds them on the CPU
  (`render.shadows.silhouette_quads`): each polygon's facing is decided
  once, so the quads of neighbouring silhouette edges always pair up (a
  geometry shader that re-tests a neighbour from its own vertex order can
  disagree with it on faces edge-on to the light, leaving stray quads that
  streak the shadow). Volume faces neither write depth nor hide each other.
  Classic volumes run from each mesh's box top down to the lowest
  terrain found by marching the object box's top corners along the light
  ray (updateOptimalExtrusionPadding 0x000F1212), less 0.1. V2 volumes move
  by a vector whose z is -(height above ground + box top + 20.1)
  (0x001074D5). The renderer counts volume faces in front of the receivers'
  depth (+1 facing the camera, -1 otherwise, as the INCR/DECR stencil
  passes) and multiplies pixels counted at least once by the GlobalLighting
  shadow colour, after fog (renderStencilShadows 0x000F0842). Receivers are
  terrain, opaque and alpha-tested objects, trees and water (WaterShader
  writes depth, and native captures show volume shadows on the water);
  translucent meshes come later. The full-screen pass belongs to the classic
  manager, so a map with only V2 casters shows no volume shadows, as in game.
- Shadow decals: optimized trees and shrubs whose Shadow is SHADOW_DECAL draw
  their template's ShadowTexture (addTreeType: doShadow = shadowKind == 1).
  Without one (Greywater's trees set none) they draw the default
  `shadow.tga` blob, which native captures show under every tree base: the
  shadow managers take "shadow" for a name of one character or less (Zero
  Hour `createDecalShadow`, BFME2 `addShadow`). The tree buffer's own decal
  draw is unmatched, so blob size and strength follow Zero Hour. In fog the
  blobs, and the stencil shadows on the terrain, fade with the fog (the game
  runs its shadow pass after fog, but its camera never sees far enough into
  fog for that to show; from low viewer angles far shadows would otherwise
  read as dark specks).
- Shadows, High: shadow mapping. Objects with a `Shadow` type cast into a
  sun-aligned depth map at the game's texel size (`ShadowMap` MapSize over
  MaxViewDistance in environment.ini); terrain and objects take four depth
  tests one texel apart and scale only the main light. UseShadowMapping
  switches volumes and decals off (GameLOD ApplyPreset).
- Objects: W3D models in bind pose (HLOD, hierarchy, skins) with
  `InstanceScaleFuzziness`. The light environment is the map's object
  ambient and object lights as `LightEnvironmentClass::Add_Light`
  (0x00140770) keeps them: lights below 0.05 in every channel are dropped
  (Greywater's third light), the rest sorted by brightness. At Low and Medium
  (ShaderLOD <= 1) the scene (0x0006E716) and the vegetation step
  (0x00071A1F) scale it by the GlobalLighting chunk's final three values;
  W3DPropDraw props (`W3DPropBuffer::drawProps`) are not scaled.
- Classic W3D materials (no FX chunk) go through the fixed-function path at
  every detail level: per-vertex lighting from the vertex material, with DCG
  folded in as `MeshMatDescClass::Post_Load_Process` does (diffuse and
  ambient taken from the vertex colour), saturated, times the texture
  (`MODULATE2X` when the map is overbright). Blending, depth writes and
  culling follow `ShaderClass::Apply`: alpha test >= 0x60, >= 1 for
  SrcAlpha/InvSrcAlpha blending, back faces culled unless the mesh is
  two-sided. High's `ShaderMaterialReplacement` (DefaultW3D.fx) is not
  reproduced.
- Sky domes: retail maps place a `WaterReflectionSkydome_*` object (KindOf SKYBOX) near the
  centre, a dome model with a `simple.fx` material: texture x ColorEmissive, unlit, no
  shadows, fogged only with FogEnable (off in the domes). Top views leave sky domes out.
  `mapkit.weather.add_sky` places one for a preset, scaled to enclose the map.
  Views with a sky draw it first and fade the non-playable border out over its width
  onto it (the game blacks the border out; top views still do); below the dome, past
  the map's edge, the background takes the dome's horizon colour.
- Spanned bridges: two map objects flagged `0x10` and `0x20` name a `Bridge`
  type (roads.ini or the map's map.ini); as in `W3DBridge::load` and
  `getIndicesNVertices`, its model's `BRIDGE_LEFT` piece starts at the first
  point, `BRIDGE_SPAN` repeats as often as fits and `BRIDGE_RIGHT` ends at the
  second, scaled along the axis to fit and by `BridgeScale` across and up, 0.25
  above the terrain at each end, with the type's `Texture`
  ([render/bridges.py](../src/mapworkshop/render/bridges.py)). They are lit as
  objects, not with the game's terrain lighting (`doTheLight`), and drawn
  undamaged.
- Object scale: the map's `objectPrototypeScale` multiplies an object's scale
  (Object::updateObjValuesFromMapProperties), trees and shrubs included; retail maps use
  it for bushes (Grey Havens: 2.2 to 2.4) and sky domes.
- FX materials: the technique is picked like water's (`InitializeShader`).
  `normalmapped.fx` runs `Default_M` at Medium (DirectionalLight[0] and [2]
  per vertex, DirectionalLight[1] bump-mapped, specular from light 0) and
  `Default_L` at Low (vertex lighting, doubled); High's two-pass `Default`
  is drawn with the `Default_M` port and flagged in the report
  (`fx_materials`). Other effects are drawn as lit textured materials.
- Trees and shrubs: `KindOf TREE` / `KindOf SHRUB` templates with a
  `W3DTreeDraw` are handed to the tree and shrub buffers at map load with
  the map position, the map angle and the template's `Scale`: a new game
  creates each one's drawable at the map angle and its `W3DTreeDraw` adds it
  (BFME1/Zero Hour `reactToTransformChange`; only a loaded savegame re-adds
  them with an identity matrix and scale 1, GameLogic 0x00246422). Positions
  are rotated, normals stay in model space (0x000E7DF3). Zero Hour and BFME1
  zero the scale randomness (WorldBuilder rolls it into the map), so
  `InstanceScaleFuzziness` is not applied at load; a map's per-object
  `objectPrototypeScale` is, and native captures show tree-buffer trees at
  those sizes (Greywater's build gives each tree 0.75..1.3 and each shrub
  0.8..1.2, as hand-tuned retail maps do). The buffers copy the
  model's first mesh (bone translation only, model-space normals, DCG with
  alpha 255, UVs clamped to [0, 1]) and the `TextureName` texture, and keep
  the first 1,200 trees and 2,000 shrubs in map order (64 types each);
  shrubs need `ShowProps` (Medium and up). They are drawn with
  `vegetation.fx` (`Vegetation.fx`, technique `Default` at the global
  ShaderLOD): `Default_L` at Low and Medium, `Default` at High. Lighting is
  |N.L| for each light, (lights + ambient) x vertex colour x 0.5 saturated,
  then x 2 with the texture; `Default` also multiplies the cloud texture.
  Alpha test >= 96; trees alpha-blend (`Vegetation.IsAlphaBlendEnabled`),
  shrubs do not; back faces are culled. Sway: `SwayOffsets` from the default
  breeze (ScriptEngine::reset) scaled by height above the tree's base, one
  of ten random sway types per tree (none for `TaintedTree`), animated by
  `--time`.

Animation (the viewer's clock, or `render --time SECONDS` for stills; time 0 by default):

- Water: WaterShader's preshader scrolls both ripple frames by Time x (WindSpeed + WaveSpeed) along WindAngle -/+
  WaveAngle/2, Time being WW3D's sync time in seconds.
- Cloud shadows: the cloud texture moves by weather.ini's CloudOffsetPerSecond (texture units per second).
- Rain and snow: particles fall by time x SnowSpeed and wrap in the box (W3DSnowManager::update 0x000949D9), wobble
  with the height, and drift by time x SnowXYSpeed less one fall's worth per wrap. Lightning flashes are not drawn.
- Object effects: torch flames, smoke, embers and glows (`render.effects`). See
  [Particle effects](#particle-effects).

Open questions, approximated for now:

- Water techniques other than BumpSpecular, BumpSpecular_M and PCA_L (the
  other PCA techniques, the default technique) are not ported.
- Terrain: the composited tile textures are 16-bit (format 25) or DXT1 in
  game; the renderer samples the source textures at the same texel density
  without that quantization. What the composited normal texture holds for
  textures without `_nrm` maps is not recovered from the code; a flat normal
  without gloss matches the Specular Lab screenshots. On its normal-mapped
  half the renderer is a little brighter than the game (mean 30 against 27 of
  255) with stronger sparkles. Fog and the Medium cloud/macro pass follow
  native captures, not the passes' render states (FogEnable false,
  ColorWriteEnable 0 on P1), which the engine evidently overrides; the order
  (cloud and macro, then fog) follows the single-pass shaders. Low's fog is
  assumed to match. The tessellated tile mesh (`isInMesh`), scene point
  lights in `doTheLight`, weather darkening/lightning, shroud and taint are
  not drawn.
- Sway phases: the game rolls each sway type's speed and amplitude with
  `GetGameClientRandomValueReal`; fixed factors stand in, and the cycle
  assumes one sway step per logic frame (30 per second). Per-tree sway types
  are a hash of the object index.
- Shroud, point lights, tree fading near units and push-aside are not drawn.
- ShaderMaterialReplacement at High and normalmapped.fx `Default` (High) are
  not ported (see Objects above).
- Water reflections (`BumpSpecular`, WaterLOD High and up): the game binds
  `WaterDraw.ReflectionTexture` only when GlobalData+0x5E (ApplyPreset sets
  it to WaterLOD >= High), the water object (always created by
  W3DTerrainVisual::init) and WaterTransparency `ReflectionOn` (offset 0x50 in
  its field table; map.ini over water.ini, retail No) are all set (callback
  0x00080168; the reflection camera, 0x0007FD89, is added under the same two
  settings); otherwise it binds black. `wtr_Riv03` lerps 80% towards it, so
  maps with `ReflectionOn = No` (Greywater, Bramble Hollow) have near-black
  water at High, in game as here. With reflections on, the renderer draws the
  scene mirrored about `ReflectionPlaneZ` into a texture the size of the view,
  and the water reads it at the pixel's own screen position, as vs 78 sets
  `oT2 = ((clip.xy + clip.w) / 2, clip.w)` and the pixel shader divides by
  it. What that pass draws was read from game screenshots
  ([Reflection Lab](../maps/reflection_lab/map.py), High, 15 October 2026),
  not from the code: sky domes, the tree buffer and objects with KindOf
  `CAN_CAST_REFLECTIONS` (rocks, many ruins and houses), cut at the plane;
  not the terrain, the shrub buffer or other objects (the lab's towers and
  bushes). Approximations: the game's reflection texture size and clear
  colour (black here; sky domes cover it) are not traced, its pass's lighting,
  fog and shadows neither (objects are lit as in the view, unshadowed), and
  `ReflectionGuard` is ignored. The lab's game shots show two things not
  drawn here: a small pale shape on the water that moves between shots and a
  dark notch at the lake's north-west corner.
  `ShowSoftWaterEdge` (GlobalData+0x84) is only read by
  W3DShaderManager::startRenderToTexture (0x00075BD8), to keep destination
  alpha during screen-filter passes; standing water's shoreline fade is the
  per-vertex depth alpha. Greywater has no river areas (empty `RiverAreas`).
- Shadow-map fitting (High): the light camera is a copy of the view camera
  refitted by 0x0007C8AE (994 instructions, not matched), which reads the
  view's clip planes and frustum, the ShadowMap block at 0x00DB447C (MapSize,
  MaxViewDistance, MinShadowedTerrainHeight) and the constants 400, 10 and
  0.1. The renderer fits an orthographic map to the camera's ground
  footprint instead, and which objects draw into the game's shadow map is
  not traced.
- Shadow volumes: skinned meshes extrude in their bind pose; the NON_SELF
  variants are treated as SHADOW_VOLUME; the extra per-mesh z term in
  updateVolumes (0x000F3D23, banked near-miss) is taken as 0; V2's z-fail
  path with caps (camera inside a volume's bounds, 0x00107B41) is not used,
  which matters only for cameras below object tops; the count is per pixel,
  not per MSAA sample. Decal shadows of non-tree SHADOW_DECAL objects
  (W3DProjectedShadowManager) are not drawn, and tree decal quads keep a
  size estimate (the tree buffer's shadow quad builder is not matched).
- Rain density and lean: the rain ramp (RampControl, RampSpacing,
  RampSpeed) runs through W3DSnowManager's state transition (0x00094652,
  matched) into 0x00093B5B and 0x00093349, which are not, so spacing and
  speed stay at SnowSpacing/SnowSpeed; native rain looks denser and slightly
  slanted. The drop brightness gate (0x000932E1) and lightning
  (LightningEnabled/Factor/Duration/Chance; trigger 0x0009322D matched) are
  not drawn.

Previews draw every tree and shrub of the map. The game keeps only the first
1,200 trees and 2,000 shrubs in map order; `render --vegetation-limits` (or
`MapRenderer(vegetation_limits=True)`) applies those limits, and the render
report lists how many were dropped under `vegetation`.

Cliff-mapped cells (`mapkit.cliffs`) take their record's corner UVs in their own texture, wrapping,
and its triangle flip. Not reproduced: roads and shroud. River areas follow the game's river drawing
([rivers](reference/mapping/terrain-and-presentation/rivers-and-waves.md#rivers)). Textures smaller than their declared terrain
class are drawn but reported, because the game cannot load them.

## Particle effects

Objects get particle effects in two ways, and the renderer draws both:

- **W3D emitters.** The model's HLOD aggregate array (chunk `0x705`) names
  emitter files on bones. `GenericTorch`'s `GBTORCH`, for example, has
  `E_Fire_SM`, `E_Smoke_SM` and `E_FireSparks_SM`, which hold its flame.
- **INI particle systems.** `ParticleSysBone = <bone> <system>` lines in the
  draw module's `DefaultModelConditionState` and `IdleAnimationState` attach
  an `FXParticleSystem` from `fxparticlesystem.ini`. `FireCampfire`'s
  embers and `FireBonfire`'s glow and smoke work this way.

Only drawables in the scene run effects. `W3DPropDraw` templates go to the
prop buffer, which renders their models without adding them to a scene, so
their emitters never update: `W3DPropDraw::reactToTransformChange` feeds
`W3DPropBuffer`, and `ParticleEmitterClass::Render` is empty. Trees and shrubs
have none.

Effects are shown as on a map that has run for a while:

- Systems that stop stay off: those with a `SystemLifetime`, `IsOneShot`, or
  emitters with `MaxEmissions`.
- Systems below the detail level's `MinParticlePriority` (`gamelod.ini`;
  `HIGH_OR_ABOVE` is off at Medium) are not drawn.

Each particle's state is a closed-form function of its age, so any instant
renders without simulating up to it. Randomness is a hash of the object, the
emission and the particle, so stills are reproducible and the viewer animates.

- **Emitters** (WW3D2 `part_emt.cpp`, `part_buf.cpp`, `pointgr.cpp`):
  - Emission every `int(1000 / rate)` ms, in bursts.
  - Position: a random point in the creation volume and a velocity (random,
    plus outward, plus base), both rotated by the bone, under world
    acceleration.
  - Colour, opacity, size, rotation and texture frame follow the keyframes,
    plus per-particle randoms.
  - The point group forces the MODULATE gradient.
  - Triangle particles span a frame 3.464 x size wide; quads are 1 x size.
  - The object's scale scales sizes, offsets and speeds.
- **INI systems** (Zero Hour `ParticleSys.cpp`):
  - A burst every BurstDelay + 1 frames.
  - Each frame, as `Particle::update`: velocity plus gravity, times damping;
    position plus velocity plus drift; damped size and angle rates.
  - Colour keys, with BFME2's colour scale drawn per non-zero channel of keys
    1 to 6 (the colour module constructor, 0x0055BCF1).
  - Alpha keys for non-additive shaders.
  - Point, line, sphere, box and cylinder volumes, with ortho, outward,
    spherical, hemispherical and cylindrical velocities.
  - Placed at the bone's position times the object's scale, turned by the
    bone's Z rotation only (W3DModelDraw).
  - Drawn as `DefaultDraw` camera-facing quads (ground-aligned ones flat),
    with the sprite shader of their `Shader`.

Particles are drawn after water, without depth writes: alpha-blended groups
first, sorted back to front, then additive ones. Fog fades additive particles
to black. Particle textures are uploaded as they are: additive textures keep
colour under zero alpha, which the alpha bleed applied to object textures
would overwrite.

The render report lists `effects`: emitters and systems attached, and those
skipped with the reason.

### Flame and glow meshes

Many lamps also carry flames and glows as meshes. `GPTOWNLAMP5` (the hanging
lantern `TownLamp5`) has only these, and they work in the prop buffer too.

- **Camera-facing meshes.** W3D geometry type `CAMERA_ORIENTED` (`0x60000`)
  or `CAMERA_ALIGNED` (`0x10000`). The DX8 mesh renderer draws them with
  `Obj_Look_At` at the bone's position instead of the mesh transform: local
  +x points at the camera (oriented) or along the camera's z axis (aligned),
  and y stays level (dx8renderer.cpp). The geometry type is a field, not
  bits: `0x60000` shares the skin bit, which the loader used to take for a
  skin.
- **Grid mapper.** Stage-0 mapping `0x00070000`
  (`GridTextureMapperClass`). The UVs cover the first frame of a
  2<sup>Log2Width</sup> grid, which is stepped at `FPS` frames per second,
  row by row, up to `Last` frames. The flame sequence `EXFireTorchSeq` is a
  4 x 4 grid at 15 frames per second.
- **Detail stage.** `DetailColorFunc` combines texture stage 1, with its own
  UVs, into stage 0. DETAIL, SCALE, ADD, ADDSIGNED, ADDSIGNED2X and SCALE2X
  are drawn. `FIREGLOW` multiplies its glow spot by itself (SCALE), which
  darkens the spot's grey surround to almost black.
- **Textures used as stored.** Materials that neither alpha blend nor alpha
  test skip `bleed_alpha`. Additive glows draw the colour under zero alpha,
  which the bleed would replace with neighbouring atlas art; `FIREGLOW`
  then showed as a patterned red square.

Approximations:

- Burst delays use the mean of `BurstDelay`.
- `Wind`, `StartSizeRate`, slave and per-particle attached systems, `Event`
  modules and the cylinder's `RadiusRate` are left out.
- Other draw modules are skipped: `StreakDraw`, `GpuDraw`, `RenderObjectDraw`,
  `LightningDraw` and `ButterflyDraw`.
- Whether BFME2 also adds the colour scale every frame, as Generals does, is
  not recovered.
- Effects of other model-condition states (damaged, night, snow) are not
  drawn.

The sources behind this are listed in bfme2-map-workshop's
`docs/research/particle-effects.md`.

## Compiled effects

`python -m mapworkshop.formats.fxo <file.fxo> [--disassemble] [--technique NAME]` lists a
compiled D3DX9 effect's techniques, passes, render states, texture bindings
and shader-array selectors (with the decoded preshader that computes the
element index), and prints the shader assembly through
d3dcompiler_47's `D3DDisassemble`. The effects live in the game archives under
`shaders/compiled/`.
