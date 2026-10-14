# Terrain and presentation

Build elevation, materials and scenery first, then apply water, lighting and
camera choices. Visual appearance and gameplay passability are separate concerns.

| Topic | Reference and current support |
| --- | --- |
| Heights | [Heightmap import](heightmaps.md), world/sample conversion, borders and elevation limits |
| Textures, blends and cliffs | [Terrain records](terrain.md), palette/index inspection, original material authoring and native test panels |
| Water and shores | [Stored geometry](../file-structure/reference.md#trigger-and-water-geometry); standing-water writer and [depth tests](../navigation/README.md); [rivers, shore waves and shipwrights](rivers-and-waves.md) |
| Lighting | [Versioned lighting](lighting.md), original writer and native field readback |
| Objects and scenery | [Creation workflow](../../../map-workflow.md); template assets, footprint and behavior come from the installed game |
| Environment and cameras | [Environment](../file-structure/reference.md#environment-and-lighting) and [camera layouts](../file-structure/reference.md#cameras); semantic coverage is partial |
| Diagnostic graphics | [Reusable map graphics](graphics.md): placement atlases, equal-scale forest samples, terrain plans and design overlays |
| Screenshots | [Reproducible native capture](../compatibility/screenshots.md) with map hashes and camera settings |

One terrain sample step is **10 world units**. World coordinates exclude the
border; stored elevation is `uint16 × 0.0390625`. A heightmap is an elevation
input, not a complete map: materials, navigation, objects, starts and gameplay
still need authoring. See the guides before resizing or importing an image.

## Remaining work

- Rhûn's border-only texture IDs, custom edges and arbitrary cliff/blend seams.
- River and wave authoring, shore interactions, weather and environment effects.
- Lighting's third array and unresolved extension-field semantics.
- Camera interpolation, focal parameters and complete cinematic authoring.
- Mixed-feature visual examples beyond the existing terrain and lighting labs.

Do not infer a forest speed penalty from trees, or an impassable mountain from
its height. The [navigation experiments](../navigation/README.md) document the
behavior actually observed in the game.
