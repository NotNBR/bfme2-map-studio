# Map graphics

Generate placement comparisons and terrain plans from native BFME2 map data,
without modifying the map or launching the game. The tool uses NumPy and Pillow,
already available in the project's Python environment.

Implementation: `src/mapworkshop/mapkit/graphics.py`. It supports current and legacy terrain
records through the shared native inspection reader.

## Generate one map

From the repository root:

```powershell
mw graphics `
  --map 'local/build/greywater-marches/map mp bfmexbar greywater marches.map' `
  --name 'Greywater Marches' --out 'local/renders/map-graphics/greywater'
```

Choose a new output directory for each map revision. A nonempty output directory
requires `--overwrite`; this replaces generated outputs without deleting unrelated
files. The source maps, INIs and archive contents are never edited.

## Outputs

| File | What it shows |
| --- | --- |
| `index.html` | Local gallery, measurements, legends and links to every graphic |
| `placement-atlas.png` | Whole-map tree/object positions, water, height relief and starts; each map fits its own panel |
| `equal-scale-forest-patches.png` | Locally dense forest samples, all at the same world scale |
| `metrics.json` | Source paths and SHA-256 hashes, object counts, spacing, species, palettes and output settings |
| `<map-name>/terrain-plan.png` | Shaded material categories, contours, numbered starts, scenery, stored roads and optional design overlays |
| `<map-name>/terrain-overview.png` | Material-category relief with scenery and water, without planning annotations |
| `<map-name>/heightmap.png` | Border-free elevation, individually normalized to 8-bit grayscale |
| `<map-name>/slope.png` | Geometric steepness: green low, red high; rise/run capped at 1.5 for coloring |
| `<map-name>/passability.png` | Stored impassable terrain flags in red, other cells green, water blue |

Open `index.html` in a browser or inspect the PNGs directly. Keep the folder
together: the HTML uses relative image links. A one-map run also produces the
atlas and equal-scale patch, so the same workflow covers individual maps and
comparisons.

## Compare maps, including originals

Use a JSON config. Paths inside the config are relative to the config's directory;
CLI paths are relative to the current working directory. A map uses exactly one of
`file` or `entry`. `source` is a display label, not an automatic classification.

```json
{
  "maps": [
    {
      "name": "Fords of Isen II",
      "source": "original",
      "entry": "maps/map mp fords of isen ii/map mp fords of isen ii.map"
    },
    {
      "name": "Greywater Marches",
      "source": "ours",
      "file": "../../local/build/greywater-marches/map mp bfmexbar greywater marches.map"
    }
  ],
  "patch_maps": ["Fords of Isen II", "Greywater Marches"]
}
```

The file path in this example assumes the config is in `maps/`. Save it there
(for example as `maps/graphics-comparison.json`) and supply the game's map
archive with `--archive`:

```powershell
mw graphics `
  --config maps/graphics-comparison.json `
  --archive 'C:\path\to\BFME2\Maps.big' `
  --out local/renders/map-graphics/green-comparison
```

An `archive` path may also be specified at the config root or per map. CLI
`--archive` overrides the root default; an explicit per-map archive still wins.
An entry may use its full archive path or an unambiguous short name such as
`map wor ithilien`. Missing or ambiguous entries fail rather than selecting a
different map. Retail binaries stay in the local archive; only derived graphics
and measurements are written.

## Terrain plan overlays

Stored starts, roads and scenery are read automatically. Proposed regions and
routes need explicit design data; the tool does not invent connections from
straight lines between bases. Pass `--plan plan.json` for a single-map run, or
set `plan` inside a config map entry to an inline object or a JSON path.

```json
{
  "regions": [
    {
      "name": "Proposed woodland",
      "color": "#78ae61",
      "points": [[2800, 4200], [3600, 4200], [3500, 4900], [2850, 4800]]
    }
  ],
  "routes": [
    {
      "name": "Army corridor",
      "color": "#80cbd7",
      "width": 360,
      "points": [[1700, 3200], [2300, 3500], [3000, 3600]]
    }
  ],
  "markers": [
    {"name": "Proposed crossing", "position": [3000, 3600], "color": "#ffbc67"}
  ]
}
```

All coordinates and route widths use native world units. World XY starts at the
lower-left playable corner; the file's heightmap border is excluded. One terrain
sample is 10 world units. The tool flips the terrain raster for image display and
uses the same coordinate conversion for every overlay. Contours use elevation
units, not horizontal world distance. Routes describe design intent and are not
proof of unit navigation or bridge traversal.

## Options and interpretation

- `--ini PATH`: effective object-definition directory. Defaults to
  `local/game/data/ini/object`, extracted by `mw setup`. Classification
  follows `ObjectReskin`/`ChildObject` inheritance and `KindOf`; unknown templates
  remain `gameplay/other`. Use the INIs for the mod being inspected.
- `--columns 1..6`: number of atlas and forest-panel columns; default 3.
- `--patch-size 1000`: square world extent of each forest sample. Its center is
  the tree with the most neighbors within one quarter of that extent. The first
  object breaks ties. This is a dense-area example, not average map coverage.
- `--crown-radius 16`: illustrative tree-dot radius, shared by all panels. It is
  **not** the measured canopy or collision radius of the native model.
- `--contour-step 25`: elevation interval; use 0 to disable contours.
- `--overwrite`: explicitly regenerate into an existing output directory.

Nearest-neighbor distances use actual object positions in bounded-memory NumPy
blocks. Spacing is unavailable for zero or one tree; fifth-neighbor distance is
unavailable below six trees. Duplicate tree positions count as zero spacing.
Dead trees, logs and stumps are counted separately from living trees. Ground cover
includes grass, shrubs and ferns, including decoration outside forests. Area
density uses the full playable rectangle, including water and blocked terrain.

These are **diagnostic plans, not native screenshots**. Material colors are
approximate categories derived from texture names; native texture art, blends,
model silhouettes, lighting, wave effects and LOD are not rendered. Unsupported
palette cells appear magenta and are counted in the report. Stored passability
does not include dynamic objects, formation footprints or bridge deck behavior.
Heightmap PNGs normalize each map independently; `height_range` in `metrics.json`
records the original range. Map-level scale values do not include every native
template's built-in scale fuzziness. Use native tests for rendering, traversal
and performance conclusions.
