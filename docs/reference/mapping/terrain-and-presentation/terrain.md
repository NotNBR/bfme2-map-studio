# WorldBuilder terrain: source and verified records

WorldBuilder's terrain implementation is partly available through EA's released
Generals/Zero Hour source. It is a useful guide to the SAGE editor, but is not a
BFME2 WorldBuilder source release. This investigation checks its record layout
against BFME2 files before using its terminology in our tools.

## Where to look

| Source | Useful entry points |
|---|---|
| [EA WorldBuilder](https://github.com/electronicarts/CnC_Generals_Zero_Hour/tree/main/GeneralsMD/Code/Tools/WorldBuilder/src) | `BlendEdgeTool.cpp` handles the brush gesture; `WHeightMapEdit.cpp` contains `blendSpecificTiles`, `doCliffAdjustment`, `updateForAdjacentCliffs`, `adjustForTiling`, and serialization. |
| [EA terrain renderer](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngineDevice/Source/W3DDevice/GameClient/WorldHeightMap.cpp) | `getAlphaUVData` connects blend fields to corner alpha and triangle orientation. Masks are defined in the adjacent `TileData.h` header. |
| [OpenSAGE map schemas](https://github.com/OpenSAGE/OpenSAGE/tree/master/src/OpenSage.Game/Data/Map) | `BlendDescription`, `BlendTileData`, and `CliffTextureMapping` independently describe the serialized fields, retaining uncertainties across games. |
| [Open-BFME-2](https://github.com/Open-BFME/Open-BFME-2) | Reconstructed runtime code and verification ledgers. Some terrain files are inherited Generals code: their presence alone does not establish BFME2 equivalence. |

Local Open-BFME-2 revision inspected: `33f02e4222f3ac9c284d9b71cf5e7438799988bb`.
The initial source audit did not include a renderer test. A subsequent isolated
native experiment is recorded below. A BFME2 WorldBuilder executable round-trip
remains unverified. The existing Eight Kingdoms map was not regenerated.

## The terrain tail

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

## Retail check, 8 October 2026

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

## What this changes for our maps

Our material writer currently emits one cardinal blend per cell. Native records
also support diagonal and third-layer blends. The editor coordinates triangle
orientation between layers, so adding a third texture needs more than another
palette index.

Cliff correction also has neighbouring-cell seam matching and tiling logic.
Do not directly transplant its legacy height/texture scaling into BFME2's
16-bit terrain. Use the isolated test map below, source comparisons and native
tests on adjoining slopes before enabling a new projection on Eight Kingdoms.

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

See [map-file structure](../file-structure/format.md) for the surrounding container and
[heightmap workflow](heightmaps.md) for elevation authoring.

The isolated test generator and repeatable capture command are documented in
[native screenshots](../compatibility/screenshots.md).
