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
| 1 2 3 4 5 6 7 8 | Objects, water, shadows, normal maps, clouds, weather, walkable, river flow arrows |
| G, B, P, F5, Ctrl+B, F1 | Grid, border, screenshot, reload, build, controls |
| Del, Ctrl+Z | Delete the selected mark, undo a mark change |
| Esc | Step back one level (see [marking](#marking-the-map-for-an-agent)); quit when nothing is left |

## River flow

**View → River flow arrows** (key 8) draws yellow chevrons along each river
strip, pointing and drifting downstream, with the strip's banks in blue, its
first cross-section green and its last red. `mw render ... --flow` draws the
same into still renders, and `mw rivers <map>` prints each strip's course as
compass runs.

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
reports the game's grid from a short skirmish (about 7 seconds, on the game
runtime described under [testing in-game](making-maps.md#testing-in-game)).
Native captures are tied to the map file's hash; a changed build needs a new
capture. The default CLI and viewer always use the local calculation.

## The toolbar

- **Map**: your map projects first, then the game's own maps. **Open project
  folder** opens the current project's source folder; **Browse...** opens any
  `.map` file. The menu opens at the current map; a menu taller than the window
  scrolls with the wheel or its arrow strips.
- **Properties** opens a window with the map's map-wide settings, in tabs:
  the project's title, description and weather preset; the camera limits;
  WorldInfo flags; the environment (water alpha, macro and cloud textures);
  water reflections; fog, clouds, snow and lightning. Each field shows the
  map's value, or in grey the game's default where `map.ini` leaves it out.
  For a project, **Save and build** writes the changed fields into `map.toml`
  as [properties](making-maps.md#map-properties) and rebuilds; a field set
  there is marked `map.toml` and has a **Reset** button that hands it back to
  `map.py`. One of the game's maps, or a loose `.map` file, is shown read-only.
- **Build** rebuilds the current project in the background, also while the
  first load is still running or after it failed. The status bar shows the
  build's progress, and the scene reloads when the build is done. A failed
  build shows the start of its error there (the full output goes to the
  terminal) and leaves the previous build in place.
- **Test In-Game** starts BFME2 straight in a skirmish on the current project,
  you against an easy AI, as `mw play` does
  ([making maps](making-maps.md#testing-in-game)). The status bar says when
  the skirmish is playable and when the game has closed. Its camera zooms out
  to the whole map and tilts with the middle button
  ([camera](making-maps.md#camera)). When the game is
  not BFME2 1.06, or for one of the game's own maps, it starts the normal
  game at its menu.
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
A load that takes longer than a quarter of a second shows a toast at the top
left, below the toolbar: the map or the changed settings, the current step and
a progress bar. When the load ends, the toast briefly shows how long it took,
or the error.
Models and textures are cached between reloads. If the new file can't be read,
the last good scene stays and the toast and status bar show the error. Individual GPU
uploads and first-use shader compilation can still cause short pauses.

`mw dev [MAP]` is the quickest way to work on a map: it builds the project,
opens the viewer and rebuilds whenever you save a file in the project folder.

## Marking the map for an agent

**Mark** opens a second toolbar row for pointing at places on the map. The
mouse keeps navigating until you pick a tool; the tool then stays armed (a
crosshair cursor) so you can draw several marks, until Esc or a second click
on it puts it away. Right drag and the wheel still pan and zoom while a tool
is armed.

- **Pin**: click a point.
- **Circle**: drag from the centre outwards.
- **Rectangle**: drag from corner to corner. Its sides line up with the screen,
  so turn the view to line it up with a diagonal road first; within 10 degrees
  of north it lines up with the map axes.
- **Freehand**: hold the button and draw. A path whose ends meet is an area.
- **Delete**, **Clear all** and **Copy for agent**.

With no tool armed, the mark under the cursor lights up; click it to select
it. A new mark is selected as soon as it is drawn. Drag a selected mark (or
any mark's number, pin or outline) to move it, and drag the square handles of
a selected circle or rectangle to resize it. A selected rectangle also has a
round handle on a stem: drag it to rotate the rectangle around its centre
(hold Shift to snap to 15 degrees). Del or Backspace deletes the selected
mark, and Ctrl+Z undoes adding, moving, resizing, rotating, deleting and
Clear all. A rotated rectangle is reported with its size, angle and four
corners.

Marks are red, numbered and draped on the terrain. They are kept per map in
`local/marks/<map>.json`, rewritten on every change. A panel at the right lists
each mark with the objects inside it. Esc steps back one level: it closes an
open menu, cancels a drawing, drops the selection, puts the tool away, closes
the row and only then quits.

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
it. Changing the map, the detail level, the weather, the sun or the game object
limits reloads the scene, with the loading toast described under
[Live reload](#live-reload).
