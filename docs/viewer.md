# The viewer

```powershell
mw view [MAP] [--lod medium] [--weather rain] [--sun ember] [--fps 60]
```

`mw` alone opens the map you worked on last, and so does double-clicking
`Map Workshop.cmd`. `MAP` is a project id or any unique start of it
(`grey`), a stock map ("fords of isen") or a `.map` file. The window uses the
[renderer](rendering.md), so maps look as they do in the game at the chosen
detail level.

## Moving around

The controls are those of a 3D editor, not the game's:

| Input | Action |
| --- | --- |
| Left drag | Orbit around the focus point |
| Right or middle drag | Grab and pan the ground |
| Wheel | Zoom towards the cursor |
| Double-click | Fly to the clicked point |
| W A S D / arrows | Move (Shift faster, Ctrl slower) |
| Q / E, R / F, Z / X | Rotate, tilt, zoom |
| Space / Home, T | Reset to the whole map, toggle top-down |
| 1 2 3 4 5 6 7 | Objects, water, shadows, normal maps, clouds, weather, walkable |
| G, B, P, F5, Ctrl+B, F1, Esc | Grid, border, screenshot, reload, build, controls, quit |

## Walkable areas

**View → Walkable** (key 7) computes a local walkability estimate without
starting the game: open ground green, shallow water blue, bridge decks cyan, blocked
cells red and striped (cliffs, deep water, buildings), and in orange the
walkable areas no player start can reach. `mw walkable <map>` prints the same
as text, with each cut-off area's position, and `mw render ... --walkable`
draws it into renders. The viewer recomputes it after reloading a changed map.
The calculation runs in the background; you can keep moving around while the
status bar says **Computing walkability**.

Terrain flags, water depth, inherited object geometry and the models' walking
meshes supply the estimate. Bridge edges and connections are approximate;
spawned fortresses, units, scripts and dynamic gate/wall states are not
simulated. Reachability combines decks and ground in a top-down grid, so
overpasses can join routes that are separate in the game. This is an editing
aid, not proof that a particular unit can follow a route.

`mw walkable <map> --compare` compares against an existing native capture
without launching anything. For explicit verification, `--native` reads and
reports the game's grid from a short skirmish (about a minute, through
[bfme-workshop](https://github.com/NotNBR/bfme-workshop)'s native runtime).
Native captures are tied to the map file's hash; a changed build needs a new
capture. The default CLI and viewer always use the local calculation.

## The toolbar

- **Map**: your map projects first, then the game's own maps. **Open project
  folder** opens the current project's source folder; **Browse...** opens any
  `.map` file.
- **Build** rebuilds the current project in the background. The status bar shows
  the build's progress, and the scene reloads when the build is done. A failed
  build shows its error there and leaves the previous build in place.
- **Play** copies the current project into the game's user maps folder and
  starts BFME2; pick the map under Skirmish.
- **Detail**: Low, Medium or High, as `--lod`.
- **Weather**: **Map's own** uses the map's `map.ini` weather. **Clear**, **Haze**,
  **Rain**, **Snow** and **Dusk** apply the
  [weather presets](../src/mapworkshop/mapkit/weather.py) (fog, falling rain or
  snow, lighting and the preset's sky dome) without changing the map.
- **Sun**: **Weather's own**, or a light rig over the weather. The Mordor suns
  (Ember, Copper, Blood red, Sulphur glow, High sun through ash, Dusk violet) bring
  the Minas Morgul sky and a matching fog tint.
- **View**: check marks that stay open while you switch them: objects, water,
  shadows; cloud shadows, normal maps, fog and rain/snow; grid, map border;
  animate and **game object limits**. The limits keep only the first 1,200 trees
  and 2,000 shrubs, as the game's buffers do. Off (the default) draws every one.
- **Mark** shows the marking row (see below).
- **Top view**, **Reset view** and **Screenshot** (saved to `local/renders/`).
- **Frame rate**, at the right edge: the measured rate and the cap, for example
  `60 fps / 60`. Click it to cap at 30, 60 (the default), 90, 120 or 144 fps,
  follow the monitor (**VSync**) or run **Unlimited**.

## Live reload

The viewer watches the map file and its `map.ini`. When either changes (a
build from the toolbar, `mw build`, `mw dev`, an editor save), it reloads the
scene in place and the camera stays where it is. Map preparation runs in the
background and GPU uploads are spread across frames. The current scene and
controls remain usable while loading, including when switching maps or changing
detail, weather or sun. Selecting another map replaces the pending request.
Models and textures are cached between reloads. If the new file can't be read,
the last good scene stays and the status bar shows the error. Individual GPU
uploads and first-use shader compilation can still cause short pauses.

`mw dev [MAP]` is the quickest way to work on a map: it builds the project,
opens the viewer and rebuilds whenever you save a file in the project folder.

## Marking the map for an agent

**Mark** opens a second toolbar row for pointing at places on the map:

- **Pin**: click a point.
- **Circle**: drag from the centre outwards.
- **Rectangle**: drag from corner to corner, aligned to the map axes.
- **Freehand**: hold the button and draw. A path whose ends meet is an area.
- **Select**: click a mark, drag it to move it, Del to delete it.
- **Delete**, **Clear all** and **Copy for agent**.

Marks are red, numbered and draped on the terrain. They are kept per map in
`local/marks/<map>.json`, rewritten on every change. A panel at the right lists
each mark with the objects inside it. Esc steps back: it cancels a drawing,
drops the selection, closes the row and only then quits.

**Copy for agent** puts the marks on the clipboard. Paste them into an agent's
prompt with your request ("add a forest in mark 2", "remove the bridge at
pin 1"). The text has every mark in map coordinates (x east, y north, the
coordinates of map objects and build scripts; z is the terrain height), its
centre, size and area, and the objects inside it: structures and props one by
one with their positions and layer (the name the build placed them with),
vegetation counted by template, and a count per layer. It ends with the
map's source project and how to rebuild it. `mw marks [MAP] [--json]` prints the
same text, so an agent can also read the marks itself; see
[AGENTS.md](../AGENTS.md).

## Notes

The camera is a preview camera, not the game's. Animation (water ripples,
cloud shadows, rain and snow) runs on the game's clocks; **Animate** pauses
it. A weather or sun change applies in place in well under a second; changing
the map or the detail level reloads the scene, with a progress card.
