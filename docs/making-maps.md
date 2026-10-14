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
- `mapkit.bridges`: bridges the game spans between two points at any length
  (`add_bridge`; `bridge_type` for a map's own type), walkable; only models
  with left/span/right pieces work, which it checks
  ([spanned bridges](reference/mapping/navigation/roads-and-bridges.md#spanned-bridges)).
- `mapkit.walls`: the game's chainable walls (`wall_line` lays segments, hubs,
  gates and towers along a path for a faction's kit; `place_wall` adds them
  with an owner; `ground_rise` finds pieces on uneven ground) and castle sites
  (`castle_site`, a CastleFlag that unpacks the capturing faction's castle;
  `castle_layout` reads one) ([walls and castles](reference/mapping/navigation/walls-and-castles.md)).
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
objects, `local/game/data/ini/terrain.ini` the textures.

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
- Builds are reproducible: the same source gives the same map, byte for byte.
  (The process runs with a fixed `PYTHONHASHSEED`, because some builds iterate
  sets of names.)

## Testing in-game

`mw play <map>` (the viewer's **Test In-Game**) starts BFME2 straight in a
skirmish on the current build, without going through the menus. It uses
[bfme-workshop](https://github.com/NotNBR/bfme-workshop)'s isolated runtime
(a checkout next to this one, or `mw config bfme_workshop <folder>`), as
`mw walkable --native` does: the build is copied into that runtime's mod and
registered in its map cache, and the game opens in a 1600 x 1200 window, you
against an easy AI, with bfme-workshop's strategic camera. The runtime has its
own profile, so your normal game, its options and saved games are untouched,
and it needs no administrator rights. The launcher log is in
`local/cache/play/<map>.log`; closing the game ends the launcher.

Without a prepared bfme-workshop runtime, or with `mw play --normal-game`, the
build goes into the game's user maps folder
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
