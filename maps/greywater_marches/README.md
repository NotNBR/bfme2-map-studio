# The Greywater Marches

A large six-player skirmish map, 13,500 × 9,000 world units, built from the supplied 3:2 heightmap. Six spacious construction areas sit in rolling grassland between branching rivers and ridged mountain ranges. Nine native stone bridges cross natural narrow reaches. The layout is balanced by walking distance for both free-for-all and 3v3 (north 1–3 against south 4–6).

```
mw build greywater-marches     build it
mw view greywater-marches      look at it in the viewer
mw play greywater-marches      install it into the game and start BFME2
```

`map.py` builds the terrain, textures, water, sky and lighting; `scenery.py` places the objects. See [the viewer](../../docs/viewer.md) for previews and marks.

## Layout and fairness

Distances below are walking distances over the passable ground and bridge decks (see [mapkit.strategy](../../src/mapworkshop/mapkit/checks/strategy.py)).

- **Starts.** Every base is 5,100–5,180 from its nearest opponent, so no free-for-all player is rushed sooner than another. The layout is close to point-symmetric (1↔4, 2↔5, 3↔6). In 3v3 the nearest enemies pair up the same way: 1 and 6 at 6,550, 2 and 5 at 7,450, 3 and 4 at 6,250. The centre bases sit furthest from the front.
- **Bridges.** Six single spans and three island hops. The east hop and the eastern bend connect base 3 to base 4 across the strip between the two eastern channels. Two southeast hops connect bases 4 and 5 by way of the river island, mirroring the 1–2 and 3–4 links in the north. The old upper-west and lower-east bridges were removed because they added no useful route.
- **Outposts.** Each player has an outpost about 2,400 from their base and at least 1,000 closer to them than to anyone else, so it is an expansion rather than part of the base. A seventh, contested outpost sits in the central meadow, 3,700 from bases 2 and 5.
- **Warg lairs.** One lair sits roughly halfway on the walking route between each pair of neighbouring bases, within about 400 of even for both.
- Flat home ground differs, and corner bases have more room behind them, but even the smallest base has over 6 million square units of flat ground of its own within 2,500.

## Terrain

- **Rivers.** The water plane is at 145. Banks ease to the waterline over a 55–280 unit band that varies along the river, with occasional short earth banks. A shallow shelf leads into a channel about 40 units deep, so the game's transparent water edge shows sloping riverbed. Inland hollows away from the rivers are lifted so only the channels hold water.
- **Mountains.** The reference's ranges are raised with domain-warped ridged noise. Height grows towards each range's core and with the size of the massif: the large edge ranges peak near 760, while isolated hills become rounded grassy knolls. A light talus pass removes spikes without rounding the crests.
- **Edges.** A rim of rough hills of varying width frames the playable edge, so the land does not stop at a cut. River mouths, bases and bridge reaches stay open.
- **Grading.** Bases are flat across a 350-unit radius and blend into the land over about 800 units. Bridge abutments and the scour below each deck are oval and feathered. A final talus pass relaxes walls left near the water.

## Materials

Thirteen native textures, each declared at its real size (the game skips texture classes declared larger than their file). Edges use diagonal and long-diagonal blends as well as straight ones.

- Meadows mix four grasses at several scales, with darker grass on damp lowland and small worn patches.
- Gravel, scree and rock fan out from exposed slopes of the large ranges, broken up by noise; high ground carries broken rock, crags, scree shelves, alpine grass and snow fields.
- Shores run from a thin line of wet sand through damp earth with pebble patches to grass; the riverbed is dark silt and gravel.
- Worn tracks meander between the bases, outposts, lairs and bridges.

## Scenery

About 9,000 objects:

- Woodland groves with dense stands and open glades (2,800 trees, deciduous and banyan in valleys, evergreens towards the foothills), parkland copses on the open meadows, and pine belts on the large ranges below a noisy treeline.
- Shrub clumps and grass drifts across the meadows; rushes along gentle waterlines.
- Boulders on rock aprons and steep banks, stones in the shallows.
- Farmsteads around the outposts (haystacks, tents, fence runs, a fire pit) and bones, skull poles and dead trees around the warg lairs, each on a worn clearing.
- Five landmark ruins on hill shoulders.

Lighting is a warm afternoon sun with a cool sky fill. The minimap is rendered from the terrain textures with the headless renderer (the plan colours are used when no GPU is available).

Weather presets ([mapkit.weather](../../src/mapworkshop/mapkit/weather.py)): `clear`, `haze`, `rain`, `snow` and `dusk`, set by `weather` in [map.toml](map.toml). Build a variant without changing it with `GREYWATER_WEATHER=rain mw build greywater-marches`. The WorldInfo `weather` value only picks the weather sound and lightning; the look comes from the map.ini fog and falling particles and the lighting. Fog distances are measured from the camera: the retail 600–1,800 fogs this map's wide views completely, so fully fogged optimized trees turn into flat fog-coloured silhouettes. The presets start the fog beyond the playing view, and drop rain or snow from a 1,600-unit box so it falls near the camera.

## Checks

Each build verifies that all six starts, the outposts, lairs and bridges share one connected walkable area (a conservative terrain-plus-footprint grid, separate from native movement tests), that the construction areas are flat, and that placed templates exist in the installed INIs. It also fails if the nearest-opponent distances differ by more than 400 or an own outpost is less than 1,000 safer for its owner; the figures are recorded under `strategy` in `build.json`. For a territory map and per-site detail, run `python -m mapworkshop.mapkit.checks.strategy --map <map> --out DIR --teams 1,2,3/4,5,6`; it writes `strategy.json` and `strategy.png`.

Not all vegetation is drawn in game. BFME2 keeps the first 1,200 trees and 2,000 shrubs in map order and drops the rest; this map places about 5,200 trees and 3,200 shrubs, so the woodland groves placed first appear in game while later pine belts, tor trees and copses do not. Headless previews show the full set.

[mapkit.vegetation](../../src/mapworkshop/mapkit/vegetation.py) can move the overflow to map-local `GW_` templates in `map.ini` that draw the same models through `W3DModelDraw` (`VEGETATION_OVERFLOW` in map.py). It is off: with it, the game crashed while loading the map (logic frame 0, an empty "Game crash" dialog, no crash report). Probably the cause: the game hangs loading a map whose map.ini adds new object types, while changing its own objects works ([what a map.ini may define](../../docs/game/water.md#what-a-mapini-may-define)); the build now lists such blocks.

Authoring follows [designing maps](../../docs/guide/designing-maps.md), [heightmap conventions](../eight_kingdoms/heightmap.md), [terrain records](../../docs/game/terrain-textures.md) and [native bridge evidence](../../docs/game/roads-and-bridges.md). Reference images are copied without alteration.
