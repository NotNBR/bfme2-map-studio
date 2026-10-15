# Native map screenshots

> **History.** Recorded with
> [bfme-workshop](https://github.com/NotNBR/bfme-workshop), the repository this
> one grew out of, in October 2026. Its commands and paths (`scripts/workshop.py`,
> `python -m mapkit.*`, `src/host/`, `local/artifacts/`, `local/runtime/bfme-host/`)
> are that repository's and do not exist here. What it established is in
> [how BFME2 behaves](../game/README.md).

Capture map views through the game's D3D9 render target, including the HUD.
The command starts a separate test skirmish, reveals terrain, moves the camera
through the requested views and closes its test process afterward. It refuses
to start while another game is running. It does not attach to an existing match.

Prepare the licensed game runtime and build the strategic extension first:

```powershell
python scripts/workshop.py mod build
python scripts/workshop.py screenshots `
  --map 'maps\map mp bfmexbar eight kingdoms.map' `
  --shot overview 5700 6000 17000 `
  --shot citadel 5700 6000 1800 `
  --out local/artifacts/screenshots/eight-kingdoms-001
```

Each `--shot` takes **name, world X, world Y, camera height**. Names must be
unique lowercase filenames using letters, digits and hyphens. Supply 1–8 shots;
focus positions must be inside the playable map. The map must be installed in
the prepared mod, including its map-cache entry. A flattened name resolves to
the matching `maps\name\name.map` file when present for hashing; the original
map identifier is passed to the game. Use the flattened identifier shown above
for the workshop maps.

Alternatively, pass `--tour path/to/tour.json` with a `shots` array:

```json
{"shots": [["overview", 960, 960, 3400], ["cliffs", 960, 1610, 1700]]}
```

The output directory must be new or empty. It contains:

- Named PNG files: original rendered pixels, without rescaling.
- `capture.json`: map SHA-256, requested views, graphics preset, completion
  status, image hashes/dimensions, logic frames and observed camera state.
- `tour.json`: the effective camera configuration.
- `native-validation.json` and `engine-report.json`: validation and raw game evidence.

The native check rejects missing/blank views, extension faults and changes to the
original profile. The command also checks that the source map stayed unchanged.
A successful capture proves loading and render readback, not visual correctness,
WorldBuilder compatibility, pathfinding or multiplayer balance. Inspect the PNGs.
The simulation advances between views, so this is not a synchronized snapshot.
Very flat scenes may fail the conservative image-variation check; inspect the
image instead of interpreting that result as an engine failure.

## Terrain experiment

```powershell
python -m mapkit.terrain_lab --install
python scripts/workshop.py screenshots `
  --map 'maps\map mp bfmexbar terrain lab.map' `
  --tour local/artifacts/terrain-lab/tour.json `
  --out local/artifacts/terrain-lab/capture-001
```

This builds a small map with 16 isolated panels: four cardinal blends, six
diagonal variations, two three-way combinations, and four identical ridges with
default/experimental UV mappings. The generator, panel coordinates and source
hash are retained; it never rewrites Eight Kingdoms. The cliff scales are test
candidates, not recommended production values. Installation also generates radar
and loading TGAs and registers the test map in the isolated map cache.
See [terrain research](../game/terrain-textures.md).
