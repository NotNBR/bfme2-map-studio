# Designing a map

A map develops like a painting: establish its composition, build large forms,
resolve secondary forms, then add selective detail and finish. At every stage
it should read as a coherent landscape at that stage's level of detail. This
page is the method; [projects and builds](projects-and-builds.md) and
[the toolkit](toolkit.md) are the means.

The maps in [maps/](../../maps/README.md) are worked examples. Bramble Hollow,
Brightwater Fold and the Hollin Dales are the most complete; the
[Brightwater Fold showcase](../../misc/studio_showcase/README.md) follows one
map from `mw new` to its last details in seven steps.

## The passes

| Pass | Painting | On the map | Review question |
|---|---|---|---|
| 0 Intention | canvas and brief | place, mood, players, what the terrain should offer | What experience should this place create? |
| 1 Composition | thumbnails | masses, voids, routes, a focal point; starts | Is the whole map interesting before any props exist? |
| 2 Large forms | block-in | broad heights and open lowlands | Can the landscape be understood in three or four shapes? |
| 3 Secondary forms | form and depth | ridges, saddles, valleys, water, crossings, routes | Do the landforms have volume, and do the routes work? |
| 4 Gameplay footprints | | bases, expansions, neutral sites, landmarks blocked in | Is a sparse match already worth playing, and fair? |
| 5 Materials and light | underpainting | a restrained texture palette, lighting, weather | Do surfaces explain the land instead of disguising it? |
| 6 Local scenes | focal detail | the landmark first, then supporting scenes | Where should the eye and the armies go? |
| 7 Fine detail | supporting detail | clusters, edges, paths, wear | Does detail reinforce the place and leave room to fight? |
| 8 Polish | finishing | seams, floating objects, the game's own view | Are the remaining rough edges distracting or obstructive? |

Use three scales deliberately: **whole-map composition**, **regional scenes**
and **ground-level detail**. Finish the decisions at the larger scale before
increasing detail at the smaller one, and revisit the larger scale whenever a
local edit changes the silhouette, drainage or route network. A weak route
sends you back to the forms; a weak composition, back to the studies.

## 0 Intention

Write a brief with a place, mood and physical story: why a road follows a
saddle, why a settlement sits on a terrace, why woodland collects on sheltered
slopes. Choose the number of players, the size and the decisions the terrain
should offer. Choose one dominant landmark and two or three supporting
regions; say what should stay open, and name a few things that would break
the theme. A skirmish battlefield and a scripted battle need different
starts, economy and scripts.

Put the brief in the module docstring of `map.py` and the facts in
`map.toml`. Bramble Hollow's docstring describes the valley, brook, hamlet and
the symmetry before any code; the Hollin Dales' describes the dales, the
gate-courts and the field, which is the composition in words.

Start from `mw new`: an empty, level plane at the intended size. Don't load,
enlarge, flatten or strip a stock map and call that a new composition; the
game's textures and objects are materials, not a landscape to inherit.

## 1 Composition

Sketch at least three alternatives in broad masses, not trees: high ground,
low ground, woodland, open ground, water and landmark, with starts and route
arrows. Choose one for its route choices, focal hierarchy and distribution of
open space; write down why the others lost. The Crown of Cardolan rejected a
central bottleneck (seven opponents would overload it) and isolated corner
forts (the centre would lose its purpose) for a centre with two circulation
routes.

Avoid equally spaced features everywhere, a lone central choke, mirrored
scenery without purpose, and a landmark whose only role is to fill a gap.
Symmetry helps fairness, but equivalent opportunities need not look
identical: Bramble Hollow, Brightwater Fold and the Hollin Dales are
point-symmetric in layout (`mirror` and `turned` in their `map.py`) while
their cliffs, woods and ruins are not.

Write the composition into the code as authored geometry: point lists for the
river, roads and ridges, start positions, landmark sites, as constants at the
top of `map.py` (`STARTS`, `UPSTREAM`, `ISLAND`, `DALES`, `GATES`). Every later
pass reads them, so moving a ford moves its banks, its road and its bridge.

## 2 Large forms

Sculpt a few broad masses from the plane: mountain shoulders, a ridge system,
a basin, a main valley and its terraces, with temporary simple materials.
Reserve the base areas and deployment spaces. No scatter yet. Look at the
heights in the viewer from low, oblique angles; a high peak at the edge does
not make a mostly flat interior interesting, and not every battle plain
should become rough ground.

Fields of distance to the authored lines (`mapkit.lines`) shape valleys and
banks; `mapkit.earth` adds warped fBm and thermal erosion; a reference image
can supply the relief, as the Greywater Marches' heightmap does. Blend bases
into the land over long, irregular shoulders: a radial flat mask with a short
falloff makes an artificial circular cliff bowl. Keep noise from erasing the
composition, and use a fixed seed.

Review the built terrain at the three scales above before adding detail.
Use [map graphics](map-graphics.md) to inspect elevations, slopes and contours,
and [rendered views](rendering.md) with `--no-objects` to see the land without
scenery. Compare the shape of each region and its transitions with the brief:
construction pads, open fields and mountain slopes have different purposes.
Keep the same views and measurement scales when comparing revisions.

## 3 Secondary forms, water and routes

Add saddles, spurs, gullies, river terraces and local shoulders that belong to
the large forms; reserve fine noise for late surface variation. Then the
water, the crossings and the routes:

- **Water is flat.** A standing water area has one height, and so does a river
  strip; water runs downhill only in flat steps, as pools and rapids, or as
  particle water ([water](../game/water.md)). Put the water plane below the
  ground and carve the channels into it.
- **Water deeper than 5 blocks units; height alone never does**
  ([navigation](../game/navigation.md)). A ford is a shelf at most 5 below the
  water (the maps use 2.5, `FORD_DEPTH`); a mountain is impassable only if
  something makes it so.
- **Bridges** carry units on their deck meshes: walkable object bridges, or
  bridges spanned between two points ([roads and bridges](../game/roads-and-bridges.md)).
  Bramble Hollow keeps the channel deep beside its footbridges so there is no
  ford round them.

Design roads around gradients and destinations: each critical route's purpose,
narrowest width, climb and fallback. `mw walkable` and the viewer's key **7**
show areas cut off from every start; it is a local estimate, not horde
movement, so check the crossings that matter in the game.

## 4 Gameplay footprints

Place the starts, expansion space, neutral sites (`mapkit.sites`: outposts,
inns, signal fires with their capture flags, creep lairs) and the places
where armies gather. Fairness is more than equal straight-line distances:
compare walking distance, exposure on the approach, usable building space and
retreat. `mw sites <map> --teams 1-4/5-8` lists each site's walking distance
from each team and the bases' walks to their nearest site of each kind
([neutral sites](projects-and-builds.md#neutral-sites-and-walking-distances)).
Measure it in the build and refuse an unfair result: Brightwater
Fold, Bramble Hollow and the Hollin Dales check walking distances with
`mapkit.checks.strategy` and fail the build when they differ too much; the
Greywater Marches allows 400.

Block in landmarks with a few representative objects and fit each site into
the terrain with a terrace, foundations, retaining slopes or rubble.
**Advance when** a sparse match is already worth playing (`mw play`) and the
landmark silhouettes help orient the player.

## 5 Materials and light

Choose a small palette (`PALETTE` in the maps) and paint large material zones
first, following slope, moisture, geology and use: exposed rock, grassy
shoulders, damp low ground, worn road and paving. Keep light and dark, warm
and cool readable at strategic distance, and add a secondary material only
where it explains a transition. `mw find --textures` finds textures by region
and type.

Don't cover open ground with noise-threshold material islands to hide tiling:
even similar colours read as camouflage when their edges are too dense. The
Ashen March's second revision was rejected for that
([its findings](../history/ashen-march-findings.md)); establish a continuous
base soil, then paint wear and rock where the scene calls for it. Map steep
faces with `mapkit.cliffs` so their texture does not streak.

Choose lighting and weather (`mapkit.weather`, `weather` in `map.toml`) to
support the theme while keeping slopes and units legible; judge lighting at
the detail level players use (Medium, as test games run).

## 6 Local scenes

Finish the main landmark first, then the supporting scenes. Give each a short
physical story: how a wall fell, how a path reaches an entrance, why rubble
collected there, which side of a ruin became overgrown. Align structures to
their site and vary damage deliberately; randomly rotated walls do not make a
believable settlement. Turn each building's door to its path: find its front by
looking ([finding assets](finding-assets.md#turning-a-building-to-face-the-right-way))
and record it, as the maps' `DOOR_SIDES` do. Brightwater Fold's hold and
Bramble Hollow's hamlet are examples.

Treat forests as shapes with cores, edges, clearings and approach views; vary
density by slope, shelter and ground. Place rocks as outcrops with related
fragments, and undergrowth at transitions rather than everywhere. Finish one
region to the intended quality before repeating its method elsewhere.

## 7 Fine detail

Add small rubble, roots, grasses, path wear, broken edges and shoreline
accents where players look, fight, move or recognize a place; keep quieter
areas quiet. Detail is a hierarchy of meaningful relationships, not an object
count.

Give each object its own random numbers (`mapkit.variety.spot_random`), so a
small edit doesn't reshuffle the map, and check placements against slope,
water, footprints and reserved space. Mind the game's limits: it draws only
the first 1,200 trees and 2,000 shrubs in map order
([objects and vegetation](../game/renderer/objects.md)), so place the trees
that matter first. Re-run the route checks after scenery is in.

## 8 Polish and the game's view

Review at three distances, tactical, transition and strategic, from every
start. Look for material seams, floating objects, exposed borders, accidental
repetition and a misleading minimap. The renderer is a preview; `mw play`
shows the game, and `mw capture` takes its screenshots when a review needs
them. Keep a critique list ordered by impact (broken routes or starts, weak
terrain or composition, collision, local polish), repair the earliest pass it
belongs to, and rerun the later checks.

## Working in iterations

Each build is a step: change one class of concern at a time (topology,
elevation, materials, landmarks, vegetation or presentation), build, and look.

- `mw dev` rebuilds on every save with the viewer open.
- Every build ends with what it changed (`mw diff`): a deliberate edit lists
  first, with the seeded scatter it shifted after it. Unexpected changes
  elsewhere mean the edit reached further than intended.
- Look from where it matters: `mw render ... --view` for a fixed camera to
  compare before and after, the viewer to walk round.
- When the user marks places in the viewer, read them with `mw marks` and
  write their coordinates into the code ([AGENTS.md](../../AGENTS.md)).
- Keep a fixed seed while tuning placement rules, so comparisons stay
  meaningful; the last five builds are in `mw history`.
- Missing evidence means unverified, not passed: say which checks ran.
