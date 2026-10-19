# Projects and builds

A map is a project folder in [maps/](../../maps): a `map.toml` that names it and
a `map.py` that builds it. The workshop runs the build, keeps every result and
shows it in the viewer.

```powershell
mw new "Misty Vale" --players 4 --size 600x600   # an empty, level map
mw dev misty-vale                                # build, open the viewer, rebuild on save
mw play misty-vale                               # test it in-game: a skirmish on it, straight away
```

`mw maps` lists the projects; [maps/README.md](../../maps/README.md) says what
each one is. For the design side (composition, landforms, materials, detail),
see [designing maps](designing-maps.md); for the building blocks a `map.py`
uses, [the toolkit](toolkit.md).

## A project

```
maps/misty_vale/
├── map.toml        id, title, native name, players, description, weather
├── map.py          def build(b): ...
├── references/     source images: heightmaps, sketches (optional)
└── README.md
```

`mw new "Misty Vale"` makes one (`--players`, `--size` in cells, `--id` for an
id other than the one made from the title). Its `map.py` makes a level grass
plane with the player starts, sky and lighting, and shows where heights,
textures and objects go.

For larger terrain studies, a project's `map.py` can call
`blank.create(..., experimental_large=True)`. This explicitly raises the
constructor's guard from 2,048 to 4,096 stored samples per axis, including
borders; each cell is 10 world units. The default and `mw new` size range
stay unchanged. The larger bound matches the document reader, not a verified
game limit. Build, render and check connectivity before relying on a larger
draft; native loading and performance require separate game verification.

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
for the build to read, as Eight Kingdoms does for its size and seed. A
`[play]` table seats `mw play`'s slots
([line-ups](testing-in-game.md#line-ups)).

### Map properties

A `[properties]` table sets map-wide properties over what the build writes;
the viewer's **Properties** window writes it
([mapkit/properties.py](../../src/mapworkshop/mapkit/properties.py) lists them):

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
| `b.save(m, ini='', minimap=None, fallback=None)` | write the map `m`, its `map.ini` text and the in-game minimap; without `minimap`, the minimap is rendered from above once the build is published, or is `fallback` (an image) without a GPU |
| `b.cached(fn, *args)` | `fn(*args)`, or its result from an earlier build when nothing it depends on has changed ([reusing earlier results](#reusing-earlier-results)) |
| `b.image(name, image)` | keep a plan or preview image (PIL) with this build |
| `b.report` | a dict saved as `report.json` with the build |
| `b.work` | this build's folder, for other files |
| `b.assets` | the game's assets: templates, INIs, textures, models (`render.assets.GameAssets`) |
| `b.args` | extra command-line arguments: `mw build crown -- --phase terrain` |

Most projects in `maps/` use `build(b)`; Bramble Hollow, Brightwater Fold
and the Hollin Dales are complete examples of a whole map. Four older ones
(Ashen March, Crown of Cardolan, Eight Kingdoms, Ithilien Frontier) have a
`build.py` with `main()`, which the pipeline runs the same way. They read their
output folders from module globals the pipeline sets: `OUT` (the build's
folder), `CHECK` (its checkpoints) and `TARGET` (where the map goes). Without a
`b`, they get their map.toml settings with `PROJECT = here(__file__)`
(`mapworkshop.project`). Start new maps with `build(b)`.

## Builds

`mw build [MAP]` (and **Build** in the viewer, and `mw dev`) builds in a fresh
Python process. `mw dev` rebuilds on every save with the viewer open
(`--no-view` without it).

- The build runs in its own folder, `local/history/<id>/<time>/`, with its plans,
  `report.json` and `build.json` (time, source hash, git commit, map hash).
- Only a build that succeeds replaces `local/build/<id>/`: the `.map`, `map.ini`,
  minimap and `preview.png`. An open viewer then reloads it. A failed build
  leaves the previous one in place. The map is published as soon as it is
  written: the minimap, the comparison and the checks below follow while the
  viewer reloads (the previous build's minimap is kept when the map is unchanged).
- The last five builds are kept; `mw history [MAP]` lists them.
- Each build ends with what it changed since the previous one, also kept in its
  `build.json` (`changes`): heights and repainted textures with their area,
  passability, objects added, removed, moved or changed (by layer, fewest first),
  every other section by name and property, and `map.ini` lines. `mw diff [MAP]`
  shows it again; `mw diff MAP OTHER` compares any two maps (projects, stock maps
  or `.map` files), `--json` gives everything and `--limit` the detail lines
  per part. Objects are matched by template and position, so renumbered
  uniqueIDs are not changes ([mapkit/mapdiff.py](../../src/mapworkshop/mapkit/mapdiff.py)).
- It then lists placed templates to know about, with their count and layers,
  also in `build.json` (`template_concerns`): names the game doesn't define,
  obsolete, cinematic or spawned-only templates, and faction gameplay buildings
  that no player owns. They inform; the build still succeeds, and
  `mw item NAME --info` says more ([finding assets](finding-assets.md)).
- It also lists what the build's `map.ini` defines that the game will not take,
  also in `build.json` (`ini_concerns`): an `Object` block that adds an object
  type (the game hangs loading such a map; a `map.ini` may change the game's
  objects and add particle systems,
  [what a map.ini may define](../game/water.md#what-a-mapini-may-define)), and
  particle systems whose texture the game doesn't have.
- Builds are reproducible: the same source gives the same map, byte for byte.
  (The process runs with a fixed `PYTHONHASHSEED`, because some builds iterate
  sets of names.)

`mw build --install` also copies the build into the game's user maps folder;
[testing in-game](testing-in-game.md) covers `mw play`.

### Reusing earlier results

Because builds are reproducible, a calculation given the same inputs by the
same code gives the same result, so builds keep slow ones in `local/cache/memo/`
and reuse them ([mapkit/memo.py](../../src/mapworkshop/mapkit/memo.py)). The
map comes out byte for byte the same either way; the build says how many it reused.

- Toolkit functions of large arrays are reused when their arguments and their
  own module are unchanged: noise (`earth.fbm`), talus erosion, distances to
  lines (`lines.polyline_distance`) and walking distances
  (`checks.strategy.distance_field`). Noise over the terrain grid is almost
  always reused, even after an edit to the terrain.
- A project caches a stage of its own with `t = b.cached(terrain)`. It is reused
  while its arguments, the code it reaches (the functions and module-level values
  it names, followed through the project's files), the project's other files
  (references, heightmaps), the toolkit it can call (`formats`, `mapkit` and the
  modules they import) and the numpy and Pillow versions are unchanged. Greywater Marches,
  Bramble Hollow and Brightwater Fold cache their `terrain()`, so an edit to
  their objects skips it. Each call gets its own copy, so the build may change it.
- A cached stage must depend on nothing else: no game data, no files outside the
  project, nothing reached through an object other than its arguments. A stage
  that assigns module globals, or names something the key cannot describe, runs
  every build, with a note saying why.
- `mw build --no-cache` (and `mw dev --no-cache`) makes everything again and
  stores nothing. The cache keeps at most 3 GB, dropping the least recently
  used results first; deleting `local/cache/memo/` is always safe.

## Checking a build

| Command | Shows |
|---|---|
| `mw diff [MAP]` | what the last build changed (above) |
| `mw render --map MAP --view ...` | a picture from any camera ([rendering](rendering.md)) |
| `mw walkable [MAP]` | a local walkability estimate: areas cut off from every start (`--image` writes it as a PNG, `--json` lists them) |
| `mw rivers [MAP]` | which way each river strip flows, as compass runs (`--json`: every cross-section) |
| `mw sites [MAP]` | walking distances from the bases to the neutral sites and lairs (below) |
| `mw graphics --map FILE` | diagnostic plans: placement atlas, heights, slope, passability ([map graphics](map-graphics.md)) |
| `mw play MAP`, `mw capture MAP` | the game itself ([testing in-game](testing-in-game.md)) |

### Walkability

`mw walkable <map>` estimates where units can walk without starting the game
([mapkit/walkable.py](../../src/mapworkshop/mapkit/walkable.py)) and lists the
walkable areas no player start can reach, with their positions; the viewer
(key **7**) and `mw render --walkable` draw it. Terrain flags, water depth,
inherited object geometry and the models' walking meshes supply the estimate.
Bridge edges and connections are approximate; spawned fortresses, units,
scripts and dynamic gate and wall states are not simulated. Reachability
combines decks and ground in a top-down grid, so overpasses can join routes
that are separate in the game. It is an editing aid, not proof that a
particular unit can follow a route ([navigation](../game/navigation.md) has
what the game was measured to do).

`--native` reads the game's own grid from a short headless skirmish (about 7
seconds, [testing in the game](testing-in-game.md)) and reports it;
`--compare` compares the estimate against the last native capture without
launching anything. Native captures are tied to the map file's hash, so a
changed build needs a new one. Without `--native`, the command and the viewer
always use the local estimate.

### Neutral sites and walking distances

`mw sites <map>` measures how far each base walks to the others and to every
outpost, inn, signal fire, shipwright and creep lair
([mapkit/checks/strategy.py](../../src/mapworkshop/mapkit/checks/strategy.py)).
It prints three tables:

- **Sites:** each site with its nearest base, and how much nearer that base
  is than the next one.
- **Bases:** each base with its nearest enemy and its nearest site of each kind.
- **Per kind:** the least, median and most any base walks to its nearest site
  of that kind.

```
mw sites nanduhirion --teams 1-4/5-8                  # per team: whose each site is, and by how much
mw sites nanduhirion-v1 --teams 1-8/9-16 --bases 1150,8300 1200,5650 ...
mw sites nanduhirion --image local/renders/sites/nanduhirion.png
```

- `--teams` groups the bases. Each site then lists the nearest base of each
  team and the margin between the teams.
- `--bases X,Y ...` measures from those points instead of the starts, for a
  map laid out for more players than it seats.
- `--image` draws the ground nearest each base, with the sites and their
  margins.
- `--json` prints the full report.

To compare a stretched copy with its original, set each walk against the
same map's walk to the nearest enemy. Unit speeds stay the same, so the
absolute walks are what set a match's pace.

The distances come from the stored impassable plane on 20-unit cells,
with bridge decks added; they are not `mw walkable`'s estimate.
[What each site gives](../game/neutral-sites.md#what-each-site-gives) says
what the walks are for.

## Where things live

Everything the workshop writes stays in the ignored `local/` folder
([config.py](../../src/mapworkshop/config.py)):

```text
local/config.toml      settings: the BFME2 folder, the last opened map
local/game/            the game's INI and map trees, extracted by `mw setup`
local/build/<map>/     the latest build of each map project
local/history/<map>/   earlier builds, one folder per build
local/marks/           viewer marks, one file per map
local/renders/         renders and viewer screenshots
local/runtime/         the isolated copy of the game test games run in
local/openbfme/        OpenBFME for `mw play --godot`: its tools, build, game files and packed maps
local/workspaces/      hand-edit workspaces for single .map files
local/cache/           caches (the asset catalogue among them)
```

`mw config` prints the settings; `mw config KEY` one of them and
`mw config KEY VALUE` changes it (`game`, the BFME2 folder, which also runs the
setup; `last_map`, the map commands use when none is given; `test_game`, what
the viewer's **Test In-Game** starts: `original` or `openbfme`).

`profile` selects `bfme2` or `rotwk`; `rotwk` is the expansion folder. The ROTWK
profile puts the output folders above under `local/profiles/rotwk/`, while
`local/config.toml` and the map sources stay shared. Each `build.json` records
its profile. See [ROTWK setup](getting-started.md#rise-of-the-witch-king).
