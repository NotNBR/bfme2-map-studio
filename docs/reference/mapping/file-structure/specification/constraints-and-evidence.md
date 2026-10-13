# Constraints, example and evidence

[Specification index](../specification.md) · [Previous](presentation.md)

## Cross-record constraints

For a reader/writer conforming to this documented profile:

1. Bound every count, length and child to its containing buffer. Consume the
   entire known payload; do not silently accept leftover bytes as padding.
2. Resolve name IDs through the document table. Preserve existing IDs when any
   opaque data survives; newly added names can receive new IDs.
3. Keep height/material dimensions consistent. Preserve row padding, index
   widths and table zero-slot rules for the actual chunk version.
4. Validate interpreted table references while retaining/reporting documented
   exceptions in inspection mode. Do not normalize unexplained retail values.
5. Keep object, team, player, waypoint, trigger, library and script references
   consistent. These use different IDs/names and are not interchangeable.
6. Spatial edits must address terrain, objects, starts, water, triggers, links,
   camera tracks/bookmarks, base data and position-valued script arguments as
   applicable. Preserve unknown spatial records or refuse that transformation.
7. Preserve unknown flags, raw fields and opaque chunks. A numeric enum from
   another SAGE game is insufficient evidence to reinterpret a BFME2 value.
8. Refresh external cache/sidecar/package metadata after changes. File byte
   length and compressed-file hash differ from decompressed document identity.

These rules establish structural consistency. They do not establish gameplay
balance, asset availability, route clearance, AI behavior, multiplayer sync or
save/load correctness. Engine rules live partly outside the map file.


## Worked binary example

This **56-byte synthetic document** contains only `WorldInfo.mapName = "Demo"`.
It illustrates parsing and name references; it is **not a playable map** because
terrain, sides and other scenario sections are absent.

```text
Offset  Hex bytes                                 Meaning
0000    43 6b 4d 70                               CkMp
0004    02 00 00 00                               two names
0008    09 57 6f 72 6c 64 49 6e 66 6f            UTF-8 "WorldInfo", length 9
0012    02 00 00 00                               name ID 2
0016    07 6d 61 70 4e 61 6d 65                  UTF-8 "mapName", length 7
001e    01 00 00 00                               name ID 1
0022    02 00 00 00 01 00 0c 00 00 00            WorldInfo chunk: ID 2, v1, 12 bytes
002c    01 00                                     one property
002e    03 01 00 00                               type 3, name ID 1
0032    04 00 44 65 6d 6f                         CP1252 "Demo", length 4
```

Offsets are hexadecimal. The chunk begins at decimal 34; payload at 44; document
ends at 56. The shared table supplies both the chunk name and property key.
The example was constructed and byte-round-tripped with the current container
reader; no game launch is implied.


## Implementation and evidence

| Subject | Implementation / detailed evidence |
| --- | --- |
| EAR and RefPack | [map_archive.py](../../../../../src/mapworkshop/formats/map_archive.py) |
| Container and properties | [map.py](../../../../../src/mapworkshop/formats/map.py) |
| Every section, read and written from one layout each (records, nested lists, scripts, objects) | [sections.py](../../../../../src/mapworkshop/formats/sections.py) |
| Heights, texture planes and blend/cliff/edge tables | [terrain.py](../../../../../src/mapworkshop/formats/terrain.py), [terrain evidence](../../terrain-and-presentation/terrain.md) |
| Script inspection and operand layouts | [scripts.py](../../../../../src/mapworkshop/formats/scripts.py), [script reference](../../scripts/README.md) |
| Lighting | [lighting.py](../../../../../src/mapworkshop/formats/lighting.py) |
| Bases | [castles.py](../../../../../src/mapworkshop/formats/castles.py), [base/library evidence](../../players-economy-and-ai/bases.md) |
| Cache convention | [cache.py](../../../../../src/mapworkshop/mapkit/cache.py) |
| Observed corpus and constraints | [Coverage reference](../reference.md), [measured file offsets](../format.md) |
| Source attribution | [Third-party notices](../../../licenses/THIRD_PARTY.md): OpenSAGE, EA source and OpenBFME2 |

The local corpus comprises 67 maps from Maps.big, 152 base documents and 51 library
maps. The source/behavior references record which claims are corpus observations,
source-derived interpretations, synthetic fixtures or native tests. Unresolved
semantics remain unresolved even where the byte layout is fully consumed.

Inspection, from an installed checkout:

```powershell
python -m mapkit.analyze 'path/to/map.map' --out local/artifacts/map-analysis.json
python -m mapkit.coverage 'path/to/Maps.big' --out local/artifacts/map-coverage.json
```

The analyzer is read-only. Its JSON exposes chunk versions/sizes/offsets,
decoded records, unresolved sections and exact decompressed round-trip status.
`mw test --corpus` checks the writers: every section of all 270 documents,
decoded and encoded again through `formats.sections`, gives back its exact bytes.
Reports and licensed input files stay local; the repository distributes the
specification, independent tooling and original test fixtures.
