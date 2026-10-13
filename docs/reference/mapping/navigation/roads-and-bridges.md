# Roads and bridges

A road segment is two adjacent `Object v3` records in `ObjectsList`. A walkable
bridge can instead be one ordinary object with deck and ramp meshes. Keep these
mechanisms separate when generating or transforming a map.

## Road records

The first endpoint carries flag `0x02`, the immediately following endpoint
`0x04`. Both carry the same road template name. Coordinates use map world XY;
do not add the terrain border. Preserve Z, properties, flags and record order.

The retail `Maps.big` audit found **4,493 pairs across 67 maps**. Every start had
an adjacent end with the same template, and every end had an adjacent start.
Eighteen pairs have identical XY coordinates; inspection reports and preserves
them. Their intended effect remains unknown. No `0x10/0x20` bridge endpoint
records occurred in this corpus; they work in BFME2 nonetheless (see
[spanned bridges](#spanned-bridges) below).

| Flag | Source-family interpretation | BFME2 evidence here |
| --- | --- | --- |
| `0x02`, `0x04` | Road start/end | Retail pairing and original native lab |
| `0x08` | Angled corner | Retail roads; rendering effect pending |
| `0x40` | Tight curve | Retail roads; rendering effect pending |
| `0x80` | Alpha join | Retail roads; rendering effect pending |
| `0x10`, `0x20` | Paired bridge endpoints | No corpus example; native runs below (spanned bridges) |
| `0x100` | Editor-only hidden flag in Generals | BFME2 meaning unverified; retained raw |

These names come from EA's
[MapObject flags](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngine/Include/Common/MapObject.h).
OpenSAGE calls `0x80` `EndCap` and leaves `0x100` unknown in its
[RoadType enum](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Data/Map/RoadType.cs).
We use the source name `ALPHA_JOIN` without claiming its BFME2 effect proven.
OpenBFME2's `W3DRoadBuffer::addMapObjects`, revision
`33f02e4222f3ac9c284d9b71cf5e7438799988bb`, describes adjacent pairs and modifiers,
but that body is **present-unmatched**. It is supporting research, not a matched
BFME2 implementation.

[`roads.py`](../../../../src/mapworkshop/mapkit/roads.py) adds original road pairs. Its
inspection appears in the map analyzer's `roads` field and reports orphan
endpoints, mixed templates, nonfinite or zero-length geometry, and uninterpreted
flag bits without changing the map.

```python
from mapkit.roads import add_segment, ANGLED

add_segment(m, "DaleRoad01", (300, 500, 0), (900, 500, 0),
            name="approach", start_options=ANGLED)
```

Use a road template available in the user's `TerrainRoads` definitions. The
writer gives the endpoints distinct unique IDs and rejects duplicate IDs,
zero-length segments, nonfinite positions and unsupported option bits. It does
not flatten terrain or change navigation planes. Connected corners, joins,
material widths, overlaps and paired bridges still need dedicated experiments.

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

## Walkable object bridges

The original bridge lab uses `GondorIthilienBridge2`, also used by Eight Kingdoms.
The local retail INI declares `WALK_ON_TOP_OF_WALL`, a wall-bounds mesh and two
ramp meshes. Its long axis is local Y; `-pi/2` spans world X. Declared footprint
radii are 76 and 275. The model meshes determine walking height, not simply the
INI geometry height or the map object's origin.

The lab places a 320-unit water gap between banks at height 100, with bed at 20
and water at 80. Infantry, cavalry, catapult and troll receive scripted move
orders across it. Full-width dividers prevent going around the gap.

| Case | Path query and movement, all four units |
| --- | --- |
| Dry control | Reachable; crossed |
| Water gap without bridge | Blocked; stayed on near bank |
| Bridge origin at Z 99 | Reachable; crossed on deck |
| Same bridge origin at Z 199 | Blocked; stayed on near bank |

The correctly placed bridge stores map Z **79** over terrain **20**; native
position reads **99**. The raised control stores **179**, producing **199**.
This confirms terrain-relative Z for this template. Traversing units rose to
approximately **154.39** on the deck within its lateral footprint. An object's
origin is not its walking height.

Runs **009 and 010** passed with map SHA-256
`80c570ab4c3b2f94a8a851412cb75c5056244777c29d7876037bb3ac7e3dbb7d`.
Run 010 also requires expected positive/negative query markers and trajectory
samples inside the gap, within bridge width and above Z 100. This rejects a
spurious crossing on the river bed. All three runs use the isolated BFME2 1.06
runtime without the strategic extension. The observer only reads objects;
map scripts create markers and issue movement orders.

## Spanned bridges

A second kind of bridge is spanned by the game between two points: two
adjacent objects carrying a `Bridge` type's name (from `roads.ini`, or the
map's own `map.ini`), flagged `0x10` and `0x20`. The game lays the type's
model from one point to the other: its `BRIDGE_LEFT` piece, `BRIDGE_SPAN`
repeated as often as fits, `BRIDGE_RIGHT`, scaled along its length to end
exactly at the second point (`W3DBridgeBuffer::loadBridges`, `W3DBridge`);
`BridgeScale` sets width and height. Each gets a `GenericBridge` logic object
and its own pathfinding layer. No retail BFME2 map uses one, and BFME2 ships
only two types, `TEST_EuropeanBridgeWide` and `TEST_NewBridgeWide`.
[`bridges.py`](../../../../src/mapworkshop/mapkit/bridges.py) writes them
(`add_bridge`, `bridge_type` for a map's own type) and checks the model first.

Native observations on 13 October 2026, BFME2 1.06 in bfme-workshop's isolated
runtime, without the strategic extension:

| Case | Result |
| --- | --- |
| `TEST_EuropeanBridgeWide` (CBWBrdgeArc, flat deck), 400 and 700 long | Spans bank to bank; four unit types cross on the deck at 100.25 (banks at 100), as fast as on dry ground |
| Same model as a map's own `map.ini` Bridge type | Loads and spans the same way |
| `TEST_NewBridgeWide` (CBBrdge1, arched, on piers) | Units cross at 100.25 as well, but the model's deck lies about 40 below that line: it looks sunken |
| `TEST_NewBridgeWide` with both ends raised 40 (object Z) | Looks right; units cross on the riverbed beneath (Z 20), not the deck |
| A one-piece model (`NBTreeBrdge`, GenericTreeBridge's) as a map.ini type | The game crashes while loading the map (access violation in `W3DBridge::load`) |

The walkable surface is the straight line between the two points, 0.25 above
the terrain at each, whatever the model's shape. Of the 12,751 models in the
game's archives only `CBWBrdgeArc` and `CBBrdge1` have the three pieces, so
only `CBWBrdgeArc` gives a deck that matches the walkable line. Ends on terrain
raised about 40 above the banks might fit `CBBrdge1` (untested).

Crossing runs use the navigation lab below with its two object bridges replaced
by endpoint pairs (420 and 700 long). Run `endpoint-bridges-001`
(`TEST_EuropeanBridgeWide`, map SHA-256
`c4610dffb45bab05617b9c77ba08ed0c9bbf37b9d413335abec951e52cfe5149`) and
`endpoint-bridges-003` (`TEST_NewBridgeWide`,
`b026ab2e71b09fa75b1777895860e03c36562cb55526e576b9510ef48d15e457`) passed all
16 trajectory checks, including deck height; `endpoint-bridges-002`
(`TEST_NewBridgeWide`, ends raised 40) failed them for all eight bridge units.
The appearance comes from native screenshots of the
[bridge lab](../../../../maps/bridge_lab/map.py) project. Untested: slopes
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
