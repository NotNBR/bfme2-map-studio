# Making maps

A map is a project folder in [maps/](../maps): a `map.toml` that names it and
a `map.py` that builds it. The workshop runs the build, keeps every result and
shows it in the viewer.

```powershell
mw new "Misty Vale" --players 4 --size 600x600   # an empty, level map
mw dev misty-vale                                # build, open the viewer, rebuild on save
mw play misty-vale                               # test it in-game: a skirmish on it, straight away
```

For the design side (composition, landforms, materials, detail), follow the
[map workflow](map-workflow.md) and its [worked example](map-workflow-example.md).

## A project

```
maps/misty_vale/
├── map.toml        id, title, native name, players, description, weather
├── map.py          def build(b): ...
├── references/     source images: heightmaps, sketches (optional)
└── README.md
```

`map.toml`:

```toml
id = "misty-vale"                       # what commands take: mw build misty-vale (or mw build misty)
title = "Misty Vale"                    # shown in the viewer and the game
native_name = "map mp misty vale"       # the map's file and folder name in the game
players = 4                             # player slots in the game
description = "A 4-player map."        # shown in the game's map list
weather = "clear"                       # clear, haze, rain, snow, dusk (mapworkshop.mapkit.weather)
```

These settings live only here: `map.py` reads them from `b.project` and passes
them on, e.g. `create(..., title=b.project.title, description=b.project.description,
player_count=b.project.players)`, instead of repeating them. Other keys are free
for the build to read, as Eight Kingdoms does for its size and seed.

### Map properties

A `[properties]` table sets map-wide properties over what the build writes;
the viewer's **Properties** window writes it
([mapkit/properties.py](../src/mapworkshop/mapkit/properties.py) lists them):

```toml
[properties.world]                      # WorldInfo, by the game's key names
cameraMaxHeight = 25000.0
[properties.environment]                # the EnvironmentData chunk
deep_water_alpha = 0.9
[properties.ini.WaterTransparency]      # fields of a map.ini block
ReflectionOn = true
[properties.ini.Weather]
HardwareFogColor = [120, 130, 150]      # colours [r, g, b], pairs [x, y]
```

The build applies them after `map.py` has run, to the `.map` and `map.ini` it
wrote, and lists the values they changed. Fix a value in `map.py` instead
when the code depends on it (the water level, say), and keep `[properties]`
for settings the code leaves alone.

## The build

`map.py` defines `build(b)`. `b` is the build (`mapworkshop.project.Build`):

| | |
|---|---|
| `b.project` | the project: `id`, `title`, `native_name`, `players`, `description`, `weather`, `config` (all of map.toml), `folder` |
| `b.save(m, ini='', minimap=None)` | write the map `m`, its `map.ini` text and the in-game minimap; without `minimap`, the minimap is rendered from above |
| `b.image(name, image)` | keep a plan or preview image (PIL) with this build |
| `b.report` | a dict saved as `report.json` with the build |
| `b.work` | this build's folder, for other files |
| `b.assets` | the game's assets: templates, INIs, textures, models (`render.assets.GameAssets`) |
| `b.args` | extra command-line arguments: `mw build misty -- --fast` |

`mw new` writes a `map.py` that makes a level grass plane with the player
starts, sky and lighting, and shows where heights, textures and objects go.
The five maps in `maps/` are complete examples. Greywater Marches uses
`build(b)`; the others still have a `build.py` with `main()`, which the
pipeline runs the same way (see below).

Building blocks, in `src/mapworkshop/`:

- `mapkit.blank`: `create` (a new native map document), `set_heights`,
  `set_materials` (texture indices per cell, with corner blends), `add_object`,
  `starts`, `terrain_cell_sizes`, `water_plane` (one water level for the map),
  `set_world` (WorldInfo values by name, e.g. `cameraMaxHeight`).
- `mapkit.earth` (`fbm` noise, `thermal_erosion`) and `mapkit.relief`
  (`distance_to`, smoothing): landforms.
- `mapkit.lines`: distance from every terrain sample to authored lines
  (`polyline_distance` with the arc length along the line, `nearest` of
  several). Pass `reach` for fields only compared against short distances,
  such as roads and lanes: it measures each segment only against the samples
  near it, with the same values there, and is far faster on long lines.
  Beyond `reach` the distance is infinite, so choose it above the largest
  distance the field is compared against (the maps' road and lane fields use
  500 for comparisons up to about 200), or leave it out.
- `mapkit.variety`: `spot_random(seed, template, x, y)`, an object's own random
  numbers for its size and rotation. Drawn from one shared stream instead, every
  object after an added or skipped placement would get a new size, and a small
  edit would change the whole map (`mw diff` shows it).
- `mapkit.roads`: road pairs; `formats.water.standing_water`: several water areas.
- `mapkit.rivers`: a river's flowing surface over standing water (`add_river`
  along a line, `cross_sections`) and shore waves (`add_shore_waves`); the
  renderer draws the rivers ([rivers, shore waves and shipwrights](reference/mapping/terrain-and-presentation/rivers-and-waves.md)).
  `mw rivers <map>`, the viewer (key **8**) and `mw render --flow` show which
  way each strip flows.
- `mapkit.pathing` and `mapkit.walkable`: local walkability estimates from terrain,
  water, object footprints and walking meshes, without starting the game.
  `mw walkable <map>`, the viewer (key **7**) and `mw render --walkable` show
  areas cut off from every start. `--compare` checks a saved native grid;
  `--native` explicitly starts a skirmish to capture one. See the
  [viewer guide](viewer.md#walkable-areas) for the estimate's limits.
- `mapkit.cliffs`: cliff texture mapping, so steep faces do not stretch
  their texture into streaks: `set_materials(..., cliffs=steep_cells(heights))`
  writes a cliff record per masked cell, its UVs measured along the face as
  the stock maps' are. One texture per map (the game builds the cliff
  texture from the first record's); mapped cells keep no blend, so put that
  texture last in the palette
  ([cliff mapping](reference/mapping/terrain-and-presentation/terrain.md#cliff-mapping)).
- `mapkit.bridges`: bridges the game spans between two points at any length
  (`add_bridge`; `bridge_type` for a map's own type), walkable; only models
  with left/span/right pieces work, which it checks
  ([spanned bridges](reference/mapping/navigation/roads-and-bridges.md#spanned-bridges)).
- `mapkit.walls`: the game's chainable walls (`wall_line` lays segments, hubs,
  gates and towers along a path for a faction's kit; `place_wall` adds them
  with an owner; `ground_rise` finds pieces on uneven ground) and castle sites
  (`castle_site`, a CastleFlag that unpacks the capturing faction's castle;
  `castle_layout` reads one) ([walls and castles](reference/mapping/navigation/walls-and-castles.md)).
- `mapkit.script_writer`: map scripts from the game's own catalogue of
  conditions and actions (`Writer(m).operation`, `.script`, `.install`),
  each checked against its argument signature; for scripted test scenarios
  ([map scripts](reference/mapping/scripts/README.md)).
- `mapkit.sites`: outposts, inns, signal fires and shipwrights with the
  capture flag they are taken by (`neutral_site`, `shipwright` on a shore), creep lairs
  (`creep_lair`), skirmish Gollum's spawn points (`gollum_spawns`) and
  `spread` for evenly spaced points; `mapkit.ambient`: a map's sound bed and
  emitters by kind of place (`ambient`, palettes per setting)
  ([neutral sites](reference/mapping/players-economy-and-ai/neutral-sites.md)).
- `mapkit.vegetation`: keeps trees and shrubs past the game's 1,200 / 2,000
  buffer limits visible as full models.
- `mapkit.weather`: weather presets with the map's own sun and fill
  (`apply_weather`), sky domes (`add_sky`) and the map.ini Weather block
  (`ini_block`).
- `mapkit.checks`: `analyze` (the map's records, checked), `strategy`
  (walking distances and fairness between players), `coverage`,
  `terrain_audit`, `lighting_check`.
- `formats`: the native files themselves: `.map`, `.big`, W3D models, lighting,
  scripts, castles, compiled effects. `formats.sections` reads and writes
  every section of a map as Python values (`read(m, 'NamedCameras')`, change
  them, `write(m, ...)`): terrain, players, teams, scripts, water, cameras,
  lighting and the rest; `Map.objects()` and `Map.set_objects()` do the same
  for objects.

Positions are map units, 10 per terrain cell: x runs east and y north from the
playable area's south-west corner, the same coordinates as the viewer's marks.
Template and texture names are the game's: `b.assets.templates` lists the
objects, `local/game/data/ini/terrain.ini` the textures; `mw find` searches
them.

## Finding objects, textures and effects

`mw find` searches the game's object templates by what they are rather than by
name alone ([render/catalog.py](../src/mapworkshop/render/catalog.py)):

```powershell
mw find stone bridge                        # every word must match name, type, region, material or variant
mw find --type tree --region shire --used   # filters; --used: only what the stock maps place
mw find snow ruin --size large              # footprint: small <10, medium <40, large <120, huge (map units)
mw find torch --render                      # also an `mw items` collage of the results
mw find --textures mordor --type cliff      # terrain textures by terrain.ini's Type and Region
mw find --roads | --sounds | --effects [WORDS]
mw item FireCampfire --info                 # everything known about one template
```

Each template has a group and type (Nature: tree, shrub, rock, cliff, water
feature, animal...; Built scenery: house, wall, tower, gate, bridge, ruin,
statue, light / fire, clutter...; Gameplay neutrals: lairs, capturable
buildings, flags), a region (Shire, Gondor / Minas Tirith, Erebor, Mordor, ...),
variants (Snow, Ruined, Rubble, Damaged, Dead / burnt, Night), a material, its
footprint radius and its use in the 72 stock maps. Results cover every group,
in order of use in the stock maps; `--group` narrows them (nature, built,
gameplay, faction, creeps, sound, system, obsolete). `--json` prints the full
entries.

Groups follow the game's own `EditorSorting`, `KindOf`, `Side` and the INI each
template is defined in; types, regions and variants also use rules over names,
so a few templates are misfiled. Material shows its evidence: `game flag` (the
game's `MADE_OF_*`, set on few templates), `type` (trees are vegetation),
`name`, `texture` (the model's texture names) or `culture guess` (Gondor and
dwarf buildings stone, Rohan and Shire wood), weakest last. Effects list the
templates that carry each particle system (a map shows a particle system
through an object that carries it). The index is built once (about half a
minute) into `local/cache/catalog.json` and again when the game data or the
stock maps change; `--refresh` forces it.

A `!` marks templates the game marks obsolete, defines for cinematics or
tests, or spawns itself, and a faction's gameplay buildings (production,
defence, economy, fortress); `mw item NAME --info` says which. Every build
lists the same for the objects it placed (below).

## Builds

`mw build [MAP]` (and **Build** in the viewer, and `mw dev`) builds in a fresh
Python process:

- The build runs in its own folder, `local/history/<id>/<time>/`, with its plans,
  `report.json` and `build.json` (time, source hash, git commit, map hash).
- Only a build that succeeds replaces `local/build/<id>/`: the `.map`, `map.ini`,
  minimap and `preview.png`. An open viewer then reloads it. A failed build
  leaves the previous one in place.
- The last five builds are kept; `mw history [MAP]` lists them.
- Each build ends with what it changed since the previous one, also kept in its
  `build.json` (`changes`): heights and repainted textures with their area,
  passability, objects added, removed, moved or changed (by layer, fewest first),
  every other section by name and property, and `map.ini` lines. `mw diff [MAP]`
  shows it again; `mw diff MAP OTHER` compares any two maps (projects, stock maps
  or `.map` files), `--json` gives everything. Objects are matched by template and
  position, so renumbered uniqueIDs are not changes.
- It then lists placed templates to know about, with their count and layers,
  also in `build.json` (`template_concerns`): names the game doesn't define,
  obsolete, cinematic or spawned-only templates, and faction gameplay buildings
  that no player owns. They inform; the build still succeeds, and
  `mw item NAME --info` says more.
- Builds are reproducible: the same source gives the same map, byte for byte.
  (The process runs with a fixed `PYTHONHASHSEED`, because some builds iterate
  sets of names.)

## Testing in-game

`mw play <map>` (the viewer's **Test In-Game**) starts BFME2 straight in a
skirmish on the current build, without going through the menus: the game opens
in a 1600 x 1200 window, you against an easy AI, at Medium detail
(`--graphics Low|Medium|High|UltraHigh` for another). It runs an isolated copy
of the game in `local/runtime/` ([native/runtime.py](../src/mapworkshop/native/runtime.py)),
made on first use from the installed BFME2, which must be version 1.06:

- `game/`: the install's archives and movies as hard links (no extra disk), the
  rest (about 30 MB) as copies, so nothing a run writes reaches the install;
- `mod/maps/`: the builds installed for test games and their map-cache entries
  (the game starts with `-mod` on this folder);
- `appdata/`: the profile the game is given instead of yours, so your normal
  game, its options and saved games are untouched;
- `logs/`: the launcher logs.

Every start skips the five seconds the game spends on its EA title logo after
loading: the runtime's mod folder carries the game's INI that defines that
image, without it, and the game shows the logo only when the image exists.

The launcher ([native/debugger.py](../src/mapworkshop/native/debugger.py),
ported from openbfme2's test harness) runs the game as its debugger. That is
how it starts the game in a skirmish (it finishes the setup the skirmish menu
would do), keeps it on the sandbox profile and away from focus stalls, and
learns from the game itself, not from a timer, when the skirmish is ready: a
breakpoint at the end of the game's new-game pass, after the map is loaded and
the players placed, reports it. `mw play` returns at that moment ("playable in
BFME2, 5 s after the start"), or with the launcher's last line if the game
ends before then; the viewer's status bar shows the start, then "playable",
then "closed" when the game ends. Retail BFME2 ignores its window's close
button and Alt+F4; the launcher catches that close request and ends the game,
so closing the window works. The launcher log is
`local/runtime/logs/play-<map>.log`. It needs no administrator rights.

### Camera

Test games have a free camera, to look at the map from any distance and angle:

| Input | Does |
| --- | --- |
| Mouse wheel | zooms, from close up to far enough to see the whole map |
| Middle button held, mouse up or down | tilts, from near the horizon to straight down |
| Middle button held, mouse sideways | rotates (the game's own) |
| Middle click | the game's own camera again, at its default angle and zoom |

Scrolling, the minimap and rotation work as usual, and scrolling covers as
much of the screen per step at any zoom. The camera stays the game's own
until you first zoom or tilt, and scripted camera moves hand it back to the
game. The game draws no sky near the horizon, so low angles show black above
the terrain, and the map's edge shows as black.

It comes from a small DLL the launcher loads into every game it starts
([native/ingame/ingame.cpp](../src/mapworkshop/native/ingame/ingame.cpp),
committed built; `python -m mapworkshop.native.msvc ingame` rebuilds it with
Visual C++ .NET 2003, setting `msvc71`). It lets the game build its camera,
then turns it to the chosen tilt and moves it to the chosen distance from the
same focus point, before the game sets it and the terrain picks what to draw
from it; it also moves the clip planes out, which the game keeps at 10 to
1,800 units. It replaces the game's zoom steps (the wheel arrives there only
when no menu took it), watches the mouse for the middle-button drag, and
scales the scroll offset.

The same runtime serves two other tools. They run headless: the game starts
on a hidden desktop of its own, so no window appears and your focus stays where
it is, and it ends as soon as the tool has what it came for.

- `mw walkable <map> --native` reads the game's pathfinding grid at logic
  frame 10 (about 7 seconds; see [the viewer](viewer.md#walkable-areas)).
- `mw capture <map> --shot NAME X Y HEIGHT [--shot ...] [--graphics High]`
  saves screenshots rendered by the game, HUD included, into
  `local/renders/game/<map>/` (about 10 seconds for a few shots). The camera
  looks at the ground at X, Y from HEIGHT (the game's own camera; 300 is its
  usual zoom). The camera DLL above
  ([native/ingame/ingame.cpp](../src/mapworkshop/native/ingame/ingame.cpp))
  places the camera and copies the frame. Use it for what the renderer does not show, such as the water
  reflections at High. `--show` runs it in a visible window instead.
  `--at FRAME` (one per `--shot`, rising) holds each shot until the game's
  logic reaches that frame, about 5 per second of game time, to photograph
  a scripted scenario as it plays out; `--timeout` gives a long one time.

Direct3D 9 does not render on a desktop that is not shown, so headless runs
start `local/runtime/game-headless/`: hard links to the runtime's files plus
the `d3d9.dll` of [DXVK](https://github.com/doitsujin/dxvk), which runs
Direct3D 9 on Vulkan. The first headless run downloads that DXVK release
(18 MB) and checks it against its published SHA-256. Its frames match native
Direct3D 9 to about 2 levels in 255 on average, at Medium and at High with
water reflections; test games and `--show` keep native Direct3D 9. A
`dxvk.conf` there turns DXVK's graphics pipeline libraries off: with them the
loading screen waited on shader compilation, about 5 seconds per start.

### Faster map loading

Most of a map's loading time is the game building its terrain textures: for
each one it composites the terrain on the CPU, then Microsoft's D3DX library
compresses it to DXT1 and builds its mipmaps, one texture after another on one
core (about 8.5 of 10 seconds on Brightwater Fold at Medium; 1,156 textures).
Every runtime start loads
[loading.cpp](https://github.com/NotNBR/bfme2-map-quickload/blob/main/loading.cpp) (the `native/loading` submodule)
into the game, which hands those two D3DX calls to worker threads (one fewer
than the processor count, up to 15) while the map loads: each texture gets the
same calls with the same input, on a CPU-only staging copy made on a Direct3D
device of the DLL's own (multithreaded, on a window that is never shown, so the
workers never touch the game's device, which is not thread-safe), and the
game's main thread copies the finished textures in; the launcher waits for the last ones
when the new-game pass ends, before the first frame. The terrain comes out the
same: screenshots with and without it differ only where things move (water,
trees, the HUD). Any other caller, a texture outside Direct3D's managed pool,
or the game after loading gets the game's own synchronous calls.

| Brightwater Fold, Medium | Gameplay after | Three screenshots |
| --- | --- | --- |
| Before (title logo, one core) | 17.0 s (headless 22.5 s) | about 30 s |
| Without the title logo | 12.2 s | 20.7 s |
| With loading.dll as well | 4.5 s | 9.0 s |

Larger maps gain more. The Greywater Marches (1,350 x 900 cells, 5,340
terrain textures) reaches gameplay in 9.2 s instead of 49 s (headless 11 s),
and two screenshots take 13 s instead of 54.

`runtime.start(..., fast=False)` loads the map as the game alone does, for
comparisons. The rest of the load (about 2 s to the engine, 2 s of map on
Brightwater Fold) stays on the main thread.

### In your normal game

`mw patch install` puts the same faster loading into your BFME2 folder, for
every map and every game you start there, skirmish or multiplayer:

```
mw patch            # status: not installed, installed, outdated or foreign
mw patch install    # copy dinput8.dll into the game folder
mw patch remove     # take it out again
```

The patch is its own public project,
[bfme2-map-quickload](https://github.com/NotNBR/bfme2-map-quickload) (players
can download `dinput8.dll` from its releases without this toolkit), and
`src/mapworkshop/native/loading/` is that repository as a submodule: its
`loading.cpp` builds both `bin/loading.dll`, which test games load, and
`bin/dinput8.dll`, which `mw patch` installs. The game imports
DirectInput from `dinput8.dll` and finds this copy before Windows' own, which
it forwards to. Without a launcher, the DLL works out the end of each load
itself: it defers while the game shows its loading screen and finishes the
terrain textures in the tactical view's first update after it, before the map
is drawn. It also skips the five seconds of title logo after loading, by
setting the 5000 milliseconds of that wait to 0 in memory, so the fade-in
after it still runs. Brightwater Fold reaches gameplay 4.5 s after the start,
the Greywater Marches 9.3 s.

- It works only with BFME2 1.06 (`install` checks `game.dat`); in any other
  version, or any other program that loads it, it only forwards DirectInput.
- It changes how fast textures are built, not what the game simulates, so it
  should not affect multiplayer; that is untested.
- `install` never replaces a `dinput8.dll` that is not this patch (another
  mod's), and `remove` never deletes one. A folder in Program Files needs an
  administrator prompt.
- The runtime does not copy it: test games load `loading.dll` themselves.

With `mw play --normal-game`, or when the game is not BFME2 1.06, the build
goes into the game's user maps folder
(`%APPDATA%\My Battle for Middle-earth(tm) II Files\Maps`) and BFME2 starts at
its menu; pick the map under Skirmish. `mw build --install` copies it there
too.

Older projects with `build.py` and `main()` read their output folders from
module globals the pipeline sets: `OUT` (the build's folder), `CHECK` (its
checkpoints) and `TARGET` (where the map goes). Without a `b`, they get
their map.toml settings with `PROJECT = here(__file__)` (`mapworkshop.project`).

## Editing a single map file

For hand edits of an existing `.map` (a stock map, or a build to refine in
WorldBuilder), `mw workspace` keeps an isolated copy with checkpoints:

1. `inspect` measures a map and validates its terrain and texture references.
2. `catalog` returns the exact texture and object names already in it.
3. `checkout` makes an editable copy in `local/workspaces/<name>/`, with its
   sidecar files.
4. Save and close the map in WorldBuilder before file edits; an unsaved document
   could later overwrite them. `status` gives the saved file's SHA-256.
5. `apply` takes a seeded JSON recipe and that SHA-256. It validates the whole
   result before replacing the working file and keeps the before and after maps,
   the recipe, a chunk diff and a checkpoint. Applying a recipe twice is refused.
6. `preview` draws a quick heights, texture categories and objects diagnostic.
7. Open the working map in WorldBuilder, refine, save, then `checkpoint`.
8. `diff` shows exactly what the editor changed: the changed sections, and
   (`changes`) the same readable lines as `mw diff`.

```powershell
$map = 'local/game/maps/map wor ithilien/map wor ithilien.map'
mw workspace inspect $map
mw workspace catalog $map
mw workspace checkout $map ithilien-lab
mw workspace status ithilien-lab
mw workspace apply ithilien-lab maps/ithilien_frontier/authoring-demo.json --expect-sha <file_sha256>
mw workspace handoff ithilien-lab
mw workspace checkpoint ithilien-lab --note 'Saved and visually checked in WorldBuilder'
mw workspace diff <checkpoint.map> <working.map>
```

Checkpoint notes are descriptions, not proof that an editor or game check
happened; `status` leaves those gates unverified. There is no destructive
restore; branch a checkpoint with `checkout`.

### Recipe operations

Positions, radii and spacing are map units; angles are degrees; heights are
map units.

- `raise`: `x`, `y`, `radius`, `amount`; a smooth radial falloff, up or down.
- `flatten`: `x`, `y`, `radius`, `height`, optional `strength` (0..1).
- `paint`: `x`, `y`, `radius`, `texture` from the map's catalog. A bulk base
  coat; edges need WorldBuilder's blend brush.
- `scatter`: `template`, `count`, `rect: [x0,y0,x1,y1]`, `spacing`, `max_slope`.
  Uses existing unnamed scenery as a prototype and checks bounds, painted
  impassability, slope, exclusions and spacing.
- `place`: one existing unnamed landmark template at `x`, `y`, optional
  `angle_degrees`, `spacing`, `max_slope`, with a fresh `uniqueID`.

Recipes have `schema: 1`, a unique lowercase `id`, `seed`, `operations` and
optional `exclude_rects` that protect bases, lanes and crossings. Too few valid
positions abort the whole transaction. Water, scripts, teams, cameras and
starts survive unchanged.

`mw workspace plan-size MAP --area-factor 3` proposes playable dimensions for a
map of a given area at the same proportions (a proposal, not a supported-size
claim).

## Format references

The [mapping reference](reference/mapping/README.md) holds the measured file
layouts, rules and open questions. Layouts were cross-checked against
[OpenSAGE's map parsers](https://github.com/OpenSAGE/OpenSAGE/tree/master/src/OpenSage.Game/Data/Map);
see [third-party notices](reference/licenses/THIRD_PARTY.md).
