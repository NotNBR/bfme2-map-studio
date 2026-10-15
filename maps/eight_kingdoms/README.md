# Eight Kingdoms

`build.py` builds this map, with `terrain.py`, `materials.py`, `scenery.py`, `vegetation.py` and `presentation.py`.

```
mw build eight-kingdoms     build it
mw view eight-kingdoms      look at it in the viewer
mw play eight-kingdoms      install it into the game and start BFME2
```

An eight-player BFME2 battlefield following the supplied references: eight outer
kingdoms, winding waterways, mountain-framed shores, a raised central citadel and
two small sanctuary islands. The kingdoms occupy a 900 x 960 tile region covering
9,000 x 9,600 world units. Surrounding ocean expands the active map to 1,140 x 1,200
tiles. Twenty-four native stone bridges link the realms and their inner passes.
There are eight neutral outposts, eight warg lairs, two inns and a central signal
fire. Starting terrain is graded across a 550-unit radius; a clear 300-unit
fortress core and two additional building pockets leave room among the foliage.

## Terrain authoring

The two reference images were supplied by NotNBR and confirmed as AI-generated
on 8 October 2026. See the [media provenance notes](../../docs/licenses/README.md#media-provenance).

See the [heightmap workflow](heightmap.md) for source-image
processing, grid orientation, native elevation precision and rebuild outputs,
and the [map-file specification](../../docs/format/README.md) for binary sections.

The source document begins as an empty native plane; no stock `.map` landscape
is loaded. `reference-height.jpg` supplies relative elevation and coastline
shape. The header/legend are excluded and small disconnected text fragments
are removed. Bright point markers are softened before elevation conversion.
The colored reference guides woodland groups and the landmark composition.

The native map uses 16-bit elevations. Erosion softens local slopes. Cleared
starts, curved routes, building foundations, bridge banks and underwater bridge
beds are authored separately. Native walk-on-wall bridge models supply deck
and ramp geometry. The grayscale image's shading is an artistic elevation guide.

The terrain plan and minimap are diagnostic cartography generated from the map
data. Native screenshots are kept separately as evidence of the game's appearance.
The detail palette uses green meadow and woodland textures, natural grey cliff
rock, scree below exposed slopes, shaded forest soil and snow on high, gentler
surfaces. Steep river banks use rock instead of grass. Native terrain projection
is retained; the custom cliff projection trial was rejected after a render check.

Dark natural boulders and smaller fragments form downhill rockfall fans at cliff
toes. Leafy valley woods blend into evergreen foothills, with undergrowth and
sparse fringes. Ruins, street-aligned buildings, broken boundaries and debris
compose small scenes around neutral settlements. Each site has seeded variation
in setbacks, orientation, building choices and missing boundary sections.
Full sampled scenery footprints are checked against water, blocked terrain,
route clearance, local relief and reserved starting space;
building plots can move locally to find a sound foundation.
Each base has three uneven vegetation pockets, with leafy trees, shrubs, ferns,
grass and occasional stumps. Their size and position vary by a fixed seed.
The inner 300 units and two 140-unit-radius building pockets remain clear;
vegetation can grow inside the former 550-unit exclusion. Subtle meadow texture
variation softens the old uniform grass circles. Small shrub, grass and stone
groups also follow woodland edges and rocky shoulders elsewhere on the map.
`detail-placement.json` records placements and foundation checks. The two internal bridges are removed. Their gaps remain as irregular water-filled rocky hollows with sloping banks.

The native terrain grid grows to 1,200 x 1,260 samples. A 1,200-world-unit ocean
margin surrounds the original kingdom region inside the active boundary, with
another 30 border tiles beyond it. The original relief is retained apart from those two reshaped hollows;
all objects and test cameras receive the same 1,200-unit X/Y translation.
Scenery audit coordinates are local to the kingdom region; `build.json` records
the translation as `world_coordinate_offset`. No custom ocean model or shader is
required. The map is finite, so sufficiently distant or off-center views can
still reach its outer edge. Larger trials exceeded native graphics-memory limits and are not distributed.

## History

The launch presets, native checks, captures and recorded builds made with
bfme-workshop, the repository this one grew out of, are in
[its history](../../docs/history/eight-kingdoms.md).
