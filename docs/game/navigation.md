# Navigation

What makes ground walkable or blocked in BFME2 1.06, as measured in the game.
Every result here comes from bfme-workshop's navigation lab: small original
maps with four isolated corridors, each crossed by `GondorFighter`,
`GondorCavalry`, `MordorCatapult` and `MordorAttackTroll` under scripted
orders, with the units' positions read from the game
([how it was measured](../history/bfme-workshop-experiments.md#navigation-lab),
with the map hashes). The workshop's own estimate, `mw walkable`, models these
rules; [the viewer](../viewer.md#walkable-areas) describes its limits.

## In short

- **Height alone never blocks.** Ramps of 26.6 to 87.1 degrees were climbed by
  all four unit types. Make a mountain impassable with the impassable plane,
  cliffs or objects, and check it.
- **Water deeper than 5 blocks.** Units crossed water 5 deep and stopped at 6
  and deeper, on flat terrain. A ford is water 5 or less above the ground.
- **The impassable plane blocks; nothing else in the terrain overrides it.**
  `extra_passable` does not reopen it, and roads do not either.
- **An object's origin is not its walking height.** Walkable bridges carry
  units on their deck meshes; a bridge placed too high leaves units on the
  river bed ([roads and bridges](roads-and-bridges.md)).

## Terrain planes

A full-width barrier across each corridor, set in the terrain's flag planes
([BlendTileData planes](../format/terrain.md#blendtiledata-v18-planes)):

| Barrier | Path query, all four units | Scripted movement, all four units |
| --- | --- | --- |
| None | Reachable | Crossed |
| `impassable=1` | Blocked | Approached near bank, did not cross |
| `impassable_players=1` only | Reachable | Crossed |
| `impassable=1`, `extra_passable=1` | Blocked | Approached near bank, did not cross |

Extra passability does not override the blocked plane in these cases. This
does not establish the general purpose of the player-only plane. Script-issued
movement can differ from mouse-issued player commands; the latter remains
untested.

## Water depth

Water polygons over flat terrain at height 100, alongside a dry control. All
four unit types crossed water 0, 1 and 5 above the ground, and were blocked at
6, 7, 8, 10, 15 and 20; path queries agreed with the movement. That is an
**observed boundary between 5 and 6** on this flat map. Fractional terrain
elevations, other locomotors, rivers and formation behavior remain separate
tests. Changing visual water alpha is not evidence that logical water depth or
navigation changed. Under a river strip, the standing water below it is what
units wade in; whether a strip alone affects movement is untested
([rivers](rivers-and-waves.md#rivers)).

## Height-only slopes

A triangular ridge across each corridor, rising for five ten-unit samples and
descending for five, without setting the blocked plane. At rises of 5, 10, 20,
50, 100 and 200 per sample (about 26.6, 45, 63.4, 78.7, 84.3 and 87.1
degrees) all four unit types queried reachable and crossed, their height
following the ridges to above 1,000 in the steepest case.

**Do not rely on height alone to make a mountain impassable.** Author explicit
navigation barriers and test them. This result concerns original height-only
terrain, not a claim that every cliff, wall or locomotor ignores slope.

## Not yet measured

Formation clearance, building placement, a general slope limit, manual player
orders, bridge destruction, and every locomotor's behavior. A recorded
crossing is positive evidence; no crossing within the finite observation window
does not prove an absolute engine prohibition in every situation.
