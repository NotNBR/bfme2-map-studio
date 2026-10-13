# The Crown of Cardolan

An original eight-player battlefield around a fallen Arnorian hill-city. The
landscape is invented for this workshop, inspired by the ruined northern kingdoms of
Middle-earth; it is not presented as a canonical reconstruction of a named city.

## Composition

Eight rival marches share a ring of open moorland around the ruined Crown.
The 920 × 920 playable tiles span 9,200 × 9,200 world units, with a 30-tile border
and 980 × 980 stored height samples. Eight perimeter starts are evenly spaced
around the same radius. Each has a graded building area, a direct inward approach
and access to a winding outer road. The breached city has its own circulation
route, so reaching the centre does not require passing through one narrow gate.

The repeating gameplay opportunities are intentional. Scenery is asymmetric:
Black Pines and Greywood have different tree families; the eastern barrows are
small earthen mounds with stones and broken statues; the Old Quarry has an excavated
floor and abandoned stone; Northwatch overlooks the road; outer hamlets retain
lanes, carts and fire pits. The central citadel combines a broken stronghold,
tower, statues, fragments of curtain wall and eight ruined gate districts.

Building space and army routes are reserved before optional detail. Rubble clusters
around masonry and the backs of settlement plots. Forest floor objects follow
woodland edges. Exposed shoulders receive rock outcrops; empty plains are not
covered with random prop noise. The base terrain uses muted, fine stony soil,
with material changes reserved for wear and exposed rock. There is no broad soil
camouflage pass. Native cast shadows and visible props use the tested Medium preset.

## Painting stages

1. Create a new uniform plane, then add eight functional starts in a separate checkpoint.
2. Compose a broken crown around open moorland. A central bottleneck was rejected
   because seven opponents would overload it; isolated corner forts would leave
   the central landscape without a purpose. The selected layout offers a centre
   and two circulation routes.
3. Sculpt boundary shoulders, interior spurs and a city terrace. Domain warp,
   rotated fBm and thermal relaxation break up the forms; road and base grading
   happen afterward.
4. Check level base disks and flood the graded road band to confirm all eight
   starts connect. This is an authoring check, not a substitute for horde movement.
5. Inspect the actual terrain artwork, then paint a restrained material palette.
6. Place the main keep first, then breached walls, districts and regional scenes.
7. Add ecological clusters, masonry rubble and forest floor detail; review actual
   native close-ups and the whole-map view before accepting the result.

## Build and play

```
mw build crown-of-cardolan     build it
mw view crown-of-cardolan      look at it in the viewer
mw play crown-of-cardolan      install it into the game and start BFME2
```

`mw build crown-of-cardolan -- --phase functional|terrain|detail` builds an earlier stage.
The map has eight unrestricted starts; choose teams in a normal skirmish lobby.

> The native checks, launch presets and captures recorded below were made with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), whose `workshop.py play` presets and launchers are not
> part of this repository.

## Technical findings and verification boundaries

Eight waypoints alone are insufficient. The new-document constructor now accepts
2–8 player sides, emitting matching Teams, LibraryMapLists and PlayerScriptsList
entries. Eight-player documents contain 18 side records including neutral,
civilian, creeps and the six faction templates. The map cache derives numPlayers
from distinct sequential start names, instead of its old hardcoded value of two.

The reference launch helper intentionally creates just one AI when its human-player
flag is used. The new wrapper fills slots 1–7 with AI state, accepted/has-map flags
and explicit faction templates. The native test separately counts owners of
instantiated builder objects; configured slots alone do not prove eight armies exist.
That census uses the same version-guarded object and KindOf layouts as the strategic
extension and performs read-only memory inspection once during the test.

Palette inspection found a valid-looking INI entry, DirtEttenmoors04, whose referenced
texture was absent from the scanned installed archives. It was excluded. Inspect
the actual artwork and installed asset, not just a template's name.

WorldBuilder open/save remains unverified. Native loading, eight-player instantiation,
route-grid connectivity and representative rendering are distinct checks. Extended
AI matches, full horde traversal, network play and competitive balance require playtesting.

## Native review and refinement

The functional eight-player test passed before decoration. The engine instantiated
eight distinct owners (indices 3–10), each with starting builders; all eight slots
had the requested factions. Four native views and the simulation check passed.

The first detailed pass had 2,593 objects. Native review found pink foliage from
`PTreeOak02`: its PTOakFall2 model exists, but its named texture is absent from the
installed texture archives. It was replaced with verified Tree01/Tree05 variants.
The map also sets `LowLodTreeName = TreeLowLODArnor` so its distant woodland fits
the northern theme. The compiled PTLowArnor texture was verified before use.

Placement inspection found that road protection had excluded Northwatch and most
of the quarry. Northwatch moved to clear ground and became a required placement;
the quarry was relocated between approaches and recut before placing its stone.
Woodland sampling and density increased while keeping the same protected base
disks and road widths. The cloudy base soil was replaced by finer-grained stone
to avoid repeating the earlier Ashen March texture problem.

The refined build has 3,882 records: 1,603 woodland trees, 1,063 outcrops, 434 forest
floor details, 315 masonry-rubble placements, 120 solitary trees, 145 settlement
debris objects, 88 gate-district objects, 30 quarry stones, 27 wall fragments,
25 outer-village objects, 18 barrow pieces, five citadel pieces, Northwatch and
eight starts. Height range and route measurements are in `build.json`.
