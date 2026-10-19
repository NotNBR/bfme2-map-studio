# The toolkit

What a `map.py` builds with, one entry per module of `src/mapworkshop/`. Each
module's docstring is its documentation: open it for the functions, their
arguments and what is known about the game behind them. This page says which
module to open.

Positions are map units, 10 per terrain cell: x runs east and y north from the
playable area's south-west corner, the same coordinates as the viewer's marks.
Map angles are radians, counter-clockwise; at angle 0 a model's local +y points
north. Template and texture names are the game's: `b.assets.templates` lists
the objects, `local/game/data/ini/terrain.ini` the textures, and `mw find`
searches both ([finding assets](finding-assets.md)).

## Building a map: `mapkit`

| Module | For |
|---|---|
| [blank](../../src/mapworkshop/mapkit/blank.py) | the native map document: `create`, `set_heights`, `set_materials` (texture indices per cell, with corner blends), `add_object`, `starts`, `terrain_cell_sizes`, `water_plane` (one water level for the map), `set_world` (WorldInfo values by name, e.g. `cameraMaxHeight`) |
| [earth](../../src/mapworkshop/mapkit/earth.py), [relief](../../src/mapworkshop/mapkit/relief.py) | landforms: `fbm` noise, `thermal_erosion`; `distance_to`, smoothing (relief also holds Ithilien Frontier's own landforms) |
| [lines](../../src/mapworkshop/mapkit/lines.py) | distance from every terrain sample to authored lines (`polyline_distance` with the arc length along the line, `nearest` of several). Pass `reach` for fields only compared against short distances, such as roads and lanes: it measures each segment only against the samples near it and is far faster on long lines. Beyond `reach` the distance is infinite, so choose it above the largest distance the field is compared against (the maps use 500 for comparisons up to about 200) |
| [variety](../../src/mapworkshop/mapkit/variety.py) | `spot_random(seed, template, x, y)`, an object's own random numbers for its size and rotation. Drawn from one shared stream instead, every object after an added or skipped placement would get a new size, and a small edit would change the whole map (`mw diff` shows it) |
| [roads](../../src/mapworkshop/mapkit/roads.py) | road segment pairs ([roads and bridges](../game/roads-and-bridges.md)) |
| [rivers](../../src/mapworkshop/mapkit/rivers.py) | a river's flowing surface over standing water (`add_river` along a line, `cross_sections`, `bank_width`) and shore waves (`add_shore_waves`) ([rivers and waves](../game/rivers-and-waves.md)). Water runs downhill only in flat steps: [water](../game/water.md) |
| [cliffs](../../src/mapworkshop/mapkit/cliffs.py) | cliff texture mapping, so steep faces do not stretch their texture into streaks: `set_materials(..., cliffs=steep_cells(heights))`. One texture per map, and it goes last in the palette ([cliff mapping](../game/terrain-textures.md#cliff-mapping)) |
| [bridges](../../src/mapworkshop/mapkit/bridges.py) | bridges the game spans between two points at any length (`add_bridge`; `bridge_type` for a map's own type), walkable; only models with left/span/right pieces work, which it checks ([spanned bridges](../game/roads-and-bridges.md#spanned-bridges)) |
| [walls](../../src/mapworkshop/mapkit/walls.py) | the game's chainable walls (`wall_line` lays segments, hubs, gates and towers along a path for a faction's kit; `place_wall` adds them with an owner; `ground_rise` finds pieces on uneven ground) and castle sites (`castle_site`, `castle_layout`) ([walls and castles](../game/walls-and-castles.md)) |
| [sites](../../src/mapworkshop/mapkit/sites.py) | outposts, inns, signal fires and shipwrights with their capture flags (`neutral_site`, `shipwright`), creep lairs (`creep_lair`), skirmish Gollum's spawn points (`gollum_spawns`), `spread` for evenly spaced points ([neutral sites](../game/neutral-sites.md)) |
| [ambient](../../src/mapworkshop/mapkit/ambient.py) | a map's sound bed and emitters by kind of place (`ambient`, palettes per setting) |
| [vegetation](../../src/mapworkshop/mapkit/vegetation.py) | keeps trees and shrubs past the game's 1,200 / 2,000 buffer limits visible as full models (crashes the game as it stands: see the Greywater Marches [README](../../maps/greywater_marches/README.md#checks)) |
| [weather](../../src/mapworkshop/mapkit/weather.py) | weather presets with the map's own sun and fill (`apply_weather`), sky domes (`add_sky`) and the map.ini Weather block (`ini_block`) |
| [cinematics](../../src/mapworkshop/mapkit/cinematics.py) | films a map's scripts play: camera shots (`Film.shot`, `orbit`, `move`) as the game's camera animations, each key with its own field of view and roll, the interface hidden, each shot on a timer (`Film.install`) ([cinematics](../game/scripts.md#cinematics)) |
| [script_writer](../../src/mapworkshop/mapkit/script_writer.py) | map scripts from the game's own catalogue of conditions and actions (`Writer(m).operation`, `.script`, `.install`), each checked against its argument signature ([map scripts](../game/scripts.md)) |
| [properties](../../src/mapworkshop/mapkit/properties.py) | the map-wide settings a `map.toml` `[properties]` table and the viewer's Properties window set ([projects](projects-and-builds.md#map-properties)) |
| [cache](../../src/mapworkshop/mapkit/cache.py) | checks a build's player starts (2 to 8, consecutive) the way the game's map cache counts them |
| [memo](../../src/mapworkshop/mapkit/memo.py) | reuse slow calculations across builds: `pure` for array functions, `stage` through `b.cached` for project stages ([reusing earlier results](projects-and-builds.md#reusing-earlier-results)) |

## Checking a map

| Module | For |
|---|---|
| [pathing](../../src/mapworkshop/mapkit/pathing.py), [walkable](../../src/mapworkshop/mapkit/walkable.py) | local walkability estimates from terrain, water, object footprints and walking meshes, without starting the game (`mw walkable`, the viewer's key **7**, `mw render --walkable`) |
| [checks.strategy](../../src/mapworkshop/mapkit/checks/strategy.py) | walking distances and fairness between players, and from the bases to the neutral sites and lairs (`mw sites`); the maps call it to refuse an unfair build |
| [checks.analyze](../../src/mapworkshop/mapkit/checks/analyze.py) | every record of a `.map`, decoded and checked: `python -m mapworkshop.mapkit.checks.analyze FILE.map --out FILE.json` |
| [checks.coverage](../../src/mapworkshop/mapkit/checks/coverage.py), [checks.terrain_audit](../../src/mapworkshop/mapkit/checks/terrain_audit.py) | surveys of a whole archive (`Maps.big`): which sections and terrain records it holds ([format tools](../format/tools.md)) |
| [checks.lighting_check](../../src/mapworkshop/mapkit/checks/lighting_check.py) | reads the lighting arrays from the running game's memory; written for bfme-workshop's host, nothing here calls it yet |
| [mapdiff](../../src/mapworkshop/mapkit/mapdiff.py) | what changed between two maps (`mw diff`) |
| [graphics](../../src/mapworkshop/mapkit/graphics.py) | terrain heightmaps, slopes, shaded plans with contours, scenery placement and map comparisons (`mw graphics`, [map graphics](map-graphics.md)) |
| [workspace](../../src/mapworkshop/mapkit/workspace.py), [author](../../src/mapworkshop/mapkit/author.py) | hand edits of one `.map` file and their recipes (`mw workspace`, [hand-editing](hand-editing.md)) |

## The files themselves: `formats`

| Module | For |
|---|---|
| [sections](../../src/mapworkshop/formats/sections.py) | every section of a map as Python values: `read(m, 'NamedCameras')`, change them, `write(m, ...)`; `Map.objects()` and `Map.set_objects()` do the same for objects |
| [map](../../src/mapworkshop/formats/map.py), [map_archive](../../src/mapworkshop/formats/map_archive.py) | the CkMp container and its EAR/RefPack compression |
| [terrain](../../src/mapworkshop/formats/terrain.py), [water](../../src/mapworkshop/formats/water.py), [lighting](../../src/mapworkshop/formats/lighting.py), [scripts](../../src/mapworkshop/formats/scripts.py), [castles](../../src/mapworkshop/formats/castles.py) | single sections with more than a layout to them |
| [big](../../src/mapworkshop/formats/big.py), [w3d](../../src/mapworkshop/formats/w3d.py), [fxo](../../src/mapworkshop/formats/fxo.py) | the game's archives, models and compiled effects (`python -m mapworkshop.formats.fxo FILE.fxo --disassemble`) |

The [map-file specification](../format/README.md) describes the bytes.

## The game's files: `assets`

Below `mapkit` and `render`, which both read the installed game through it.

| Module | For |
|---|---|
| [library](../../src/mapworkshop/assets/library.py) | `GameAssets`: the game's archives and loose files in its override order, its object templates (`templates`, `template_model`, a unit's idle animation), INIs, textures and models; `b.assets` in a build |
| [models](../../src/mapworkshop/assets/models.py) | W3D models made ready to draw or measure (`ModelCache.load`, `load_tree`): meshes on their bones, materials and shader states |
| [ini](../../src/mapworkshop/assets/ini.py) | the one INI reader: a template with its parents and their #include files (`bodies`), its own top-level values (`inherited`; a module's Scale or Shadow is not the object's), the statements and the blocks they lie in (`statements`, `in_module`); `=` optional and `;`/`//` comments, as the game reads them |

## Around the build

| Module | For |
|---|---|
| [project](../../src/mapworkshop/project.py) | the projects in `maps/` and the build pipeline ([projects and builds](projects-and-builds.md)) |
| [game](../../src/mapworkshop/game.py) | the BFME2 installation: find it, extract its data, install maps (`mw setup`) |
| [render](../../src/mapworkshop/render/) | the renderer (`mw render`, the viewer), the asset catalogue (`catalog`: `mw find`), single objects (`items`: `mw item`, `mw items`) and their measured outlines, footprints and named points, on their own or where a map places them (`footprint`: `mw item --section`, `mw where`, [measuring](finding-assets.md#measuring-outlines-footprints-and-positions)); [rendering](rendering.md), and [the renderer](../game/renderer/README.md) for what it reproduces of the game |
| [native](../../src/mapworkshop/native/) | the game itself: test games, its pathfinding grid, screenshots, the loading patch ([testing in-game](testing-in-game.md), [the runtime](../game/runtime.md)) |
| [viewer](../../src/mapworkshop/viewer/) | the viewer ([the viewer](../viewer.md)) |
| [video](../../src/mapworkshop/video/) | FFmpeg encoding for the videos in `misc/` |

## Heightmaps

A map can take its relief from an image: the Greywater Marches reads
`references/heightmap.png` in [map.py](../../maps/greywater_marches/map.py),
Eight Kingdoms a grayscale illustration ([its pipeline](../../maps/eight_kingdoms/heightmap.md)).
There is no general importer; read the image with PIL, scale it to the grid
and pass the heights to `set_heights`. Heights are stored as
`round(z / 0.0390625)` in 16 bits, 0 to 2,559.96 map units.
