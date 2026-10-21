# Rendering maps

`mw render` draws pictures of a map without starting the game. Use it for fast
iteration, and check what matters in the game itself
([testing in the game](testing-in-game.md)). `--engine` picks what draws them:

- **godot** (the default): the [Godot viewer](../viewer.md#the-godot-viewer)
  on OpenBFME's library, a port of the game's own engine, started unseen on a
  hidden desktop of its own (no window appears, the focus stays where it is).
  It opens the map once and takes every view in turn: a few seconds to open,
  then about a second a view. It needs OpenBFME and its game files, English
  RotWK 2.01 and BFME2 1.06 ([OpenBFME](testing-in-game.md#openbfme-mw-play---godot));
  the first run builds OpenBFME, which takes minutes. OpenBFME has no detail levels, shadows, normal
  maps, cloud shadows or falling rain and snow, and no switches for units,
  editor markers or the object limits, so `--lod`, `--normal-maps`,
  `--no-clouds`, `--vegetation-limits`, `--editor-markers`, `--no-units` and
  `--time` need `--engine studio`. Where its pictures differ from the studio
  renderer's is listed in [the Godot viewer's checklist](../godot-viewer/parity.md#how-openbfme-draws-the-map-differently).
- **studio**: the studio's Python renderer, offscreen on the GPU, which
  reads terrain textures, models and INIs from the installed archives and
  the extracted game data. [What it reproduces](#what-it-reproduces) was
  measured against the game.
- **game**: the game itself, through [`mw capture`](testing-in-game.md#screenshots-from-the-game-mw-capture):
  each orbit view of a project's build as a cinematic shot from above its
  target, at the game's own resolution and field of view, HUD included; no top
  views, and none of the options that change the picture (the game draws the
  map as it is).

```powershell
mw render --map greywater-marches --out local/renders/greywater `
  --view base5  target=5500,1090 distance=1800 elevation=40 `
  --view bridge target=11900,3850 distance=900 elevation=30 heading=300 `
  --view sw     region=0,0,4500,3000 `
  --top
```

`--map` takes a map project, a stock map name or a `.map` file (the Godot
engine opens stock maps under the RotWK profile only). Each run writes one PNG
per view plus `render.json` (map hash, the engine, camera settings; with the
studio engine also missing assets and texture-size errors).

To render single objects or a collage of them, see `mw item` and `mw items` in
[finding assets](finding-assets.md#looking-mw-item-and-mw-items).

## Cameras

`--view NAME KEY=VALUE...` specs are plain preview cameras. World units: X
east, Y north, origin at the playable south-west corner, 10 units per terrain
cell.

| Key | Default | Meaning |
| --- | --- | --- |
| `target=X,Y[,Z]` | required | Point to look at; Z defaults to the terrain height |
| `distance=` | 1500 | Camera distance from the target |
| `elevation=` | 45 | Degrees above the horizon; 90 looks straight down |
| `heading=` | 0 | Direction the camera faces: 0 N, 90 E, 180 S, 270 W |
| `fov=` | 50 | Horizontal field of view in degrees |
| `eye=X,Y,Z` | — | Explicit camera position instead of distance/elevation/heading |
| `region=X0,Y0,X1,Y1` | — | Orthographic top view of a rectangle, north up |
| `near=` | | Near clip |
| `roll=` | 0 | Degrees the camera turns about its view direction, positive to the right (clockwise from behind; the picture turns left) |
| `focal=` | — | Focal length in mm on a full-frame 36 x 24 mm sensor, in place of `fov`: the image is the sensor's largest crop of its aspect, 36 mm wide at 3:2 and wider (39 mm is then 50 degrees), 24 mm tall when narrower |
| `aperture=` | — | f-number: depth of field around `focus` (none: everything sharp) |
| `focus=` | the target's distance | Distance in focus along the view, map units |
| `ev=` | 0 | Exposure in stops: brighter above 0, darker below |

The last four are photo effects the game does not have
([render/photo.py](../../src/mapworkshop/render/photo.py)); the viewer's Photo
mode writes them, and **Copy view** gives a `mw render` command with them
([saved views](../viewer.md#photo-mode-and-the-camera-bar)). Depth of field
counts 10 map units to the metre, so a real lens's blur: focused across the
map (1,000 units and more), little blurs; focused within a few hundred units,
the distance does.

`--top` adds a top view of the whole map at `--top-scale` pixels per cell
(default 2). `--size` sets the size of orbit views (default 1600x1200).
Reusable view sets go in a JSON file passed with `--views`:

```json
{"views": {
  "river-shore": {"target": [6700, 6050], "distance": 1700, "elevation": 40},
  "southwest":   {"region": [0, 0, 4500, 3000]}
}}
```

## Options

| Option | Does |
|---|---|
| `--engine godot\|studio\|game` | what draws the pictures (above); godot by default |
| `--lod low\|medium\|high` | the game detail level to imitate (default medium, as test games run): Medium has no terrain normal maps and uses stencil volume shadows; High adds normal maps and shadow mapping |
| `--weather PRESET`, `--sun NAME` | the viewer's weather presets (clear, haze, rain, snow, dusk) and light rigs (ember, copper, blood, sulphur, ash, violet) over the map's own |
| `--no-weather` | ignore the map.ini Weather block (fog, falling rain or snow) |
| `--time SECONDS` | animation time: water ripples, clouds, falling rain and snow, particle effects (0) |
| `--vegetation-limits` | keep only the game's first 1,200 trees and 2,000 shrubs, as the game does (default: draw every one) |
| `--editor-markers` | also draw the WorldBuilder-only models the game never shows, such as the AI's farm sites (default: leave them out, as the game does) |
| `--no-units` | leave out the units (default: each horde as its members in their ranks, every unit in its idle pose; [units](../game/renderer/objects.md#units)) |
| `--no-objects`, `--no-shadows`, `--no-clouds` | leave those out (the cloud texture is on in game, frozen at time 0 here) |
| `--normal-maps auto\|on\|off` | terrain normal maps; auto follows `--lod` |
| `--border` | draw the 30-cell border outside the playable area, which the game draws black (generators often fill it by repeating the edge, which looks streaked) |
| `--grid` | a 100-unit world grid |
| `--walkable` | the local walkability estimate, areas cut off from every start marked |
| `--flow` | river flow arrows: yellow chevrons pointing downstream along each river strip, its banks in blue, its first cross-section green and its last red, so joins and overlaps between strips show |

## What it reproduces

This section is about the studio engine. The renderer ports the game's own
drawing: its effect files, its terrain compositing, its shadow volumes, its
tree buffers and particle systems.
[How the game draws a map](../game/renderer/README.md) records each part,
what is ported and what is approximated; read it before changing the
renderer or when a render and a game screenshot disagree. In short, not drawn:
shroud, roads, point lights, shore waves and lightning; approximated: water
techniques other than the common ones, High's shadow-map fitting and object
material replacement.
