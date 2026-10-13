# Section directory and versions

[Specification index](../specification.md) · [Previous](binary-container.md) · [Next](terrain.md)

The corpus has **23 top-level names / 43 name-version combinations** in **270
documents**. The versions below are observed, not a whitelist of every legal
version. Some implementation branches additionally have source/synthetic coverage.

| Section | Observed versions | Payload family |
| --- | --- | --- |
| `HeightMapData` | 5 | Terrain dimensions and elevations |
| `BlendTileData` | 8, 9, 11, 14, 15, 16, 17, 18 | Material/index/flag planes and descriptor tables |
| `WorldInfo` | 1 | `props` |
| `ObjectsList` | 3 | `Object` child chunks |
| `MPPositionList` | 0 | `MPPositionInfo` child chunks |
| `SidesList` | 5, 6 | Sides and embedded build lists |
| `Teams` | 1 | Counted `props` |
| `BuildLists` | 1 | Counted faction build lists |
| `CastleTemplates` | 1–5 | Base-template buildings and paths |
| `LibraryMapLists` | 1 | `LibraryMaps` child chunks |
| `PlayerScriptsList` | 1, 5, 6 | `ScriptList` child chunks |
| `WaypointsList` | 1 | ID-to-ID links |
| `TriggerAreas` | 1 | Named polygons |
| `PolygonTriggers` | 4, 5 | Legacy trigger/water polygons |
| `StandingWaterAreas` | 2 | Water polygons |
| `RiverAreas` | 1, 2 | River cross-sections |
| `StandingWaveAreas` | 1, 2 | Shore-wave geometry/parameters |
| `GlobalLighting` | 7, 8 | Four lighting configurations and extension fields |
| `PostEffectsChunk` | 1 | Counted effect records, **u8 count** |
| `EnvironmentData` | 2, 3 | Water-alpha/macro/cloud settings |
| `NamedCameras` | 2 | Camera bookmarks |
| `CameraAnimationList` | 1, 3 | Animation tracks |
| `SkyboxSettings` | 1 | Skybox transform and scheme |

Typical modern generated skirmish documents contain all of these except
`CastleTemplates`, `PolygonTriggers` and `SkyboxSettings`; many counted lists
are empty. This describes the constructor profile, **not a proven minimal
mandatory-section set**. Context matters for base/library documents.
