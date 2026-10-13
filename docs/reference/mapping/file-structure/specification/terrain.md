# Terrain

[Specification index](../specification.md) · [Previous](sections.md) · [Next](objects-and-waypoints.md)

## HeightMapData v5

```text
u32 W                              # samples including border
u32 H                              # samples including border
u32 B                              # border width in samples
u32 borderRecordCount
u32[2] borderRecords[borderRecordCount]
u32 A                              # must equal W * H
u16 elevations[H][W]               # row-major, X changes fastest
```

The payload length is `20 + 8*borderRecordCount + 2*W*H`. The modern constructor
emits one border record `(W-2B, H-2B)`. Preserve multiple records when reading;
their broader runtime interpretation is not established here.

```text
world Z = elevationSample * 0.0390625
sample X = world X / 10 + B
sample Y = world Y / 10 + B
playable dimensions = (W - 2B, H - 2B) samples
reported world extent = ((W - 2B)*10, (H - 2B)*10)
```

Elevation storage spans `0 .. 2559.9609375` world units. World positions do not
include the border offset. Row-major storage does not imply screen-image Y
orientation; diagnostic images flip rows when presenting a top-down view.
Dimension guards in the parser/writer are tool policy, not proven engine maxima.

## BlendTileData v18 planes

Read `u32 A`, matching the heightmap area, then these planes in order:

| Plane | Stored size | Role |
| --- | --- | --- |
| `tiles` | `u16[A]` | Primary terrain subtile IDs |
| `blends` | `u32[A]` | Blend table indices |
| `three_way` | `u32[A]` | Additional blend indices |
| `cliffs` | `u32[A]` | Cliff-mapping indices |
| `impassable` | packed bits | General blocked plane |
| `impassable_players` | packed bits | Source-labelled player plane; scripted orders differ from assumed semantics |
| `passage_widths` | packed bits | Source-labelled plane; full meaning unresolved |
| `taintable` | packed bits | Source-labelled plane |
| `extra_passable` | packed bits | Does not override `impassable` in recorded tests |
| `flammability` | `u8[A]` | Byte plane; full value semantics unresolved |
| `visible` | packed bits | Source-labelled plane |

Each packed plane occupies `H * ceil(W/8)` bytes. Each row is padded separately;
the low bit represents the first X sample in that byte. Never pack all `W*H`
bits as one uninterrupted bitstream unless row widths are byte-aligned.

For legacy versions, the four index planes remain in the same order, but
blend/three-way/cliff indices are `u16` before v14 and `u32` from v14. Optional
planes are introduced at versions: impassable 8, players 10, passage 11,
taintable 14, extra-passable 15, flammability 16, visible 17. This describes the
implemented v8–18 layout family; v10/12/13 are not observed in the audited corpus.
Legacy decoding does not imply support for editing those versions.

## BlendTileData descriptor tail

Immediately after the final plane:

```text
u32 textureCellCount
u32 declaredBlendCount
u32 declaredCliffCount
u32 textureClassCount
repeat textureClassCount:
  u32 firstCell
  u32 cellCount
  u32 cellSize
  u32 reserved                    # observed/required zero in current parser
  str textureName
u32 edgeCellCount
u32 edgeClassCount
repeat edgeClassCount:
  u32 firstCell
  u32 cellCount
  u32 cellSize
  str textureName
BlendRecord[max(declaredBlendCount-1, 0)]
CliffRecord[max(declaredCliffCount-1, 0)]
```

Ordinary texture descriptors satisfy `cellCount == cellSize²` in the supported
profile. Each bitmap cell has four subtiles. Plane IDs address subtiles across
the sequential descriptor palette; descriptor `firstCell` is not an arbitrary
filename index. The current mapping uses a cumulative `4*cellCount` subtile span
per texture. Within a repeating class of size `S`, phase is:

```text
4 * (((y // 2) % S) * S + (x // 2) % S) + (y % 2)*2 + x % 2
```

Blend/cliff index zero means no record. Declared counts normally include this
implicit zero slot; stored records begin at index 1. A zero declared cliff count
also occurs and is treated as an empty table. Edge-table nonempty layouts have
synthetic/source coverage, not a confirmed nonempty retail example here.

`BlendRecord` is **18 bytes**:

| Offset | Type | Field |
| ---: | --- | --- |
| 0 | `u32` | Secondary subtile ID |
| 4 | 4 bytes | Horizontal, vertical, right-diagonal, left-diagonal switches |
| 8 | `u8` | Flags: source bit 0 invert, bit 1 force flip; retain other bits |
| 9 | `u8` | Long-diagonal/two-sided raw value |
| 10 | `i32` | Custom edge-class index; `-1` = none |
| 14 | `u32` | Observed marker `0x7ada0000` |

`CliffRecord` is **38 bytes**: `u32 subtile`, four `vec2` UV coordinates, `u8 flip`,
`u8 mutant`. Source corner order is `(x,y), (x+1,y), (x+1,y+1), (x,y+1)`.
These are texture mappings, not gameplay cliff objects or automatic barriers.

**Preserved exception:** Rhûn has 711 out-of-palette primary IDs, all outside
the playable rectangle. Inspection retains/reports them; authoring guards reject
them. Their intended meaning is unresolved. Do not silently clamp retail data.
