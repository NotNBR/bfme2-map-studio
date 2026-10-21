# Terrain

How the game draws terrain ([how the game draws a map](README.md)).

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
  the primary blend. Mixing the same layers per pixel with the per-corner
  ramps of `getAlphaUVData` (diagonal flips included) gives the same weights,
  as the studio's Python renderer did. Tiles beyond `updateCenter`'s distance
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
  flat ground shows no sun glare, where B = 255 in the studio's Python
  renderer mirrored the sun over whole fields seen from afar ([Specular Lab](../../../maps/specular_lab/map.py), High
  screenshots facing the sun, 15 October 2026). Macro UV: stretched
  `(x + border, -(y + border)) / (samples x 10)`, else `(x, -y) / 660`.
  Cloud UV: world / CloudTextureSize plus Time x CloudOffsetPerSecond.
- Cliff-mapped cells (`mapkit.cliffs`) take their record's corner UVs in
  their own texture, wrapping, and its triangle flip
  ([cliff mapping](../terrain-textures.md#cliff-mapping)).

## Open questions

- Terrain: the composited tile textures are 16-bit (format 25) or DXT1 in
  game; the studio's Python renderer sampled the source textures at the same
  texel density without that quantization. What the composited normal texture
  holds for textures without `_nrm` maps is not recovered from the code; a
  flat normal without gloss matches the Specular Lab screenshots. On the
  lab's normal-mapped half the Python renderer came out a little brighter
  than the game (mean 30 against 27 of 255), with stronger sparkles. Fog and
  the Medium cloud/macro pass are taken from native captures, not the passes'
  render states (FogEnable false, ColorWriteEnable 0 on P1), which the engine
  evidently overrides; the order (cloud and macro, then fog) follows the
  single-pass shaders. Low's fog is assumed to match. The tessellated tile
  mesh (`isInMesh`), scene point lights in `doTheLight`, weather
  darkening/lightning, shroud and taint are not traced.
