# Corpus coverage and authoring rules

What the readers have been checked against: every section and version in the
local corpus of retail maps, bases and libraries, and the rules a writer must
keep. The [specification](README.md) presents the format in parsing order, with
the exact layouts; this page records coverage and constraints, not complete
engine semantics.

## What the coverage means

The read-only audit on 8 October 2026 examined all **67 `.map` entries** in the
local BFME2 `Maps.big`: **22 top-level section names, 25 section/version pairs**.
Every container re-encoded to identical **decompressed** bytes. This does not
prove that opaque payloads were understood or that edits would behave correctly.

In the table, **decoded** means the implemented layout consumes the payload
exactly. **Partial** means useful fields are decoded but unknown fields or nested
payloads remain. Neither term certifies every engine rule. Versions not listed
are outside this audit. Optional sections absent from the corpus may still be
legal; this is not a whitelist of everything the engine can read.

| Section | Version | Maps | Current coverage |
| --- | ---: | ---: | --- |
| HeightMapData | 5 | 67 | Decoded; dimensions, borders, elevations |
| BlendTileData | 18 | 66 | Partial; all layouts consumed, Rhûn's 711 out-of-palette samples reported without normalization |
| BlendTileData | 14 | 1 | Read-only legacy layout decoded; modern authoring guards remain |
| WorldInfo | 1 | 67 | Decoded typed properties; property meanings depend on engine consumers |
| ObjectsList | 3 | 67 | Decoded Object v3 children; template behavior is external |
| MPPositionList | 0 | 67 | Decoded MPPositionInfo v0/v1 children |
| SidesList | 6 | 67 | Partial; leading boolean unresolved; embedded build lists decoded |
| Teams | 1 | 67 | Decoded property dictionaries |
| LibraryMapLists | 1 | 67 | Decoded LibraryMaps v1 children |
| PlayerScriptsList | 1 | 66 | Partial semantics; full stored hierarchy and arguments decoded, opcode behavior still under investigation |
| PlayerScriptsList | 5 | 1 | Stored hierarchy decoded, including Script v2 / Action v2 / Condition v4; semantics partial |
| BuildLists | 1 | 67 | Decoded BFME faction lists; nonempty entries source/synthetic tested only |
| TriggerAreas | 1 | 66 | Partial; polygons decoded, trailing integer unresolved |
| PolygonTriggers | 5 | 1 | Legacy layout decoded; retail example empty, nonempty layout synthetic-tested; semantics partial |
| StandingWaterAreas | 2 | 66 | Decoded polygons, height and material references |
| RiverAreas | 2 | 66 | Decoded cross-sections and water parameters |
| StandingWaveAreas | 2 | 66 | Partial; raw parameters retained alongside source-derived names |
| GlobalLighting | 8 | 66 | Full layout decoded and serialized; third light array and extension-field meanings partial |
| GlobalLighting | 7 | 1 | Same layout without the three v8 final values |
| PostEffectsChunk | 1 | 66 | Decoded effects, blend factors and lookup images |
| EnvironmentData | 3 | 67 | Decoded water alpha and macro/cloud texture settings |
| NamedCameras | 2 | 67 | Partial; bookmark fields include an unresolved float |
| CameraAnimationList | 3 | 66 | Partial; free/look tracks decoded, focal/interpolation semantics need verification |
| SkyboxSettings | 1 | 1 | Decoded transform and texture-scheme reference |
| WaypointsList | 1 | 67 | Decoded ID-to-ID links; positions live in ObjectsList |

The legacy combinations occur in `maps/shellmapbackup/shellmapbackup.map`.
Four maps have nonempty camera-animation lists and all four now decode. There
are **718 immediate script/group children in the modern maps**. The recursive
[script audit](../game/scripts.md), now including the legacy file, decodes 3,340 scripts,
4,186 conditions and 10,254 actions. These counts do not establish complete opcode semantics.
All faction and embedded build lists in this corpus contain zero build entries;
passing them cannot establish real-world nonempty build-list compatibility.

Rhûn contains 711 primary-tile samples with IDs between 31501 and 31511 despite
a descriptor palette of 2432 subtiles. All 711 are outside the playable rectangle.
The read-only inspection consumes the terrain without dropping these values;
authoring operations still reject them. Their original intended meaning remains
unresolved. Do not clamp the IDs or label the retail map corrupt.

As of 9 October, every observed top-level section/version has a structural
decoder. This closes the corpus layout inventory, not all semantic, authoring
or runtime workstreams. Optional features absent from retail Maps.big still need
separate cases.

The expanded 9 October audit also includes **152 documents in `Bases.big`**
(150 `.bse` files and two `.map` files) and **51 in `Libraries.big`**. All 270
containers round-trip exactly, and every observed top-level section/version has
a decoder: **23 section names and 43 section/version pairs** overall.
This is a local corpus result, not a completeness claim for every
legal BFME2 file. Base files add `CastleTemplates v1–5`, real faction/side build
lists and additional legacy variants. See [bases and libraries](../game/bases-and-libraries.md).

Reproduce from the checkout (the [format tools](tools.md)):

```powershell
python -m mapworkshop.mapkit.checks.coverage 'C:\path\to\BFME2\Maps.big' --out local/renders/coverage.json
```

The report includes each map's hash, independent section results, unsupported
reasons and exact container round-trip status. One section's failure does not
hide the rest of the map. It exports no retail maps. The separate
`mapkit.checks.terrain_audit` inventories detailed terrain records.

## Authoring rules and their limits

| Area | Rule or constraint | Evidence / limit |
| --- | --- | --- |
| Container | Keep chunk versions, lengths and name IDs consistent; preserve unknown payloads and their referenced IDs. | Parser and exact retail round-trips; byte preservation is not semantic editing support. |
| Primitives | Numbers are little-endian. Chunk names use variable-length UTF-8 lengths; record strings use uint16 byte lengths and CP1252. Property type 4 uses UTF-16LE character counts. | Current BFME layout; do not substitute one string encoding for another. |
| Properties | uint16 count; each key is byte type plus three-byte name ID. Types 0/1/2 are byte bool/int32/float32; 3/5 narrow strings; 4 wide string. | Known type layout; legal property names and effects are open-ended engine inputs. |
| Terrain coordinates | One XY sample step is 10 world units; sample coordinates are `(worldX / 10 + border, worldY / 10 + border)`. Elevation is uint16 × 0.0390625. | Source, retail measurements and authored native tests. |
| Heights and limits | The storage range is 0–2559.9609375 world units. Writer bounds and dimension guards are tool policy, not proven engine maximums. | uint16 representation; native loading of particular large maps does not establish a universal size limit. |
| Resizing | Height samples and all eleven texture/flag planes must agree; bits are padded per row. Transform spatial records, including script coordinates if present. | Binary layout; refuse transformations of unresolved coordinate-bearing payloads. |
| Textures | Resolve palette names through installed terrain definitions. Preserve 2×2 subtile ordering and native tile scale. Zero blend/cliff index means no record. | Retail layouts and native authored texture checks; see terrain reference for record counts and seams. |
| Objects | Resolve template names through Object, ChildObject and ObjectReskin definitions. Object Z is a terrain-relative offset; orientation is radians. | Source and native placement observations. Model footprint, collision and LOD come from game data. |
| Starts | Our skirmish writer emits distinct `Player_1_Start` through `Player_N_Start`, N=2–8, with unique waypoint IDs. | Tested authoring convention; eight MP-position slots do not imply eight active players. Campaigns differ. |
| Ownership | Keep owner/team references valid and per-side library/script entries aligned when adding or removing sides. | Known schemas and generated-map loads; side count includes neutral/faction roles. |
| Paths | Waypoint links reference waypoint IDs; road/bridge endpoint objects have separate flags. Texture-painted roads do not establish routing. | Record structure; destructible bridge logic and traversal need engine-specific evidence. |
| Water | Transform polygons and river cross-sections in XY; decide water heights separately. Shore-wave geometry is separate. | Decoded layout; water appearance does not prove impassability or a usable ford. |
| Clearance | Terrain flags, slopes, object collision, locomotors and formation size jointly affect movement/building placement. | No verified universal slope threshold or corridor width for all units. |
| Bounds | Border scenery, off-map spawns and camera bookmarks may lie outside playable bounds. | Retail examples; do not clamp all coordinates indiscriminately. |
| Discovery | Installed maps need matching discovery/cache data and start counts; update paths, byte counts and extents after edits. | Tested isolated file-launch path; exact EA checksum equivalence and all menu/network paths remain unverified. |
| Validation | Check structure, resolve referenced assets, then test relevant engine behavior with a recorded map hash. | Native load/screenshots prove the tested views, not combat balance or multiplayer compatibility. |

A concept image's labels are design intent. For example, “forest slows units”
does not automatically create a native movement modifier when trees are placed.
Likewise, map bytes do not contain all game rules: INI definitions, scripts,
object modules and the executable determine much of the result.

The record layouts are in the [specification chapters](README.md#chapters), implemented in
[sections.py](../../src/mapworkshop/formats/sections.py) and
[`analyze.py`](../../src/mapworkshop/mapkit/checks/analyze.py), cross-checked with
[OpenSAGE map sources](https://github.com/OpenSAGE/OpenSAGE/tree/master/src/OpenSage.Game/Data/Map),
[BuildListInfo](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Logic/Map/BuildListInfo.cs)
and [SidesList](https://github.com/OpenSAGE/OpenSAGE/blob/master/src/OpenSage.Game/Logic/Map/SidesList.cs).

## Coverage boundaries

A section is not complete merely because it round-trips. Completion requires
version-specific, bounds-checked decoding; nonempty cases; field units and
references; authoring support; and relevant native behavior evidence. Preserve
unknown values and label limitations. `semantics_complete: false` in the
coverage report is intentional.

Open work: [not yet established](../game/README.md#not-yet-established).
