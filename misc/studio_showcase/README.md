# Map Studio showcase: Brightwater Fold

A two-minute video of one new map made from start to finish:
[Brightwater Fold](../../maps/brightwater_fold/README.md), from `mw new` to
its last details, in seven steps.

| Step | What happened |
|---|---|
| 1 New | `mw new "Brightwater Fold" --size 480x480`: a flat field |
| 2 Shape | heights and water: downs, the river and its island knoll, escarpments |
| 3 Paint | Rohan textures and roads, chosen from a sheet of the game's textures |
| 4 Populate | the hold, fords, bridges, copses, rocks and reeds; fairness and walkability checked |
| 5 Creek | a freehand mark in the viewer, turned into a creek with a footbridge |
| 6 Paddock | a circle mark, turned into a paddock, then reshaped after "too perfectly circular" |
| 7 Polish | pins on the gateways: torches, a trodden plaza and late-afternoon light |

Everything in the video happened. Each step was kept as a snapshot in the
ignored `local/videos/studio-showcase/steps/` (that step's `map.py`, `map.toml`,
build, marks and command output), and the images Claude looked at while
making the map are in `looks/` next to it. `facts.py` collects the map
changes between the steps (as `mw diff` prints them) and the lines of
`map.py` each step added.

```powershell
python -m misc.studio_showcase.facts                    # facts.json from the step snapshots
python -m misc.studio_showcase.showcase --stills 27,52  # check single frames
python -m misc.studio_showcase.showcase                 # the video, with its score and exports
```

`showcase.py` draws every frame with the workshop's renderer from the step
builds, with the viewer's own toolbar and mark overlay. The changes between
steps animate the renderer's own data: heights rise from the flat field, the
river fills, textures spread from the water, objects grow at their places,
and new light sweeps across. `score.py` is the original music.
