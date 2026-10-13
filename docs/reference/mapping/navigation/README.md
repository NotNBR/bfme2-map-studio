# Navigation

> Recorded with [bfme-workshop](https://github.com/NotNBR/bfme-workshop), whose native host, capture tools and
> isolated game runtime are not part of this repository. Paths below `local/runtime/`
> are that checkout's; here the game data lives in `local/game/` and builds in `local/build/`.

The workshop tests navigation with original small maps and native script
commands. These tests separate a path query from actual movement. They do not
yet establish formation clearance, build placement, slope limits, manual player
orders, bridge destruction, or every locomotor's behavior.

The [roads and bridges experiment](roads-and-bridges.md) extends these
corridors with original road endpoint pairs and walkable object bridges,
including a raised-bridge negative control and deck-height trajectory checks.

## Flat corridors

`mapkit/navigation_lab.py` creates four isolated corridors, each containing
`GondorFighter`, `GondorCavalry`, `MordorCatapult` and `MordorAttackTroll`.
Full-width blocked dividers prevent detours into another corridor. The test
barrier occupies world X 1,200–1,300. Coordinates in terrain planes include
the eight-sample map border; world positions do not.

Each unit gets a `UNIT_CAN_PATH_TO_WAYPOINT` query. A true/false script branch
creates one of two named outcome markers. The observer only reads object
positions and names. `--movement` also issues `MOVE_NAMED_UNIT_TO` in both
branches, including when the path query returned false. Separate scripts verify
the declared owner with `NAMED_OWNED_BY_PLAYER`.

| Barrier | Civilian path query, all four units | Player_1 query and scripted movement, all four units |
| --- | --- | --- |
| None | Reachable | Crossed |
| `impassable=1` | Blocked | Approached near bank, did not cross |
| `impassable_players=1` only | Reachable | Crossed |
| `impassable=1`, `extra_passable=1` | Blocked | Approached near bank, did not cross |

This establishes that **extra passability does not override the blocked plane
in these cases**. It does not establish the general purpose of the player-only
plane. Script-issued movement can differ from mouse-issued player commands;
the latter remains untested.

Civilian query run 001 passed with map SHA-256
`440dcd4d347c093775c35c7280b48ad42a8170641cb15f8ee91efd25c6e14622`.
Player_1 movement run 002 observed 612 simulation frames, verified all ownership
markers and recorded all 16 trajectories. Reachable units crossed; blocked
units never reached the barrier. Some catapults and trolls later moved away.
The original final-position validator therefore failed four cases. Its result
is retained as `native-validation-original.json`; revalidation checks the full
trajectory. Do not discard the earlier failure or describe it as a pathfinding
failure. The later motion's cause has not been isolated.

Fresh movement run 003 independently passed all 16 trajectory checks with map
SHA-256 `fea632327f436f01fa9aecaa70eb3fe3ffcc1f08e4ad4b6bc5e4a7d7cb6edc4d`.

All runs use the isolated retail runtime without the strategic extension.
The observer samples approximately once per second. A recorded crossing is
positive evidence; no recorded crossing within the finite observation window
does not prove an absolute engine prohibition in every situation.

## Reproduce

The commands use the bundled, native-reconciled [script catalogue](../scripts/README.md).
An explicit `--catalog` can override it:

```powershell
python -m mapkit.navigation_lab `
  --out local/artifacts/navigation-lab/run-NEW --movement --human-owned --install
python -m host.launch `
  --script-check local/artifacts/navigation-lab/run-NEW/proof.json `
  --map 'maps\map mp bfmexbar navigation lab.map'
```

Omit `--human-owned` to use `PlyrCivilian`. Omit `--movement` for path-query
observations only. Fresh evidence directories are mandatory; installation
overwrites only this named laboratory map in the isolated mod. Finish a native
run before installing another variant of the lab.

`--surface water` replaces the flag barriers with water polygons at terrain
height, one unit above it and twenty units above it, alongside a dry control.
This uses the original standing-water writer in `formats/water.py`; water
material references resolve against the user's game. Water experiment results
must be recorded separately from the flat flag table above.

Native water run 004 passed all 16 trajectory checks with map SHA-256
`c7a73e75b2b3bc73970196ef3223f43763ea9648f4591d0cce65df8a380010f5`.
All four unit types crossed the dry, depth-zero and depth-one cases; all were
blocked at depth twenty. These are authored water heights 100, 101 and 120 over
flat terrain at 100. They establish a shallow/deep distinction for these units,
not the exact threshold. `--water-depths A B C` selects three distinct integer
depths for further isolated experiments.

Run 005 narrowed the interval: depth 5 was passable, while depths 10 and 15
were blocked for all four units, with path queries agreeing with observed
traversal. Map SHA-256:
`cb136909d0e0b3eb178bbff82df57106384820952d80d33b9b2a78b3097733fb`.

Run 006 tested depths 6, 7 and 8; all were blocked for all four units and the
dry control remained passable. Map SHA-256:
`0fd8fb0cb6f91197115d5d4a9f8aa7d07547d944599bb3199cfbf1179dd20164`.
Together these establish an **observed integer-depth boundary between 5 and 6**
on this flat map. Fractional terrain elevations, other locomotors, rivers and
formation behavior remain separate tests. Changing visual water alpha is not
evidence that logical water depth or navigation changed.

## Height-only slopes

`--surface slopes` creates a triangular ridge across each test corridor,
without setting its blocked plane. It rises for five ten-unit samples and
descends for five. `--slope-rises A B C` sets the rise per sample; defaults
are 5, 10 and 20 world units, giving slopes of approximately 26.6°, 45° and 63.4°.

Native run 007 passed all queries and crossings for the four unit types at
all three slopes. Object Z samples confirmed they climbed the authored terrain.
Map SHA-256:
`45397d91a51c3a64920bf2354c3d149407a62b0d3cbb229e4abeb8fea496002e`.
Thus these height-only ramps do not become impassable automatically. This does
not yet give a general slope limit or validate cliff-painted/editor-generated
passability. Compare it with the explicit blocked-plane results above before
assuming a visually steep mountain prevents movement.

Run 008 repeated this at rises of 50, 100 and 200 per ten-unit sample
(approximately 78.7°, 84.3° and 87.1°). All four unit types again queried reachable
and crossed. Their Z observations followed the ridges, reaching above 1,000
world units in the steepest case. Map SHA-256:
`609beb490e410afb9f1475aaea77ba67a5d236f9b13429b1c3cd3460c1ebf008`.
**Do not rely on height alone to make a mountain impassable.** Author explicit
navigation barriers and test them. This result concerns original height-only
terrain, not a claim that every cliff, wall or locomotor ignores slope.
