# BFME II map-file specification

**Revision:** 9 October 2026. **Target:** the BFME II 1.06 map family.

This is an implementation-oriented description of the files that make up a map:
their encodings, binary records, relationships and external dependencies. It is
an independently reconstructed specification, not an official EA specification.
It describes all section/version combinations observed in the workshop's local
corpus; unknown meanings and untested variants are explicitly identified.

The principal reference is the serialized data, supported by repository readers,
retail-file comparisons and recorded engine observations. A decoded field is not
automatically a fully understood gameplay feature. Tool limits below are not
claimed engine limits.

## Chapters

Read in order for a complete format walkthrough, or open the relevant section.
Each chapter links to the previous and next one. This index is the stable entry
point; the byte-level details live in the files below.

| Chapter | Contents |
| --- | --- |
| 1. [Files and dependencies](files.md) | Map package, sidecars, archives and external assets |
| 2. [Binary encoding and container](binary-container.md) | Numbers, strings, EAR/RefPack, CkMp, chunks and properties |
| 3. [Section directory and versions](sections.md) | Observed section names, versions and payload families |
| 4. [Terrain](terrain.md) | Height samples, material/flag planes, blends, edges and cliffs |
| 5. [World settings, objects and waypoints](objects-and-waypoints.md) | WorldInfo, Object records, roads and waypoint links |
| 6. [Players, teams, libraries and bases](players-and-bases.md) | Sides, slots, ownership, build lists and castle templates |
| 7. [Scripts](scripts.md) | Nested script chunks, operations, typed arguments and version differences |
| 8. [Triggers and water](triggers-and-water.md) | Trigger polygons, standing water, rivers, waves and legacy polygons |
| 9. [Lighting, environment and cameras](presentation.md) | Light arrays, environment, post effects, bookmarks and animation tracks |
| 10. [Constraints, example and evidence](constraints-and-evidence.md) | Reference consistency, worked hex example, implementation and evidence |

Alongside the chapters:

| Page | Contents |
| --- | --- |
| [Coverage and authoring rules](coverage.md) | What the readers were checked against (270 retail documents, 23 sections, 43 section/version pairs) and the rules a writer must keep |
| [Lighting](lighting.md) | GlobalLighting in detail: what the reader does with each field |
| [Inspecting map files](tools.md) | The analyzer, the corpus surveys and `mw test --corpus` |

Every observed layout has a decoder and an encoder, from one layout per section
in [formats/sections.py](../../src/mapworkshop/formats/sections.py). What the
game does with the data is in [how BFME2 behaves](../game/README.md).
