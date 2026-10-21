# Walls and castles

BFME2 has three kinds of wall object. `mapworkshop.mapkit.walls` places the
first two; the third are ordinary objects.

| Kind | Objects | Chained by | In a map |
|---|---|---|---|
| Chain walls (`WallHubBehavior`) | `MenWallSegmentSmall`, `MenWallHubSmall`, gates, posterns, towers, trebuchets; the same for Dwarves, Dol Guldur, Elves, Isengard and the faction castle kits | the engine, when a player places hubs; by hand in a map | `wall_line`, `place_wall` |
| Castles (`CastleBehavior`) | `CastleFlag`, `CastleFlagNE/NW/SE/SW` | a castle template unpacked on capture | `castle_site` |
| Decorative castle members (`CastleMemberBehavior`) | `RohanEdorasWall`, `GondorCastleWall`, the set pieces of Erebor, Blue Mountains, Osgiliath and others | not at all | `add_object` |

## Chain walls

A wall hub's `WallHubBehavior` (retail INI; module data in
[Open-BFME-2](https://github.com/Open-BFME/Open-BFME-2)'s
`WallHubBehaviorModuleDataCtor.cpp`) lists the segment pattern built along a
span (`SegmentTemplateName`, repeated; the Men fortress lays eight segments
then a hub), the hub, cliff, shore and border caps, the elevated segment,
`MaxBuildoutDistance` from the fortress (650–700 in retail) and a
`StaggeredBuildFactor`. The skirmish AI builds walls through `AIWallBuilder`.

The pieces are structures (`STRUCTURE IMMOBILE WALL_SEGMENT DEFENSIVE_WALL
SCALEABLE_WALL`): they block paths, have health (a Men segment 3,500), leave
rubble, are rebuilt, and siege ladders scale them. A segment can replace
itself with a hub, gate, postern, tower or trebuchet (`ReplaceSelfUpgrade`).

A map holds no chain: every piece is its own object. Measured in the stock
maps that place them (the advanced tutorial, Withered Heath, both Dol Guldur
maps, Mirkwood, both Grey Havens):

- segments stand end to end, one length apart: 38 for every small kit, in
  420 of 434 Dol Guldur pairs, 88 of 93 at Withered Heath;
- each is turned to its run: map angle = run direction + 90 degrees for kits
  long along their local y, the run direction itself for Dol Guldur's (long
  along x); the stock maps use + 90 and + 270 alike, and front and back of
  the pieces look the same;
- a hub stands at each end and corner, about 20–40 from the nearest segment;
- a gate takes three segments' places (its neighbours stand 76 away), a tower,
  postern, trebuchet or catapult one.

`wall_line` follows these rules. Rebuilt between their own hubs, with their
own gates, towers and trebuchets, the advanced tutorial's straight runs come
out with the same pieces, each within 20 units of the stock one
(`test_walls.Stock`, run by `mw test --corpus`). The castle kits
(`gondor_castle`, `dwarven_castle`, `mordor_castle`, `wild_castle`,
`isengard`) are built by fortresses in the game and appear in no stock map:
their lengths are model bounds only. None of this is yet confirmed by a native
capture.

## Castles

A `CastleFlag` (`civilianbuildings.ini`) carries a `CastleBehavior` with
`CastleToUnpackForFaction` entries: on capture it unpacks `Castle_<Faction>`
for the capturing player's faction within `MaxCastleRadius = 420`, handing
`STRUCTURE`, `WALK_ON_TOP_OF_WALL`, `BASE_FOUNDATION` and `TACTICAL_MARKER`
objects to the player and the rest (rocks, props) to the neutral player. The
templates are `bases/castle_<faction>[ne|nw|se|sw]/<same>.bse` in the game's
archives: small map documents whose `CastleTemplates` chunk lists the
buildings relative to the centre. `Castle_Men`, for example: a keep, seven
walls, two elevators (the stairs onto the wall), a pair of gates, five tower
nodes, lamps and props. The skirmish AI reads the same `.bse` files as its
base layouts (Open-BFME-2 `BaseTemplateLibraryParseBaseTemplateFiles.cpp`).
All 30 decode with `formats.castles`; no stock BFME2 map places a CastleFlag.

## Walkability

The local estimate (`mapkit.pathing`) counts chain-wall pieces as structure
footprints and reports gates and wall upgrades as states it does not
simulate. Until 14 October 2026 it missed the top-level `KindOf` and
`Geometry` of 608 of the game's 4,189 templates, the Men and Dwarven wall
kits among them: their `Draw` blocks contain `ParticleSysBone` lines, script
calls and `BeginScript` regions, which it took for nested blocks.
