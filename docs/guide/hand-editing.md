# Hand-editing a single map file

Map projects are built from code. For hand edits of an existing `.map` (a
stock map, or a build to refine in WorldBuilder), `mw workspace` keeps an
isolated copy with checkpoints ([mapkit/workspace.py](../../src/mapworkshop/mapkit/workspace.py);
`mw workspace --help` lists the steps):

1. `inspect` measures a map and validates its terrain and texture references.
2. `catalog` returns the exact texture and object names already in it.
3. `checkout` makes an editable copy in `local/workspaces/<name>/`, with its
   sidecar files.
4. Save and close the map in WorldBuilder before file edits; an unsaved document
   could later overwrite them. `status` gives the saved file's SHA-256.
5. `apply` takes a seeded JSON recipe and that SHA-256. It validates the whole
   result before replacing the working file and keeps the before and after maps,
   the recipe, a chunk diff and a checkpoint. Applying a recipe twice is refused.
6. `preview` draws a quick heights, texture categories and objects diagnostic.
7. Open the working map in WorldBuilder, refine, save, then `checkpoint`.
8. `diff` shows exactly what the editor changed: the changed sections, and
   (`changes`) the same readable lines as `mw diff`.

```powershell
$map = 'local/game/maps/map wor ithilien/map wor ithilien.map'
mw workspace inspect $map
mw workspace catalog $map
mw workspace checkout $map ithilien-lab
mw workspace status ithilien-lab
mw workspace apply ithilien-lab maps/ithilien_frontier/authoring-demo.json --expect-sha <file_sha256>
mw workspace handoff ithilien-lab
mw workspace checkpoint ithilien-lab --note 'Saved and visually checked in WorldBuilder'
mw workspace diff <checkpoint.map> <working.map>
```

Checkpoint notes are descriptions, not proof that an editor or game check
happened; `status` leaves those gates unverified. There is no destructive
restore; branch a checkpoint with `checkout`. Use one map writer at a time:
reload the map in the editor before its next pass, since an unsaved editor
copy can overwrite newer edits.

## Recipe operations

Positions, radii and spacing are map units; angles are degrees; heights are
map units.

- `raise`: `x`, `y`, `radius`, `amount`; a smooth radial falloff, up or down.
- `flatten`: `x`, `y`, `radius`, `height`, optional `strength` (0..1).
- `paint`: `x`, `y`, `radius`, `texture` from the map's catalog. A hard-edged
  bulk base coat that clears existing blends; edges need WorldBuilder's blend
  brush.
- `scatter`: `template`, `count`, `rect: [x0,y0,x1,y1]`, `spacing`, `max_slope`.
  Uses existing unnamed scenery as a prototype and checks bounds, painted
  impassability, slope, exclusions and spacing.
- `place`: one existing unnamed landmark template at `x`, `y`, optional
  `angle_degrees`, `spacing`, `max_slope`, with a fresh `uniqueID`.

Recipes have `schema: 1`, a unique lowercase `id`, `seed`, `operations` and
optional `exclude_rects` that protect bases, lanes and crossings. Too few valid
positions abort the whole transaction. Water, scripts, teams, cameras and
starts survive unchanged. [authoring-demo.json](../../maps/ithilien_frontier/authoring-demo.json)
is an example.

`mw workspace plan-size MAP --area-factor 3` proposes playable dimensions for a
map of a given area at the same proportions (a proposal, not a supported-size
claim).
