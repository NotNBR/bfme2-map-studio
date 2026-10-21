# How the game draws a map

The workshop's renderer ([render/](../../../src/mapworkshop/render/)) draws
maps for `mw render --engine studio`, `mw item` and map graphics
([rendering](../../guide/rendering.md)); the viewer and `mw render`'s default
engine draw on OpenBFME instead ([the viewer](../../viewer.md)). These
pages record how BFME2 1.06 draws each part of a map, read from `game.dat`, the
retail effect files and the openbfme2/EA source and checked against game
screenshots; what the renderer ports of it; and what it approximates. Read the
relevant page before changing the renderer, or when a render and a game
screenshot disagree.

The renderer imitates a game detail level from `GameLOD.ini`: `--lod medium` (default), `high` or `low`. Medium has no terrain normal maps and uses stencil
volume shadows; High adds normal maps and uses shadow mapping. `--normal-maps`
switches the terrain between the High and Medium techniques, as
`UseTerrainNormalMap` does in game.

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

`render.camera.GameCamera` reproduces the game's camera from the matched W3DView
code, to render the views of game screenshots from the same camera (bfme-workshop
compared them side by side with its `render-compare`).

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

## Sky domes, spanned bridges and object scale

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
  ([mapkit/bridges.py](../../../src/mapworkshop/mapkit/bridges.py)). They are lit as
  objects, not with the game's terrain lighting (`doTheLight`), and drawn
  undamaged.
- Object scale: the map's `objectPrototypeScale` multiplies an object's scale
  (Object::updateObjValuesFromMapProperties), trees and shrubs included; retail maps use
  it for bushes (Grey Havens: 2.2 to 2.4) and sky domes.

## Animation

By `render --time SECONDS` for stills (time 0 by default):

- Water: WaterShader's preshader scrolls both ripple frames by Time x (WindSpeed + WaveSpeed) along WindAngle -/+
  WaveAngle/2, Time being WW3D's sync time in seconds.
- Cloud shadows: the cloud texture moves by weather.ini's CloudOffsetPerSecond (texture units per second).
- Rain and snow: particles fall by time x SnowSpeed and wrap in the box (W3DSnowManager::update 0x000949D9), wobble
  with the height, and drift by time x SnowXYSpeed less one fall's worth per wrap. Lightning flashes are not drawn.
- Object effects: torch flames, smoke, embers and glows (`render.effects`). See
  [particle effects](effects.md).

## Not drawn

- Shroud, roads, point lights, tree fading near units and push-aside.
- Textures smaller than their declared terrain class are drawn but reported,
  because the game cannot load them.

## Compiled effects

`python -m mapworkshop.formats.fxo <file.fxo> [--disassemble] [--technique NAME]` lists a
compiled D3DX9 effect's techniques, passes, render states, texture bindings
and shader-array selectors (with the decoded preshader that computes the
element index), and prints the shader assembly through
d3dcompiler_47's `D3DDisassemble`. The effects live in the game archives under
`shaders/compiled/`.
