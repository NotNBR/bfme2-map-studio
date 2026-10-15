# The viewer

The viewer shows a map as the game draws it, reloads it whenever it is
rebuilt, and lets you mark places on it for an agent.

```powershell
mw view [MAP] [--lod low|medium|high] [--weather map|clear|haze|rain|snow|dusk]
        [--sun own|ember|copper|blood|sulphur|ash|violet] [--fps 60] [--size 1600x1000] [--samples 4]
```

`mw` alone opens the map you worked on last, and so does double-clicking
`Map Workshop.cmd`. `MAP` is a project id or any unique start of it
(`grey`), a stock map ("fords of isen") or a `.map` file. The window uses the
[renderer](guide/rendering.md), so maps look as they do in the game at the
chosen detail level. `--fps` caps the frame rate (30, 60, 90, 120, 144,
`vsync` or `unlimited`), `--size` sets the window and `--samples` the
anti-aliasing. The code is in [viewer/](../src/mapworkshop/viewer/); F1 prints
the controls.

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
| M | Show or hide the marks |
| G, B, P, F5, Ctrl+B, F1 | Grid, border, screenshot, reload, build, controls |
| Del, Ctrl+Z | Delete the selected mark, undo a mark change |
| Esc | Step back one level (see [marking](#marking-the-map-for-an-agent)); quit when nothing is left |

The camera is a preview camera, not the game's; [test games](guide/testing-in-game.md#camera)
have the game's own, freed to zoom out and tilt.

## Live reload

`mw dev [MAP]` is the quickest way to work on a map: it builds the project,
opens the viewer and rebuilds whenever you save a file in the project folder.

The viewer watches the map file and its `map.ini`. When either changes (a
build from the toolbar, `mw build`, `mw dev`, an editor save), it reloads the
scene in place and the camera stays where it is. Loading runs in the
background, and the scene and controls stay usable meanwhile, also when
switching maps or changing detail, weather or sun; selecting another map
replaces the pending request. A load longer than a quarter of a second shows a
toast at the top left with the current step and a progress bar, then briefly
how long it took, or the error. If the new file can't be read, the last good
scene stays. Models and textures are cached between reloads; first-use shader
compilation can still cause short pauses.

## The toolbar

- **Map**: your map projects first, then the game's own maps. **Open project
  folder** opens the current project's source folder; **Browse...** opens any
  `.map` file. The menu opens at the current map and scrolls when it is taller
  than the window.
- **Properties** opens a window with the map's map-wide settings, in tabs:
  the project's title, description and weather preset; the camera limits;
  WorldInfo flags; the environment (water alpha, macro and cloud textures);
  water reflections; fog, clouds, snow and lightning. Each field shows the
  map's value, or in grey the game's default where `map.ini` leaves it out.
  For a project, **Save and build** writes the changed fields into `map.toml`
  as [properties](guide/projects-and-builds.md#map-properties) and rebuilds; a
  field set there is marked `map.toml` and has a **Reset** button that hands it
  back to `map.py`. One of the game's maps, or a loose `.map` file, is shown
  read-only.
- **Build** rebuilds the current project in the background, also while the
  first load is still running or after it failed. The scene reloads when the
  build is done. A failed build shows the start of its error in the status bar
  (the full output goes to the terminal) and leaves the previous build in
  place. A chip at the right of the toolbar shows a running build, then when
  the last one ended and how long it took, or that it failed.
- **Test In-Game** starts BFME2 straight in a skirmish on the current project,
  you against an easy AI, as `mw play` does
  ([testing in the game](guide/testing-in-game.md)). The status bar says when
  the skirmish is playable and when the game has closed. When the game is not
  BFME2 1.06, or for one of the game's own maps, it starts the normal game at
  its menu.
- **Preview** shows the map another way without changing it. Its button shows
  the current choice, for example `Medium · Map's own`, and the menu stays open
  while you switch:
  - **Detail**: Low, Medium or High, as `--lod`.
  - **Weather**: **Map's own** uses the map's `map.ini` weather. **Clear**,
    **Haze**, **Rain**, **Snow** and **Dusk** apply the
    [weather presets](../src/mapworkshop/mapkit/weather.py) (fog, falling rain
    or snow, lighting and the preset's sky dome). The map's own weather is set
    in **Properties**.
  - **Sun**: **Weather's own**, or a light rig over the weather. The Mordor suns
    (Ember, Copper, Blood red, Sulphur glow, High sun through ash, Dusk violet)
    bring the Minas Morgul sky and a matching fog tint.
- **View**: check marks that stay open while you switch them: objects, water,
  shadows; cloud shadows, normal maps, fog and rain/snow; grid, map border,
  walkable, river flow arrows, marks; **Animate** (water ripples, cloud
  shadows, rain and snow, on the game's clocks); and **Game object limits**,
  which keeps only the first 1,200 trees and 2,000 shrubs, as the game's
  buffers do (off by default: every one is drawn).
- **Top view**, **Reset view** and **Screenshot** (saved to `local/renders/`).
- **Frame rate**, at the right edge: the measured rate and the cap, for example
  `60 fps / 60`. Click it to change the cap.

Changing the map, the detail level, the weather, the sun or the game object
limits reloads the scene.

## Marking the map for an agent

The palette at the top left of the view holds the tools for pointing at
places on the map; hover a button to see its name. The mouse navigates
(**Navigate**, the arrow) until you pick a tool; the tool then stays armed (a
crosshair cursor) so you can draw several marks, until Esc, a second click on
it or Navigate puts it away. Right drag and the wheel still pan and zoom while
a tool is armed.

- **Pin**: click a point.
- **Circle**: drag from the centre outwards.
- **Rectangle**: drag from corner to corner. Its sides line up with the screen,
  so turn the view to line it up with a diagonal road first; within 10 degrees
  of north it lines up with the map axes.
- **Freehand**: hold the button and draw. A path whose ends meet is an area.
- **Undo**, **Delete** (the selected mark), **Clear all** and, last, **Copy
  for agent** (the clipboard).

With no tool armed, the mark under the cursor lights up; click it to select
it. A new mark is selected as soon as it is drawn. Drag a selected mark (or
any mark's number, pin or outline) to move it, and drag the square handles of
a selected circle or rectangle to resize it. A selected rectangle also has a
round handle on a stem: drag it to rotate the rectangle around its centre
(hold Shift to snap to 15 degrees). Del or Backspace deletes the selected
mark, and Ctrl+Z undoes adding, moving, resizing, rotating, deleting and
Clear all.

Marks are red, numbered and draped on the terrain. They are kept per map in
`local/marks/<map>.json`, rewritten on every change. A panel at the right lists
each mark with the objects inside it. **View → Marks** (key M) hides the marks
and the panel; picking a tool shows them again. Esc steps back one level: it
closes an open menu, cancels a drawing, drops the selection, puts the tool
away and only then quits.

**Copy for agent** puts the marks on the clipboard. Paste them into an agent's
prompt with your request ("add a forest in mark 2", "remove the bridge at
pin 1"). The text has every mark in map coordinates (x east, y north, the
coordinates of map objects and build scripts; z is the terrain height), its
centre, size and area (a rotated rectangle with its angle and four corners),
and the objects inside it: structures and props one by one with their
positions and layer (the name the build placed them with), vegetation counted
by template, and a count per layer. It ends with the map's source project and
how to rebuild it.

`mw marks [MAP]` prints the same text, so an agent can also read the marks
itself ([AGENTS.md](../AGENTS.md)); `--json` gives the exact outlines, and
`--near` the distance around pins and open paths that counts as inside (150).

## Overlays

**View → Walkable** (key 7) draws the local walkability estimate: open ground
green, shallow water blue, bridge decks cyan, blocked cells red and striped
(cliffs, deep water, buildings), and in orange the walkable areas no player
start can reach. It runs in the background after each reload, while the status
bar says **Computing walkability**. It is the same estimate as `mw walkable`;
[walkability](guide/projects-and-builds.md#walkability) says what it leaves out.

**View → River flow arrows** (key 8) draws yellow chevrons along each river
strip, pointing and drifting downstream, with the strip's banks in blue, its
first cross-section green and its last red, so joins and overlaps between
strips show. `mw render ... --flow` draws the same into still renders, and
`mw rivers <map>` prints each strip's course as compass runs.
