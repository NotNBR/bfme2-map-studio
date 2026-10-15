# Terrain textures: blends and cliffs

How the game blends terrain textures and maps them onto cliffs, and what
`mapkit.blank.set_materials` and `mapkit.cliffs` write accordingly. The byte
layouts are in the [terrain specification](../format/terrain.md); how the
renderer draws them, in [the renderer's terrain](renderer/terrain.md).

WorldBuilder's terrain implementation is partly available through EA's released
Generals/Zero Hour source. It is a useful guide to the SAGE editor, but is not a
BFME2 WorldBuilder source release; its record layout was checked against BFME2
files before its terminology was used here.

## Where to look

| Source | Useful entry points |
|---|---|
| [EA WorldBuilder](https://github.com/electronicarts/CnC_Generals_Zero_Hour/tree/main/GeneralsMD/Code/Tools/WorldBuilder/src) | `BlendEdgeTool.cpp` handles the brush gesture; `WHeightMapEdit.cpp` contains `blendSpecificTiles`, `doCliffAdjustment`, `updateForAdjacentCliffs`, `adjustForTiling`, and serialization. |
| [EA terrain renderer](https://github.com/electronicarts/CnC_Generals_Zero_Hour/blob/main/GeneralsMD/Code/GameEngineDevice/Source/W3DDevice/GameClient/WorldHeightMap.cpp) | `getAlphaUVData` connects blend fields to corner alpha and triangle orientation. Masks are defined in the adjacent `TileData.h` header. |
| [OpenSAGE map schemas](https://github.com/OpenSAGE/OpenSAGE/tree/master/src/OpenSage.Game/Data/Map) | `BlendDescription`, `BlendTileData`, and `CliffTextureMapping` independently describe the serialized fields, retaining uncertainties across games. |
| [Open-BFME-2](https://github.com/Open-BFME/Open-BFME-2) | Reconstructed runtime code and verification ledgers. Some terrain files are inherited Generals code: their presence alone does not establish BFME2 equivalence. |

Local Open-BFME-2 revision inspected: `33f02e4222f3ac9c284d9b71cf5e7438799988bb`.
A BFME2 WorldBuilder executable round-trip remains unverified.

A read-only audit of the 67 retail maps found 1,120,750 blend records and
40,692 cliff mappings (in 8 maps), all four blend directions, blend flags 0-3,
every custom edge class `-1` and every edge table empty
([audit](../history/bfme-workshop-experiments.md#terrain-records-audit)).

## Blends

With `corner_blends`, the material writer (`mapkit.blank.set_materials`)
emits diagonal and long-diagonal blends and uses the three-way layer, following
the byte-matched BFME 2 code in Open-BFME-2:

- `getPointerToTileData` (0x000AED2E) composites the base tile, the primary
  blend, then the three-way blend, each through one of the 64x64 alpha tiles
  of `setupAlphaTiles` (0x000AC6F9). The three-way layer needs
  `Use3WayTerrainBlends` (on in BFME 2's GameData.ini) and is skipped on cells
  without a primary blend or on cliff cells.
- The tile is composited per pixel, so WorldBuilder's coordination of triangle
  orientation between layers (inherited from Generals) does not matter. Its
  forced-flip flag bit (2) is harmful: `getRGBAlphaDataForWidth` (0x000AC6A6)
  tests the whole flag byte, so a flip-only record gets the inverted ramp.
  The loader keeps the bit while three-way blends are on. Several thousand
  stock-map cells carry flip-only primary blends.
- No alpha tile covers all four corners. A cell whose four corners a higher
  texture touches therefore takes that texture (`fill_enclosed`), as
  WorldBuilder converts mostly-surrounded cells; otherwise it shows as a
  sharp square.

The writer puts the highest neighbouring texture in the three-way layer and
the next one in the primary layer, never writes the flip bit, and writes
opposite corners of one texture as a single-corner blend in each layer.

WorldBuilder's cliff correction also has neighbouring-cell seam matching and
tiling logic. Do not directly transplant its legacy height/texture scaling into
BFME2's 16-bit terrain; `mapkit.cliffs` (below) measures its own.

## Cliff mapping

`mapkit.cliffs` writes cliff records for steep cells
(`set_materials(..., cliffs=steep_cells(heights))`): each cell's corners are
projected onto the vertical plane along its face, U along the face and V up
it, at the stock maps' density (0.155 UV per cell of surface length for
4-tile textures, measured over the 8 stock maps with cliff records). The face
direction is smoothed over neighbouring cells and taken in 45-degree steps;
neighbouring cells share their corner UVs exactly.

The game applies a record only when its tile's texture is the cell's own
(getUVForTileIndex, 0x000AE490), and builds the cliff texture from the first
record's texture alone (0x000AEAA6), so one texture per map is mapped. Mapped
cells take no blends (0x000ABD19), so the cliff texture goes last in the
palette and blends over its unmapped neighbours.

Native checks (15 October 2026, `maps/cliff_lab`, Medium): a map with 138,033
records loads; mapped faces take the projected texture instead of the
stretched one; triangle flip and the record's tile do not change the result.
Open: a dark vertical band of one cell column shows on some mapped faces in
the game but not in the renderer. It moves when every U is shifted by half a
repeat, so it depends on where in the texture a cell falls; WorldBuilder keeps
each cell's U inside the texture's width (`adjustForTiling`), which the
module does not yet do.
