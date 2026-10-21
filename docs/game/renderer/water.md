# Water

How the game draws standing water ([how the game draws a map](README.md)). Rivers: [rivers and waves](../rivers-and-waves.md#rivers);
what water can do on a map: [water](../water.md).

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
- Water shading: the compiled `WaterShader.fx` shaders, read with the
  studio's former `formats.fxo` reader ([compiled effects](README.md#compiled-effects))
  and ported to GLSL in its Python renderer. `BumpSpecular_M` and
  `BumpSpecular` take two bump samples in
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
  fog off. The other techniques (`PCA_M`, `PCA`, `PCA_U`) read the engine's
  `PCAWater` bases.
- Underwater terrain: as in `getStaticDiffuse` (0x0006B4CC), the terrain
  vertex colour under a standing-water area is multiplied by the area's depth
  LUT (24-bit TGA, e.g. `LUTDepthTint.tga`) sampled at
  `(waterZ - groundZ) / max(waterZ, 1)`.

## Open questions

- Water techniques other than BumpSpecular, BumpSpecular_M and PCA_L (the
  other PCA techniques, the default technique) are not traced.
- Water reflections (`BumpSpecular`, WaterLOD High and up): the game binds
  `WaterDraw.ReflectionTexture` only when GlobalData+0x5E (ApplyPreset sets
  it to WaterLOD >= High), the water object (always created by
  W3DTerrainVisual::init) and WaterTransparency `ReflectionOn` (offset 0x50 in
  its field table; map.ini over water.ini, retail No) are all set (callback
  0x00080168; the reflection camera, 0x0007FD89, is added under the same two
  settings); otherwise it binds black. `wtr_Riv03` lerps 80% towards it, so
  maps with `ReflectionOn = No` (Greywater, Bramble Hollow) have near-black
  water at High in game. With reflections on, the water reads the reflection
  texture at the pixel's own screen position, as vs 78 sets
  `oT2 = ((clip.xy + clip.w) / 2, clip.w)` and the pixel shader divides by
  it; the studio's Python renderer drew the scene mirrored about
  `ReflectionPlaneZ` into a texture the size of the view for it. What the
  reflection pass draws was read from game
  screenshots ([Reflection Lab](../../../maps/reflection_lab/map.py), High,
  15 October 2026), not from the code: sky domes, the tree buffer and objects
  with KindOf `CAN_CAST_REFLECTIONS` (rocks, many ruins and houses), cut at
  the plane; not the terrain, the shrub buffer or other objects (the lab's
  towers and bushes). Not traced: the game's reflection texture size and
  clear colour (sky domes cover it), its pass's lighting, fog and shadows,
  and `ReflectionGuard`. The lab's game shots also show a small pale shape
  on the water that moves between shots and a dark notch at the lake's
  north-west corner, which the Python renderer did not reproduce.
  `ShowSoftWaterEdge` (GlobalData+0x84) is only read by
  W3DShaderManager::startRenderToTexture (0x00075BD8), to keep destination
  alpha during screen-filter passes; standing water's shoreline fade is the
  per-vertex depth alpha. Greywater has no river areas (empty `RiverAreas`).
