# World settings, objects and waypoints

[Specification index](../specification.md) · [Previous](terrain.md) · [Next](players-and-bases.md)

## WorldInfo v1

Payload: one `props` dictionary. Used keys include `mapName`, `mapDescription`,
`cameraMaxHeight`, pitch/yaw, camera-ground fields, weather and scenario flags.
These are typed properties, not a fixed struct. Missing keys can rely on game
defaults. Do not infer terrain elevation from camera-ground settings or assume
the `compression` property overrides the actual outer file signature.

## ObjectsList v3 / Object v3

`ObjectsList` contains consecutive `Object` child chunks, **without a count**.
Each modern `Object` payload is:

| Offset | Type | Field |
| ---: | --- | --- |
| 0 | `vec3` | World X/Y and terrain-relative Z offset |
| 12 | `f32` | Orientation in radians |
| 16 | `u32` | Object/road flags |
| 20 | `str` | Object or road template name |
| variable | `props` | Placement properties |

Object definitions, models, footprint, collision and behavior are external game
data. Common properties include `uniqueID`, `objectName`, `originalOwner`,
`objectLayer`, health and enabled state. These names are not interchangeable:
`objectName` is used by named script references; `uniqueID` is placement identity;
`originalOwner` commonly combines a player and team path.

Road segments use adjacent start/end objects with flags `0x02` and `0x04`, same
template name. Modifier bits `0x08/0x40/0x80` have source-derived corner/join
interpretations; native modifier rendering remains incomplete. Preserve all
other bits. A `GondorIthilienBridge2` is instead one ordinary walk-on-wall object.
See [road/bridge evidence](../../navigation/roads-and-bridges.md) before conflating
these with the source-family `0x10/0x20` paired bridge format.

## Waypoints

Waypoint **positions** are `Object v3` records with template
`*Waypoints/Waypoint` and properties such as `waypointID`, `waypointName` and
`waypointTypeOption`. Skirmish starts conventionally use `Player_1_Start` etc.

`WaypointsList v1` stores **links**, not waypoint positions:

```text
u32 linkCount
repeat linkCount: i32 startID, i32 endID
```

IDs refer to waypoint object properties. Reordering objects is different from
renumbering waypoint IDs. Script references may use waypoint names instead.
