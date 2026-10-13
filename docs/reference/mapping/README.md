# BFME2 mapping

Tools and reference material for creating original **BFME II 1.06** maps without
depending on WorldBuilder. The aim is to understand the file format, authoring
rules and engine behavior well enough to use each supported feature deliberately.

Playable maps can already be built from scratch. The observed file layouts are
covered; the full set of gameplay rules and authoring features is still in progress.

| Area | Contents | Current state |
| --- | --- | --- |
| [File structure](file-structure/README.md) | Containers, sections, properties, versions and references | All observed layouts across 270 map/base documents decode and round-trip |
| [Terrain and presentation](terrain-and-presentation/README.md) | Heightmaps, textures, blends, cliffs, water, lighting and cameras | Core authoring and selected native tests; advanced visual rules remain |
| [Navigation](navigation/README.md) | Passability, slopes, roads, bridges, collision and placement | Controlled movement tests; building placement and formations remain |
| [Scripts](scripts/README.md) | Script trees, typed arguments, conditions, actions and scenarios | 595 action and 195 condition signatures; limited behavior coverage |
| [Players, economy and AI](players-economy-and-ai/README.md) | Starts, teams, ownership, bases, build lists and libraries | Basic scenarios and format tooling; broad gameplay/AI validation remains |
| [Compatibility](compatibility/README.md) | Installation, evidence, screenshots, multiplayer, save/load and limits | Local native evidence documented; further checks paused |

## Start here

- **Understand the files:** read the [technical map-file specification](file-structure/specification.md)
  for binary layouts, encodings, sections, versions and companion files.
- **Create a map:** follow the [creation workflow](../../map-workflow.md), then the
  [heightmap guide](terrain-and-presentation/heightmaps.md) if importing terrain.
- **Inspect an existing map:** use the [file-format tools](file-structure/README.md)
  and [versioned reference](file-structure/reference.md).
- **Find implementation:** serializers are in `src/mapworkshop/formats/`, reusable
  authoring and feature labs in `src/mapworkshop/mapkit/`, and individual maps in
  [`maps/`](../../../maps).
- **Understand evidence:** consult [compatibility and validation](compatibility/README.md).

## What remains

1. Terrain blend/cliff exceptions, river and shore behavior, weather and cameras.
2. Building placement, collision, formations, bridge variants and destruction.
3. Script groups, difficulty, wider opcode behavior, objectives and cinematics.
4. Economy, diplomacy, victory rules and sustained AI base/attack behavior.
5. Normal-menu discovery, multiplayer, save/load, performance and patch differences.

Detailed gaps live with each area. Compatibility checks are paused as of
**9 October 2026**; this documentation records the existing results, not a claim
that those remaining checks passed.

A capability needs **read, understand, write, validate and document** coverage.
A byte-perfect round-trip proves preservation; a signature catalogue proves
argument shape; a screenshot proves a rendered view. None alone proves complete
gameplay behavior. Engine limits and unsupported cases remain explicit.
