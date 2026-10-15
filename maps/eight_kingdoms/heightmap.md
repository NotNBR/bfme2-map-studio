# Eight Kingdoms: the heightmap

Eight Kingdoms builds native terrain from the supplied grayscale illustration.
The importer is currently specific to that reference image; there is no general
CLI for arbitrary grayscale or 16-bit heightmap inputs.

## Source and implementation

- [Reference height image](references/reference-height.jpg): relative elevation and coastline.
- [Terrain conversion](terrain.py): image cleanup, elevation generation and playable terrain shaping.
- [Build orchestration](build.py): reference crop, water level, native document and previews.
- [Map settings](map.toml): dimensions, borders and deterministic seed.
- [Native terrain writer](../../src/mapworkshop/mapkit/blank.py): `set_heights` and material planes.

The colored reference guides scenery composition. It is not used as a texture
stretched over the terrain. Native terrain materials and placed assets are
authored separately in the project's `materials.py` and `scenery.py`.

## Image-to-terrain pipeline

1. Convert the source to 8-bit grayscale. Repair the title-obscured northwest
   outline using the corresponding southern outline, then crop to pixel bounds
   `(8, 24, 1148, 1256)` to exclude the legend and compass.
2. Resize to 900 columns by 960 rows using bilinear sampling. Blur brightness
   markers before elevation conversion. Flip vertically to match world Y.
3. Derive land from luminance greater than 53, remove disconnected components
   smaller than 250 pixels, close small outline cracks and soften shorelines.
4. Convert relative brightness to relief, add seeded broad and fine terrain
   noise, and run six thermal-erosion iterations. The water level is 60 world
   units, ordinary ground is 160, and the sea floor starts at 20. These values
   and the nonlinear brightness-to-relief curve are implementation constants,
   not image metadata or CLI parameters.
5. Grade routes, starting clearings, bridge banks and building foundations.
   Lower bridge beds beneath native bridge models. Preserve the two internal
   water hollows with irregular banks. Derive slopes and terrain traversal flags.
6. Write elevations into `HeightMapData`, then author texture/blend planes,
   water geometry, objects and the remaining native map sections.

The source is an artistic illustration: highlights and printed markers are not
physical altitude measurements. The playable result deliberately includes the
terrain corrections above instead of interpreting every bright pixel literally.

## Grid, orientation and native precision

Arrays use `[row_y, column_x]`, with 10 world units between terrain samples.
The 900 x 960 kingdom region is initially padded by 150 samples on each side,
giving a stored grid of 1,200 columns by 1,260 rows. The final build reduces the
native border to 30 samples, exposing the surrounding ocean, and translates
world placements by +1,200 units in X and Y. It does not resample the terrain
when exposing that margin.

Native elevations are unsigned 16-bit little-endian samples:

```text
stored_height = round(world_z / 0.0390625)
world_z       = stored_height * 0.0390625
```

`set_heights` requires the existing document's exact grid shape, finite values,
and elevations between 0 and 2559 world units. The current image ingestion still
starts from 8-bit luminance; writing 16-bit native values does not recover source
detail lost during that conversion.

## Rebuild and inspect

From the repository root, using the configured project Python environment:

```powershell
mw build eight-kingdoms
```

The latest build is in `local/build/eight-kingdoms/`, and every build keeps its
own folder in `local/history/eight-kingdoms/<time>/`:

- `map/`: the generated native map and its map assets.
- `heightmap.png`: grayscale diagnostic elevation preview.
- `terrain-overview.png` and `layout.png`: terrain and layout checks.
- `report.json`: reference and map hashes and build audits; `build.json`: the build record.

The preview uses `round(clamp((z - 20) / 720, 0, 1) * 255)` and flips vertically
for image display. It is an 8-bit visualization, **not a lossless export** of the
native elevation samples.

To adapt another source image, change the reference, crop and title-repair logic
in the project code, then review the land threshold, elevation curve and authored
routes/starts. Simply replacing the JPEG is not a supported general import
workflow. A reusable importer would need explicit crop/orientation, elevation
range, water level and source bit-depth handling.

Grid audits do not establish that every crossing works for native hordes. See
the [map's verification scope](../../docs/history/eight-kingdoms.md#verification-scope)
for the native checks completed so far.

## How this relates to a `.map` file

The heightmap supplies only terrain elevations. A complete map also needs
materials and traversal planes, asset placements, player starts, water and other
versioned sections. See the [map-file specification](../../docs/format/README.md) for the binary
container, chunk headers, `HeightMapData`, `BlendTileData`, objects and properties.
