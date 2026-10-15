# Experiments in bfme-workshop

> **History.** These runs were made with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), the repository this
> one grew out of, between 8 and 13 October 2026. Its commands
> (`scripts/workshop.py`, `python -m mapkit.*`, `host.launch`), labs and
> `local/artifacts/` paths are that repository's and do not exist here. What the
> runs established is in [docs/game/](../game/README.md); this page keeps how
> it was measured, with the map hashes.

## Navigation lab

The workshop tests navigation with original small maps and native script
commands. These tests separate a path query from actual movement. They do not
yet establish formation clearance, build placement, slope limits, manual player
orders, bridge destruction, or every locomotor's behavior.

The [roads and bridges experiment](../game/roads-and-bridges.md) extends these
corridors with original road endpoint pairs and walkable object bridges,
including a raised-bridge negative control and deck-height trajectory checks.
[Walls and castles](../game/walls-and-castles.md) covers the chainable wall kits and
castle sites.

### Flat corridors

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

### Reproduce

The commands use the bundled, native-reconciled [script catalogue](../game/scripts.md).
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

### Height-only slopes

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

## Roads and bridges lab

Native run **011** authored 16 original `DaleRoad01` segments over the four
flag-test corridors. Open and player-only-flag corridors remained traversable;
impassable and impassable-plus-extra-passable corridors remained blocked for all
four units. Thus these roads did not override explicit terrain barriers. Map
SHA-256: `bff216d9afaaeb5c40f00cf93dde5724a15e1a90ed4d531cb556dcd52de135d9`.
This is loading/navigation evidence, not visual verification of corner modifiers.

The already completed `roads-capture-001` shows the authored straight segments
rendering with the `DaleRoad01` material. Its close-up PNG has SHA-256
`1c9af7ca699b2ba4d7f71501a5df744ee5b3a8ad856c061e49da4ba3316bc653`.
This separate visual run used the strategic extension for camera/reveal control;
it does not change the extension-free movement evidence or establish modifier
semantics. Images and raw reports remain local, ignored outputs.

Runs **009 and 010** passed with map SHA-256
`80c570ab4c3b2f94a8a851412cb75c5056244777c29d7876037bb3ac7e3dbb7d`.
Run 010 also requires expected positive/negative query markers and trajectory
samples inside the gap, within bridge width and above Z 100. This rejects a
spurious crossing on the river bed. All three runs use the isolated BFME2 1.06
runtime without the strategic extension. The observer only reads objects;
map scripts create markers and issue movement orders.

Crossing runs use the navigation lab below with its two object bridges replaced
by endpoint pairs (420 and 700 long). Run `endpoint-bridges-001`
(`TEST_EuropeanBridgeWide`, map SHA-256
`c4610dffb45bab05617b9c77ba08ed0c9bbf37b9d413335abec951e52cfe5149`) and
`endpoint-bridges-003` (`TEST_NewBridgeWide`,
`b026ab2e71b09fa75b1777895860e03c36562cb55526e576b9510ef48d15e457`) passed all
16 trajectory checks, including deck height; `endpoint-bridges-002`
(`TEST_NewBridgeWide`, ends raised 40) failed them for all eight bridge units.
The appearance comes from native screenshots of the
[bridge lab](../../maps/bridge_lab/map.py) project. Untested: slopes
between unequal banks, formations, destruction and rebuilding.

## Reproduce

```powershell
python -m mapkit.navigation_lab `
  --out local/artifacts/navigation-lab/bridge-NEW `
  --surface bridges --movement --human-owned --install
python -m host.launch `
  --script-check local/artifacts/navigation-lab/bridge-NEW/proof.json `
  --map 'maps\map mp bfmexbar navigation lab.map'
```

Use `--surface roads` and a fresh directory for the road experiment. Finish one
native run before installing another variant. Untested: other bridge models,
ramp-gap tolerance, formations, alternate rotations, destruction/rebuilding and
overlapping walkable layers. This bridge has an immortal body, so it does not
exercise destruction/rebuilding.

## Script lab

Reproduce from the installed workshop environment:

```powershell
.\local\venv\Scripts\python.exe -m mapkit.script_audit `
  'C:\path\to\BFME2\Maps.big' `
  --out local/artifacts/worldbuilder-analysis/script-audit.json
```

The JSON reports per-map hashes, record versions, numeric argument types and
observed signatures `(chunk, opcode, internal name, ordered argument types)`.
It records unresolved payloads rather than treating an unknown node as success.
The ordinary map analyzer now includes recursive script trees and field values.
Reports and retail inputs stay in ignored local directories.

`mapkit.script_catalog` extracts the BFME2 initializers from a separately
installed Open-BFME-2 checkout. It processes action initialization before condition
initialization because the action function also fills two condition slots. Later
assignments override earlier ones. Unsupported relevant C++ assignments stop the
extractor rather than silently omitting fields.

```powershell
.\local\venv\Scripts\python.exe -m mapkit.script_catalog `
  'C:\path\to\Open-BFME-2' --audit local/artifacts/worldbuilder-analysis/script-audit.json `
  --out local/artifacts/worldbuilder-analysis/script-catalog.json
```

After a native script check, add `--native <run>/native-templates.json` and write
to a new catalogue filename. Source SHA-256 hashes and a normalized snapshot hash
record provenance. The extracted signatures are not executable C++ and do not
include the upstream implementation.

```powershell
.\local\venv\Scripts\python.exe -m mapkit.script_lab `
  --catalog local/artifacts/worldbuilder-analysis/script-catalog.json `
  --out local/artifacts/script-lab/run-NEW --install
.\local\venv\Scripts\python.exe scripts/workshop.py play `
  --script-check local/artifacts/script-lab/run-NEW/proof.json `
  --map 'maps\map mp bfmexbar script lab.map'
```

The original 128×128 lab uses a pre-placed named control unit and twelve scripts
on the `PlyrCivilian` side. Script results spawn additional named units. The
observer only reads live object state and template tables: it never executes
the tested actions or creates their marker units. It verifies the installed map
hash, final exact marker counts, forbidden markers, elapsed time and frames.
It preserves the engine report and uses the existing isolated game/profile.

Run 003 passed with map SHA-256
`60a980d43dcd42b7c795d27ac74101350ed6b5c22d9cebf9ad4f6f31d939edd0`.
The strategic extension was **not loaded**. This still uses the workshop's mod
directory and compatibility/test launcher; it is not yet a clean-install/menu or
multiplayer test.

Failed runs are retained: run 001 had no markers; run 002 established most
behavior but failed the initial inversion and frame-based seconds-timer
expectations. Run 003 tests the corrected BFME2 contract. The first run changed
side assignment and marker template before retrying, so its precise cause is
not isolated. Do not claim that every script on side zero fails.

## Lighting readback

For native readback, add `--lighting-probe` to the [script lab](../game/scripts.md).
It gives every time/light slot distinct original values and records the engine's
arrays, overbright toggle, flag, vectors, shadow color and final values. The
observer only reads memory and compares it with the authored map. A successful
readback verifies loading, not every rendering effect of those values.

Native run `script-lab/run-004` passed on 9 October 2026 with map SHA-256
`79a5e9e7136f63153e083378cdd22dbce86d9b938b93d28ac0eb72b04f9f0db5`.
All 36 distinct records and all extension fields matched; the strategic
extension was disabled. The existing script markers also passed. This uses
the isolated workshop runtime, not a clean-menu or multiplayer test.

## Terrain records audit

### The terrain tail

After the terrain planes and ordinary texture descriptors, two uint32 values
give the **edge bitmap-cell count and edge texture-class count**. Each edge class
has three uint32 fields (first cell, cell count, width), followed by a string.
Our analyzer previously skipped only the two counts; it now reads this table.
Nonempty edge tables have synthetic coverage, not retail BFME2 confirmation.

Each blend record is 18 bytes, little-endian:

| Offset | Field | Interpretation from EA source |
|---:|---|---|
| 0 | uint32 | Secondary texture tile |
| 4–7 | Four bytes | Horizontal, vertical, right-diagonal, left-diagonal switches |
| 8 | Byte | Bit 0: invert alpha; bit 1: force triangle flip for cardinal blends |
| 9 | Byte | `longDiagonal`, called `TwoSided` by OpenSAGE |
| 10 | int32 | Custom edge texture class; `-1` means none |
| 14 | uint32 | Record marker `0x7ada0000` |

Each cliff record is 38 bytes: a uint32 tile index, four float32 UV pairs, then
separate `flip` and `mutant` bytes. Corner order is `(x,y)`, `(x+1,y)`,
`(x+1,y+1)`, `(x,y+1)`. We previously treated the final two bytes as one unnamed
uint16. The editor uses `mutant` in its UV seam/tiling adjustments; it should not
be interpreted as a gameplay or impassability flag.

Blend/cliff plane index zero means no record. Normally the declared table count
includes this implicit zero slot; records begin at one. A retail Osgiliath file
also declares zero cliff entries, which the reader accepts as an empty table.

### Retail check, 8 October 2026

The read-only scan of the local `Maps.big` examined 67 map entries:

| Measurement | Result |
|---|---:|
| Maps whose terrain tables parsed and decompressed bytes round-tripped exactly | 65 |
| Blend records | 1,102,662 |
| Cliff mappings | 40,692 |
| Maps with cliff mappings | 8 |
| Unexpected values reported within those decoded records | 0 |

All four directions occur. Blend flags use values 0–3, `longDiagonal` uses 0/1,
and all four combinations of the cliff bytes occur. Every custom edge class is
`-1`, and every edge table is empty. This supports the layout and value ranges;
it does not independently prove each field's rendering behavior in BFME2.

That initial scan excluded `map wor rhun` at the primary-tile palette-range check
and `shellmapbackup` at its v14 version guard. The 9 October read-only decoder
expansion now consumes both layouts. Rhûn adds 18,088 blend records; the legacy
map adds no blends/cliffs. The full corpus therefore contains 1,120,750 blends
and 40,692 cliff mappings. v14 has eight planes: the four index planes and
impassability, player impassability, passage widths and taintability. It lacks
v18's extra-passability, flammability and visibility planes.

Rhûn's 711 primary indices outside its 2432-subtile palette are all outside the
playable rectangle (560×560 samples, border 30). The bytes are retained and
reported. Inspection is explicitly separate from editing: the regular authoring
path still requires v18 and valid references. The original meaning of those
border indices is not established by consuming the file successfully.

Reproduce from the repository root with an installed workshop environment:

```powershell
.\local\venv\Scripts\python.exe -m mapkit.terrain_audit `
  'C:\path\to\BFME2\Maps.big' `
  --out local/artifacts/worldbuilder-analysis/terrain-audit.json
```

The JSON includes per-map hashes, record distributions, examples, issues and
skipped-map reasons. It exports no map files. The ordinary map analyzer now
reports the same terrain details; raw unusual values are retained and flagged.

## Terrain lab

## Isolated native experiment

`python -m mapkit.terrain_lab --install` generates a 192 × 192 playable
test map with 16 panels. The four cliff panels share identical geometry and
material: native default projection, explicit planar UV, and UV scales 2 and 4.
The scale-2 candidate uses a surface-length estimate for this particular 60°
slope. This is not the editor's general seam-matching algorithm.

Tested map SHA-256:
`93a7e614727c3122a97593f669d8e4a6b0223d35375baca5f047a6593057144e`.

The overview capture passed in BFME2 1.06 at Medium graphics: four 1600 × 1200
native PNGs, 331 logic frames, zero extension faults, and no original-profile or
guarded game-file changes. Evidence is in
`local/artifacts/terrain-lab/capture-002/capture.json`. Close views of the diagonal,
three-way and cliff panels are in `local/artifacts/terrain-lab/closeups-001/`.

Inspection shows the authored blend patches, including three-material cells,
and clearly different texture density/stretching on the identical cliff panels.
This establishes that the test records affect the renderer. It does not certify
every blend orientation, eliminate seams on arbitrary terrain, or establish a
production UV scale. The close views remain raw images with the HUD included.

No editor open/save comparison is claimed. It is optional supporting evidence,
not a prerequisite for the format investigation. The next verification should
cover irregular adjoining slopes and triangle orientation with controlled native
cases and source analysis before a production-map change.

See [map-file structure](grey-mountains-analysis.md) for the surrounding container and
[heightmap workflow](../../maps/eight_kingdoms/heightmap.md) for elevation authoring.

The isolated test generator and repeatable capture command are documented in
[native screenshots](native-screenshots.md).

## Base and library audit

```powershell
python -m mapkit.coverage 'C:\path\to\BFME2\Bases.big' --out local/artifacts/bases-coverage.json
python -m mapkit.coverage 'C:\path\to\BFME2\Libraries.big' --out local/artifacts/libraries-coverage.json
python -m mapkit.script_audit 'C:\path\to\BFME2\Libraries.big' --out local/artifacts/library-scripts.json
```
