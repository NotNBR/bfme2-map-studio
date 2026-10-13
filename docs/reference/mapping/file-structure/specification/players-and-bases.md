# Players, teams, libraries and bases

[Specification index](../specification.md) · [Previous](objects-and-waypoints.md) · [Next](scripts.md)

## MPPositionList v0

Consecutive `MPPositionInfo` chunks, no leading count:

```text
MPPositionInfo v0: u8 human, u8 computer, u32 team
MPPositionInfo v1: u8 human, u8 computer, u8 loadAI, u32 team,
                  u32 restrictionCount, str sideRestrictions[restrictionCount]
```

The constructor emits eight multiplayer slots even for a two-start map. Slot
count, number of starts, side count and active players are different quantities.

## SidesList v5/v6 and Teams v1

```text
SidesList:
  if version >= 6: u8 leadingBooleanRaw
  u32 sideCount
  repeat sideCount:
    props side
    u32 buildEntryCount
    BuildEntry entries[buildEntryCount]

Teams:
  u32 teamCount
  props teams[teamCount]
```

The leading side byte's purpose remains unresolved. Side properties include
player name, faction, display name, human flag, allies and enemies. Teams use
names and owners, not object-list indices. Neutral/supporting sides occur beside
playable sides. The matched retail side reader supports at most 20 sides;
that is a side-reader constraint, not 20 playable multiplayer slots.

## BuildLists v1 and BuildEntry

```text
u32 factionCount
repeat factionCount:
  nameKey faction
  u32 entryCount
  BuildEntry entries[entryCount]

BuildEntry:
  str buildingName
  str template
  vec3 position
  f32 angle
  u8 initiallyBuilt
  u32 rebuilds
  str script
  i32 health
  u8 whinerRaw, u8 unsellable, u8 repairable
```

This is the BFME **map** build-list record, not the larger savegame struct or
another SAGE game's same-numbered section. The matched embedded-side reader
consumes XYZ but uses runtime Z=0; the standalone faction-list reader retains Z.
Source interprets `0xffffffff` rebuilds as unlimited. Wider execution behavior
and `whinerRaw` remain unresolved.

## LibraryMapLists v1 / LibraryMaps v1

Outer payload is a sequence of `LibraryMaps` child chunks. Each child contains
`u32 mapCount`, then `str mapNames[mapCount]`. Keep list slots aligned with the
side/script contexts. Library linking merges scripts/teams; a name string does
not itself contain the referenced library's records. See [base/library semantics](../../players-economy-and-ai/bases.md).

## CastleTemplates v1–5

```text
nameKey faction
u32 buildingCount
repeat buildingCount:
  str buildingName, str template
  vec3 relativePosition
  f32 angle
  if version >= 4: i32 priority, i32 phase
if version >= 2:
  u32 pathCount
  repeat pathCount:
    if version >= 5: str pathName
    u32 pointCount
    if version == 2: i32[3] points[pointCount]
    if version >= 3: vec2 points[pointCount]
```

Coordinates are relative to the base center. The matched retail chunk reader
discards stored priority/phase, path names and old points' third integer; preserve
them for other consumers. Writing this chunk alone does not create a working AI
base. Original objects, selection properties, definitions and AI rules also matter.
