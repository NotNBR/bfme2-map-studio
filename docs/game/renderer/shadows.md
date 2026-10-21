# Shadows

How the game draws shadows at each detail level
([how the game draws a map](README.md)).

- Shadows, Medium: stencil shadow volumes. W3DShadowManager::addShadow (0x0009A8D3) sends
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
  instance. The game builds them on the CPU: each polygon's facing is
  decided once, so the quads of neighbouring silhouette edges always pair up
  (the studio's Python renderer, which built them the same way, found that a
  geometry shader re-testing a neighbour from its own vertex order can
  disagree with it on faces edge-on to the light, leaving stray quads that
  streak the shadow). Volume faces neither write depth nor hide each other.
  Classic volumes run from each mesh's box top down to the lowest
  terrain found by marching the object box's top corners along the light
  ray (updateOptimalExtrusionPadding 0x000F1212), less 0.1. V2 volumes move
  by a vector whose z is -(height above ground + box top + 20.1)
  (0x001074D5). The INCR/DECR stencil passes count volume faces in front of
  the receivers' depth (+1 facing the camera, -1 otherwise), and pixels
  counted at least once are multiplied by the GlobalLighting shadow colour,
  after fog (renderStencilShadows 0x000F0842). Receivers are
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
  draw is unmatched, so blob size and strength are known only from Zero
  Hour. The game runs its shadow pass after fog, but its camera never sees
  far enough into fog for that to show; the studio's Python renderer faded
  the blobs and the stencil shadows on the terrain with the fog, as from
  low viewer angles far shadows otherwise read as dark specks.
- Shadows, High: shadow mapping. Objects with a `Shadow` type cast into a
  sun-aligned depth map at the game's texel size (`ShadowMap` MapSize over
  MaxViewDistance in environment.ini); terrain and objects take four depth
  tests one texel apart and scale only the main light. UseShadowMapping
  switches volumes and decals off (GameLOD ApplyPreset).

## Open questions

- Shadow-map fitting (High): the light camera is a copy of the view camera
  refitted by 0x0007C8AE (994 instructions, not matched), which reads the
  view's clip planes and frustum, the ShadowMap block at 0x00DB447C (MapSize,
  MaxViewDistance, MinShadowedTerrainHeight) and the constants 400, 10 and
  0.1. The studio's Python renderer fitted an orthographic map to the
  camera's ground footprint instead. Which objects draw into the game's
  shadow map is not traced.
- Shadow volumes: how the game extrudes skinned meshes, what the NON_SELF
  variants do differently from SHADOW_VOLUME and the extra per-mesh z term
  in updateVolumes (0x000F3D23, banked near-miss) are not traced; the
  Python renderer extruded skinned meshes in their bind pose, treated
  NON_SELF as SHADOW_VOLUME and took the z term as 0. V2 has a z-fail path
  with caps for a camera inside a volume's bounds (0x00107B41), which
  matters only for cameras below object tops. Decal shadows of non-tree
  SHADOW_DECAL objects (W3DProjectedShadowManager) and the tree buffer's
  shadow quad builder are not matched.
