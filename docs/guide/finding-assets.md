# Finding objects, textures and effects

A map places the game's own objects and paints its own textures, by name. Find
a name with `mw find`, learn what the game says about it with `mw item --info`,
and look at the candidates with `mw items` before choosing.

## Searching: `mw find`

`mw find` searches the game's object templates by what they are rather than by
name alone ([render/catalog.py](../../src/mapworkshop/render/catalog.py)):

```powershell
mw find stone bridge                        # every word must match name, type, region, material or variant
mw find --type tree --region shire --used   # filters; --used: only what the stock maps place
mw find snow ruin --size large              # footprint: small <10, medium <40, large <120, huge (map units)
mw find --material stone --variant ruined   # material and variant filters
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
gameplay, faction, creeps, sound, system, obsolete), `--limit` shows more than
25. `--json` prints the full entries.

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
defence, economy, fortress); `mw item NAME --info` says which: its INI file
and line, KindOf, footprint, effects and the stock maps that place it. Every
build lists the same for the objects it placed
([builds](projects-and-builds.md#builds)).

## Looking: `mw item` and `mw items`

`mw item` renders one object template on its own; `mw items` puts any number
of them into one labelled collage. Each stands on a plain background (white,
`--background transparent` or `#rrggbb`) with a soft ground shadow (`--no-shadow`),
drawn by the workshop's renderer, so models, materials and textures are those
of the map renders.

```powershell
mw item GenericTreeBridge                              # three-quarter view, framed to the model
mw item GenericTreeBridge --heading 90 --elevation 20 --rotation 45
mw item ShireGeneric03 --top                           # straight down: the footprint
mw items "*bridge*"                                    # every template with "bridge" in its name
mw items ShireGeneric01 CBHobbitBldg01 --views 3q,side,top
mw items --from-map bramble-hollow --layer Hamlet      # what a map places, most used first
```

Patterns are template names or case-insensitive wildcards over the game's
templates that have a model. Views: `3q` (default), `front`, `back`, `left`,
`right`, `side`, `top`, or `HEADING/ELEVATION` such as `135/20`; several views
give one row per object. `--heading` and `--elevation` change the `3q` view,
`--rotation` turns the object itself, `--distance` moves the camera;
`--columns` and `--tile` (pixels, 384) lay out the collage.

Each image is cropped to the object and its shadow and fills its tile, so a
scale bar in the corner gives the size (map units at the object's centre;
exact in top views). Each tile is labelled with the template and its size in
map units (width x depth x height of the model as placed). Images go to
`local/renders/items/` (or `--out`), each with a JSON file listing every
object's model, scale and size, and the templates left out and why. About 60
bridges take 11 seconds.

## Turning a building to face the right way

Models don't agree on which side is their front, and many have doors on more
than one side, so look before setting a building's angle:

```powershell
mw items CBHobbitBldg01 --views 0/40,90/40,180/40,270/40
```

shows its local -y, -x, +y and +x sides, in that order. On a map, angles are
radians, counter-clockwise, and at angle 0 a model's local +y points north.
Write in the code which side you chose as its front.

The named views are camera positions around the object at rotation 0, not the
model's own sides: `front` (heading 0) shows its local -y side, `back` its +y
side, `left` (heading 270) its +x side and `right`/`side` its -x side. They
look from 15 degrees up, which leaves the side away from the sun dark; the
four views at 40 degrees above show all four sides more clearly.

## Measuring: outlines, footprints and positions

To place something against an object's real edges, such as foam against a
bridge's piers or a path along a wall, measure the model rather than a
render ([render/footprint.py](../../src/mapworkshop/render/footprint.py)):

```powershell
mw item GondorIthilienBridge2 --section -11      # the model cut 11 below its origin: what is solid there
mw item CBHobbitBldg01 --footprint               # the ground it covers seen from above
mw item GondorIthilienBridge2 --footprint --high -5   # only what lies below -5
mw item GondorIthilienBridge2 --bones            # its named points
mw where hollin-dales bridge --section 165       # where it stands on a map, cut at the map height 165
mw where hollin-dales Player_1_Start             # a waypoint
mw where hollin-dales --layer BridgeWater --near 5455,3765,300
```

`mw item` prints in the object's own frame: map units, x east and y north at
angle 0, z up from its origin. `mw where` finds the objects placed on a map
whose template, object name or waypoint name matches (a wildcard such as
`*bridge*`, else any part of the name), and prints each one's position, the
ground there, its origin's height and its angle; with `--section`,
`--footprint` or `--bones` it prints those on the map, in map coordinates,
and `--section Z` and `--low`/`--high` take map heights (the water's, say).
`--json` prints everything for code.

Outlines are closed polygons, counter-clockwise round solid ground and
clockwise round a hole. They are traced on a 1-unit grid (`--step`), so an
edge is accurate to about one unit and straight edges come out straight.
`--section` keeps what is solid at that height: closed parts of the model,
overlapping ones joined; a lone wall plane has no inside and drops out.
`--footprint` keeps everything the model covers from above, overhangs too.

Neither is what blocks units: that is the template's `Geometry`, a box or
cylinder that `mw item NAME --info` prints. A map's own code calls the same
functions: `footprint.section(template, height)`, `footprint.footprint(...)`,
`footprint.bones(template)`, and `footprint.to_world(points, x, y, angle)` to
put them where an object stands.
