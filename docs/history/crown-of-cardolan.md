# The Crown of Cardolan: history

> **History.** Recorded with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), the repository this
> one grew out of, in October 2026. Its launchers, commands and paths
> (`scripts/launchers/`, `scripts/workshop.py`, `src/host/`, `local/artifacts/`,
> `local/runtime/bfme-host/`) are that repository's and do not exist here.

The native review of the Crown of Cardolan in bfme-workshop; the map itself is described in its [README](../../maps/crown_of_cardolan/README.md).

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
