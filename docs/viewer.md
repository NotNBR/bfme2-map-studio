# The viewer

The viewer shows a map as the game draws it, reloads it whenever it is
rebuilt, and lets you mark places on it for an agent.

```powershell
mw view [MAP] [--weather map|clear|haze|rain|snow|dusk] [--sun own|ember|copper|blood|sulphur|ash|violet]
        [--fps 60] [--size 1600x1000]
mw view MAP --view "target=X,Y distance=D ..." [--screenshot PICTURE.png] [--probe X,Y[,Z] ...]
```

`mw` alone, `mw view` without a map, and double-clicking `Map Workshop.cmd`
open a blank Studio with the **Open Map** modal already visible. Its two
columns list **Custom maps** on the left and **Original maps** on the right; search filters both.
Select a map, then click **Open Map** at the bottom. For an unbuilt custom map,
the button reads **Build and Open**. **Browse .map…** opens a downloaded or
separately generated map. Selecting an entry alone never opens or builds it; a failed build
keeps the modal open with its error. Close the modal to leave Studio blank,
then use **Open Map** in the toolbar to return. Map controls become available
once a map is loaded.
Commands with an explicit `MAP` open it directly.
The command window shows opening and build progress. Godot's detailed output is
saved to `local/openbfme/logs/viewer-*.log`; if the viewer exits with an error,
the command prints the exact log path.
`MAP` is a project id or any unique start of it
(`grey`), a stock map ("fords of isen") or a `.map` file of either. The
viewer is a Godot project of the studio's own on
[OpenBFME](guide/testing-in-game.md#openbfme-mw-play---godot)'s library, a port
of the game's engine: the map as the game draws it, roads included and the
units in their idle animations, in about two seconds. It needs OpenBFME
built (the first start builds it, which takes minutes), the game files it
plays from, English RotWK 2.01 and BFME2 1.06, and a graphics card with
Vulkan. `--weather` and `--sun` start
with a preview (the toolbar's [Atmosphere](#the-toolbar)), `--fps` caps the frame rate (30, 60, 90, 120,
144, `vsync` or `unlimited`) and `--size` sets the window. F1 shows the
controls.

A project opens from its last build, which goes into OpenBFME's user maps
folder in `local/openbfme/appdata/`; a stock map opens from RotWK's archives,
so only under the RotWK profile. While the window is open, `mw view` keeps
running: it is the viewer's companion, which keeps the marks, watches the
build and works out what needs the map's analysis. The code is in
[viewer/](../src/mapworkshop/viewer/): `godot_viewer.py` starts it,
`godot_link.py` is the companion and `godot/` the Godot project;
[the plan](history/godot-viewer-plan.md) records how it was built and
[the checklist](history/godot-viewer-parity.md) how it compared with the Python
viewer it replaced.

`--view` takes the words of `mw render --view` (an orbit view, not a top
view) and starts there, and the first move orbits from it. The view is worked
out as `mw render` works it out, so the camera puts a map point on the same
pixel as `mw render`'s; `--probe` prints that pixel from each. `--screenshot`
saves the view, unseen on a hidden desktop, and closes. A view with an
`aperture` or an `ev` opens in Photo mode with that lens, so its screenshot
has `mw render`'s depth of field and exposure.

## Grass and ground detail

In **Layers**, enable **Grass** to add the camera-local blade field to the map
being edited. Switch it off to hide the blades immediately. **Ground detail**
independently toggles the enhanced turf texture. Both start off; the choices
survive map reloads and weather previews in the open viewer. These are visual
preview options and do not alter the saved map. Grass transitions by projected
blade size: dense nearby blades, sparser wider blades at medium range, then
matching terrain canopy shading at overview scale. Distant coverage has no
render-distance cutoff and follows the same Grass toggle. Blade tiles cover
the visible camera frustum, including shallow angles, rather than a fixed
area around the ground focus. Its colour and
irregular density stay anchored to the terrain while zooming and panning.
Grass selects MSAA 8x and restores the previous setting when switched off.
Sample coverage replaces the noisy pixel fade; slightly wider distant blades
and reduced distant wind also limit shimmer. Blade distance is twice the
previous screen-size cutoff. Grass keeps 65% of the ground colour and 35% of
the meadow tint, with restrained brightness variation. Mixed blade shapes
grow in uneven clumps, with shorter flattened verges and subtle root shading.
Sparse leaves near tree templates, dead stems and small pebbles share the
Grass toggle. It avoids roads,
water and steep slopes; interactive trampling and building-footprint clearance are not
implemented.

## Moving around

The viewer has two cameras; **V** or the camera bar switches between them,
and the view stays where it is. The camera bar's third mode, **Test**, runs
the map as a game ([Test mode](#test-mode-the-map-as-a-game)).

- **Edit**, the default, orbits a point on the ground, as in a 3D editor. Use
  it to work on the map: the marks, their tools and the marks panel are shown.
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
| 1 2 3 6 7 8 | Objects, water, starting positions, fog, walkable, river flow arrows |
| M | Show or hide the marks |
| G, B, P, F5, Ctrl+B | Grid, border, screenshot, read the map again, build |
| F1 | Show or hide the controls, also before a map is open; Esc closes them too |
| Del, Ctrl+Z | Delete the selected mark, undo a mark change (Edit) |
| Esc | Step back one level (see [marking](#marking-the-map-for-an-agent)); in Photo free the mouse, then go back to Edit; never closes the viewer |

## Photo mode and the camera bar

In Photo mode the mouse is captured, as in a first-person game: moving it
looks around. Esc frees it to use the bars; a click in the view takes it back.
The camera goes anywhere: nothing holds it above the ground, and it can look
straight up at the sky or out past the map's edge. The marks, their tools and
the marks panel are hidden; a short list of the controls below sits above the
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

The **camera bar** along the bottom holds, from the left:

- **Edit / Photo**, the camera, and **Test**, the map run as a game
  ([Test mode](#test-mode-the-map-as-a-game)).
- **Views**: the saved views with their thumbnails, Photo or Edit and their
  key. Click one to go there; **Save the current view** puts it in the first
  free slot, and **Rename...** and **Delete** at the end of the list change
  one. Views are kept per map in `local/views/<map file name>.json`, in the
  form `mw render --views` reads ([rendering](guide/rendering.md#cameras)),
  with the thumbnails in a folder beside it.
- **Copy view**: the view as a `mw render --map ... --view view ...` command on
  the clipboard, to render it at full quality or hand it to an agent. Besides
  the camera it carries the size (Photo: the frame's), Atmosphere's weather and
  sun and the view switches `mw render` has (objects, fog, grid, border,
  walkable, flow). Hidden water is the one setting it cannot carry. Saved
  views keep the camera only.
- In Photo mode, the lens, OpenBFME's pro camera (the engine's
  `godot/scripts/pro_lens.gd` and `pro_lens_effect.gd`, brought from the pinned
  engine by [engine_adapter.py](../src/mapworkshop/native/engine_adapter.py); the
  studio keeps no copy, so a fix there reaches the viewer with the next engine pin):
  **focal length** (mm on a full-frame 36 x 24 mm sensor; 39 mm is Edit's 50
  degrees), **aperture** (f/ - is everything sharp; an f-number blurs what is
  nearer or further than the focus), **focus** distance along the view, and
  exposure compensation (**EV**). The wheel or a sideways drag over a field
  changes it; a click opens its presets. Depth of field follows a thin lens
  with 10 map units to the metre, blurring in linear light on the graphics
  card, as `mw render` does: focused across the map, little blurs; focused
  within a few hundred units, the distance does. The aperture changes only
  the depth of field, not the brightness. Depth of field and exposure are
  effects the game does not have.
- In Photo mode, the framing aids: **Thirds** lines and the **frame**'s
  aspect (Free, 16:9, 21:9, 3:2, 4:3, 1:1), shown by darkening outside it.
  The frame is the sensor's largest crop of its aspect, as in a camera's crop
  modes: 36 mm wide at 3:2 and wider, 24 mm tall when narrower, so a focal
  length frames a square picture as a 24 x 24 mm crop would. Screenshots in
  Photo mode (P) include the lens and exposure, are cropped to the frame and
  saved as `<map> photo <time>.png`.
- The status line: the latest message for a few seconds, else what the mouse
  does now. Before a map is open the bar shows only the status line.
- The **readout**, at the right: in Edit the target, distance, heading and
  tilt; in Photo the camera's position, heading, tilt, roll, the frame's field
  of view and, with an aperture, the distances that stay sharp (blur under
  1/1500 of the frame's diagonal).

## Test mode: the map as a game

**Test** on the camera bar runs the map as a game: OpenBFME's GameWorld, the
game's own logic, takes the place of the still objects. Battalions form up,
units animate, and they move and fight as ordered. Test uses OpenBFME's Uber
performance profile. Every slot of the map's
line-up (`map.toml`'s `[play]`, else Men against Mordor) is human, so no AI
moves an army, and both armies take orders: an order goes out as the owner
of the units selected. The marks and their tools are put away meanwhile;
**Edit** or **Photo** ends the game, and the map is as it was.

| Mouse or key | Does |
|---|---|
| Left click a unit, left drag a box | select it, or the units in the box (Shift adds); one owner's units at a time |
| Right click the ground | move the selection there (Shift: a waypoint after the last) |
| Right click a unit of another owner | attack it |
| X | stop |
| Esc | let go of the selection |
| Middle drag | orbit (the left drag is the box); the right drag still pans, the wheel and the keys move the camera, but Z and X do not zoom |

The panel at the top left pauses the game, sets its speed (0.5 to 4 times)
and draws **Paths**: the path each unit's AI follows, live, for the selected
units (and their battalions' members) or for every unit. A path runs from the
unit through the nodes still ahead to a cross at its end, the nodes behind it
faint; it is orange while the unit waits for the pathfinder and red while it
is blocked. A unit or battalion is drawn thick, a battalion's members thin.
The game reads them from each unit's movement code
(`GameWorld.get_object_path`, a commit on the [pin](guide/testing-in-game.md#the-pin-and-a-clean-submodule)). The first start takes about five seconds, while the game's objects
load.

The game reads the map from an archive the companion packs when the viewer
starts ([native/openbfme.py](../src/mapworkshop/native/openbfme.py),
`pack_for_test`): OpenBFME runs a game only on a map in its archives (a game
on a user map is part 2 of the user-maps change, not written yet), and the
archive stays open while the viewer runs. So after a new build, another map
or another weather or sun, **Test** starts the viewer again on the map as it is,
at the same camera, in Test mode. [Test Mode Lab](../maps/test_mode_lab/map.py)
(`mw view test-mode-lab`) has two small armies for it. The game's HUD (the
command bar, powers, building) is not there; **Play in game** with OpenBFME
has it.

## Live reload

`mw dev [MAP]` is the quickest way to work on a map: it builds the project,
opens the viewer and rebuilds whenever you save a file in the project folder.

The companion watches the map file and its `map.ini`. When a new build has
settled (from the toolbar, `mw build` or `mw dev`), it goes into OpenBFME's
user maps folder and the viewer builds the map again in place, about three
seconds after the build for a small map; the camera stays where it is. The
window waits while the library builds the map, with a toast saying what it is
loading and then how long it took. If the new build cannot be read, the last
good map stays and the status line says so. Stock maps are not watched; F5
reads the map shown again.

## The toolbar

- **Open Map** opens the modal with Custom and Original map columns (original maps open under
  the RotWK profile only). **Browse .map…** picks a `.map` file and opens it (one that is
  neither a project's build nor a stock map as a copy in the user maps
  folder).
- **Map** acts on the map shown:
  - **Properties…** opens a window with the map's map-wide settings, in tabs:
    the project's title, description and weather preset; the camera limits;
    WorldInfo flags; the environment (water alpha, macro and cloud textures);
    water reflections; fog, clouds, snow and lightning. Each field shows the
    map's value, or in grey the game's default where `map.ini` leaves it out.
    For a project, **Save and build** writes the changed fields into `map.toml`
    as [properties](guide/projects-and-builds.md#map-properties) and builds it;
    the new build reloads. A field set there is marked `map.toml` and has a
    **Reset** button that hands it back to `map.py`. One of the game's maps is
    shown read-only.
  - **Open project folder** opens the project's source folder (a project's
    map only).
  - **Export placement plan** saves and opens a plan of the map, with starts,
    buildings, lairs and capture-flag footprint closeups
    ([placement plans](guide/map-graphics.md#placement-plans)).
- **Build** rebuilds the current project in the background; the map reloads
  when the build is done. A failed build shows the start of its error in the
  status line (the full output goes to the terminal) and leaves the previous
  build in place. A chip beside the button shows a running build, then when
  the last one ended and how long it took, or that it failed.
- **Play in game** starts BFME2 straight in a skirmish on the current project,
  you against an easy AI, as `mw play` does
  ([testing in the game](guide/testing-in-game.md)). The status line says
  when the skirmish is playable and when the game has closed. When the game is
  not BFME2 1.06, or for one of the game's own maps, it starts the normal game
  at its menu. The dropdown beside the button picks what it starts: the
  selected game, or **OpenBFME (Godot)**, which starts a skirmish on the
  project's map, as `mw play --godot` does
  ([OpenBFME](guide/testing-in-game.md#openbfme-mw-play---godot)). The choice
  is kept as `test_game` in `local/config.toml`. The adjacent **⚙** opens a compact
  panel for OpenBFME test rounds: resolution, window mode, grass, ground detail,
  and fog of war. **Save** remembers the choices as `test_settings`; they apply
  on the next launch. Saved game setting preserves the existing display choice;
  explicit display choices update only those fields in the isolated game's
  configuration. Borderless fullscreen uses the monitor's resolution. Original
  game launches keep their existing settings. The viewer minimises once the
  game is up and comes back when a skirmish or OpenBFME it started closes; a
  start that fails leaves it open, with the error in the status line.
  **Test** on the camera bar is the other way to try a map: it runs it inside
  the viewer ([Test mode](#test-mode-the-map-as-a-game)).
- Three menus switch what the view shows; each stays open while you switch
  its entries, and the key in brackets switches an entry too:
  - **Layers**, the map's own content: **Objects**, **Animate** (the units'
    idle animations, the falling rain or snow and the flow arrows),
    **Water**, **Roads**, [**Grass** and **Ground detail**](#grass-and-ground-detail),
    and under **Opens a copy of the map**, **Units** and **The game's tree and
    shrub limits** (only the first 1,200 trees, 2,000 shrubs and 64 kinds of
    tree the game keeps). Those last two open a copy of the map without what
    they leave out, as a preview does.
  - **Overlays**, helpers drawn over the map that the game never shows:
    **Marks**, **Starting positions**, **Grid**, **Map border**, and under
    **Analysis**, **Walkable** and **River flow arrows** ([overlays](#overlays)).
  - **Atmosphere** shows the map another way without changing it. Its button
    names the choice when it is not the map's own, for example
    `Atmosphere: Rain · Mordor: Ember`.
    - **Weather**: **Map's own** uses the map's `map.ini` weather. **Clear**,
      **Haze**, **Rain**, **Snow** and **Dusk** apply the
      [weather presets](../src/mapworkshop/mapkit/weather.py): fog, lighting
      and the preset's sky dome. The map's own weather is set in
      **Map → Properties…**.
    - **Sun**: **Weather's own**, or a light rig over the weather. The Mordor
      suns (Ember, Copper, Blood red, Sulphur glow, High sun through ash, Dusk
      violet) bring the Minas Morgul sky and a matching fog tint.
    - **Effects**: **Fog, rain and snow** (the map's own; switching it builds
      the terrain again) and **Cloud shadows**.

    OpenBFME draws a map as its file and `map.ini` say, so a weather or sun
    preview is a copy of the map with the preset's world weather, lighting,
    fog and sky, which the viewer opens in the map's place (`<map> studio
    preview` in the user maps folder, removed when the viewer closes; while it
    is open, OpenBFME's Skirmish list shows it too). Rain and snow bring their
    fog, light and sky and the rain or snow falling, as the game lays it out;
    the sky changes only on the map's `WaterReflectionSkydome` objects.
- **Top view**, **Reset view** and **Screenshot**, like T, Space and P; Top
  view and Reset view leave Photo mode but keep a Test game running. Screenshots
  are saved without the controls (Test mode's panel too)
  into `godot/` in the profile's renders folder,
  `local/profiles/<profile>/renders/godot/`).
- **Frame rate**, at the right edge: the measured rate and the cap, for
  example `60 fps / 60`. Click it to change the cap.

OpenBFME has no detail levels, shadows or normal maps, so the viewer has none
of them, and it draws without anti-aliasing
([where it differs from the game](guide/rendering.md#where-it-differs-from-the-game)).

## Marking the map for an agent

The tools down the left edge of the view point at places on the map; hover a
button to see what it does. The mouse navigates (**Navigate**) until you pick
a tool; the tool then stays armed (a crosshair cursor) so you can draw several
marks, until Esc, a second click on it or Navigate puts it away. Right drag
and the wheel still pan and zoom while a tool is armed.

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
each mark with the objects inside it. **Overlays → Marks** (key M) hides the marks
and the panel; picking a tool shows them again. Esc steps back one level: it
cancels a drawing, drops the selection and puts the tool away. It never closes
the viewer.

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

**Overlays → Starting positions** (key 3) shows numbered gold rings on the ground
at the map's `Player_N_Start` waypoints. They are on by default while exploring
a map and hidden during Test mode. Automated renders leave them out by default.

**Overlays → Walkable** (key 7) draws the local walkability estimate: open ground
green, shallow water blue, bridge decks cyan, blocked cells red and striped
(cliffs, deep water, buildings), and in orange the walkable areas no player
start can reach. The companion works it out once per build, in the
background, while the status line says **Computing walkability**. It is the
same estimate as `mw walkable`;
[walkability](guide/projects-and-builds.md#walkability) says what it leaves out.

**Overlays → River flow arrows** (key 8) draws yellow chevrons along each river
strip, pointing and drifting downstream, with the strip's banks in blue, its
first cross-section green and its last red, so joins and overlaps between
strips show. It covers every river, as OpenBFME draws them all. `mw render ...
--flow` draws the same into still renders, and `mw rivers <map>` prints each
strip's course as compass runs.

**Overlays → Grid** (G) draws a 100-unit grid on the ground. Without **Map border**
(B) the ground outside the playable area fades to black, in the top view too,
and the water and roads there stay; with it, the whole border shows.
