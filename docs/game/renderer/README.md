# How the game draws a map

These pages record how BFME2 1.06 draws each part of a map, read from
`game.dat`, the retail effect files and the openbfme2/EA source and checked
against game screenshots. They were measured for the studio's former Python
renderer, removed in October 2026 (its code is in git history up to commit
9f32a1f); where a fact rests on that renderer's comparison with the game, the
page says so. Pictures are now drawn by the viewer and `mw render` on
OpenBFME's library, or by the game itself (`mw render --engine game`;
[rendering](../../guide/rendering.md), [the viewer](../../viewer.md)). Read the
relevant page when a picture from the viewer or `mw render` disagrees with the
game, or before changing how OpenBFME draws something.

The game draws at a detail level from `GameLOD.ini` (Low, Medium, High). Medium
has no terrain normal maps and uses stencil volume shadows; High adds normal
maps and uses shadow mapping. `UseTerrainNormalMap` switches the terrain
between the High and Medium techniques. The viewer has no detail levels:
OpenBFME draws one way.

| Page | Covers |
|---|---|
| [Terrain](terrain.md) | terrain techniques per detail level, tile compositing, terrain lighting, cliff-mapped cells |
| [Water](water.md) | standing-water meshes, water techniques and shading, underwater tint, reflections at High |
| [Shadows](shadows.md) | stencil shadow volumes (Medium), tree shadow decals, shadow mapping (High) |
| [Objects and vegetation](objects.md) | object lighting, classic and FX materials, the tree and shrub buffers, sway |
| [Weather](weather.md) | fog, falling rain and snow |
| [Particle effects](effects.md) | W3D emitters, INI particle systems, flame and glow meshes |

Rivers are drawn as in [rivers and waves](../rivers-and-waves.md#rivers).

## The game camera

The game's camera, from the matched W3DView code. `lookAt` (0x0008D55D) keeps
the focus with z = 0 and sets the ground level G to the map's smoothed camera
height at the focus (`SmoothCameraHeightField`
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
(`camera.renderHeight`). The studio's Python renderer rebuilt this camera to
render the views of game screenshots (bfme-workshop compared them side by
side with its `render-compare`), taking the recorded eye height when present
and otherwise replaying the convergence from the previous shot; on the
Greywater captures it reproduced every recorded eye height to float precision
(the first shot of a run to 0.1 units) and the native framing to within one
pixel.

## Sky domes, spanned bridges and object scale

- Sky domes: retail maps place a `WaterReflectionSkydome_*` object (KindOf SKYBOX) near the
  centre, a dome model with a `simple.fx` material: texture x ColorEmissive, unlit, no
  shadows, fogged only with FogEnable (off in the domes).
  `mapkit.weather.add_sky` places one for a preset, scaled to enclose the map.
  The game blacks the non-playable border out.
- Spanned bridges: two map objects flagged `0x10` and `0x20` name a `Bridge`
  type (roads.ini or the map's map.ini); as in `W3DBridge::load` and
  `getIndicesNVertices`, its model's `BRIDGE_LEFT` piece starts at the first
  point, `BRIDGE_SPAN` repeats as often as fits and `BRIDGE_RIGHT` ends at the
  second, scaled along the axis to fit and by `BridgeScale` across and up, 0.25
  above the terrain at each end, with the type's `Texture`
  ([mapkit/bridges.py](../../../src/mapworkshop/mapkit/bridges.py)). The game
  lights them with its terrain lighting (`doTheLight`), not as objects.
- Object scale: the map's `objectPrototypeScale` multiplies an object's scale
  (Object::updateObjValuesFromMapProperties), trees and shrubs included; retail maps use
  it for bushes (Grey Havens: 2.2 to 2.4) and sky domes.

## Animation

What moves with time in game:

- Water: WaterShader's preshader scrolls both ripple frames by Time x (WindSpeed + WaveSpeed) along WindAngle -/+
  WaveAngle/2, Time being WW3D's sync time in seconds.
- Cloud shadows: the cloud texture moves by weather.ini's CloudOffsetPerSecond (texture units per second).
- Rain and snow: particles fall by time x SnowSpeed and wrap in the box (W3DSnowManager::update 0x000949D9), wobble
  with the height, and drift by time x SnowXYSpeed less one fall's worth per wrap.
- Object effects: torch flames, smoke, embers and glows. See
  [particle effects](effects.md).

## Not covered

These pages do not trace the shroud, roads, point lights, or tree fading and
push-aside near units. Textures smaller than their declared terrain class
cannot be loaded by the game.

## Compiled effects

The effects live in the game archives under `shaders/compiled/`, as compiled
D3DX9 effects. The facts on these pages about techniques, passes, render
states, texture bindings and shader-array selectors (with the preshaders that
compute the element index) were read with the studio's former
`formats.fxo` reader, removed with the Python renderer, which printed the
shader assembly through d3dcompiler_47's `D3DDisassemble`.
