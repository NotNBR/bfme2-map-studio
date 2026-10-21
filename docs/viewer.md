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

The viewer has two cameras; **V** or the camera bar switches between them,
and the view stays where it is.

- **Edit**, the default, orbits a point on the ground, as in a 3D editor. Use
  it to work on the map: marks, the palette and the marks panel are shown.
- **Photo** is a free camera with a lens, for looking at the map from anywhere
  and for pictures ([Photo mode](#photo-mode-and-the-camera-bar)).

Neither is the game's camera; [test games](guide/testing-in-game.md#camera)
have the game's own, freed to zoom out and tilt.

| Input (Edit) | Action |
| --- | --- |
| Left drag | Orbit around the focus point |
| Right or middle drag | Grab and pan the ground |
| Wheel | Zoom towards the cursor |
| Double-click | Fly to the clicked point |
| W A S D / arrows | Move (Shift faster, Ctrl slower) |
| Q / E, R / F, Z / X | Rotate, tilt, zoom |
| Space / Home, T | Reset to the whole map, toggle top-down |

| Input (both) | Action |
| --- | --- |
| V | Edit or Photo |
| Ctrl+1..9, Ctrl+Shift+1..9 | Go to saved view 1-9, save the view there |
| Ctrl+C | Copy the view as a `mw render` command |
| 1 2 3 4 5 6 7 8 9 | Objects, water, shadows, normal maps, clouds, weather, walkable, river flow arrows, editor markers |
| U | Show or hide the units |
| M | Show or hide the marks |
| G, B, P, F5, Ctrl+B, F1 | Grid, border, screenshot, reload, build, controls |
| Del, Ctrl+Z | Delete the selected mark, undo a mark change (Edit) |
| Esc | Step back one level (see [marking](#marking-the-map-for-an-agent)); in Photo free the mouse, then go back to Edit; never closes the viewer |

## Photo mode and the camera bar

In Photo mode the mouse is captured, as in a first-person game: moving it
looks around. Esc frees it to use the bars; a click in the view takes it back.
The camera goes anywhere: nothing holds it above the ground, and it can look
straight up at the sky or out past the map's edge. Marks, the palette and the
marks panel are hidden; a short list of the controls below sits above the
camera bar.

| Input (Photo) | Action |
| --- | --- |
| Mouse | Look around (slower on a long lens) |
| Right drag | Slide sideways and up |
| Wheel | Move forward or back |
| Alt+wheel, Shift+wheel | Focal length, focus distance |
| Middle click | Focus on what is at the centre of the view, ground or object |
| W A S D / arrows | Fly along the view (Shift faster, Ctrl slower; speed grows with the height above the ground) |
| Space / C | Up / down |
| Q / E, R | Roll left / right, level again |

The **camera bar** at the bottom left holds, from the left:

- **Edit / Photo**, the camera.
- **Views**: the saved views with their thumbnails, Photo or Edit and their
  key. Click one to go there; **…** renames it, **×** deletes it; **Save the
  current view** puts it in the first free slot. Views are kept per map in
  `local/views/<map file name>.json`, in the form `mw render --views` reads
  ([rendering](guide/rendering.md#cameras)), with the thumbnails in a folder
  beside it.
- **Copy view**: the view as a `mw render --map ... --view view ...` command on
  the clipboard, to render it at full quality or hand it to an agent. It
  reproduces the picture: besides the camera it carries each preview setting
  that differs from `mw render`'s default, namely the size (Photo: the frame's), `--lod`,
  `--weather`, `--sun`, `--time`, `--normal-maps` and the layers `mw render`
  can switch (objects, units, shadows, clouds, fog and rain, vegetation limits,
  editor markers, grid, border, walkable, flow). Hidden water is the one
  setting it cannot carry. Saved views keep the camera only.
- In Photo mode, the lens ([render/photo.py](../src/mapworkshop/render/photo.py)):
  **focal length** (mm on a full-frame 36 x 24 mm sensor; 39 mm is Edit's 50
  degrees), **aperture** (f/ - is everything sharp; an f-number blurs what is
  nearer or further than the focus), **focus** distance along the view, and
  exposure compensation (**EV**). The wheel or a sideways drag over a field
  changes it; a click opens its presets. Depth of field follows a thin lens
  with 10 map units to the metre, blurring in linear light: focused across
  the map, little blurs; focused within a few hundred units, the distance
  does. The aperture changes only the depth of field, not the brightness.
  Depth of field and exposure are effects the game does not have.
- In Photo mode, the framing aids: **Thirds** lines and the **frame**'s
  aspect (Free, 16:9, 21:9, 3:2, 4:3, 1:1), shown by darkening outside it.
  The frame is the sensor's largest crop of its aspect, as in a camera's crop
  modes: 36 mm wide at 3:2 and wider, 24 mm tall when narrower, so a focal
  length frames a square picture as a 24 x 24 mm crop would. Screenshots in
  Photo mode (P) include the lens and exposure, are cropped to the frame and
  saved as `<map>-photo-<time>.png`.
- The **readout**: in Edit the target, distance, heading and tilt; in Photo the
  camera's position, heading, tilt, roll, the frame's field of view and, with
  an aperture, the distances that stay sharp (blur under 1/1500 of the
  frame's diagonal).

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
  its menu. The dropdown beside the button picks what it starts: the selected
  game, or **OpenBFME (Godot)**, which opens at its menu with the project's map
  in the Skirmish list, as `mw play --godot` does
  ([OpenBFME](guide/testing-in-game.md#openbfme-mw-play---godot)). The first
  OpenBFME start builds it, which the status bar follows. The choice is kept as
  `test_game` in `local/config.toml`. The viewer minimises once the game is up
  (the skirmish playable, or the game or OpenBFME open) and comes back when a
  skirmish or OpenBFME it started closes; a start that fails leaves it open,
  with the error in the status bar.
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
- **View**: check marks that stay open while you switch them: objects,
  **Units**, water, shadows; cloud shadows, normal maps, fog and rain/snow; grid, map border,
  walkable, river flow arrows, marks; **Animate** (water ripples, cloud
  shadows, rain and snow, on the game's clocks); **Game object limits**,
  which keeps only the first 1,200 trees and 2,000 shrubs, as the game's
  buffers do (off by default: every one is drawn); and **Editor markers**,
  the models WorldBuilder shows and the game never draws, such as the AI's
  farm sites (off by default, as in the game;
  [objects](game/renderer/objects.md)). **Units** (on by default) draws the
  units as a new game creates them: each horde as its members in their ranks,
  every unit in the pose of its idle animation; off leaves every unit out, to
  see the ground beneath an army ([units](game/renderer/objects.md#units)).
- **Top view**, **Reset view** and **Screenshot** (saved to `local/renders/`).
- **Frame rate**, at the right edge: the measured rate and the cap, for example
  `60 fps / 60`. Click it to change the cap.

Changing the map, the detail level, the weather, the sun, the game object
limits, the editor markers or the units reloads the scene.

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
closes an open menu, cancels a drawing, drops the selection and puts the
tool away. It never closes the viewer.

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

## The Godot viewer

```powershell
mw view MAP --godot [--view "target=X,Y distance=D ..."] [--size 1600x1000] [--weather W] [--sun S] [--fps F]
mw dev MAP --godot
mw view MAP --godot --view "..." --screenshot PICTURE.png
mw view MAP --godot --view "..." --probe X,Y[,Z] [--probe ...]
```

`--godot` opens the map in the studio's new viewer instead, on
[OpenBFME](guide/testing-in-game.md#openbfme-mw-play---godot)'s library: the
map as the game draws it, roads included and the units in their idle
animations, in about two seconds once OpenBFME is built. It is a step of
[moving the viewer to Godot](godot-viewer/plan.md) and does less than the
viewer above so far. Its window has the toolbar along the top, the marks
tools down the left edge, the marks panel at the right and a bar along the
bottom with the status line and the camera's readout. It has:

- the toolbar, as in [The toolbar](#the-toolbar): **Map** (the map projects,
  the game's maps, Open project folder, and Browse... for a project's build
  or a stock map), **Properties** (the studio viewer's window; the build its
  Save starts reloads here), **Build** with its chip, **Test In-Game** and
  the choice of what it starts, **Preview**, **View**, **Top view**, **Reset
  view**, **Screenshot** and the frame rate;
- **Preview**, as in [The toolbar](#the-toolbar): **Weather** and **Sun**,
  with the button showing the choice. OpenBFME draws a map as its file and
  `map.ini` say, so a preview is a copy of the map with the preset's world
  weather, lighting, fog and sky, which the viewer opens in the map's place
  (`<map> studio preview` in the user maps folder, removed when the viewer
  closes; while it is open, OpenBFME's Skirmish list shows it too). A
  screenshot (P) of a preview is named after the copy. Rain and snow bring
  their fog, light and sky but no falling rain or snow, and the sky changes
  only on the map's `WaterReflectionSkydome` objects. There is no
  **Detail**: OpenBFME has no detail levels;
- **View**, as in [The toolbar](#the-toolbar): objects (units included),
  water, roads, fog (the map's own; switching it builds the terrain again),
  Animate (the units' idle animations and the flow arrows), grid, map border,
  walkable, river flow arrows and marks. Walkable and the flow arrows are the
  estimate and the strips described above, worked out by the companion in
  Python: walkable once per build, taking as long as in the viewer above, with
  the bar saying when it is ready; the arrows cover every river, as OpenBFME
  draws them all. Without **Map border** the ground outside the playable area
  fades to black, in the top view too, and the water and roads there stay;
- the Edit camera, as in [Moving around](#moving-around): left drag orbits,
  right or middle drag pans, the wheel zooms, a double-click flies there,
  W A S D, Q / E, R / F, Z / X, Space or Home and T;
- marking, as in [Marking the map for an agent](#marking-the-map-for-an-agent):
  the tools at the left, selecting, moving, resizing and rotating, Del,
  Ctrl+Z and Esc, the marks panel at the right and **Copy for agent**. The
  marks are the same file, so `mw marks` reads them as from the viewer above;
- the camera bar and Photo mode, as in
  [Photo mode and the camera bar](#photo-mode-and-the-camera-bar), along the
  bottom with the status line: **Edit / Photo**, **Views** and **Copy view**
  (the same views files and command as the viewer above, Ctrl+1-9,
  Ctrl+Shift+1-9 and Ctrl+C; renaming and deleting are at the end of the
  Views list), the lens and the framing aids. The depth of field and
  exposure are `mw render`'s, run on the graphics card; a screenshot (P) in
  Photo mode is named `<map> photo <time>.png`. Copy view carries the size,
  the Preview's weather and sun and the View switches `mw render` has; the
  rest (units, shadows, clouds, detail, time, normal maps) are `mw render`'s
  defaults, which the Godot viewer does not draw;
- live reload, as in [Live reload](#live-reload): a new build of a project
  (`mw build`, `mw dev MAP --godot`) is built again in place, about three
  seconds after the build for a small map, and the camera stays. A build that
  cannot be read leaves the last good map and says so in the status line;
  stock maps are not watched;
- **1** for the objects, **2** the water, **6** the fog, **7** walkable,
  **8** the flow arrows, **G** the grid, **B** the map border, **M** the
  marks, **V** Photo mode, **P** a screenshot into `godot/` in the profile's
  renders folder (`local/profiles/<profile>/renders/godot/`), **F1** the
  controls.

Shadows, normal maps, cloud shadows, rain and snow, editor markers and the
game object limits are not in the View menu: OpenBFME's library draws none of
them as switches.

A project opens from its last build, which goes into OpenBFME's user maps
folder in `local/openbfme/appdata/`; a stock map opens from RotWK's archives,
so only under the RotWK profile. While the window is open, `mw view --godot`
keeps running: it is the viewer's companion, which keeps the marks and
watches the build. `--view` takes the words of `mw render --view` (an orbit
view, not a top view) and starts there, and the first move orbits from it:
the view is worked out as `mw render` works it out, so the camera puts a map
point on the same pixel as `mw render`'s. `--probe` prints that pixel from
each, and `--screenshot` saves the view and closes; both need the window at
the `--size` asked for. A view with an `aperture` or an `ev` opens in Photo
mode with that lens, so its screenshot has `mw render`'s depth of field and
exposure.
